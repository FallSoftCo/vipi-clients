package co.fallsoft.vipi

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.core.view.WindowInsetsCompat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle

/** Actual activity, editor, navigation, encrypted outbox and peer decryption.
 * Only service time/HTTP and Play SDK boundaries are controlled. No checkout. */
class FirstMonthExpiryJourneyDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()

    @Test fun expiredSendKeepsQueuedMessageAndNextDraftThroughPlansAndRecreation() {
        val services = JourneyServices(profileRequired = false, expectedBotPosts = 0, cardlessAccess = true)
        MainActivityJourneyFixture("first-month-expiry", services::model).use { f ->
            fun screen(expected: Screen) = compose.waitUntil(10_000) { f.model.screen == expected }
            fun ime(): Boolean {
                var visible = false
                f.instrumentation.runOnMainSync {
                    visible = android.view.inspector.WindowInspector.getGlobalWindowViews().any { view ->
                        view.rootWindowInsets?.let { WindowInsetsCompat.toWindowInsetsCompat(it)
                            .isVisible(WindowInsetsCompat.Type.ime()) } == true
                    }
                }
                return visible
            }
            val queued = "I am reading a book now."
            val next = "Keep this next message until I am ready."
            try {
                f.launch(); screen(Screen.HOME)
                compose.waitUntil(10_000) { f.model.subscriptions?.accessCheckState == AccessCheckState.LOADED }
                compose.runOnIdle {
                    val access = requireNotNull(f.model.subscriptions?.access)
                    assertTrue(access.active(SubscriptionPlan.BASE))
                    assertFalse(access.active(SubscriptionPlan.BOT_MINI))
                    assertEquals(services.cardlessEnds, access.base.cardlessTrial?.endsAt)
                    services.assertNoPurchase()
                }
                compose.onNodeWithContentDescription(f.base.getString(R.string.nav_new_chat)).performTouchInput { click() }
                screen(Screen.NEW_CHAT)
                compose.onNode(hasSetTextAction()).performScrollTo().performTouchInput { click() }
                compose.onNode(hasSetTextAction()).performTextInput("journey_friend")
                compose.onNodeWithText(f.base.getString(R.string.ui_ba6e8c9b0c3e)).performScrollTo().performTouchInput { click() }
                screen(Screen.CONVERSATION)
                // The screen still has yesterday's access snapshot. The server
                // refuses this first send at the boundary; no test sets needsPlan.
                services.baseExpired.set(true)
                compose.onNodeWithTag("message-input").performTouchInput { click() }
                compose.waitUntil(8_000) { ime() }
                compose.onNodeWithTag("message-input").performTextInput(queued)
                compose.onNodeWithTag("message-send").assertIsEnabled().performTouchInput { click() }
                compose.waitUntil(10_000) { services.refusedFriendIDs.isNotEmpty() && f.model.chat?.needsPlan == true }
                val id = compose.runOnIdle {
                    val row = requireNotNull(f.model.chat).messages(services.peer).single()
                    assertEquals(queued, row.text)
                    assertNotEquals("delivered", row.state)
                    assertEquals(services.refusedFriendIDs.first(), row.id)
                    assertEquals(0, services.friendPosts.get())
                    assertNull(services.peerReceived)
                    row.id
                }
                compose.onNodeWithTag("message-input").performTextInput(next)
                if (ime()) f.device.pressBack()
                compose.waitUntil(5_000) { !ime() }
                compose.onNodeWithText(f.base.getString(R.string.ui_f1af503686b6)).performScrollTo().assertIsDisplayed()
                compose.onNodeWithText(f.base.getString(R.string.ui_b30a48ba0b99)).performScrollTo().assertIsDisplayed()
                f.capture("01-refused-send-preserves-next-draft")
                compose.onNodeWithText(f.base.getString(R.string.ui_b30a48ba0b99)).performTouchInput { click() }
                screen(Screen.PLANS)
                compose.waitUntil(10_000) {
                    f.model.subscriptions?.accessCheckState == AccessCheckState.LOADED &&
                        f.model.subscriptions?.access?.base?.cardlessTrial?.active == false
                }
                val end = DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG).withZone(ZoneId.systemDefault()).format(services.cardlessEnds)
                compose.onNodeWithText(f.base.getString(R.string.cardless_ended, end)).performScrollTo().assertIsDisplayed()
                compose.onNodeWithText(f.base.getString(R.string.subscribe_annual, "$12.00"))
                    .performScrollTo().assertIsDisplayed().assertIsEnabled()
                compose.runOnIdle {
                    assertEquals(id, f.model.chat?.messages(services.peer)?.single()?.id)
                    assertEquals(next, f.model.chat?.compose(services.peer))
                    assertFalse(requireNotNull(f.model.subscriptions?.access).active(SubscriptionPlan.BOT_MINI))
                    services.assertNoPurchase()
                }
                f.capture("02-ended-month-offers-base-without-checkout")
                f.device.pressBack(); screen(Screen.HOME)
                compose.onNodeWithText("Journey Friend").performTouchInput { click() }; screen(Screen.CONVERSATION)
                compose.onNodeWithTag("message-input").assertTextEquals(next)
                f.recreate(); screen(Screen.CONVERSATION)
                compose.onNodeWithTag("message-input").assertTextEquals(next)
                compose.runOnIdle {
                    val row = requireNotNull(f.model.chat).messages(services.peer).single()
                    assertEquals(id, row.id); assertEquals(queued, row.text)
                    assertTrue(services.refusedFriendIDs.all { it == id })
                    assertEquals(1, services.refusedFriendCiphertexts.distinct().size)
                    services.assertNoPurchase()
                }
                // Independent encrypted disk read, not merely the surviving UI model.
                MessageVault(f.isolated, services.account).use { vault ->
                    val history = ConversationHistory(vault)
                    assertEquals(next, history.composeDraft(services.peer))
                    assertEquals(id, history.messages(services.peer).single().id)
                }
                // Controlled server entitlement update, not a simulated purchase.
                services.baseRestored.set(true)
                runBlocking { withContext(Dispatchers.Main) { requireNotNull(f.model.subscriptions).refreshAccess() } }
                compose.waitUntil(10_000) { f.model.chat?.messages(services.peer)?.singleOrNull()?.state == "delivered" }
                compose.runOnIdle {
                    assertEquals(1, services.friendPosts.get())
                    assertEquals(id, services.outgoingFriendId)
                    assertEquals(queued, services.peerReceived)
                    assertFalse(requireNotNull(f.model.chat).needsPlan)
                    assertNull(f.model.chat?.notice)
                    assertEquals(next, f.model.chat?.compose(services.peer))
                    assertEquals(services.cardlessStarted, f.model.subscriptions?.access?.base?.cardlessTrial?.startedAt)
                    assertEquals(services.cardlessEnds, f.model.subscriptions?.access?.base?.cardlessTrial?.endsAt)
                    assertFalse(requireNotNull(f.model.subscriptions?.access).active(SubscriptionPlan.BOT_MINI))
                    services.assertNoPurchase()
                }
                compose.onNodeWithTag("message-input").assertTextEquals(next)
                compose.onNodeWithText(f.base.getString(R.string.ui_b30a48ba0b99)).assertDoesNotExist()
                f.capture("03-restored-access-delivers-same-message-keeps-next-draft")
                File(f.output, "receipt.json").writeText(JSONObject()
                    .put("actual_main_activity", true).put("real_signal_peer_decryption", true)
                    .put("server_expiry_refusals", services.refusedFriendIDs.size)
                    .put("same_message_id_and_ciphertext_retained", true).put("accepted_posts", 1)
                    .put("independent_vault_draft_and_queue_verified", true).put("billing_launches", 0)
                    .put("bot_access_not_granted", true).put("live_purchase_or_time_wait", false).toString(2))
            } catch (failure: Throwable) {
                runCatching { f.capture("failure") }.onFailure { failure.addSuppressed(it) }
                throw failure
            } finally { f.stopActivity(); services.close() }
        }
    }
}
