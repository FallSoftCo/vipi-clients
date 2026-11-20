package co.fallsoft.vipi

import android.app.Activity
import android.view.WindowInsets
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.regex.Pattern

/** Real root/editor/Signal journal, supplied screenshot translations + controlled
 * network events. No live account, native translation or notification-delivery claim. */
class ChatPolishJourneyDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()
    private val originals = listOf("I found a quiet café nearby.", "That sounds lovely! Is it near the station?",
        "Yes, just a five-minute walk. ☕", "Perfect. Shall we meet at six?", "See you there — I will bring the book.")
    private val practices = listOf("我在附近找到了一家安静的咖啡馆。", "听起来很棒！离车站近吗？", "是的，走路只要五分钟。☕", "太好了。我们六点见面好吗？", "到时见，我会把书带来。")
    private fun services() = JourneyServices(profileRequired = false, expectedFriendPosts = 20,
        accountDisplayName = "Alex", peerDisplayName = "Maya", translationFactory = {
            object : LanguageTranslation {
                override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = Unit
                override suspend fun isReady(source: String, target: String) = true
                override suspend fun translate(text: String, source: String, target: String): String {
                    val index = originals.indexOf(text); check(index >= 0) { "Unrecorded controlled fixture source" }
                    return practices[index]
                }
                override fun close() = Unit
            }
        })
    private fun screen(f: MainActivityJourneyFixture, screen: Screen) = compose.waitUntil(15_000) { f.model.screen == screen }
    private fun open(f: MainActivityJourneyFixture, appearance: Appearance) {
        f.instrumentation.runOnMainSync { f.model.changeAppearance(appearance); f.model.selectTarget("zh"); f.model.selectImmersionMode(ImmersionMode.FULL_MESSAGES) }
        f.launch(); screen(f, Screen.HOME)
        compose.onNodeWithContentDescription(f.base.getString(R.string.nav_new_chat)).performClick(); screen(f, Screen.NEW_CHAT)
        compose.onNode(hasSetTextAction()).performScrollTo().performTextInput("journey_friend")
        compose.onNode(hasSetTextAction()).performImeAction(); screen(f, Screen.CONVERSATION)
        f.bindConversationCapture(compose, "message-input")
    }
    private fun ime(): Boolean {
        var result = false
        androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().runOnMainSync {
            val activity = ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).singleOrNull() as? Activity
            result = activity?.window?.decorView?.rootWindowInsets?.isVisible(WindowInsets.Type.ime()) == true
        }
        return result
    }
    private fun send(f: MainActivityJourneyFixture, text: String) {
        compose.onNodeWithTag("message-input").performTouchInput { click() }
        compose.onNodeWithTag("message-input").performTextInput(text)
        compose.onNodeWithTag("message-send").performClick()
        compose.waitUntil(15_000) { f.model.chat!!.messages(requireNotNull(peer)).any { it.text == text && it.outgoing && it.state in setOf("delivered", "read") } }
    }
    private var peer: UUID? = null
    private fun receive(f: MainActivityJourneyFixture, service: JourneyServices, text: String): UUID {
        var id: UUID? = null
        compose.runOnIdle { id = service.queueAdditionalPeerReplyAndSignalInbox(text) }
        compose.waitUntil(15_000) { f.model.chat!!.messages(service.peer).any { it.id == id } }
        compose.waitUntil(15_000) { f.model.chat!!.translations!!.state(requireNotNull(id).toString(), text)?.phase == MessageTranslationPhase.READY }
        compose.mainClock.advanceTimeBy(300); compose.waitForIdle()
        return requireNotNull(id)
    }
    @Test fun dayChatPreservesHistoryAndShowsActualTypingReadAndNewMessageJump() = review(Appearance.LIGHT)
    @Test fun nightChatPreservesHistoryAndShowsActualTypingReadAndNewMessageJump() = review(Appearance.DARK)
    private fun review(appearance: Appearance) {
        val service = services(); peer = service.peer
        MainActivityJourneyFixture("chat-polish-${appearance.name.lowercase()}", service::model).use { f ->
            try {
                open(f, appearance)
                compose.onNodeWithTag("conversation-immersion").assertIsDisplayed()
                f.capture("01-empty")
                compose.runOnIdle { service.peerTyping(true) }
                compose.waitUntil(5_000) { f.model.chat!!.isPeerTyping(service.peer) }
                compose.onNodeWithTag("conversation-typing").assertIsDisplayed(); f.capture("02-typing-empty")
                compose.runOnIdle { service.peerTyping(false) }
                compose.waitUntil(5_000) { !f.model.chat!!.isPeerTyping(service.peer) }
                send(f, originals[0])
                if (!PushDelivery.allowed(f.base)) {
                    compose.onNodeWithTag("reply-notification-card").assertIsDisplayed()
                    compose.onNodeWithTag("message-input").assertIsDisplayed()
                    f.capture("03-notification-invitation")
                    compose.onNodeWithTag("reply-notification-later").performClick()
                    compose.onNodeWithTag("reply-notification-card").assertDoesNotExist()
                }
                assertTrue(f.model.replyNotificationEducation.shownOrHandled)
                val first = f.model.chat!!.messages(service.peer).single { it.outgoing }.id
                compose.runOnIdle { service.markOutgoingRead(first) }
                compose.waitUntil(8_000) { f.model.chat!!.messages(service.peer).single { it.id == first }.state == "read" }
                compose.runOnIdle { service.peerTyping(true) }
                compose.waitUntil(5_000) { f.model.chat!!.isPeerTyping(service.peer) }
                receive(f, service, originals[1]); assertFalse(f.model.chat!!.isPeerTyping(service.peer)); send(f, originals[2]); receive(f, service, originals[3]); send(f, originals[4])
                compose.waitUntil(5_000) { ime() }
                f.device.pressBack(); compose.waitUntil(5_000) { !ime() }; screen(f, Screen.CONVERSATION)
                compose.mainClock.advanceTimeBy(500); compose.waitForIdle(); f.capture("04-natural-latest")
                // Seed real encrypted journal traffic, keeping the scene vocabulary natural.
                repeat(10) { index ->
                    val value = originals[index % originals.size]
                    compose.runOnIdle { f.model.chat!!.send(value, service.peer) }
                }
                runBlocking { withContext(Dispatchers.Main) { f.model.chat!!.synchronize() } }
                compose.waitUntil(15_000) { f.model.chat!!.messages(service.peer).count { it.outgoing && it.state in setOf("delivered", "read") } == 13 }
                // The same tap switches twice, retaining the exact editor content/selection.
                val draft = "Keep this unsent café plan ☕"
                compose.onNodeWithTag("message-input").performTextInput(draft)
                val caret = compose.onNodeWithTag("message-input").fetchSemanticsNode().config[SemanticsProperties.TextSelectionRange]
                repeat(2) { compose.onNodeWithTag("conversation-immersion").performTouchInput { click() }; compose.waitForIdle() }
                assertEquals(ImmersionMode.FULL_MESSAGES, f.model.immersionMode)
                compose.onNodeWithTag("message-input").assertTextEquals(draft)
                assertEquals(caret, compose.onNodeWithTag("message-input").fetchSemanticsNode().config[SemanticsProperties.TextSelectionRange])
                val timeline = compose.onNodeWithTag("conversation-timeline")
                timeline.performScrollToIndex(1); compose.mainClock.advanceTimeBy(500); compose.waitForIdle()
                compose.onNodeWithTag("conversation-latest").assertIsDisplayed()
                val viewport = timeline.fetchSemanticsNode().boundsInWindow
                val rows = compose.onAllNodes(SemanticsMatcher("message row") { it.config.getOrNull(SemanticsProperties.TestTag)?.startsWith("message-row-") == true }).fetchSemanticsNodes()
                val anchor = rows.first { it.boundsInWindow.top >= viewport.top && it.boundsInWindow.bottom <= viewport.bottom }
                val anchorTag = anchor.config[SemanticsProperties.TestTag]; val before = anchor.boundsInWindow.top
                val id = receive(f, service, originals[1])
                compose.mainClock.advanceTimeBy(500); compose.waitForIdle()
                val after = compose.onNodeWithTag(anchorTag).fetchSemanticsNode().boundsInWindow.top
                assertEquals("New reply must not steal the history anchor", before, after, 2f)
                assertFalse("Offscreen reply must not be claimed seen", id in service.seenMessages)
                compose.onNodeWithText(f.base.getString(R.string.chat_new_messages)).assertIsDisplayed()
                f.capture("05-history-new-message")
                compose.onNodeWithTag("conversation-latest").performClick(); compose.mainClock.advanceTimeBy(500)
                compose.waitUntil(8_000) { id in service.seenMessages }
                compose.runOnIdle { service.peerTyping(true) }; compose.onNodeWithTag("conversation-typing").assertIsDisplayed()
                f.capture("06-active-typing-latest")
                compose.runOnIdle { service.peerTyping(false) }
                compose.onNodeWithTag("reply-notification-card").assertDoesNotExist()
                assertEquals(draft, f.model.chat!!.compose(service.peer)); service.assertNoPurchase()
            } catch (failure: Throwable) { runCatching { f.capture("failure") }; throw failure }
            finally { f.stopActivity(); service.close() }
        }
    }
    /** Composition/AX completion precedes SurfaceFlinger paint. Await real native
     * frame commits, rather than weakening the pixels into a node-existence claim. */
    private fun committedNativeFrames() {
        val instrumentation = androidx.test.platform.app.InstrumentationRegistry.getInstrumentation()
        repeat(2) {
            val committed = CountDownLatch(1)
            instrumentation.runOnMainSync {
                val activity = ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).single()
                val root = activity.window.decorView
                check(root.isHardwareAccelerated)
                root.viewTreeObserver.registerFrameCommitCallback { committed.countDown() }
                root.invalidate()
            }
            check(committed.await(3, TimeUnit.SECONDS)) { "Actual native frame did not commit" }
        }
    }
    @Test fun actualNativeFramesShowEmptyAndActiveTypingBeforeExpiry() {
        val service = services(); peer = service.peer
        MainActivityJourneyFixture("chat-typing-native-frames", service::model).use { f ->
            try {
                open(f, Appearance.LIGHT)
                fun captureTyping(name: String) {
                    compose.runOnIdle { service.peerTyping(true) }
                    compose.waitUntil(5_000) { f.model.chat!!.isPeerTyping(service.peer) }
                    compose.mainClock.advanceTimeBy(400); compose.waitForIdle()
                    assertTrue(f.device.wait(Until.hasObject(By.text(f.base.getString(R.string.chat_typing, "Maya"))), 3_000))
                    committedNativeFrames()
                    assertTrue(f.model.chat!!.isPeerTyping(service.peer)); f.capture(name)
                    assertTrue("Typing must remain real during capture, not expire behind an old screenshot", f.model.chat!!.isPeerTyping(service.peer))
                }
                captureTyping("01-empty-typing-painted")
                send(f, originals[0])
                compose.onNodeWithTag("reply-notification-later").performClick()
                receive(f, service, originals[1]); assertFalse(f.model.chat!!.isPeerTyping(service.peer))
                if (ime()) { f.device.pressBack(); compose.waitUntil(5_000) { !ime() } }
                captureTyping("02-active-typing-day-painted")
                compose.runOnIdle { f.model.changeAppearance(Appearance.DARK) }
                captureTyping("03-active-typing-night-painted")
                compose.runOnIdle { service.peerTyping(false) }
                compose.waitUntil(5_000) { !f.model.chat!!.isPeerTyping(service.peer) }
            } catch (failure: Throwable) { runCatching { f.capture("failure") }; throw failure }
            finally { f.stopActivity(); service.close() }
        }
    }
    @Test fun firstSendNotificationOptInIsExplicitAndNotRepeatedAfterReopen() {
        val service = services(); peer = service.peer
        MainActivityJourneyFixture("chat-notification-opt-in", service::model).use { f ->
            try {
                check(!PushDelivery.allowed(f.base)) { "Requires externally preserved, denied QA notification permission" }
                open(f, Appearance.LIGHT); send(f, originals[0])
                compose.onNodeWithTag("reply-notification-card").assertIsDisplayed()
                assertFalse(PushDelivery.allowed(f.base))
                compose.onNodeWithTag("reply-notification-allow").performClick()
                val allow = f.device.wait(Until.findObject(By.res(Pattern.compile(".*:id/permission_allow_button"))), 8_000)
                assertNotNull("Actual Android notification permission dialog", allow)
                requireNotNull(allow).click()
                compose.waitUntil(8_000) { PushDelivery.allowed(f.base) }
                compose.onNodeWithTag("reply-notification-card").assertDoesNotExist()
                f.capture("01-explicit-opt-in")
                f.relaunch { app -> VipiModel(app, NoJourneyModelTranslation, service) }; screen(f, Screen.HOME)
                assertTrue(f.model.replyNotificationEducation.shownOrHandled)
                service.assertNoPurchase()
            } catch (failure: Throwable) { runCatching { f.capture("failure") }; throw failure }
            finally { f.stopActivity(); service.close() }
        }
    }
}
