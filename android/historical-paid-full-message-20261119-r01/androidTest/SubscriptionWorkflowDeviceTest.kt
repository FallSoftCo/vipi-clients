package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.IOException
import java.time.Instant

/** Real subscription coordinator and Play SDK objects; only store/HTTP boundaries are local. */
class SubscriptionWorkflowDeviceTest {
    @Test fun olderEntitlementReadCannotRevokeVerifiedPurchase(): Unit = runBlocking(Dispatchers.Main) {
        staleEntitlementCannotRevokePurchase(failOlderRead = false)
    }

    @Test fun olderEntitlementFailureCannotEraseVerifiedPurchase(): Unit = runBlocking(Dispatchers.Main) {
        staleEntitlementCannotRevokePurchase(failOlderRead = true)
    }

    private suspend fun staleEntitlementCannotRevokePurchase(failOlderRead: Boolean) = coroutineScope {
        val oldRead = CompletableDeferred<JSONObject>()
        val verified = CompletableDeferred<Unit>()
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        var posts = 0
        val api = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject = when (path) {
                "/v1/entitlements" -> { assertEquals("GET", method); oldRead.await() }
                "/v1/purchases/google" -> {
                    assertEquals("POST", method); assertEquals("rightful", body!!.getString("purchase_token")); posts++
                    workflowAccess(bot = true).also { verified.complete(Unit) }
                }
                else -> error("Unexpected endpoint: $path")
            }
        }
        lateinit var sdk: WorkflowBillingClient
        val plans = Subscriptions(InstrumentationRegistry.getInstrumentation().targetContext, api, scope) { _, listener ->
            WorkflowBillingClient(listener).also { sdk = it }
        }
        try {
            val read = async(start = CoroutineStart.UNDISPATCHED) { plans.refreshAccess() }
            assertEquals(AccessCheckState.CHECKING, plans.accessCheckState)
            sdk.completePurchase(listOf(WorkflowBillingClient.purchase("rightful")))
            verified.await(); yield()
            assertTrue(plans.access!!.active(SubscriptionPlan.BOT_MINI))
            if (failOlderRead) oldRead.completeExceptionally(IOException("Controlled stale read failure"))
            else oldRead.complete(workflowAccess(bot = false))
            assertTrue(read.await())
            assertEquals(AccessCheckState.LOADED, plans.accessCheckState)
            assertTrue(plans.access!!.active(SubscriptionPlan.BOT_MINI)); assertEquals(1, posts)
            assertNull(plans.notice)
        } finally { plans.close(); scope.cancel() }
    }

    @Test fun foreignPurchaseDoesNotBlockRightfulRestoreAndMismatchStaysVisible(): Unit = runBlocking(Dispatchers.Main) {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        val verifiedTokens = mutableListOf<String>()
        val api = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject = when (path) {
                "/v1/entitlements" -> workflowAccess(bot = false)
                "/v1/purchases/google" -> {
                    assertEquals("POST", method)
                    val token = body!!.getString("purchase_token"); verifiedTokens += token
                    if (token == "foreign") throw ServiceFailure(409, "purchase_account_mismatch")
                    assertEquals("rightful", token); workflowAccess(bot = true)
                }
                else -> error("Unexpected endpoint: $path")
            }
        }
        lateinit var sdk: WorkflowBillingClient
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val plans = Subscriptions(context, api, scope) { _, listener -> WorkflowBillingClient(listener).also { sdk = it } }
        try {
            sdk.purchases = listOf(WorkflowBillingClient.purchase("foreign"), WorkflowBillingClient.purchase("rightful"))
            plans.refresh()
            assertEquals(listOf("foreign", "rightful"), verifiedTokens)
            assertTrue(plans.access!!.active(SubscriptionPlan.BOT_MINI))
            assertEquals(context.getString(R.string.purchase_account_mismatch), plans.notice)
            assertFalse(sdk.purchases.any { it.isAcknowledged }) // SDK acknowledgement is forbidden by boundary.
            assertEquals(0, sdk.launches); assertEquals(1, sdk.purchaseQueries)
            assertFalse(plans.busy)
            assertFalse(plans.offers.getValue(SubscriptionPlan.BASE).oneMonthTrial)
            assertTrue(plans.offers.getValue(SubscriptionPlan.BOT_MINI).oneMonthTrial)
        } finally { plans.close(); scope.cancel() }
    }

    @Test fun closeDuringVerificationCannotRestoreClosedAccountAccess(): Unit = runBlocking(Dispatchers.Main) {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        val started = CompletableDeferred<Unit>(); val response = CompletableDeferred<JSONObject>()
        val api = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject {
                assertEquals("/v1/purchases/google", path); started.complete(Unit); return response.await()
            }
        }
        lateinit var sdk: WorkflowBillingClient
        val plans = Subscriptions(InstrumentationRegistry.getInstrumentation().targetContext, api, scope) { _, listener -> WorkflowBillingClient(listener).also { sdk = it } }
        try {
            sdk.completePurchase(listOf(WorkflowBillingClient.purchase("rightful"))); started.await()
            plans.close(); response.complete(workflowAccess(bot = true)); yield()
            assertNull(plans.access); assertEquals(AccessCheckState.UNKNOWN, plans.accessCheckState)
        } finally { plans.close(); scope.cancel() }
    }
}

internal fun workflowAccess(bot: Boolean, trial: Boolean = false): JSONObject {
    val now = Instant.parse("2026-11-17T00:00:00Z")
    val end = now.plusSeconds(30L * 24 * 60 * 60)
    fun plan(active: Boolean) = JSONObject().put("active", active).put("expires_at", if (active) end.toString() else JSONObject.NULL)
        .put("trial_ends_at", JSONObject.NULL)
    val base = plan(true)
    if (trial) base.put("trial_ends_at", end.toString()).put("access_source", "cardless_trial")
        .put("cardless_trial", JSONObject().put("started_at", now.toString()).put("ends_at", end.toString()).put("active", true))
    return JSONObject().put("base", base).put("bot_mini", plan(bot).put("available", true))
        .put("billing_account_id", "b".repeat(64)).put("purchases_ready", JSONObject().put("google", true)).put("server_time", now.toString())
}
