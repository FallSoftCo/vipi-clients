package co.fallsoft.vipi

import android.app.Activity
import com.android.billingclient.api.*
import org.json.JSONArray
import org.json.JSONObject

/** Only the Play SDK boundary is controlled; Subscriptions still parses offers and verifies purchases. */
internal class WorkflowBillingClient(private val listener: PurchasesUpdatedListener) : BillingClient() {
    var purchases: List<Purchase> = emptyList()
    var catalog: List<ProductDetails> = defaultCatalog()
    var launches = 0; private set
    var productQueries = 0; private set
    var purchaseQueries = 0; private set
    private var connected = false
    var holdProductQueries = false
    private val heldProductQueries = mutableListOf<() -> Unit>()
    val heldProductQueryCount: Int get() = heldProductQueries.size
    fun releaseProductQueries() {
        holdProductQueries = false
        val pending = heldProductQueries.toList(); heldProductQueries.clear()
        pending.forEach { it() }
    }
    private val ok get() = BillingResult.newBuilder().setResponseCode(BillingResponseCode.OK).build()
    override fun isReady() = connected
    override fun getConnectionState() = if (connected) ConnectionState.CONNECTED else ConnectionState.DISCONNECTED
    override fun startConnection(listener: BillingClientStateListener) { connected = true; listener.onBillingSetupFinished(ok) }
    override fun endConnection() { connected = false; heldProductQueries.clear() }
    override fun queryProductDetailsAsync(params: QueryProductDetailsParams, listener: ProductDetailsResponseListener) {
        productQueries++
        val respond = { listener.onProductDetailsResponse(ok, QueryProductDetailsResult.create(catalog, emptyList())) }
        if (holdProductQueries) heldProductQueries += respond else respond()
    }
    override fun queryPurchasesAsync(params: QueryPurchasesParams, listener: PurchasesResponseListener) {
        purchaseQueries++; listener.onQueryPurchasesResponse(ok, purchases)
    }
    override fun launchBillingFlow(activity: Activity, params: BillingFlowParams): BillingResult { launches++; return ok }
    fun completePurchase(purchases: List<Purchase>) { listener.onPurchasesUpdated(ok, purchases) }
    override fun isFeatureSupported(feature: String): BillingResult = error("Unexpected SDK feature query")
    override fun acknowledgePurchase(params: AcknowledgePurchaseParams, listener: AcknowledgePurchaseResponseListener): Unit = error("Acknowledgement belongs to server verification")
    override fun consumeAsync(params: ConsumeParams, listener: ConsumeResponseListener): Unit = error("Subscriptions must not be consumed")
    override fun showAlternativeBillingOnlyInformationDialog(activity: Activity, listener: AlternativeBillingOnlyInformationDialogListener): BillingResult = error("Unexpected alternative billing")
    override fun showExternalOfferInformationDialog(activity: Activity, listener: ExternalOfferInformationDialogListener): BillingResult = error("Unexpected external offer")
    override fun showInAppMessages(activity: Activity, params: InAppMessageParams, listener: InAppMessageResponseListener): BillingResult = error("Unexpected in-app message")
    override fun createAlternativeBillingOnlyReportingDetailsAsync(listener: AlternativeBillingOnlyReportingDetailsListener): Unit = error("Unexpected alternative billing")
    override fun createBillingProgramReportingDetailsAsync(params: BillingProgramReportingDetailsParams, listener: BillingProgramReportingDetailsListener): Unit = error("Unexpected billing program")
    override fun createExternalOfferReportingDetailsAsync(listener: ExternalOfferReportingDetailsListener): Unit = error("Unexpected external offer")
    override fun getBillingChoiceInfoAsync(params: GetBillingChoiceInfoParams, listener: BillingChoiceInfoResponseListener): Unit = error("Unexpected billing choice")
    override fun getBillingConfigAsync(params: GetBillingConfigParams, listener: BillingConfigResponseListener): Unit = error("Unexpected billing config")
    override fun isAlternativeBillingOnlyAvailableAsync(listener: AlternativeBillingOnlyAvailabilityListener): Unit = error("Unexpected alternative billing")
    override fun isBillingProgramAvailableAsync(program: Int, listener: BillingProgramAvailabilityListener): Unit = error("Unexpected billing program")
    override fun isExternalOfferAvailableAsync(listener: ExternalOfferAvailabilityListener): Unit = error("Unexpected external offer")
    override fun launchExternalLink(activity: Activity, params: LaunchExternalLinkParams, listener: LaunchExternalLinkResponseListener): Unit = error("Unexpected external link")
    override fun showBillingProgramInformationDialog(activity: Activity, params: BillingProgramInformationDialogParams, listener: BillingProgramInformationDialogListener): Unit = error("Unexpected billing program")
    companion object {
        fun purchase(token: String, product: String = "vipi_bot_mini") = Purchase(JSONObject()
            .put("productIds", JSONArray().put(product)).put("purchaseToken", token).put("purchaseState", 0)
            .put("acknowledged", false).put("packageName", "co.fallsoft.vipi").toString(), "synthetic-sdk-boundary")
        private fun defaultCatalog(): List<ProductDetails> = listOf("vipi_base", "vipi_bot_mini").map { id ->
            fun phase(free: Boolean) = JSONObject().put("billingPeriod", if (free) "P1M" else "P1Y")
                .put("priceCurrencyCode", "USD").put("formattedPrice", if (free) "$0.00" else if (id == "vipi_base") "$12.00" else "$48.00")
                .put("priceAmountMicros", if (free) 0 else if (id == "vipi_base") 12_000_000 else 48_000_000)
                .put("recurrenceMode", if (free) 2 else 1).put("billingCycleCount", if (free) 1 else 0)
            fun offer(trial: Boolean) = JSONObject().put("basePlanId", "annual").put("offerIdToken", "$id-${if (trial) "trial" else "annual"}")
                .put("pricingPhases", JSONArray().apply { if (trial) put(phase(true)); put(phase(false)) }).put("offerTags", JSONArray())
            val json = JSONObject().put("productId", id).put("type", "subs").put("title", id).put("name", id).put("description", "Local SDK fixture")
                .put("subscriptionOfferDetails", JSONArray().put(offer(false)).apply { if (id == "vipi_bot_mini") put(offer(true)) })
            // Google exposes no public ProductDetails constructor; construct its real SDK value at this boundary.
            ProductDetails::class.java.getDeclaredConstructor(String::class.java).apply { isAccessible = true }.newInstance(json.toString())
        }
    }
}
