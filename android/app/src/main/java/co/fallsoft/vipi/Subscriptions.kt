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

internal data class CardlessTrial(val startedAt: Instant, val endsAt: Instant, val active: Boolean)

internal data class PlanAccess(val active: Boolean, val expiresAt: Instant?, val trialEndsAt: Instant?, val reviewAccess: Boolean = false,
    val accessSource: String? = null, val cardlessTrial: CardlessTrial? = null, val verificationUnavailable: Boolean = false) {
    fun usable(now: Instant = Instant.now()) = active &&
        (expiresAt?.isAfter(now) == true || (reviewAccess && expiresAt == null && trialEndsAt == null))
    companion object {
        fun parse(value: JSONObject): PlanAccess {
            fun date(key: String) = if (value.isNull(key)) null else Instant.parse(value.getString(key))
            val expires = date("expires_at")
            val trial = date("trial_ends_at")
            require(trial == null || (expires != null && !trial.isAfter(expires)))
            val review = value.opt("review_access") == true && value.opt("access_source") == "review_complimentary"
            require(!review || (expires == null && trial == null))
            val cardless = value.optJSONObject("cardless_trial")?.let {
                CardlessTrial(Instant.parse(it.getString("started_at")), Instant.parse(it.getString("ends_at")), it.getBoolean("active"))
                    .also { period -> require(period.endsAt.isAfter(period.startedAt)) }
            }
            val source = value.optString("access_source").takeUnless { it.isBlank() || it == "null" }
            if (source == "cardless_trial") {
                require(cardless != null && cardless.active && expires == cardless.endsAt && trial == cardless.endsAt)
            }
            val verificationUnavailable = when (val raw = value.opt("verification_unavailable")) {
                null, JSONObject.NULL -> false
                is Boolean -> raw
                else -> throw IllegalArgumentException("Invalid verification state")
            }
            return PlanAccess(value.getBoolean("active"), expires, trial, review, source, cardless, verificationUnavailable)
        }
    }
}

internal data class SubscriptionAccess(val base: PlanAccess, val bot: PlanAccess, val botAvailable: Boolean, val billingAccountID: String, val purchasesReady: Boolean,
    val serverTime: Instant? = null, val receivedAtElapsedMillis: Long = 0) {
    fun serverNow(): Instant = serverTime?.plusMillis((android.os.SystemClock.elapsedRealtime() - receivedAtElapsedMillis).coerceAtLeast(0)) ?: Instant.now()
    companion object {
        fun parse(value: JSONObject): SubscriptionAccess {
            val account = value.getString("billing_account_id")
            require(account.matches(Regex("[a-f0-9]{64}")))
            return SubscriptionAccess(PlanAccess.parse(value.getJSONObject("base")), PlanAccess.parse(value.getJSONObject("bot_mini")),
                value.getJSONObject("bot_mini").getBoolean("available"), account, value.optJSONObject("purchases_ready")?.optBoolean("google", false) == true,
                value.optString("server_time").takeUnless { it.isBlank() || it == "null" }?.let(Instant::parse), android.os.SystemClock.elapsedRealtime())
        }
    }
    fun active(plan: SubscriptionPlan) = serverTime != null && when (plan) {
        SubscriptionPlan.BASE -> base.usable(serverNow())
        SubscriptionPlan.BOT_MINI -> base.usable(serverNow()) && bot.usable(serverNow()) && botAvailable
    }
}

internal enum class AccessCheckState { UNKNOWN, CHECKING, ERROR, LOADED }

internal data class SubscriptionOffer(val details: ProductDetails, val token: String, val annualPrice: String,
    val annualMicros: Long, val currency: String, val oneMonthTrial: Boolean)

/** Google Play offers are display/checkout information. Only our account-bound server grants access.
 * No purchase token, store response, or entitlement is written to an unencrypted log or preferences. */
internal class Subscriptions(context: Context, private val api: ChatTransport, private val scope: CoroutineScope) : AutoCloseable {
    var access by mutableStateOf<SubscriptionAccess?>(null); private set
    var accessCheckState by mutableStateOf(AccessCheckState.UNKNOWN); private set
    private var accessRefresh: Deferred<Boolean>? = null
    var offers by mutableStateOf<Map<SubscriptionPlan, SubscriptionOffer>>(emptyMap()); private set
    var busy by mutableStateOf(false); private set
    var purchasing by mutableStateOf(false); private set
    var notice by mutableStateOf<String?>(null); private set
    private var closed = false
    private var quotesAt = 0L
    private val refreshLock = Mutex()
    private val connectionLock = Mutex()
    private val appContext = context.applicationContext
    private val client = BillingClient.newBuilder(appContext)
        .setListener { result, purchases -> scope.launch {
            if (closed) return@launch
            purchasing = false
            when (result.responseCode) {
                BillingClient.BillingResponseCode.OK -> {
                    notice = null
                    runCatching { verify(purchases.orEmpty()) }.onFailure { failure ->
                        if (failure is CancellationException) throw failure
                        notice = appContext.getString(R.string.ui_3ec68bc63f9a)
                    }
                }
                BillingClient.BillingResponseCode.USER_CANCELED -> notice = appContext.getString(R.string.ui_e9fa6f9474f3)
                BillingClient.BillingResponseCode.ITEM_ALREADY_OWNED -> refresh()
                else -> notice = appContext.getString(R.string.ui_d1fc884eb413)
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

    /** Account grants load independently of Play offers; concurrent callers share one GET. */
    suspend fun refreshAccess(ifNeeded: Boolean = false): Boolean {
        if (closed) return false
        accessRefresh?.let { return it.await() }
        if (ifNeeded && accessCheckState == AccessCheckState.LOADED) return true
        val job = scope.async(start = CoroutineStart.LAZY) {
            accessCheckState = AccessCheckState.CHECKING
            try {
                val snapshot = SubscriptionAccess.parse(api.request("GET", "/v1/entitlements"))
                if (closed) return@async false
                access = snapshot; accessCheckState = AccessCheckState.LOADED
                true
            } catch (failure: CancellationException) {
                if (!closed) accessCheckState = AccessCheckState.UNKNOWN
                throw failure
            } catch (_: Exception) {
                if (!closed) accessCheckState = AccessCheckState.ERROR
                false
            }
        }
        accessRefresh = job
        job.invokeOnCompletion { if (accessRefresh === job) accessRefresh = null }
        return job.await()
    }

    suspend fun refresh() {
        if (closed || refreshLock.isLocked) return
        refreshLock.withLock {
            busy = true; notice = null; offers = emptyMap()
            try {
                if (!refreshAccess()) {
                    if (!closed) notice = appContext.getString(R.string.ui_1f90b03e1d77)
                    return@withLock
                }
                if (closed) return@withLock
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
                    // Base has a server-provided cardless month, so never stack a
                    // store trial on top. Bot mini keeps its separate offer.
                    val selected = if (plan == SubscriptionPlan.BASE) eligible.firstOrNull { !it.oneMonthTrial }
                        else eligible.sortedByDescending { it.oneMonthTrial }.firstOrNull()
                    selected?.let { plan to it }
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
                if (offers.isEmpty() && !closed) notice = appContext.getString(R.string.ui_8927db75ddd0)
            } catch (_: TimeoutCancellationException) { if (!closed) notice = appContext.getString(R.string.ui_b4009c7a9f52) }
            catch (failure: CancellationException) { throw failure }
            catch (_: Exception) { if (!closed) notice = appContext.getString(R.string.ui_bbd30d6992ff) }
            finally { if (!closed) busy = false }
        }
    }

    private suspend fun verify(purchases: List<Purchase>) {
        for (purchase in purchases) {
            if (closed) return
            if (purchase.products.none { id -> SubscriptionPlan.entries.any { it.productID == id } }) continue
            if (purchase.purchaseState == Purchase.PurchaseState.PENDING) {
                notice = appContext.getString(R.string.ui_1652f9585f6d)
                continue
            }
            if (purchase.purchaseState != Purchase.PurchaseState.PURCHASED) continue
            // Server verifies ownership, lifecycle and product, then acknowledges the verified purchase.
            val verified = SubscriptionAccess.parse(api.request("POST", "/v1/purchases/google", JSONObject().put("purchase_token", purchase.purchaseToken)))
            if (!closed) { access = verified; accessCheckState = AccessCheckState.LOADED }
        }
    }

    fun buy(activity: Activity, plan: SubscriptionPlan) {
        if (closed || busy || purchasing) return
        val snapshot = access ?: return
        if (snapshot.serverTime == null) { notice = appContext.getString(R.string.plan_clock_unavailable); return }
        if (!snapshot.purchasesReady) { notice = appContext.getString(R.string.ui_f87b0e3bf7e6); return }
        if (plan == SubscriptionPlan.BOT_MINI && snapshot.bot.verificationUnavailable) { notice = appContext.getString(R.string.bot_verification_unavailable); return }
        if (plan == SubscriptionPlan.BOT_MINI && !snapshot.base.usable(snapshot.serverNow())) { notice = appContext.getString(R.string.ui_45787d668c50); return }
        if (if (plan == SubscriptionPlan.BASE) snapshot.base.usable(snapshot.serverNow()) else snapshot.bot.usable(snapshot.serverNow())) return
        val offer = offers[plan] ?: return
        if (android.os.SystemClock.elapsedRealtime() - quotesAt > 300_000) { notice = appContext.getString(R.string.ui_c3169261c50e); return }
        val parameters = BillingFlowParams.newBuilder().setObfuscatedAccountId(snapshot.billingAccountID)
            .setProductDetailsParamsList(listOf(BillingFlowParams.ProductDetailsParams.newBuilder()
                .setProductDetails(offer.details).setOfferToken(offer.token).build())).build()
        purchasing = true; notice = null
        val result = client.launchBillingFlow(activity, parameters)
        if (result.responseCode != BillingClient.BillingResponseCode.OK) { purchasing = false; notice = appContext.getString(R.string.ui_c753f85749ce) }
    }

    override fun close() { closed = true; accessRefresh?.cancel(); accessRefresh = null; client.endConnection(); access = null; accessCheckState = AccessCheckState.UNKNOWN; offers = emptyMap() }
}
