package co.fallsoft.vipi

import android.app.Activity
import android.app.Application
import android.app.Instrumentation
import android.content.Context
import android.content.Intent
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.core.view.WindowInsetsCompat
import androidx.test.uiautomator.By
import androidx.test.uiautomator.BySelector
import com.android.billingclient.api.BillingClient
import com.android.billingclient.api.PurchasesUpdatedListener
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import okhttp3.Request
import okhttp3.Response
import okhttp3.Protocol
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.security.KeyStore
import java.time.Instant
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

/** Real MainActivity + navigation + model + encrypted sessions. Only the external
 * service, WebSocket, billing and share boundaries are controlled. */
class MainActivityAuthenticatedJourneyDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()

    @Test fun profileToChatsInviteLookupFriendKeyboardSendAndReturnToSavedHistory() {
        val services = JourneyServices(profileRequired = true)
        MainActivityJourneyFixture("profile-friend", services::model).use { f ->
            fun assertIncomingReplyVisible(phase: String) {
                var observation = "Incoming native paragraph not yet visible"
                try {
                    compose.waitUntil(8_000) {
                        val viewport = f.unobscuredWindow()
                        var visible = false
                        f.instrumentation.runOnMainSync {
                            // Accessibility text follows the current immersed
                            // face. Authenticate the real native paragraph by
                            // its source identity while letting it keep flipping.
                            val paragraph = f.paragraphs().singleOrNull { it.displayedOriginal == services.friendReply }
                            val bounds = android.graphics.Rect()
                            if (paragraph != null) {
                                val drawn = paragraph.visibleText()
                                visible = paragraph.getGlobalVisibleRect(bounds) && f.fullyVisible(paragraph) &&
                                    viewport.contains(bounds) && drawn.isNotBlank()
                                observation = "original=${paragraph.displayedOriginal} drawn=$drawn bounds=$bounds viewport=$viewport fullyVisible=$visible"
                            }
                        }
                        visible
                    }
                } catch (failure: ComposeTimeoutException) {
                    throw AssertionError("$phase: $observation", failure)
                }
            }
            var shareCount = 0
            val share = object : Instrumentation.ActivityMonitor() {
                override fun onStartActivity(intent: Intent): Instrumentation.ActivityResult? {
                    if (intent.action != Intent.ACTION_CHOOSER) return null
                    @Suppress("DEPRECATION") val nested = intent.getParcelableExtra<Intent>(Intent.EXTRA_INTENT)
                    check(nested?.action == Intent.ACTION_SEND && nested.type == "text/plain")
                    val text = requireNotNull(nested.getStringExtra(Intent.EXTRA_TEXT))
                    check(text.contains("https://api.mambovipi.app/invite/journey_tester"))
                    check(!text.contains(services.subject))
                    shareCount++
                    return Instrumentation.ActivityResult(Activity.RESULT_CANCELED, null)
                }
            }
            f.instrumentation.addMonitor(share)
            try {
                f.launch()
                waitScreen(f, Screen.PROFILE)
                compose.onNodeWithTag("profile-submit").assertIsNotEnabled()
                compose.onNodeWithTag("profile-name").performScrollTo().performTouchInput { click() }
                compose.waitUntil(8_000) { imeVisible(f) }
                compose.onNodeWithTag("profile-name").performTextInput("Journey Tester")
                compose.onNodeWithTag("profile-username").performScrollTo().performTouchInput { click() }
                compose.onNodeWithTag("profile-username").performTextInput("journey_tester")
                compose.onNodeWithTag("profile-submit").performScrollTo().assertIsEnabled().performTouchInput { click() }
                waitScreen(f, Screen.HOME)
                compose.onNodeWithText(f.base.getString(R.string.nav_chats)).assertIsDisplayed()
                compose.runOnIdle {
                    assertEquals(1, services.profileWrites.get())
                    assertEquals(1, services.deviceRegistrations.get())
                    assertTrue(f.model.chat?.ready == true)
                }
                f.capture("01-visible-chats-after-profile")
                compose.onNodeWithContentDescription(f.base.getString(R.string.nav_new_chat)).performTouchInput { click() }
                waitScreen(f, Screen.NEW_CHAT)
                compose.onNodeWithText(f.base.getString(R.string.nav_invite)).performTouchInput { click() }
                compose.runOnIdle { assertEquals(1, shareCount) }
                val username = compose.onNode(hasSetTextAction())
                username.performScrollTo().performTouchInput { click() }
                compose.waitUntil(8_000) { imeVisible(f) }
                username.performTextInput("missing_friend")
                username.assertEditorValue("missing_friend").assertIsFocused()
                assertNativeContained(f, By.text("missing_friend"), "focused friend username above IME", 48)
                compose.onNodeWithText(f.base.getString(R.string.ui_ba6e8c9b0c3e)).performScrollTo().performTouchInput { click() }
                compose.onNodeWithText(f.base.getString(R.string.ui_eb7c5193d2ac)).assertIsDisplayed()
                compose.runOnIdle { assertEquals(Screen.NEW_CHAT, f.model.screen) }
                compose.waitUntil(5_000) { !imeVisible(f) }
                assertNativeContained(f, By.text("missing_friend"), "friend username", 48)
                assertNativeContained(f, By.text(f.base.getString(R.string.ui_ba6e8c9b0c3e)), "find friend action")
                assertNativeContained(f, By.text(f.base.getString(R.string.ui_eb7c5193d2ac)), "friend lookup error")
                f.capture("02-lookup-error-keeps-editable-username")
                username.performScrollTo().performTouchInput { click() }
                compose.waitUntil(8_000) { imeVisible(f) }
                username.performTextReplacement("@Journey_Friend")
                username.assertEditorValue("@Journey_Friend").assertIsFocused()
                assertNativeContained(f, By.text("@Journey_Friend"), "corrected friend username above IME", 48)
                compose.onNodeWithText(f.base.getString(R.string.ui_ba6e8c9b0c3e)).performScrollTo().performTouchInput { click() }
                waitScreen(f, Screen.CONVERSATION)
                compose.onNodeWithText("Journey Friend").assertIsDisplayed()
                val prompt = "I am reading a book now."
                compose.onNodeWithTag("message-input").performTouchInput { click() }
                compose.waitUntil(8_000) { imeVisible(f) }
                compose.onNodeWithTag("message-input").assertIsFocused().performTextInput(prompt)
                exerciseShortLandscapeComposer(compose, f, "message-input", "message-send", prompt, "friend-short-landscape")
                compose.runOnIdle { assertEquals(0, services.friendPosts.get()); assertEquals(prompt, f.model.chat?.compose(services.peer)) }
                f.device.pressBack()
                compose.waitUntil(5_000) { !imeVisible(f) }
                compose.runOnIdle { assertEquals(Screen.CONVERSATION, f.model.screen) }
                compose.onNodeWithTag("message-input").assertTextEquals(prompt)
                compose.onNodeWithTag("message-send").assertIsEnabled().performTouchInput { click() }
                compose.waitUntil(10_000) { f.model.chat?.messages(services.peer)?.singleOrNull()?.state == "delivered" }
                compose.onNodeWithText("Delivered", substring = true).assertIsDisplayed()
                compose.onNodeWithTag("message-input").assertEmptyEditor()
                compose.runOnIdle {
                    assertEquals(1, services.friendPosts.get())
                    assertEquals(prompt, services.peerReceived)
                    assertEquals(listOf("missing_friend", "journey_friend"), services.lookups)
                }
                f.capture("03-friend-received-through-local-encrypted-relay")
                f.device.pressBack()
                waitScreen(f, Screen.HOME)
                compose.onNodeWithText("Journey Friend").assertIsDisplayed().performTouchInput { click() }
                waitScreen(f, Screen.CONVERSATION)
                compose.onNodeWithText("Delivered", substring = true).assertIsDisplayed()
                compose.onNodeWithTag("message-input").performTouchInput { click() }
                compose.waitUntil(8_000) { imeVisible(f) }
                compose.onNodeWithTag("message-input").performTextInput("Keep this local friend draft.")
                // The reply is encrypted by the actual peer Signal session.
                // A metadata-only event wakes the production durable inbox;
                // no application message/history is inserted by the fixture.
                compose.runOnIdle { services.queuePeerReplyAndSignalInbox() }
                compose.waitUntil(8_000) {
                    f.model.chat?.messages(services.peer)?.singleOrNull { !it.outgoing }?.let {
                        it.id == services.friendReplyId && it.text == services.friendReply
                    } == true && services.friendReplyReceipts.get() == 1
                }
                assertIncomingReplyVisible("Decrypted incoming peer reply above native IME")
                compose.onNodeWithTag("message-input").assertEditorValue("Keep this local friend draft.")
                f.capture("04-incoming-signal-reply-keeps-unsent-draft")
                f.backgroundAndResume()
                waitScreen(f, Screen.CONVERSATION)
                compose.onNodeWithTag("message-input").assertTextEquals("Keep this local friend draft.")
                f.recreate()
                waitScreen(f, Screen.CONVERSATION)
                compose.onNodeWithTag("message-input").assertTextEquals("Keep this local friend draft.")
                assertIncomingReplyVisible("Incoming peer reply after activity recreation")
                // Reopen the conversation through the real list as well as
                // recreating its host; the local compose draft is independent.
                if (imeVisible(f)) { f.device.pressBack(); compose.waitUntil(5_000) { !imeVisible(f) } }
                f.device.pressBack(); waitScreen(f, Screen.HOME)
                compose.onNodeWithText("Journey Friend").performScrollTo().performTouchInput { click() }
                waitScreen(f, Screen.CONVERSATION)
                assertIncomingReplyVisible("Durable incoming peer reply after conversation reopen")
                compose.onNodeWithTag("message-input").assertEditorValue("Keep this local friend draft.")
                compose.runOnIdle {
                    MessageVault(f.isolated, services.account).use { vault ->
                        val history = ConversationHistory(vault)
                        assertEquals("Keep this local friend draft.", history.composeDraft(services.peer))
                        val saved = history.messages(services.peer)
                        assertEquals(2, saved.size)
                        assertEquals(prompt, saved.single { it.outgoing }.text)
                        assertEquals(services.outgoingFriendId, saved.single { it.outgoing }.id)
                        assertEquals(services.friendReply, saved.single { !it.outgoing }.text)
                        assertEquals(services.friendReplyId, saved.single { !it.outgoing }.id)
                    }
                    assertEquals(1, services.friendReplyReceipts.get())
                    assertEquals(1, services.inboxWakeups.get())
                }
                compose.onNodeWithTag("message-input").performTouchInput { click() }
                compose.waitUntil(8_000) { imeVisible(f) }
                f.capture("05-returned-bidirectional-friend-history-and-resumed-draft")
                compose.runOnIdle { assertEquals(1, services.friendPosts.get()); assertEquals(0, services.botPosts.get()) }
                services.assertNoPurchase()
                File(f.output, "result.json").writeText(JSONObject().put("pass", true).put("profile_writes", 1)
                    .put("share_payload_checked_external_share_blocked", true).put("native_ime", true)
                    .put("friend_encrypted_posts", 1).put("fake_peer_decrypted", true)
                    .put("peer_encrypted_replies", 1).put("metadata_only_inbox_events", 1).put("incoming_receipts", 1)
                    .put("incoming_reply_native_visible_after_sync_recreate_and_reopen", true)
                    .put("encrypted_history_exact_one_incoming_and_one_outgoing", true)
                    .put("physical_push_or_live_relay_claimed", false)
                    .put("draft_survived_incoming_reply_resume_recreate_and_reopen", true)
                    .put("draft_survived_resume_and_recreate", true).put("draft_read_from_fresh_encrypted_vault", true)
                    .put("device_registrations", 1).put("live_server_or_real_contact", false).toString(2))
            } catch (failure: Throwable) {
                runCatching { f.capture("failure-before-cleanup") }.onFailure { failure.addSuppressed(it) }
                throw failure
            } finally { f.instrumentation.removeMonitor(share); f.stopActivity(); services.close() }
        }
    }

    @Test fun botDraftSurvivesBackAccessErrorAndOneInflightSendFinishesAfterLeavingScreen() {
        val services = JourneyServices(profileRequired = false)
        MainActivityJourneyFixture("bot-lifecycle", services::model).use { f ->
            try {
                f.launch()
                waitScreen(f, Screen.HOME)
                openBot(f)
                val draft = "A local Bot lifecycle greeting."
                compose.onNodeWithTag("bot-message-input").performTouchInput { click() }
                compose.waitUntil(8_000) { imeVisible(f) }
                compose.onNodeWithTag("bot-message-input").performTextInput(draft)
                compose.onNodeWithTag("bot-message-send").assertIsNotEnabled()
                compose.onNodeWithTag("bot-consent-continue").performScrollTo().assertIsNotEnabled()
                compose.runOnIdle { assertEquals(0, services.botPosts.get()); assertFalse(f.model.bot!!.consent) }
                f.device.pressBack()
                compose.waitUntil(5_000) { !imeVisible(f) }
                compose.runOnIdle { assertEquals(Screen.BOT, f.model.screen) }
                f.device.pressBack()
                waitScreen(f, Screen.HOME)
                openBot(f)
                compose.onNodeWithTag("bot-message-input").assertTextEquals(draft).performTouchInput { click() }
                compose.waitUntil(8_000) { imeVisible(f) }
                services.failNextEntitlement.set(true)
                f.backgroundAndResume()
                compose.waitUntil(8_000) { f.model.subscriptions?.accessCheckState == AccessCheckState.ERROR }
                compose.onNodeWithTag("bot-message-input").assertTextEquals(draft)
                compose.onNodeWithText(f.base.getString(R.string.ui_541ecffcdb87)).performScrollTo().assertIsDisplayed()
                compose.onNodeWithText(f.base.getString(R.string.try_again)).performScrollTo()
                compose.onNodeWithTag("bot-message-send").assertIsNotEnabled()
                assertNativeContained(f, By.desc(f.base.getString(R.string.nav_back)), "Bot Back icon", 24)
                assertNativeContained(f, By.text(f.base.getString(R.string.ui_f173182378d0)), "Bot title", 20)
                assertNativeContained(f, By.text(draft), "Bot editor", 48)
                assertNativeContained(f, By.text(f.base.getString(R.string.try_again)), "Bot access retry")
                f.capture("01-bot-plan-error-with-retained-draft")
                compose.onNodeWithText(f.base.getString(R.string.try_again)).performScrollTo().performTouchInput { click() }
                compose.waitUntil(8_000) { f.model.subscriptions?.accessCheckState == AccessCheckState.LOADED }
                compose.onNodeWithTag("bot-consent-choice").performScrollTo().performTouchInput { click() }
                // The choice itself is not consent: the explicit Continue action is required.
                compose.onNodeWithTag("bot-message-send").assertIsNotEnabled()
                compose.runOnIdle { assertEquals(0, services.botPosts.get()); assertFalse(f.model.bot!!.consent) }
                compose.onNodeWithTag("bot-consent-continue").performScrollTo().performTouchInput { click() }
                compose.waitUntil(5_000) { f.model.bot?.consent == true }
                compose.onNodeWithTag("bot-message-input").performTouchInput { click() }
                compose.waitUntil(8_000) { imeVisible(f) }
                compose.onNodeWithTag("bot-message-send").assertIsEnabled().performTouchInput { click() }
                compose.waitUntil(5_000) { services.botPosts.get() == 1 && f.model.bot?.busy == true }
                f.device.pressBack()
                compose.waitUntil(5_000) { !imeVisible(f) }
                f.device.pressBack()
                waitScreen(f, Screen.HOME)
                services.botReplyGate.complete(Unit)
                compose.waitUntil(8_000) { f.model.bot?.messages?.size == 2 && f.model.bot?.busy == false }
                openBot(f)
                compose.waitUntil(8_000) {
                    var shown = false
                    f.instrumentation.runOnMainSync { shown = f.paragraphs().any { it.displayedOriginal == services.botReply && f.fullyVisible(it) } }
                    shown
                }
                compose.onNodeWithText("149 of 150 replies left", substring = true).assertIsDisplayed()
                compose.onNodeWithTag("bot-message-input").assertEmptyEditor().performTouchInput { click() }
                compose.waitUntil(8_000) { imeVisible(f) }
                f.capture("02-one-confirmed-reply-after-back-and-reopen")
                compose.runOnIdle {
                    assertEquals(1, services.botPosts.get())
                    assertEquals(149, f.model.bot?.allowance?.remaining)
                    assertEquals(listOf("confirmed", "confirmed"), f.model.bot?.messages?.map { it.status })
                }
                val nextDraft = "Keep this next Bot message local."
                compose.onNodeWithTag("bot-message-input").performTextInput(nextDraft)
                compose.onNodeWithTag("bot-message-input").assertEditorValue(nextDraft)
                assertReplyAudioAboveComposer(f, services.botReply, nextDraft)
                f.recreate()
                waitScreen(f, Screen.BOT)
                compose.onNodeWithTag("bot-message-input").assertTextEquals(nextDraft)
                compose.runOnIdle {
                    BotSession(f.isolated, services.account, services.transport(f.model.authentication, services.subject)).use { reopened ->
                        assertTrue(reopened.consent)
                        assertEquals(nextDraft, reopened.draft)
                        assertEquals(listOf(draft, services.botReply), reopened.messages.map { it.text })
                    }
                    assertEquals(1, services.botPosts.get())
                }
                compose.onNodeWithTag("bot-message-input").performTouchInput { click() }
                compose.waitUntil(8_000) { imeVisible(f) }
                assertReplyAudioAboveComposer(f, services.botReply, nextDraft)
                f.capture("03-recreated-bot-next-draft-with-confirmed-history")
                services.assertNoPurchase()
                File(f.output, "result.json").writeText(JSONObject().put("pass", true)
                    .put("native_back_dismisses_ime_before_navigation", true).put("draft_retained_after_back_resume", true)
                    .put("access_error_retry", true).put("one_post_survived_navigation", true)
                    .put("confirmed_reply_visible", true).put("remaining_replies", 149)
                    .put("draft_survived_recreate", true).put("consent_history_and_draft_read_from_fresh_session", true)
                    .put("real_provider_claimed", false).toString(2))
            } catch (failure: Throwable) {
                runCatching { f.capture("failure-before-cleanup") }.onFailure { failure.addSuppressed(it) }
                throw failure
            } finally { services.botReplyGate.complete(Unit); f.stopActivity(); services.close() }
        }
    }
    @Test fun uncertainBotReplyHasVisibleRecoveryWithoutReplayingThePrompt() {
        val services = JourneyServices(profileRequired = false)
        MainActivityJourneyFixture("bot-uncertain-recovery", services::model).use { f ->
            try {
                f.launch()
                waitScreen(f, Screen.HOME)
                openBot(f)
                compose.onNodeWithTag("bot-consent-choice").performScrollTo().performTouchInput { click() }
                compose.onNodeWithTag("bot-consent-continue").performScrollTo().performTouchInput { click() }
                val firstPrompt = "A local prompt with an uncertain reply."
                compose.onNodeWithTag("bot-message-input").performTouchInput { click() }
                compose.waitUntil(8_000) { imeVisible(f) }
                compose.onNodeWithTag("bot-message-input").performTextInput(firstPrompt)
                compose.waitUntil(8_000) { f.model.bot?.allowance != null && f.model.subscriptions?.accessCheckState == AccessCheckState.LOADED }
                services.failBotReply.set(true)
                compose.onNodeWithTag("bot-message-send").assertIsEnabled().performTouchInput { click() }
                compose.waitUntil(5_000) { services.botPosts.get() == 1 && f.model.bot?.busy == true }
                services.botReplyGate.complete(Unit)
                compose.waitUntil(8_000) { f.model.bot?.busy == false && f.model.bot?.messages?.singleOrNull()?.status == "unconfirmed" }
                compose.onNodeWithText(f.base.getString(R.string.bot_reply_unconfirmed)).assertIsDisplayed()
                assertNativeContained(f, By.text(f.base.getString(R.string.bot_reply_unconfirmed)), "new unconfirmed reply notice", 20)
                assertNativeContained(f, By.text(f.base.getString(R.string.ui_cf0b3e3d47ec)), "unconfirmed reply recovery action", 20)
                compose.onNodeWithTag("bot-message-input").assertEmptyEditor()
                compose.onNodeWithTag("bot-message-send").assertIsNotEnabled()
                f.capture("01-uncertain-reply-with-explicit-allowance-recovery")
                compose.onNodeWithText(f.base.getString(R.string.ui_cf0b3e3d47ec)).performTouchInput { click() }
                compose.waitUntil(8_000) { f.model.bot?.allowance != null }
                val nextDraft = "An editable draft after the uncertain reply."
                compose.onNodeWithTag("bot-message-input").performTouchInput { click() }
                compose.waitUntil(8_000) { imeVisible(f) }
                compose.onNodeWithTag("bot-message-input").performTextInput(nextDraft)
                compose.onNodeWithTag("bot-message-send").assertIsEnabled()
                f.device.pressBack()
                compose.waitUntil(5_000) { !imeVisible(f) }
                f.device.pressBack()
                waitScreen(f, Screen.HOME)
                openBot(f)
                compose.onNodeWithTag("bot-message-input").assertTextEquals(nextDraft)
                f.recreate()
                waitScreen(f, Screen.BOT)
                compose.onNodeWithTag("bot-message-input").assertTextEquals(nextDraft).performTouchInput { click() }
                compose.waitUntil(8_000) { imeVisible(f) }
                compose.runOnIdle {
                    assertEquals(1, services.botPosts.get())
                    assertEquals("unconfirmed", f.model.bot?.messages?.singleOrNull()?.status)
                    assertEquals(firstPrompt, f.model.bot?.messages?.singleOrNull()?.text)
                    BotSession(f.isolated, services.account, services.transport(f.model.authentication, services.subject)).use { reopened ->
                        assertEquals(nextDraft, reopened.draft)
                        assertEquals("unconfirmed", reopened.messages.single().status)
                    }
                }
                f.capture("02-editable-recreated-draft-without-automatic-replay")
                services.assertNoPurchase()
                File(f.output, "result.json").writeText(JSONObject().put("pass", true)
                    .put("uncertain_post_count", 1).put("unconfirmed_history_retained", true)
                    .put("allowance_recovery_did_not_replay", true).put("draft_survived_back_and_recreate", true)
                    .put("provider_result_claimed", false).toString(2))
            } catch (failure: Throwable) {
                runCatching { f.capture("failure-before-cleanup") }.onFailure { failure.addSuppressed(it) }
                throw failure
            } finally { services.botReplyGate.complete(Unit); f.stopActivity(); services.close() }
        }
    }

    @Test fun readingOlderBotHistoryKeepsItsNativeAnchorWhenPendingReplyArrivesAndImeOpens() {
        val services = JourneyServices(profileRequired = false, seedBotMessages = 30, expectedBotPosts = 2)
        MainActivityJourneyFixture("bot-history-anchor", services::model).use { f ->
            fun paragraphPosition(original: String? = null, allowPartial: Boolean = false): Pair<String, Int>? {
                if (android.os.Build.VERSION.SDK_INT >= 33) f.instrumentation.uiAutomation.clearCache()
                val listViewport = requireNotNull(f.device.findObject(By.scrollable(true).pkg(f.base.packageName))) {
                    "The real native Bot timeline must be present"
                }.visibleBounds
                val windowViewport = f.unobscuredWindow()
                var found: Pair<String, Int>? = null
                f.instrumentation.runOnMainSync {
                    // LazyLayout reuses native children in traversal order;
                    // that order is unrelated to the reader's visual position.
                    // Exclude text covered by either bar, then anchor the
                    // uppermost complete paragraph in the actual native list.
                    found = f.paragraphs().mapNotNull { view ->
                        val bounds = android.graphics.Rect()
                        val visible = view.getGlobalVisibleRect(bounds) && if (allowPartial)
                            android.graphics.Rect.intersects(listViewport, bounds) && android.graphics.Rect.intersects(windowViewport, bounds)
                        else f.fullyVisible(view) && listViewport.contains(bounds) && windowViewport.contains(bounds)
                        if (view.displayedOriginal.startsWith("Earlier local Bot message") &&
                            (original == null || view.displayedOriginal == original) && visible) {
                            val location = IntArray(2); view.getLocationOnScreen(location)
                            view.displayedOriginal to location[1]
                        } else null
                    }.minByOrNull { it.second }
                }
                return found
            }
            try {
                f.launch(); waitScreen(f, Screen.HOME); openBot(f)
                compose.onNodeWithTag("bot-message-input").performTouchInput { click() }
                compose.waitUntil(8_000) { imeVisible(f) }
                compose.onNodeWithTag("bot-message-input").performTextInput("A new local prompt while keeping older history.")
                compose.waitUntil(8_000) { f.model.bot?.allowance != null && f.model.subscriptions?.accessCheckState == AccessCheckState.LOADED }
                compose.onNodeWithTag("bot-message-send").assertIsEnabled().performTouchInput { click() }
                compose.waitUntil(5_000) { services.botPosts.get() == 1 && f.model.bot?.busy == true }
                f.device.pressBack(); compose.waitUntil(5_000) { !imeVisible(f) }
                repeat(3) {
                    compose.onNode(hasScrollToIndexAction()).performTouchInput { swipeDown(startY = height * .25f, endY = height * .8f) }
                }
                compose.waitForIdle()
                val anchor = requireNotNull(paragraphPosition()) { "A real older native paragraph must be fully visible after scrolling" }
                assertNotEquals("Earlier local Bot message 29.", anchor.first)
                f.capture("01-older-history-anchor-before-pending-reply")
                services.botReplyGate.complete(Unit)
                compose.waitUntil(8_000) { f.model.bot?.busy == false && f.model.bot?.messages?.lastOrNull()?.text == services.botReply }
                compose.waitForIdle()
                val afterReply = requireNotNull(paragraphPosition(anchor.first)) { "Incoming reply must preserve the older native paragraph" }
                assertEquals("Incoming reply moved the older reading anchor", anchor.second.toDouble(), afterReply.second.toDouble(), 2.0)
                val upperFragment = requireNotNull(paragraphPosition(allowPartial = true))
                compose.onNodeWithTag("bot-message-input").performTouchInput { click() }
                compose.waitUntil(8_000) { imeVisible(f) }
                compose.onNodeWithTag("bot-message-input").performTextInput("Keep reading this older passage.")
                compose.onNodeWithTag("bot-message-input").assertEditorValue("Keep reading this older passage.")
                compose.waitForIdle()
                // At 320 dp with enlarged type the remaining timeline can be
                // shorter than one paragraph. Keep the actual upper visible
                // fragment in place, then restore the full paragraph on hide.
                val afterIme = requireNotNull(paragraphPosition(upperFragment.first, allowPartial = true)) { "Opening IME must preserve the visible older reading fragment" }
                assertEquals("IME resize moved the visible reading fragment", upperFragment.second.toDouble(), afterIme.second.toDouble(), 2.0)
                assertNativeContained(f, By.text("Keep reading this older passage."), "older-history editor above IME", 48)
                assertEquals(1, services.botPosts.get())
                f.capture("02-older-anchor-after-reply-and-native-ime")
                f.device.pressBack(); compose.waitUntil(5_000) { !imeVisible(f) }; compose.waitForIdle()
                val restored = requireNotNull(paragraphPosition(anchor.first)) { "Hiding IME must restore the complete older paragraph" }
                assertEquals("Hiding IME moved the full older reading anchor", anchor.second.toDouble(), restored.second.toDouble(), 2.0)
                // The reader's explicit new Send is a fresh intent to follow
                // the latest exchange, even though an incoming reply was not.
                compose.onNodeWithTag("bot-message-send").assertIsEnabled().performTouchInput { click() }
                compose.waitUntil(8_000) { services.botPosts.get() == 2 && f.model.bot?.busy == false &&
                    f.model.bot?.messages?.lastOrNull()?.text == services.botFollowupReply }
                compose.onNodeWithTag("bot-message-input").assertEmptyEditor()
                val nextDraft = "A local draft after returning to the newest reply."
                compose.onNodeWithTag("bot-message-input").performTouchInput { click() }
                compose.waitUntil(8_000) { imeVisible(f) }
                compose.onNodeWithTag("bot-message-input").performTextInput(nextDraft)
                compose.onNodeWithTag("bot-message-input").assertEditorValue(nextDraft)
                assertReplyAudioAboveComposer(f, services.botFollowupReply, nextDraft)
                assertEquals(listOf("A new local prompt while keeping older history.", "Keep reading this older passage."), services.botRequestPrompts)
                assertEquals(2, services.botPosts.get())
                f.capture("03-own-send-returned-to-latest-with-audio-action")
                File(f.output, "result.json").writeText(JSONObject().put("pass", true).put("one_post_before_explicit_followup", true)
                    .put("older_anchor", anchor.first).put("anchor_y", anchor.second)
                    .put("incoming_preserved_complete_paragraph", true).put("ime_preserved_visible_fragment", upperFragment.first)
                    .put("ime_hide_restored_complete_paragraph", true).put("own_send_resumed_following_latest", true)
                    .put("one_post_per_explicit_send", true).put("total_posts", 2).put("provider_claimed", false).toString(2))
            } catch (failure: Throwable) {
                runCatching { f.capture("failure-before-cleanup") }.onFailure { failure.addSuppressed(it) }
                throw failure
            } finally { services.botReplyGate.complete(Unit); f.stopActivity(); services.close() }
        }
    }

    @Test fun shortLandscapeBotKeepsFullNativeLineCaretBackAndSendAboveImeAndDraftSurvives() {
        val services = JourneyServices(profileRequired = false, expectedBotPosts = 0)
        MainActivityJourneyFixture("bot-short-landscape", services::model).use { f ->
            try {
                f.launch(); waitScreen(f, Screen.HOME); openBot(f)
                compose.onNodeWithTag("bot-consent-choice").performScrollTo().performTouchInput { click() }
                compose.onNodeWithTag("bot-consent-continue").performScrollTo().performTouchInput { click() }
                compose.waitUntil(8_000) { f.model.bot?.allowance != null && f.model.subscriptions?.accessCheckState == AccessCheckState.LOADED }
                compose.onNodeWithTag("bot-message-input").performTouchInput { click() }
                compose.waitUntil(8_000) { imeVisible(f) }
                // Native keyboard events enter the actual focused editor;
                // layout/caret checks inspect its real pixels with the IME open.
                assertTrue(f.device.pressKeyCode(android.view.KeyEvent.KEYCODE_H))
                assertTrue(f.device.pressKeyCode(android.view.KeyEvent.KEYCODE_I))
                compose.waitUntil(5_000) { f.model.bot?.draft == "hi" }
                exerciseShortLandscapeComposer(compose, f, "bot-message-input", "bot-message-send", "hi", "bot-short-landscape")
                compose.onNodeWithTag("bot-message-send").assertIsEnabled()
                compose.runOnIdle { assertEquals(0, services.botPosts.get()); assertEquals(0, services.friendPosts.get()) }
                f.device.pressBack(); compose.waitUntil(5_000) { !imeVisible(f) }
                f.device.pressBack(); waitScreen(f, Screen.HOME); openBot(f)
                compose.onNodeWithTag("bot-message-input").assertEditorValue("hi")
                compose.runOnIdle {
                    BotSession(f.isolated, services.account, services.transport(f.model.authentication, services.subject)).use { reopened -> assertEquals("hi", reopened.draft) }
                }
                services.assertNoPurchase()
                File(f.output, "result.json").writeText(JSONObject().put("pass", true).put("native_landscape", "1920x1080@420dpi")
                    .put("posts", 0).put("full_rendered_caret_and_visual_line", true).put("draft_durable_after_restore", true).toString(2))
            } catch (failure: Throwable) {
                runCatching { f.capture("failure-before-cleanup") }.onFailure { failure.addSuppressed(it) }
                throw failure
            } finally { f.stopActivity(); services.close() }
        }
    }

    @Test fun multilineBotDraftKeepsNativeEndCaretVisibleAfterAppendAndBackReopenWithoutSending() =
        multilineDraftJourney(withHistory = false)

    @Test fun multilineBotDraftAfterConfirmedExchangeKeepsNativeEndCaretAndSavedHistoryAfterReopen() =
        multilineDraftJourney(withHistory = true)

    private fun multilineDraftJourney(withHistory: Boolean) {
        val services = JourneyServices(profileRequired = false)
        val expectedPosts = if (withHistory) 1 else 0
        val setupPrompt = "A local setup exchange before editing the next message."
        MainActivityJourneyFixture(if (withHistory) "bot-multiline-caret-with-history" else "bot-multiline-caret", services::model).use { f ->
            var proofNumber = 0
            var appendNumber = 0
            fun nativeEditor(expected: String): android.view.accessibility.AccessibilityNodeInfo? {
                fun editorIn(node: android.view.accessibility.AccessibilityNodeInfo): android.view.accessibility.AccessibilityNodeInfo? {
                    if (node.isEditable && node.isFocused && node.text?.toString() == expected) return node
                    for (index in 0 until node.childCount) node.getChild(index)?.let { child ->
                        editorIn(child)?.let { return it }
                    }
                    return null
                }
                if (android.os.Build.VERSION.SDK_INT >= 33) f.instrumentation.uiAutomation.clearCache()
                return f.instrumentation.uiAutomation.windows.mapNotNull { it.root }
                    .filter { it.packageName?.toString() == f.base.packageName }.firstNotNullOfOrNull(::editorIn)
            }
            fun appendAtNativeEnd(before: String, suffix: String) {
                compose.onNodeWithTag("bot-message-input").assertEditorValue(before).assertIsFocused()
                // A focus tap can still generate IME selection events after
                // Compose is idle. Settle that native event stream first.
                f.instrumentation.uiAutomation.waitForIdle(100, 5_000)
                compose.waitForIdle()
                var observed: android.view.accessibility.AccessibilityNodeInfo? = null
                compose.waitUntil(5_000) { observed = nativeEditor(before); observed != null }
                val editor = requireNotNull(observed)
                val alreadyAtEnd = editor.textSelectionStart == before.length && editor.textSelectionEnd == before.length
                val receipt = File(f.output, "append-selection-proof-${++appendNumber}.json")
                val attempt = JSONObject().put("action", if (alreadyAtEnd) "already_at_native_document_end" else "native_accessibility_ACTION_SET_SELECTION")
                    .put("expected_end", before.length).put("native_start_before", editor.textSelectionStart)
                    .put("native_end_before", editor.textSelectionEnd).put("native_accessibility_idle_ms", 100)
                    .put("started_uptime_ms", android.os.SystemClock.uptimeMillis())
                val args = android.os.Bundle().apply {
                    putInt(android.view.accessibility.AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, before.length)
                    putInt(android.view.accessibility.AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, before.length)
                }
                val dispatchResult = if (alreadyAtEnd) null else
                    editor.performAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_SET_SELECTION, args)
                attempt.put("dispatch_result", dispatchResult ?: JSONObject.NULL)
                receipt.writeText(attempt.toString(2))
                try {
                    compose.waitUntil(5_000) {
                        observed = nativeEditor(before)
                        observed?.let { it.textSelectionStart == before.length && it.textSelectionEnd == before.length } == true
                    }
                } catch (failure: ComposeTimeoutException) {
                    attempt.put("observed_native_start", observed?.textSelectionStart ?: -1)
                        .put("observed_native_end", observed?.textSelectionEnd ?: -1).put("selection_observed", false)
                    receipt.writeText(attempt.toString(2))
                    throw AssertionError("Native end-selection did not settle: $attempt", failure)
                }
                receipt.writeText(attempt.put("observed_native_start", before.length).put("observed_native_end", before.length)
                    .put("selection_observed", true).put("typing", "Instrumentation.sendStringSync key events").toString(2))
                f.instrumentation.sendStringSync(suffix)
            }
            fun assertNativeEndLine(expected: String) {
                compose.onNodeWithTag("bot-message-input").assertEditorValue(expected).assertIsFocused()
                val layouts = mutableListOf<androidx.compose.ui.text.TextLayoutResult>()
                compose.onNodeWithTag("bot-message-input").performSemanticsAction(androidx.compose.ui.semantics.SemanticsActions.GetTextLayoutResult) {
                    assertTrue(it(layouts))
                }
                val layout = layouts.single { it.layoutInput.text.text == expected }
                val visualLine = layout.getLineForOffset(expected.length)
                val start = layout.getLineStart(visualLine)
                val end = layout.getLineEnd(visualLine, visibleEnd = true)
                val cursor = layout.getCursorRect(expected.length)
                require(end > start && cursor.height > 0)
                proofNumber++
                var diagnostic = "No focused native editor"
                var nativeExtraDiagnostic: JSONObject? = null
                try {
                    compose.waitUntil(5_000) {
                        val editor = nativeEditor(expected)
                        if (editor?.isEditable != true || editor.text?.toString() != expected ||
                            editor.textSelectionStart != expected.length || editor.textSelectionEnd != expected.length) {
                            diagnostic = "Native editable descendant selection ${editor?.textSelectionStart}..${editor?.textSelectionEnd}, class=${editor?.className}, extras=${editor?.availableExtraData}"
                            false
                        } else {
                            if (nativeExtraDiagnostic == null) {
                                val key = android.view.accessibility.AccessibilityNodeInfo.EXTRA_DATA_TEXT_CHARACTER_LOCATION_KEY
                                val args = android.os.Bundle().apply {
                                    putInt(android.view.accessibility.AccessibilityNodeInfo.EXTRA_DATA_TEXT_CHARACTER_LOCATION_ARG_START_INDEX, start)
                                    putInt(android.view.accessibility.AccessibilityNodeInfo.EXTRA_DATA_TEXT_CHARACTER_LOCATION_ARG_LENGTH, end - start)
                                }
                                val refreshed = editor.refreshWithExtraData(key, args)
                                @Suppress("DEPRECATION") val raw = editor.extras.getParcelableArray(key)
                                nativeExtraDiagnostic = JSONObject().put("available_keys", JSONArray(editor.availableExtraData))
                                    .put("refresh_succeeded", refreshed).put("raw_count", raw?.size ?: 0)
                                    .put("nonnull_count", raw?.count { it != null } ?: 0)
                            }
                            val bounds = android.graphics.Rect(); editor.getBoundsInScreen(bounds)
                            val viewport = android.graphics.RectF(f.unobscuredWindow())
                            val field = android.graphics.RectF(bounds)
                            val bitmap = f.instrumentation.uiAutomation.takeScreenshot()
                            if (bitmap == null) false else try {
                                val pixels = IntArray(bounds.width() * bounds.height())
                                bitmap.getPixels(pixels, 0, bounds.width(), bounds.left, bounds.top, bounds.width(), bounds.height())
                                fun pixel(x: Int, y: Int) = pixels[(y - bounds.top) * bounds.width() + x - bounds.left] and 0xFFFFFF
                                val colors = mutableMapOf<Int, Int>()
                                for (y in bounds.centerY() - 10 until bounds.centerY() + 10) for (x in bounds.left until bounds.left + 12) {
                                    val color = pixel(x, y); val r = color ushr 16; val g = (color ushr 8) and 255; val b = color and 255
                                    if (g - r >= 12 && g - b >= 12) colors[color] = (colors[color] ?: 0) + 1
                                }
                                val ink = colors.maxByOrNull { it.value }?.key
                                val runs = mutableListOf<android.graphics.Rect>()
                                if (ink != null) {
                                    fun matches(color: Int) = kotlin.math.abs((color ushr 16) - (ink ushr 16)) <= 4 &&
                                        kotlin.math.abs(((color ushr 8) and 255) - ((ink ushr 8) and 255)) <= 4 &&
                                        kotlin.math.abs((color and 255) - (ink and 255)) <= 4
                                    val margin = (12 * f.base.resources.displayMetrics.density).toInt()
                                    for (x in bounds.left + margin until bounds.right - margin) {
                                        var y = bounds.top + 4
                                        while (y < bounds.bottom - 4) {
                                            if (!matches(pixel(x, y))) { y++; continue }
                                            val top = y
                                            while (y < bounds.bottom - 4 && matches(pixel(x, y))) y++
                                            if (kotlin.math.abs((y - top) - cursor.height) <= 4f) runs += android.graphics.Rect(x, top, x + 1, y)
                                        }
                                    }
                                }
                                val groups = mutableListOf<android.graphics.Rect>()
                                runs.forEach { run ->
                                    val group = groups.lastOrNull()
                                    if (group != null && run.left == group.right && kotlin.math.abs(run.top - group.top) <= 2 && kotlin.math.abs(run.bottom - group.bottom) <= 2)
                                        group.union(run) else groups += android.graphics.Rect(run)
                                }
                                val carets = groups.filter { it.width() <= 4 * f.base.resources.displayMetrics.density }
                                diagnostic = "Rendered caret candidates=$carets, layout cursor=$cursor, field=$field, viewport=$viewport, native=$nativeExtraDiagnostic"
                                if (carets.size != 1) false else {
                                    val rendered = android.graphics.RectF(carets.single())
                                    val dx = rendered.centerX() - cursor.center.x
                                    val dy = rendered.top - cursor.top
                                    val boxes = (start until end).map { offset ->
                                        val box = layout.getBoundingBox(offset)
                                        android.graphics.RectF(box.left + dx, box.top + dy, box.right + dx, box.bottom + dy)
                                    }
                                    val visible = viewport.contains(rendered) && field.contains(rendered) && dy < field.top &&
                                        boxes.all { !it.isEmpty && viewport.contains(it) && field.contains(it) }
                                    if (visible) {
                                        File(f.output, "caret-proof-$proofNumber.png").outputStream().use { bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }
                                        File(f.output, "caret-proof-$proofNumber.json").writeText(JSONObject()
                                            .put("method", "production_text_layout_translated_by_measured_native_rendered_caret")
                                            .put("native_end_selection", editor.textSelectionEnd).put("native_character_api_diagnostic", nativeExtraDiagnostic)
                                            .put("visual_line", expected.substring(start, end)).put("visual_line_offsets", "$start..$end")
                                            .put("layout_cursor", cursor.toString()).put("rendered_caret", rendered.toString())
                                            .put("translation_x", dx.toDouble()).put("translation_y", dy.toDouble())
                                            .put("editor", field.toString()).put("unobscured_window", viewport.toString())
                                            .put("projected_glyph_boxes", JSONArray(boxes.map { it.toString() }))
                                            .put("native_glyph_api_proof_claimed", false).toString(2))
                                    }
                                    visible
                                }
                            } finally { bitmap.recycle() }
                        }
                    }
                } catch (failure: ComposeTimeoutException) { throw AssertionError(diagnostic, failure) }
            }
            try {
                f.launch(); waitScreen(f, Screen.HOME); openBot(f)
                if (withHistory) {
                    compose.onNodeWithTag("bot-consent-choice").performScrollTo().performTouchInput { click() }
                    compose.onNodeWithTag("bot-consent-continue").performScrollTo().performTouchInput { click() }
                    compose.onNodeWithTag("bot-message-input").performTouchInput { click() }
                    compose.waitUntil(8_000) { imeVisible(f) }
                    compose.onNodeWithTag("bot-message-input").performTextInput(setupPrompt)
                    compose.waitUntil(8_000) { f.model.bot?.allowance != null && f.model.subscriptions?.accessCheckState == AccessCheckState.LOADED }
                    compose.onNodeWithTag("bot-message-send").assertIsEnabled().performTouchInput { click() }
                    compose.waitUntil(5_000) { services.botPosts.get() == 1 && f.model.bot?.busy == true }
                    services.botReplyGate.complete(Unit)
                    compose.waitUntil(8_000) { f.model.bot?.busy == false && f.model.bot?.messages?.size == 2 }
                    compose.onNodeWithTag("bot-message-input").assertEmptyEditor()
                    compose.runOnIdle {
                        assertEquals(listOf(setupPrompt, services.botReply), f.model.bot?.messages?.map { it.text })
                        assertTrue(f.model.bot!!.messages.all { it.status == "confirmed" })
                    }
                }
                compose.onNodeWithTag("bot-message-input").performTouchInput { click() }
                compose.waitUntil(8_000) { imeVisible(f) }
                val original = (1..6).joinToString("\n") { "Local draft line $it." }
                compose.onNodeWithTag("bot-message-input").performTextInput(original)
                val first = original + "\nFinal native line."
                appendAtNativeEnd(original, "\nFinal native line.")
                assertNativeEndLine(first)
                if (!withHistory) compose.onNodeWithTag("bot-message-send").assertIsNotEnabled()
                assertEquals(first, f.model.bot?.draft); assertEquals(expectedPosts, services.botPosts.get())
                f.capture("01-multiline-native-end-caret-above-ime")
                f.device.pressBack(); compose.waitUntil(5_000) { !imeVisible(f) }
                f.device.pressBack(); waitScreen(f, Screen.HOME); openBot(f)
                compose.onNodeWithTag("bot-message-input").assertEditorValue(first).performTouchInput { click() }
                compose.waitUntil(8_000) { imeVisible(f) }
                val restored = first + "\nReopened end line."
                appendAtNativeEnd(first, "\nReopened end line.")
                assertNativeEndLine(restored)
                compose.runOnIdle {
                    assertEquals(restored, f.model.bot?.draft); assertEquals(expectedPosts, services.botPosts.get())
                    BotSession(f.isolated, services.account, services.transport(f.model.authentication, services.subject)).use { reopened ->
                        assertEquals(restored, reopened.draft)
                        assertEquals(if (withHistory) listOf(setupPrompt, services.botReply) else emptyList<String>(), reopened.messages.map { it.text })
                        assertTrue(reopened.messages.all { it.status == "confirmed" })
                    }
                }
                f.capture("02-restored-multiline-native-end-caret-above-ime")
                services.assertNoPurchase()
                File(f.output, "result.json").writeText(JSONObject().put("pass", true).put("posts", expectedPosts)
                    .put("setup_confirmed_exchange", withHistory).put("draft_posts", 0)
                    .put("native_accessibility_end_selection_before_key_event_append", true).put("final_visual_line_layout_and_rendered_caret_inside_editor_above_ime", true)
                    .put("native_glyph_api_proof_claimed", false)
                    .put("full_draft_retained_after_back_and_reopen", true).put("durable_draft_read", true).toString(2))
            } catch (failure: Throwable) {
                runCatching { f.capture("failure-before-cleanup") }.onFailure { failure.addSuppressed(it) }
                throw failure
            } finally { f.stopActivity(); services.close() }
        }
    }

    private fun SemanticsNodeInteraction.assertEmptyEditor(): SemanticsNodeInteraction =
        assertEditorValue("")

    private fun SemanticsNodeInteraction.assertEditorValue(expected: String): SemanticsNodeInteraction =
        assert(SemanticsMatcher("EditableText plain text exactly equals the expected draft") { node ->
            node.config.contains(SemanticsProperties.EditableText) && node.config[SemanticsProperties.EditableText].text == expected
        })

    private fun assertReplyAudioAboveComposer(f: MainActivityJourneyFixture, reply: String, draft: String) {
        compose.waitForIdle()
        var audioBounds: android.graphics.Rect? = null
        var composerBounds: android.graphics.Rect? = null
        try {
            compose.waitUntil(8_000) {
                if (android.os.Build.VERSION.SDK_INT >= 33) f.instrumentation.uiAutomation.clearCache()
                val paragraph = f.device.findObject(By.text(reply).pkg(f.base.packageName))
                val audio = paragraph?.let { text ->
                    generateSequence(text.parent) { it.parent }.take(4)
                        .mapNotNull { it.findObject(By.clickable(true)) }.firstOrNull()
                }
                audioBounds = audio?.visibleBounds
                composerBounds = f.device.findObject(By.text(draft).pkg(f.base.packageName))?.visibleBounds
                val viewport = f.unobscuredWindow()
                val minimum = 48 * f.base.resources.displayMetrics.density
                val control = audioBounds
                val editor = composerBounds
                control != null && editor != null && !control.isEmpty && viewport.contains(control) &&
                    control.height() >= minimum && control.bottom <= editor.top
            }
        } catch (failure: ComposeTimeoutException) {
            throw AssertionError("Latest reply audio control $audioBounds must be fully above composer $composerBounds and native IME", failure)
        }
    }

    /** Accessibility bounds alone may extend behind a separate IME window.
     * Compare the actual native node with the window minus system/IME insets,
     * and reject a partially clipped topbar icon/title as well. */
    private fun assertNativeContained(f: MainActivityJourneyFixture, selector: BySelector, name: String, minimumHeightDp: Int = 0) {
        compose.waitForIdle()
        val appSelector = selector.pkg(f.base.packageName)
        var bounds: android.graphics.Rect? = null
        var viewport = f.unobscuredWindow()
        try {
            compose.waitUntil(5_000) {
                // Compose editing and IME layout settle before the independent
                // accessibility tree necessarily receives its latest snapshot.
                if (android.os.Build.VERSION.SDK_INT >= 33) f.instrumentation.uiAutomation.clearCache()
                viewport = f.unobscuredWindow()
                bounds = f.device.findObject(appSelector)?.visibleBounds
                bounds?.let { actual -> !actual.isEmpty && viewport.contains(actual) &&
                    actual.height() >= minimumHeightDp * f.base.resources.displayMetrics.density } == true
            }
        } catch (failure: ComposeTimeoutException) {
            throw AssertionError("$name native bounds $bounds must be fully within unobscured window $viewport with height >= $minimumHeightDp dp", failure)
        }
    }

    private fun openBot(f: MainActivityJourneyFixture) {
        compose.onNodeWithText(f.base.getString(R.string.ui_f173182378d0)).performScrollTo().performTouchInput { click() }
        waitScreen(f, Screen.BOT)
        compose.onNodeWithTag("bot-message-input").assertIsDisplayed()
    }
    private fun waitScreen(f: MainActivityJourneyFixture, screen: Screen) = compose.waitUntil(10_000) { f.model.screen == screen }
    private fun imeVisible(f: MainActivityJourneyFixture): Boolean {
        var shown = false
        f.instrumentation.runOnMainSync {
            shown = android.view.inspector.WindowInspector.getGlobalWindowViews().any { view ->
                view.rootWindowInsets?.let { WindowInsetsCompat.toWindowInsetsCompat(it).isVisible(WindowInsetsCompat.Type.ime()) } == true
            }
        }
        return shown
    }
}

/** External relay/service boundary; real account, Signal, history, Bot and
 * subscription coordinators still execute. Every unlisted request is rejected. */
private class JourneyServices(profileRequired: Boolean, private val seedBotMessages: Int = 0,
    private val expectedBotPosts: Int = 1) : VipiWorkflowBoundary, AutoCloseable {
    val account = UUID.randomUUID()
    val peer = UUID.randomUUID()
    val subject = "user_journey_${UUID.randomUUID().toString().replace("-", "")}"
    val profileWrites = AtomicInteger()
    val deviceRegistrations = AtomicInteger()
    val friendPosts = AtomicInteger()
    val friendReplyReceipts = AtomicInteger()
    val inboxWakeups = AtomicInteger()
    val friendReply = "Thanks for your message — café ☕."
    var friendReplyId: UUID? = null
        private set
    var outgoingFriendId: UUID? = null
        private set
    private var pendingPeerReply: JSONObject? = null
    val botPosts = AtomicInteger()
    val failNextEntitlement = AtomicBoolean(false)
    val failBotReply = AtomicBoolean(false)
    val botReplyGate = CompletableDeferred<Unit>()
    val botReply = "The local lifecycle reply arrived."
    val botFollowupReply = "The new local reply is now fully reachable."
    val botRequestPrompts = mutableListOf<String>()
    val lookups = mutableListOf<String>()
    var peerReceived: String? = null
    private var created = !profileRequired
    private var remaining = 150
    private var registered: DeviceCredential? = null
    private var peerVault: MessageVault? = null
    private var peerCore: MessagingCore? = null
    private var peerPublication: JSONObject? = null
    private val catalogs = mutableListOf<WorkflowBillingClient>()
    private val sockets = mutableListOf<JourneySocket>()
    fun model(application: Application): VipiModel {
        PrivateRecords(application).write("session", IdentityAuthority.FALLSOFT_VIPI_PRODUCTION.tag(JSONObject()
            .put("userID", subject).put("accessToken", "synthetic-inert-access").put("refreshToken", "synthetic-inert-refresh")))
        if (seedBotMessages > 0) MessageVault(application, account).use { history ->
            history.transaction {
                history.put("bot-settings", "consent", "deepseek-v1".toByteArray())
                val start = System.currentTimeMillis() - 60_000
                repeat(seedBotMessages) { index ->
                    val message = BotMessage("m%019d-seeded-%03d".format(java.util.Locale.ROOT, start + index, index),
                        if (index % 2 == 0) "user" else "assistant", "Earlier local Bot message $index.", "confirmed", null)
                    history.put("bot-message", message.id, message.json().toString().toByteArray())
                }
            }
        }
        val vault = MessageVault(application, peer)
        peerVault = vault
        peerCore = MessagingCore(vault)
        peerPublication = requireNotNull(peerCore).keys.publication(System.currentTimeMillis(), 2)
        requireNotNull(peerCore).keys.published(1)
        return VipiModel(application, NoJourneyModelTranslation, this)
    }
    override fun transport(authentication: Authentication, userID: String): ChatTransport {
        check(userID == subject)
        return object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject {
                return when {
                    method == "GET" && path == "/v1/me" -> {
                        if (!created) throw ServiceFailure(404, "profile_required")
                        ChatProfile(account, "journey_tester", "Journey Tester").json()
                    }
                    method == "PUT" && path == "/v1/me" -> {
                        val fields = requireNotNull(body)
                        check(!created && fields.getString("username") == "journey_tester")
                        check(fields.getString("display_name") == "Journey Tester")
                        created = true; profileWrites.incrementAndGet()
                        ChatProfile(account, "journey_tester", "Journey Tester").json()
                    }
                    method == "POST" && path == "/v1/devices" -> {
                        check(deviceRegistrations.incrementAndGet() == 1)
                        check(body?.optBoolean("replace_active") != true)
                        val fields = requireNotNull(body)
                        registered = DeviceCredential(UUID.fromString(fields.getString("device_id")), fields.getString("secret"))
                        JSONObject().put("id", registered!!.id).put("active", true)
                    }
                    method == "GET" && path == "/v1/keys" -> JSONObject().put("revision", 1).put("remaining", 20)
                    method == "GET" && path == "/v1/messages/pending" -> {
                        check(device == registered)
                        JSONObject().put("messages", JSONArray().apply { pendingPeerReply?.let { put(JSONObject(it.toString())) } })
                            .put("next_cursor", JSONObject.NULL)
                    }
                    method == "POST" && friendReplyId != null && path == "/v1/messages/$friendReplyId/receipt" -> {
                        check(device == registered && pendingPeerReply != null)
                        check(friendReplyReceipts.incrementAndGet() == 1)
                        pendingPeerReply = null
                        JSONObject().put("state", "delivered")
                    }
                    method == "GET" && path.startsWith("/v1/blocks/") -> JSONObject().put("blocked", false)
                    method == "GET" && path.startsWith("/v1/people/") -> {
                        val name = path.substringAfterLast('/')
                        lookups += name
                        if (name == "missing_friend") throw ServiceFailure(404, "person_not_found")
                        check(name == "journey_friend")
                        ChatProfile(peer, "journey_friend", "Journey Friend").json()
                    }
                    method == "POST" && path == "/v1/people/$peer/keys" -> {
                        val publication = requireNotNull(peerPublication)
                        JSONObject().put("request_id", requireNotNull(body).getString("request_id"))
                            .put("user_id", peer).put("device_id", requireNotNull(peerCore).device.id).put("signal_device_id", 1)
                            .put("registration_id", publication.getInt("registration_id")).put("identity_key", publication.getString("identity_key"))
                            .put("signed", publication.getJSONObject("signed")).put("one_time", publication.getJSONArray("one_time").getJSONObject(0))
                    }
                    method == "POST" && path == "/v1/messages" -> {
                        check(device == registered && friendPosts.incrementAndGet() == 1)
                        val encrypted = JSONObject(requireNotNull(body).toString())
                        check(!encrypted.toString().contains("I am reading a book now."))
                        outgoingFriendId = UUID.fromString(encrypted.getString("id"))
                        encrypted.put("sender_id", account).put("sender_device_id", requireNotNull(registered).id)
                        peerReceived = requireNotNull(peerCore).receive(RoutedMessage.received(encrypted, peer), System.currentTimeMillis()).text
                        JSONObject().put("state", "delivered")
                    }
                    method == "GET" && path == "/v1/entitlements" -> {
                        if (failNextEntitlement.getAndSet(false)) throw java.io.IOException("Synthetic entitlement unavailable")
                        fun plan() = JSONObject().put("active", true).put("expires_at", JSONObject.NULL).put("trial_ends_at", JSONObject.NULL)
                            .put("review_access", true).put("access_source", "review_complimentary")
                        JSONObject().put("base", plan()).put("bot_mini", plan().put("available", true))
                            .put("billing_account_id", "c".repeat(64)).put("server_time", Instant.now().toString())
                    }
                    method == "GET" && path == "/v1/bot/allowance" -> allowance()
                    method == "POST" && path == "/v1/bot/messages" -> {
                        check(device == registered)
                        val post = botPosts.incrementAndGet()
                        check(post <= expectedBotPosts)
                        val sent = requireNotNull(body)
                        check(sent.getString("consent_version") == "deepseek-v1")
                        check(sent.getJSONArray("messages").length() == if (seedBotMessages == 0) 1 else 11)
                        val context = sent.getJSONArray("messages")
                        botRequestPrompts += context.getJSONObject(context.length() - 1).getString("content")
                        botReplyGate.await()
                        if (failBotReply.get()) throw java.io.IOException("Synthetic uncertain provider outcome")
                        remaining = 150 - post
                        JSONObject().put("request_id", sent.getString("request_id")).put("reply", if (post == 1) botReply else botFollowupReply).put("allowance", allowance())
                    }
                    else -> error("Unexpected journey service boundary request: $method $path")
                }
            }
        }
    }
    fun queuePeerReplyAndSignalInbox() {
        check(android.os.Looper.myLooper() == android.os.Looper.getMainLooper())
        check(friendPosts.get() == 1 && peerReceived != null && friendReplyId == null)
        val socket = requireNotNull(sockets.lastOrNull { it.active }) { "The actual foreground inbox event connection must be open" }
        val core = requireNotNull(peerCore)
        val id = UUID.randomUUID(); val now = System.currentTimeMillis()
        val encrypted = core.queue(id, account, friendReply, now, now)
        check(encrypted.recipientDevice == requireNotNull(registered).id)
        val wire = encrypted.sendJSON().put("sender_id", peer).put("sender_device_id", core.device.id)
        check(!wire.toString().contains(friendReply))
        friendReplyId = id; pendingPeerReply = wire
        check(inboxWakeups.incrementAndGet() == 1)
        socket.inboxChanged()
    }
    private fun allowance() = JSONObject().put("available", true).put("service_ready", true)
        .put("remaining_replies", remaining).put("monthly_replies", 150).put("period", "2098-12")
        .put("resets_at", "2099-01-01T00:00:00Z").put("max_context_bytes", 8192)
    override fun requestPush(context: Context, registration: Boolean) = Unit
    override fun cancelPush(context: Context) = Unit
    override fun billingClient(context: Context, listener: PurchasesUpdatedListener): BillingClient = WorkflowBillingClient(listener).also { catalogs += it }
    override fun foregroundEvents(scope: CoroutineScope, authentication: Authentication, chat: ChatSession): ForegroundInboxEvents =
        ForegroundInboxEvents(scope, { "synthetic-inert-access" }, chat::eventDevice, { chat.synchronize() },
            sockets = WebSocket.Factory { request, listener -> JourneySocket(request, listener).also { sockets += it; it.open() } })
    fun assertNoPurchase() { assertTrue(catalogs.isNotEmpty()); assertTrue(catalogs.all { it.launches == 0 }) }
    override fun close() {
        sockets.forEach { it.cancel() }
        peerVault?.close()
        // These are isolated random fixture accounts, never a retained reviewer account.
        KeyStore.getInstance("AndroidKeyStore").apply {
            load(null); deleteEntry("co.fallsoft.vipi.messages.$account"); deleteEntry("co.fallsoft.vipi.messages.$peer")
        }
    }
    private class JourneySocket(private val request: Request, private val listener: WebSocketListener) : WebSocket {
        var active = true
            private set
        override fun request() = request
        override fun queueSize() = 0L
        override fun send(text: String) = error("No application content may use the fake event socket")
        override fun send(bytes: ByteString) = error("No application content may use the fake event socket")
        override fun close(code: Int, reason: String?): Boolean { active = false; return true }
        override fun cancel() { active = false }
        fun inboxChanged() { check(active); listener.onMessage(this, "{\"event\":\"inbox_changed\"}") }
        fun open() = listener.onOpen(this, Response.Builder().request(request).protocol(Protocol.HTTP_1_1).code(101).message("Switching Protocols").build())
    }
}
