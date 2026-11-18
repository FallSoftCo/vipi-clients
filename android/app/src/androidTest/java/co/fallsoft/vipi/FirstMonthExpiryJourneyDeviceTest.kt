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

    @Test fun expiredBaseStillReceivesPeerMessageWhileQueuedSendAndNextDraftStayIntact() {
        val services = JourneyServices(profileRequired = false, expectedBotPosts = 0,
            expectedFriendPosts = 2, cardlessAccess = true)
        MainActivityJourneyFixture("expired-incoming", services::model).use { f ->
            fun screen(expected: Screen) = compose.waitUntil(10_000) { f.model.screen == expected }
            fun ime(): Boolean {
                var shown = false
                f.instrumentation.runOnMainSync {
                    shown = android.view.inspector.WindowInspector.getGlobalWindowViews().any { view ->
                        view.rootWindowInsets?.let { WindowInsetsCompat.toWindowInsetsCompat(it)
                            .isVisible(WindowInsetsCompat.Type.ime()) } == true
                    }
                }
                return shown
            }
            fun editor(expected: String) = compose.onNodeWithTag("message-input").assert(
                SemanticsMatcher("Exact editor plain text") {
                    it.config.contains(androidx.compose.ui.semantics.SemanticsProperties.EditableText) &&
                        it.config[androidx.compose.ui.semantics.SemanticsProperties.EditableText].text == expected
                })
            val warmup = "This message establishes our encrypted conversation."
            val queued = "Keep this message queued after my free month ends."
            val next = "I can still write while I read your reply."
            try {
                f.launch(); screen(Screen.HOME)
                compose.waitUntil(10_000) { f.model.subscriptions?.accessCheckState == AccessCheckState.LOADED }
                compose.runOnIdle { assertTrue(requireNotNull(f.model.subscriptions?.access).active(SubscriptionPlan.BASE)) }
                compose.onNodeWithContentDescription(f.base.getString(R.string.nav_new_chat)).performTouchInput { click() }
                screen(Screen.NEW_CHAT)
                compose.onNode(hasSetTextAction()).performScrollTo().performTouchInput { click() }
                compose.onNode(hasSetTextAction()).performTextInput("journey_friend")
                compose.onNodeWithText(f.base.getString(R.string.ui_ba6e8c9b0c3e)).performScrollTo().performTouchInput { click() }
                screen(Screen.CONVERSATION)
                compose.onNodeWithTag("message-input").performTouchInput { click() }
                compose.waitUntil(8_000) { ime() }
                compose.onNodeWithTag("message-input").performTextInput(warmup)
                compose.onNodeWithTag("message-send").assertIsEnabled().performTouchInput { click() }
                compose.waitUntil(10_000) { services.friendPosts.get() == 1 && f.model.chat?.messages(services.peer)?.singleOrNull()?.state == "delivered" }
                compose.runOnIdle { assertEquals(warmup, services.peerReceived) }
                val warmupId = requireNotNull(services.outgoingFriendId)
                services.baseExpired.set(true)
                compose.onNodeWithTag("message-input").performTextInput(queued)
                compose.onNodeWithTag("message-send").assertIsEnabled().performTouchInput { click() }
                compose.waitUntil(10_000) { services.refusedFriendIDs.isNotEmpty() && f.model.chat?.needsPlan == true }
                val queuedId = compose.runOnIdle {
                    requireNotNull(f.model.chat).messages(services.peer).single { it.text == queued }.also {
                        assertNotEquals("delivered", it.state); assertEquals(services.refusedFriendIDs.first(), it.id)
                    }.id
                }
                compose.onNodeWithTag("message-input").performTextInput(next)
                editor(next).assertIsFocused()
                val reason = f.base.getString(R.string.ui_f1af503686b6)
                val recovery = f.base.getString(R.string.ui_b30a48ba0b99)
                // Critical refusal appears without a search or hiding the IME.
                compose.onNodeWithText(reason).assertIsDisplayed()
                f.assertNativeTextInViewport(compose, reason, "00-expired-reason-with-editable-draft")
                f.assertNativeTextInViewport(compose, next, "00-expired-editor", 48)
                f.capture("00-expired-reason-with-editable-draft")
                // The existing status region may scroll on short/large-text screens.
                compose.onNodeWithText(recovery).performScrollTo().assertIsDisplayed().assertHasClickAction()
                f.assertNativeTextInViewport(compose, recovery, "00-expired-recovery-action", 48, requireClickOwner = true)
                editor(next).assertIsFocused()
                if (ime()) f.device.pressBack()
                compose.waitUntil(5_000) { !ime() }
                compose.onNodeWithText(f.base.getString(R.string.ui_b30a48ba0b99)).performScrollTo().assertIsDisplayed().performTouchInput { click() }
                screen(Screen.PLANS)
                compose.waitUntil(10_000) {
                    f.model.subscriptions?.accessCheckState == AccessCheckState.LOADED &&
                        f.model.subscriptions?.access?.active(SubscriptionPlan.BASE) == false
                }
                compose.runOnIdle {
                    assertFalse(requireNotNull(f.model.subscriptions?.access).active(SubscriptionPlan.BOT_MINI))
                    assertEquals(services.cardlessStarted, f.model.subscriptions?.access?.base?.cardlessTrial?.startedAt)
                    assertEquals(services.cardlessEnds, f.model.subscriptions?.access?.base?.cardlessTrial?.endsAt)
                    services.assertNoPurchase()
                }
                f.device.pressBack(); screen(Screen.HOME)
                compose.onNodeWithText("Journey Friend").performTouchInput { click() }; screen(Screen.CONVERSATION)
                editor(next).performTouchInput { click() }
                compose.waitUntil(8_000) { ime() }
                editor(next).assertIsFocused()
                // Establish the real user caret BEFORE incoming reflows the
                // timeline. Do not reset focus or selection after it arrives.
                selectNativeDraftEnd(compose, f, next, "00b-native-end-selection-before-incoming")
                // A reversible real key edit clears selection-handle state
                // before the baseline proof; no input is repeated after arrival.
                assertTrue(f.device.pressKeyCode(android.view.KeyEvent.KEYCODE_X))
                compose.waitUntil(5_000) { f.focusedNativeEditor(next + "x")?.textSelectionEnd == next.length + 1 }
                assertTrue(f.device.pressKeyCode(android.view.KeyEvent.KEYCODE_DEL))
                compose.waitUntil(5_000) { f.focusedNativeEditor(next)?.textSelectionEnd == next.length }
                assertNativeDraftEndLine(compose, f, "message-input", next,
                    "00b-native-draft-end-before-incoming", requireInternalScroll = false)
                // A real Signal peer encrypts this reply. The fake event carries
                // metadata only; production ChatSession owns inbox, receipt and UI.
                compose.runOnIdle { services.queuePeerReplyAndSignalInbox() }
                compose.waitUntil(10_000) {
                    services.friendReplyReceipts.get() == 1 && f.model.chat?.messages(services.peer)?.any {
                        !it.outgoing && it.id == services.friendReplyId && it.text == services.friendReply
                    } == true
                }
                f.assertIncomingAboveComposer(compose, services.friendReply, "01-expired-base-reply-readable-with-native-ime")
                editor(next).assertIsFocused()
                assertNativeDraftEndLine(compose, f, "message-input", next,
                    "01b-native-draft-end-after-incoming-without-retap", requireInternalScroll = false)
                assertTrue(f.device.pressKeyCode(android.view.KeyEvent.KEYCODE_X))
                compose.waitUntil(5_000) { f.focusedNativeEditor(next + "x")?.textSelectionEnd == next.length + 1 }
                assertNativeDraftEndLine(compose, f, "message-input", next + "x",
                    "01c-native-appended-draft-end-after-incoming", requireInternalScroll = false)
                MessageVault(f.isolated, services.account).use { vault ->
                    assertEquals(next + "x", ConversationHistory(vault).composeDraft(services.peer))
                }
                assertTrue(f.device.pressKeyCode(android.view.KeyEvent.KEYCODE_DEL))
                compose.waitUntil(5_000) { f.focusedNativeEditor(next)?.textSelectionEnd == next.length }
                assertNativeDraftEndLine(compose, f, "message-input", next,
                    "01d-native-restored-draft-end-after-incoming", requireInternalScroll = false)
                compose.runOnIdle {
                    val rows = requireNotNull(f.model.chat).messages(services.peer)
                    assertEquals(3, rows.size)
                    assertEquals(setOf(warmupId, queuedId), rows.filter { it.outgoing }.map { it.id }.toSet())
                    assertEquals("delivered", rows.single { it.id == warmupId }.state)
                    assertNotEquals("delivered", rows.single { it.id == queuedId }.state)
                    assertEquals(next, f.model.chat?.compose(services.peer))
                    assertTrue(requireNotNull(f.model.chat).needsPlan)
                    assertTrue(services.refusedFriendIDs.all { it == queuedId })
                    assertEquals(1, services.refusedFriendCiphertexts.distinct().size)
                    assertEquals(1, services.friendPosts.get())
                    assertFalse(requireNotNull(f.model.subscriptions?.access).active(SubscriptionPlan.BASE))
                    services.assertNoPurchase()
                }
                if (ime()) f.device.pressBack()
                compose.waitUntil(5_000) { !ime() }
                compose.onNodeWithText(f.base.getString(R.string.ui_f1af503686b6)).performScrollTo().assertIsDisplayed()
                compose.onNodeWithText(f.base.getString(R.string.ui_b30a48ba0b99)).performScrollTo().assertIsDisplayed().assertHasClickAction()
                f.capture("02-expired-base-recovery-remains-actionable-after-incoming")
                MessageVault(f.isolated, services.account).use { vault ->
                    val history = ConversationHistory(vault)
                    assertEquals(next, history.composeDraft(services.peer))
                    assertEquals(3, history.messages(services.peer).size)
                    assertEquals(services.friendReply, history.messages(services.peer).single { !it.outgoing }.text)
                    assertEquals(queuedId, history.messages(services.peer).single { it.text == queued }.id)
                }
                File(f.output, "receipt.json").writeText(JSONObject().put("actual_main_activity", true)
                    .put("actual_expired_entitlement_response", true).put("outgoing_402_queued", true)
                    .put("real_signal_incoming_while_expired", true).put("incoming_receipts", 1)
                    .put("queued_message_id_and_ciphertext_unchanged", true).put("independent_next_draft_retained", true)
                    .put("native_reply_above_composer_and_ime", true).put("base_remained_expired", true)
                    .put("bot_access_not_granted", true).put("billing_launches", 0)
                    .put("live_service_physical_push_or_purchase", false).toString(2))
            } catch (failure: Throwable) {
                runCatching { f.capture("failure") }.onFailure { failure.addSuppressed(it) }; throw failure
            } finally { f.stopActivity(); services.close() }
        }
    }

}
