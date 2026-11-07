package co.fallsoft.vipi

import android.app.Activity
import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.android.billingclient.api.*
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONObject
import java.time.Instant
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

internal enum class SubscriptionPlan(val productID: String, val title: String) {
    BASE("vipi_base", "Vipi"), BOT_MINI("vipi_bot_mini", "Bot mini")
}

internal data class PlanAccess(val active: Boolean, val expiresAt: Instant?, val trialEndsAt: Instant?) {
    fun usable(now: Instant = Instant.now()) = active && expiresAt?.isAfter(now) == true
    companion object {
        fun parse(value: JSONObject): PlanAccess {
            fun date(key: String) = if (value.isNull(key)) null else Instant.parse(value.getString(key))
            val expires = date("expires_at")
            val trial = date("trial_ends_at")
            require(trial == null || (expires != null && !trial.isAfter(expires)))
            return PlanAccess(value.getBoolean("active"), expires, trial)
        }
    }
}

internal data class SubscriptionAccess(val base: PlanAccess, val bot: PlanAccess, val botAvailable: Boolean, val billingAccountID: String, val purchasesReady: Boolean) {
    companion object {
        fun parse(value: JSONObject): SubscriptionAccess {
            val account = value.getString("billing_account_id")
            require(account.matches(Regex("[a-f0-9]{64}")))
            return SubscriptionAccess(PlanAccess.parse(value.getJSONObject("base")), PlanAccess.parse(value.getJSONObject("bot_mini")),
                value.getJSONObject("bot_mini").getBoolean("available"), account, value.optJSONObject("purchases_ready")?.optBoolean("google", false) == true)
        }
    }
    fun active(plan: SubscriptionPlan) = when (plan) {
        SubscriptionPlan.BASE -> base.usable()
        SubscriptionPlan.BOT_MINI -> base.usable() && bot.usable() && botAvailable
    }
}

internal data class SubscriptionOffer(val details: ProductDetails, val token: String, val annualPrice: String,
    val annualMicros: Long, val currency: String, val oneMonthTrial: Boolean)

/** Google Play offers are display/checkout information. Only our account-bound server grants access.
 * No purchase token, store response, or entitlement is written to an unencrypted log or preferences. */
internal class Subscriptions(context: Context, private val api: ChatTransport, private val scope: CoroutineScope) : AutoCloseable {
    var access by mutableStateOf<SubscriptionAccess?>(null); private set
    var offers by mutableStateOf<Map<SubscriptionPlan, SubscriptionOffer>>(emptyMap()); private set
    var busy by mutableStateOf(false); private set
    var purchasing by mutableStateOf(false); private set
    var notice by mutableStateOf<String?>(null); private set
    private var closed = false
    private var quotesAt = 0L
    private val refreshLock = Mutex()
    private val connectionLock = Mutex()
    private val client = BillingClient.newBuilder(context.applicationContext)
        .setListener { result, purchases -> scope.launch {
            if (closed) return@launch
            purchasing = false
            when (result.responseCode) {
                BillingClient.BillingResponseCode.OK -> {
                    notice = null
                    runCatching { verify(purchases.orEmpty()) }.onFailure { failure ->
                        if (failure is CancellationException) throw failure
                        notice = "Your purchase is awaiting verification. Restore purchases to try again; don’t buy it again."
                    }
                }
                BillingClient.BillingResponseCode.USER_CANCELED -> notice = "Purchase canceled. Your plans haven’t changed."
                BillingClient.BillingResponseCode.ITEM_ALREADY_OWNED -> refresh()
                else -> notice = "Google Play couldn’t complete the purchase. Please try again."
            }
        } }
        .enablePendingPurchases(PendingPurchasesParams.newBuilder().enableOneTimeProducts().build())
        .enableAutoServiceReconnection().build()

    private suspend fun connect() = connectionLock.withLock {
        check(!closed)
        if (!client.isReady) withTimeout(20_000) { suspendCancellableCoroutine<Unit> { pending ->
            client.startConnection(object : BillingClientStateListener {
                override fun onBillingSetupFinished(result: BillingResult) {
                    if (!pending.isActive) return
                    if (result.responseCode == BillingClient.BillingResponseCode.OK) pending.resume(Unit)
                    else pending.resumeWithException(java.io.IOException("Store unavailable"))
                }
                override fun onBillingServiceDisconnected() = Unit
            })
        } }
    }

    suspend fun refresh() {
        if (closed || refreshLock.isLocked) return
        refreshLock.withLock {
            busy = true; notice = null; offers = emptyMap()
            try {
                val snapshot = SubscriptionAccess.parse(api.request("GET", "/v1/entitlements"))
                if (closed) return@withLock
                access = snapshot
                connect()
                val products = withTimeout(20_000) { suspendCancellableCoroutine<List<ProductDetails>> { pending ->
                    val query = QueryProductDetailsParams.newBuilder().setProductList(SubscriptionPlan.entries.map {
                        QueryProductDetailsParams.Product.newBuilder().setProductId(it.productID).setProductType(BillingClient.ProductType.SUBS).build()
                    }).build()
                    client.queryProductDetailsAsync(query) { result, details ->
                        if (pending.isActive) {
                            if (result.responseCode == BillingClient.BillingResponseCode.OK) pending.resume(details.productDetailsList)
                            else pending.resumeWithException(java.io.IOException("Store products unavailable"))
                        }
                    }
                } }
                if (closed) return@withLock
                offers = SubscriptionPlan.entries.mapNotNull { plan -> products.singleOrNull { it.productId == plan.productID }?.let { product ->
                    val eligible = product.subscriptionOfferDetails.orEmpty().filter { it.basePlanId == "annual" }.mapNotNull { offer ->
                        val phases = offer.pricingPhases.pricingPhaseList
                        val annual = phases.lastOrNull() ?: return@mapNotNull null
                        if (annual.billingPeriod != "P1Y" || annual.priceAmountMicros <= 0 || annual.recurrenceMode != ProductDetails.RecurrenceMode.INFINITE_RECURRING) return@mapNotNull null
                        val trial = phases.size == 2 && phases.first().priceAmountMicros == 0L && phases.first().billingPeriod == "P1M" && phases.first().billingCycleCount == 1
                        if (!trial && phases.size != 1) return@mapNotNull null
                        SubscriptionOffer(product, offer.offerToken, annual.formattedPrice, annual.priceAmountMicros, annual.priceCurrencyCode, trial)
                    }
                    eligible.sortedByDescending { it.oneMonthTrial }.firstOrNull()?.let { plan to it }
                } }.toMap()
                quotesAt = android.os.SystemClock.elapsedRealtime()
                val purchases = withTimeout(20_000) { suspendCancellableCoroutine<List<Purchase>> { pending ->
                    client.queryPurchasesAsync(QueryPurchasesParams.newBuilder().setProductType(BillingClient.ProductType.SUBS)
                        .includeSuspendedSubscriptions(true).build()) { result, purchases ->
                        if (pending.isActive) {
                            if (result.responseCode == BillingClient.BillingResponseCode.OK) pending.resume(purchases)
                            else pending.resumeWithException(java.io.IOException("Purchases unavailable"))
                        }
                    }
                } }
                verify(purchases)
                if (offers.isEmpty() && !closed) notice = "Plans aren’t available from Google Play yet. Please try again later."
            } catch (_: TimeoutCancellationException) { if (!closed) notice = "Google Play took too long to respond. Please try again." }
            catch (failure: CancellationException) { throw failure }
            catch (_: Exception) { if (!closed) notice = "We couldn’t refresh your plans. Check your connection and try again." }
            finally { if (!closed) busy = false }
        }
    }

    private suspend fun verify(purchases: List<Purchase>) {
        for (purchase in purchases) {
            if (closed) return
            if (purchase.products.none { id -> SubscriptionPlan.entries.any { it.productID == id } }) continue
            if (purchase.purchaseState == Purchase.PurchaseState.PENDING) {
                notice = "Your payment is pending in Google Play. Access starts after payment is confirmed."
                continue
            }
            if (purchase.purchaseState != Purchase.PurchaseState.PURCHASED) continue
            // Server verifies ownership, lifecycle and product, then acknowledges the verified purchase.
            val verified = SubscriptionAccess.parse(api.request("POST", "/v1/purchases/google", JSONObject().put("purchase_token", purchase.purchaseToken)))
            if (!closed) access = verified
        }
    }

    fun buy(activity: Activity, plan: SubscriptionPlan) {
        if (closed || busy || purchasing) return
        val snapshot = access ?: return
        if (!snapshot.purchasesReady) { notice = "Google Play purchases aren’t available yet. Please try again later."; return }
        if (plan == SubscriptionPlan.BOT_MINI && !snapshot.base.usable()) { notice = "Start or restore your Vipi plan before adding Bot mini."; return }
        if (if (plan == SubscriptionPlan.BASE) snapshot.base.usable() else snapshot.bot.usable()) return
        val offer = offers[plan] ?: return
        if (android.os.SystemClock.elapsedRealtime() - quotesAt > 300_000) { notice = "Refresh the current Google Play price before continuing."; return }
        val parameters = BillingFlowParams.newBuilder().setObfuscatedAccountId(snapshot.billingAccountID)
            .setProductDetailsParamsList(listOf(BillingFlowParams.ProductDetailsParams.newBuilder()
                .setProductDetails(offer.details).setOfferToken(offer.token).build())).build()
        purchasing = true; notice = null
        val result = client.launchBillingFlow(activity, parameters)
        if (result.responseCode != BillingClient.BillingResponseCode.OK) { purchasing = false; notice = "Google Play couldn’t open checkout. Refresh your plans and try again." }
    }

    override fun close() { closed = true; client.endConnection(); access = null; offers = emptyMap() }
}
