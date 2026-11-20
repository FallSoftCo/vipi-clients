package co.fallsoft.vipi

import androidx.compose.material3.Text
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

class BotAccessLoadingDeviceTest {
    @get:Rule val compose = createComposeRule()
    private fun payload(active: Boolean): JSONObject {
        fun plan() = JSONObject().put("active", active).put("expires_at", JSONObject.NULL)
            .put("trial_ends_at", JSONObject.NULL).put("review_access", true).put("access_source", "review_complimentary")
        return JSONObject().put("base", plan()).put("bot_mini", plan().put("available", active))
            .put("billing_account_id", "a".repeat(64)).put("server_time", java.time.Instant.now().toString())
    }
    private fun transition(active: Boolean) {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        val response = CompletableDeferred<JSONObject>(); var requests = 0
        val api = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String,String>): JSONObject {
                assertEquals("GET", method); assertEquals("/v1/entitlements", path); requests++
                return response.await()
            }
        }
        val plans = Subscriptions(InstrumentationRegistry.getInstrumentation().targetContext, api, scope)
        try {
            compose.setContent { BotPlanAccessGate(plans.accessCheckState, plans.access, {}, {}) { Text("COMPOSER") } }
            compose.onNodeWithText("Checking your plan…").assertExists()
            compose.onNodeWithText("View or restore Bot mini").assertDoesNotExist()
            var first: Job? = null; var second: Job? = null
            compose.runOnIdle { first = scope.launch { plans.refreshAccess(ifNeeded = true) }; second = scope.launch { plans.refreshAccess(ifNeeded = true) } }
            compose.runOnIdle { assertEquals(1, requests); assertEquals(AccessCheckState.CHECKING, plans.accessCheckState) }
            compose.onNodeWithText("Checking your plan…").assertExists()
            response.complete(payload(active))
            runBlocking { first!!.join(); second!!.join() }
            compose.waitForIdle()
            if (active) {
                compose.onNodeWithText("COMPOSER").assertExists()
                compose.onNodeWithText("View or restore Bot mini").assertDoesNotExist()
            } else {
                compose.onNodeWithText("View or restore Bot mini").assertExists()
                compose.onNodeWithText("COMPOSER").assertDoesNotExist()
            }
            compose.runOnIdle { assertEquals(1, requests); assertFalse(plans.busy); assertTrue(plans.offers.isEmpty()) }
        } finally { compose.runOnIdle { plans.close(); scope.cancel() } }
    }
    @Test fun unknownThenActiveComposesWithoutPlayOffersAndCoalescesChecks() = transition(true)
    @Test fun onlyConfirmedInactiveShowsPlanAction() = transition(false)
    @Test fun failedCheckShowsRetryAndSuccessfulRetryOpensComposer() {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        var requests = 0
        val api = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String,String>): JSONObject {
                assertEquals("GET", method); assertEquals("/v1/entitlements", path)
                requests++; if (requests == 1) throw java.io.IOException("Synthetic unavailable")
                return payload(true)
            }
        }
        val plans = Subscriptions(InstrumentationRegistry.getInstrumentation().targetContext, api, scope)
        try {
            compose.setContent { BotPlanAccessGate(plans.accessCheckState, plans.access,
                { scope.launch { plans.refreshAccess() } }, {}) { Text("COMPOSER") } }
            runBlocking { withContext(Dispatchers.Main) { plans.refreshAccess(ifNeeded = true) } }
            compose.onNodeWithText("Your plan access couldn’t be checked.").assertExists()
            compose.onNodeWithText("View or restore Bot mini").assertDoesNotExist()
            compose.onNodeWithText("COMPOSER").assertDoesNotExist()
            compose.onNodeWithText("Try again").performClick()
            compose.waitForIdle()
            compose.onNodeWithText("COMPOSER").assertExists()
            compose.runOnIdle { assertEquals(2, requests); assertEquals(AccessCheckState.LOADED, plans.accessCheckState) }
        } finally { compose.runOnIdle { plans.close(); scope.cancel() } }
    }
    @Test fun staleBotVerificationNeverOffersAnotherPurchase() {
        val response = payload(true)
        response.getJSONObject("bot_mini").put("active", false).put("verification_unavailable", true)
        val access = SubscriptionAccess.parse(response)
        compose.setContent { BotPlanAccessGate(AccessCheckState.LOADED, access, {}, {}) { Text("COMPOSER") } }
        compose.onNodeWithText("Bot mini access can’t be verified right now. Try again.").assertExists()
        compose.onNodeWithText("View or restore Bot mini").assertDoesNotExist()
        compose.onNodeWithText("COMPOSER").assertDoesNotExist()
        assertTrue(access.active(SubscriptionPlan.BASE))
    }

}
