package co.fallsoft.vipi

import android.app.Activity
import android.app.Application
import android.app.Instrumentation
import android.content.Context
import android.content.Intent
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.text.AnnotatedString
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
                f.backgroundAndResume()
                waitScreen(f, Screen.CONVERSATION)
                compose.onNodeWithTag("message-input").assertTextEquals("Keep this local friend draft.")
                f.recreate()
                waitScreen(f, Screen.CONVERSATION)
                compose.onNodeWithTag("message-input").assertTextEquals("Keep this local friend draft.")
                compose.runOnIdle {
                    MessageVault(f.isolated, services.account).use { vault ->
                        assertEquals("Keep this local friend draft.", ConversationHistory(vault).composeDraft(services.peer))
                    }
                }
                compose.onNodeWithTag("message-input").performTouchInput { click() }
                compose.waitUntil(8_000) { imeVisible(f) }
                f.capture("04-returned-friend-history-and-resumed-draft")
                compose.runOnIdle { assertEquals(1, services.friendPosts.get()); assertEquals(0, services.botPosts.get()) }
                services.assertNoPurchase()
                File(f.output, "result.json").writeText(JSONObject().put("pass", true).put("profile_writes", 1)
                    .put("share_payload_checked_external_share_blocked", true).put("native_ime", true)
                    .put("friend_encrypted_posts", 1).put("fake_peer_decrypted", true)
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

    private fun SemanticsNodeInteraction.assertEmptyEditor(): SemanticsNodeInteraction =
        assertEditorValue("")

    private fun SemanticsNodeInteraction.assertEditorValue(expected: String): SemanticsNodeInteraction =
        assert(SemanticsMatcher.expectValue(SemanticsProperties.EditableText, AnnotatedString(expected)))

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
                    method == "GET" && path == "/v1/messages/pending" -> JSONObject().put("messages", JSONArray()).put("next_cursor", JSONObject.NULL)
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
        override fun request() = request
        override fun queueSize() = 0L
        override fun send(text: String) = error("No application content may use the fake event socket")
        override fun send(bytes: ByteString) = error("No application content may use the fake event socket")
        override fun close(code: Int, reason: String?) = true
        override fun cancel() = Unit
        fun open() = listener.onOpen(this, Response.Builder().request(request).protocol(Protocol.HTTP_1_1).code(101).message("Switching Protocols").build())
    }
}
