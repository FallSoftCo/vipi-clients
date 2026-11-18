package co.fallsoft.vipi

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.core.view.WindowInsetsCompat
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.time.Instant

/** The production footer and editable field, real touch/IME, fake entitlements.
 * No account, browser, model, billing, Bot provider or send endpoint is used. */
class BotComposerInputDeviceTest {
    @get:Rule val compose = createComposeRule()
    private fun access(active: Boolean = true): JSONObject {
        fun plan() = JSONObject().put("active", active).put("expires_at", JSONObject.NULL)
            .put("trial_ends_at", JSONObject.NULL).put("review_access", true).put("access_source", "review_complimentary")
        return JSONObject().put("base", plan()).put("bot_mini", plan().put("available", active))
            .put("billing_account_id", "a".repeat(64)).put("server_time", Instant.now().toString())
    }
    private fun imeVisible(): Boolean {
        var visible = false
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            visible = android.view.inspector.WindowInspector.getGlobalWindowViews().any { view ->
                view.rootWindowInsets?.let {
                    WindowInsetsCompat.toWindowInsetsCompat(it).isVisible(WindowInsetsCompat.Type.ime())
                } == true
            }
        }
        return visible
    }
    @Test fun nativeTapOpensImeAndDraftFocusSurviveRecheckFailureRecoveryAndLossOfAccess() {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        var response = CompletableDeferred<JSONObject>().apply { complete(access()) }
        var calls = 0
        val transport = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject {
                check(method == "GET" && path == "/v1/entitlements")
                calls++
                return response.await()
            }
        }
        val plans = Subscriptions(base, transport, scope)
        val draft = mutableStateOf("")
        val consent = mutableStateOf(false)
        val consentChecked = mutableStateOf(false)
        var sendCallbacks = 0
        val allowance = BotAllowance(true, 150, 150, Instant.now().plusSeconds(3600), true)
        fun beginRefresh() {
            compose.runOnIdle {
                response = CompletableDeferred()
                scope.launch { plans.refreshAccess() }
            }
            compose.waitUntil(5_000) { plans.accessCheckState == AccessCheckState.CHECKING }
        }
        fun assertEditing(expected: String) {
            compose.onNodeWithTag("bot-message-input").assertIsDisplayed().assertIsFocused().assertTextEquals(expected)
            assertTrue("Real IME must stay visible while the draft remains focused", imeVisible())
        }
        try {
            runBlocking { withContext(Dispatchers.Main) { assertTrue(plans.refreshAccess()) } }
            compose.setContent { VipiTheme(Appearance.LIGHT) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.BottomCenter) {
                    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.background)
                        .navigationBarsPadding().imePadding().padding(horizontal = 12.dp)) {
                        BotConversationControls(plans.accessCheckState, plans.access, consent.value, consentChecked.value,
                            { consentChecked.value = it }, { consent.value = true },
                            draft.value, { draft.value = it }, {}, false, allowance,
                            { sendCallbacks++ }, { scope.launch { plans.refreshAccess() } }, {}, {})
                    }
                }
            } }
            // Pointer input requests the software keyboard through the actual field.
            // Do not call showSoftInput or use a focus requester to make this pass.
            compose.onNodeWithTag("bot-message-input").performTouchInput { click() }
            compose.waitUntil(8_000) { imeVisible() }
            compose.onNodeWithTag("bot-message-input").performTextInput("A local draft")
            assertEditing("A local draft")
            compose.onNodeWithTag("bot-message-send").assertIsNotEnabled()
            compose.runOnIdle { assertFalse(consent.value); assertEquals(0, sendCallbacks) }
            compose.onNodeWithTag("bot-consent-choice").performScrollTo().performTouchInput { click() }
            compose.onNodeWithTag("bot-message-send").assertIsNotEnabled()
            compose.onNodeWithTag("bot-consent-continue").performScrollTo().performClick()
            assertEditing("A local draft")
            compose.onNodeWithTag("bot-message-send").assertIsEnabled()

            beginRefresh()
            assertEditing("A local draft")
            compose.onNodeWithTag("bot-message-send").assertIsNotEnabled().performTouchInput { click() }
            compose.runOnIdle { assertEquals(0, sendCallbacks) }
            compose.onNodeWithTag("bot-message-input").performTextInput(" while checking")
            response.completeExceptionally(java.io.IOException("Synthetic unavailable"))
            compose.waitUntil(5_000) { plans.accessCheckState == AccessCheckState.ERROR }
            assertEditing("A local draft while checking")
            compose.onNodeWithTag("bot-message-send").assertIsNotEnabled()

            beginRefresh()
            response.complete(access())
            compose.waitUntil(5_000) { plans.accessCheckState == AccessCheckState.LOADED }
            assertEditing("A local draft while checking")
            compose.onNodeWithTag("bot-message-send").assertIsEnabled()
            compose.onNodeWithTag("bot-message-send").performClick()
            compose.runOnIdle { assertEquals(1, sendCallbacks) }

            beginRefresh()
            response.complete(access(false))
            compose.waitUntil(5_000) { plans.accessCheckState == AccessCheckState.LOADED }
            assertEditing("A local draft while checking")
            compose.onNodeWithTag("bot-message-send").assertIsNotEnabled()
            compose.runOnIdle { assertEquals(1, sendCallbacks); assertEquals(4, calls) }
        } finally {
            compose.runOnIdle {
                android.view.inspector.WindowInspector.getGlobalWindowViews().forEach {
                    it.windowInsetsController?.hide(android.view.WindowInsets.Type.ime())
                }
                plans.close(); scope.cancel()
            }
        }
    }

    @Test fun narrowLargeTextConsentScrollsAndItsWholeLabelTogglesWithoutAccepting() {
        val checked = mutableStateOf(false)
        val consent = mutableStateOf(false)
        var accepted = 0
        val currentAccess = SubscriptionAccess.parse(access())
        compose.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 2f)) {
                VipiTheme(Appearance.LIGHT) {
                    Box(Modifier.width(280.dp).height(280.dp)) {
                        BotConversationControls(AccessCheckState.LOADED, currentAccess,
                            consent.value, checked.value, { checked.value = it }, { accepted++; consent.value = true },
                            "", {}, {}, false, null, {}, {}, {}, {})
                    }
                }
            }
        }
        compose.onNodeWithTag("bot-consent-choice").performScrollTo().assertIsOff()
        // Tap the text side rather than the Checkbox's own bounds.
        compose.onNodeWithTag("bot-consent-choice").performTouchInput { click(center + androidx.compose.ui.geometry.Offset(center.x - 12f, 0f)) }
        compose.onNodeWithTag("bot-consent-choice").assertIsOn()
        compose.runOnIdle { assertEquals(0, accepted); assertFalse(consent.value) }
        compose.onNodeWithTag("bot-consent-continue").performScrollTo().assertIsEnabled().performClick()
        compose.runOnIdle { assertEquals(1, accepted); assertTrue(consent.value) }
        compose.onNodeWithTag("bot-consent").assertDoesNotExist()
        compose.onNodeWithTag("bot-message-input").assertIsDisplayed()
    }
}
