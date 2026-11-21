package co.fallsoft.vipi

import android.graphics.BitmapFactory
import android.view.WindowInsets
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.util.Locale
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** Native production Friend canvas and controls, with controlled lexical outputs.
 * This checks rendering/motion/input, never TTS or language support certification.
 */
class ConversationMotionJourneyDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()
    @Test fun actualFriendSceneKeepsForegroundStableAndCanStayStill() {
        val allowDeep = kotlinx.coroutines.CompletableDeferred<Unit>()
        val service = JourneyServices(profileRequired = false, accountDisplayName = "Alex", peerDisplayName = "Maya", expectedFriendPosts = 1,
            translationFactory = { object : LanguageTranslation {
                override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = Unit
                override suspend fun isReady(source: String, target: String) = true
                override suspend fun translate(text: String, source: String, target: String): String = when (text.lowercase(Locale.ROOT)) {
                    "coffee" -> "Café"; "yes" -> "Sí"
                    "coffee tonight?" -> { allowDeep.await(); "¿Tomamos un café esta noche?" }
                    "yes, 6:30 works!" -> "¡Sí, a las 6:30!"
                    else -> text
                }
                override fun close() = Unit
            } })
        MainActivityJourneyFixture("conversation-motion", service::model).use { f ->
            try {
                f.instrumentation.runOnMainSync { f.model.selectTarget("es"); f.model.selectImmersionMode(ImmersionMode.NEW_WORD); f.model.changeAppearance(Appearance.LIGHT) }
                f.launch(); compose.waitUntil(15_000) { f.model.screen == Screen.HOME && f.model.chat?.ready == true }
                compose.onNodeWithTag("inbox-compose").performClick()
                compose.onNode(hasSetTextAction()).performTextInput("journey_friend"); compose.onNode(hasSetTextAction()).performImeAction()
                compose.waitUntil(15_000) { f.model.screen == Screen.CONVERSATION }
                f.bindConversationCapture(compose, "message-input")
                fun committedFrames() {
                    repeat(2) {
                        val committed = CountDownLatch(1)
                        f.instrumentation.runOnMainSync {
                            val root = ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).single().window.decorView
                            root.viewTreeObserver.registerFrameCommitCallback { committed.countDown() }; root.invalidate()
                        }
                        check(committed.await(3, TimeUnit.SECONDS)) { "Native frame must commit before screenshot" }
                    }
                }
                fun paint(name: String) {
                    compose.mainClock.advanceTimeBy(400); compose.waitForIdle(); committedFrames()
                    f.capture(name)
                }
                compose.onNodeWithTag("message-input").performTextInput("Coffee tonight?")
                compose.onNodeWithTag("message-send").performClick()
                compose.waitUntil(15_000) { f.model.chat!!.messages(service.peer).any { it.outgoing && it.state in setOf("delivered", "read") } }
                if (!PushDelivery.allowed(f.base)) compose.onNodeWithTag("reply-notification-later").performClick()
                compose.runOnIdle { service.queueAdditionalPeerReplyAndSignalInbox("Yes, 6:30 works!") }
                compose.waitUntil(15_000) { f.model.chat!!.messages(service.peer).size == 2 && f.model.chat!!.messages(service.peer).all { f.model.chat!!.translations!!.state(it.id.toString(), it.text)?.phase == MessageTranslationPhase.READY } }
                fun ime(): Boolean { var shown = false; f.instrumentation.runOnMainSync { shown = ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).single().window.decorView.rootWindowInsets.isVisible(WindowInsets.Type.ime()) }; return shown }
                if (ime()) { f.device.pressBack(); compose.waitUntil(5_000) { !ime() } }
                // Preserve one unsent draft while mode changes on the actual header.
                compose.onNodeWithTag("message-input").performTextInput("Draft stays here")
                if (ime()) { f.device.pressBack(); compose.waitUntil(5_000) { !ime() } }
                for (appearance in listOf(Appearance.LIGHT, Appearance.DARK)) {
                    compose.runOnIdle { f.model.changeAppearance(appearance) }; compose.mainClock.advanceTimeBy(500)
                    val name = if (appearance == Appearance.LIGHT) "day" else "night"
                    paint("$name-shallow")
                    compose.onNodeWithTag("conversation-immersion").performClick()
                    if (appearance == Appearance.LIGHT) {
                        fun coffeeFaces(): List<Pair<String, Boolean>> {
                            var result = emptyList<Pair<String, Boolean>>()
                            f.instrumentation.runOnMainSync {
                                result = f.paragraphs().filter { it.originalMessage == "Coffee tonight?" }.map {
                                    it.text.toString() to (it.importantForAccessibility == android.view.View.IMPORTANT_FOR_ACCESSIBILITY_YES)
                                }
                            }
                            return result
                        }
                        val shallow = listOf("Café tonight?" to true)
                        val toggle = compose.onNodeWithTag("conversation-immersion")
                        compose.waitUntil(10_000) { f.model.immersionMode == ImmersionMode.FULL_MESSAGES }
                        assertEquals("While Deep is loading, keep the prepared Shallow paragraph", shallow, coffeeFaces())
                        toggle.performClick()
                        compose.waitUntil(10_000) { f.model.immersionMode == ImmersionMode.NEW_WORD }
                        assertEquals("Reversing a pending selection keeps the same paragraph", shallow, coffeeFaces())
                        toggle.performClick()
                        compose.waitUntil(10_000) { f.model.immersionMode == ImmersionMode.FULL_MESSAGES }
                        compose.mainClock.autoAdvance = false
                        try {
                            allowDeep.complete(Unit)
                            val message = f.model.chat!!.messages(service.peer).single { it.text == "Coffee tonight?" }
                            compose.waitUntil(15_000) {
                                f.model.chat!!.translations!!.state(message.id.toString(), message.text)?.phase == MessageTranslationPhase.READY
                            }
                            compose.mainClock.advanceTimeBy(80)
                            compose.waitForIdle()
                            if (android.animation.ValueAnimator.areAnimatorsEnabled()) {
                                assertEquals("Only the outgoing native paragraph is drawn before midpoint", shallow, coffeeFaces())
                                committedFrames()
                                check(f.device.takeScreenshot(File(f.output, "day-mode-before-midpoint.png")))
                                compose.mainClock.advanceTimeBy(100)
                                compose.waitForIdle()
                                assertEquals("Only the new native paragraph is drawn after midpoint",
                                    listOf("¿Tomamos un café esta noche?" to true), coffeeFaces())
                                committedFrames()
                                check(f.device.takeScreenshot(File(f.output, "day-mode-after-midpoint.png")))
                            } else {
                                assertEquals("Animations disabled: show the prepared target without a midpoint",
                                    listOf("¿Tomamos un café esta noche?" to true), coffeeFaces())
                            }
                            compose.mainClock.advanceTimeBy(350)
                        } finally { compose.mainClock.autoAdvance = true }
                    }
                    compose.waitUntil(15_000) { f.model.immersionMode == ImmersionMode.FULL_MESSAGES && f.model.chat!!.messages(service.peer).all { f.model.chat!!.translations!!.state(it.id.toString(), it.text)?.phase == MessageTranslationPhase.READY } }
                    compose.onNodeWithTag("message-input").assertTextEquals("Draft stays here")
                    paint("$name-deep")
                    compose.onNodeWithTag("conversation-immersion").performClick()
                    compose.waitUntil(15_000) { f.model.immersionMode == ImmersionMode.NEW_WORD }
                }
                paint("moving-before")
                Thread.sleep(900); compose.mainClock.advanceTimeBy(900); compose.waitForIdle(); paint("moving-after")
                val movingBefore = BitmapFactory.decodeFile(File(f.output, "moving-before.png").path)
                val movingAfter = BitmapFactory.decodeFile(File(f.output, "moving-after.png").path)
                val viewport = compose.onNodeWithTag("conversation-timeline").fetchSemanticsNode().boundsInRoot
                var movingPixels = 0
                for (y in (viewport.top + 120).toInt() until (viewport.bottom - 120).toInt().coerceAtMost(movingBefore.height)) {
                    for (x in viewport.left.toInt().coerceAtLeast(0) until viewport.right.toInt().coerceAtMost(movingBefore.width)) {
                        if (movingBefore.getPixel(x, y) != movingAfter.getPixel(x, y)) movingPixels++
                    }
                }
                if (android.animation.ValueAnimator.areAnimatorsEnabled()) {
                    assertTrue("Actual background changes while animation is enabled", movingPixels > 0)
                } else assertEquals("Disabled motion leaves the background still", 0, movingPixels)
                // Read the real native paragraph rectangle, not an inferred Compose frame.
                var paragraph = android.graphics.Rect()
                f.instrumentation.runOnMainSync {
                    val view = f.paragraphs().first(); val point = IntArray(2); view.getLocationOnScreen(point)
                    paragraph = android.graphics.Rect(point[0], point[1], point[0] + view.width, point[1] + view.height)
                }
                var foregroundChanges = 0
                for (y in paragraph.top until paragraph.bottom.coerceAtMost(movingBefore.height)) for (x in paragraph.left until paragraph.right.coerceAtMost(movingBefore.width)) {
                    if (movingBefore.getPixel(x, y) != movingAfter.getPixel(x, y)) foregroundChanges++
                }
                assertEquals("Actual message paragraph stays stationary while water moves", 0, foregroundChanges)
                movingBefore.recycle(); movingAfter.recycle()
                compose.runOnIdle { f.model.changeConversationAnimation(false) }
                compose.waitForIdle(); paint("paused-before")
                Thread.sleep(900); compose.mainClock.advanceTimeBy(900); compose.waitForIdle(); paint("paused-after")
                val bounds = compose.onNodeWithTag("conversation-timeline").fetchSemanticsNode().boundsInRoot
                val before = BitmapFactory.decodeFile(File(f.output, "paused-before.png").path)
                val after = BitmapFactory.decodeFile(File(f.output, "paused-after.png").path)
                // The root view begins below the Android status bar; compare the
                // interior of the native timeline, away from either system bar.
                val left = bounds.left.toInt().coerceAtLeast(0); val right = bounds.right.toInt().coerceAtMost(before.width)
                val top = (bounds.top + 120).toInt().coerceAtLeast(0); val bottom = (bounds.bottom - 120).toInt().coerceAtMost(before.height)
                var changed = 0
                for (y in top until bottom) for (x in left until right) if (before.getPixel(x, y) != after.getPixel(x, y)) changed++
                assertEquals("Paused timeline pixels stay still", 0, changed)
                before.recycle(); after.recycle()
                // Fill a real scrollable thread with replies through the existing
                // synthetic peer. Confirm a mode change preserves both reader intents.
                val timeline = compose.onNodeWithTag("conversation-timeline")
                val incoming = mutableListOf<java.util.UUID>()
                repeat(12) {
                    var reply: java.util.UUID? = null
                    compose.runOnIdle { reply = service.queueAdditionalPeerReplyAndSignalInbox("Yes, 6:30 works!") }
                    compose.waitUntil(10_000) { f.model.chat!!.messages(service.peer).any { it.id == reply } }
                    incoming += requireNotNull(reply)
                }
                fun switchAndSettle(mode: ImmersionMode, id: java.util.UUID) {
                    compose.onNodeWithTag("conversation-immersion").performClick()
                    compose.waitUntil(15_000) {
                        f.model.chat!!.translations?.let { it.mode == mode &&
                            it.state(id.toString(), "Yes, 6:30 works!")?.phase == MessageTranslationPhase.READY } == true
                    }
                    compose.mainClock.advanceTimeBy(500)
                    compose.waitForIdle()
                }
                val last = compose.onNodeWithTag("message-row-${incoming.last()}")
                compose.mainClock.advanceTimeBy(500)
                switchAndSettle(ImmersionMode.FULL_MESSAGES, incoming.last())
                last.assertIsDisplayed()
                assertTrue("Latest message remains above the composer",
                    last.fetchSemanticsNode().boundsInWindow.bottom <= timeline.fetchSemanticsNode().boundsInWindow.bottom)
                timeline.performScrollToIndex(3)
                compose.mainClock.advanceTimeBy(500)
                val historyViewport = timeline.fetchSemanticsNode().boundsInWindow
                val anchored = incoming.first { id ->
                    compose.onAllNodesWithTag("message-row-$id").fetchSemanticsNodes().singleOrNull()?.boundsInWindow?.let {
                        it.height > 0 && it.top >= historyViewport.top && it.bottom <= historyViewport.bottom
                    } == true
                }
                val row = compose.onNodeWithTag("message-row-$anchored")
                val historyTop = row.fetchSemanticsNode().boundsInWindow.top
                for (mode in listOf(ImmersionMode.NEW_WORD, ImmersionMode.FULL_MESSAGES)) {
                    switchAndSettle(mode, anchored)
                    assertEquals("Reading history stays at the same message and screen coordinate",
                        historyTop, row.fetchSemanticsNode().boundsInWindow.top, 2f)
                }
                compose.runOnIdle { f.model.navigate(Screen.SETTINGS) }
                compose.onNodeWithTag("settings-conversation-motion").performScrollTo().assertIsOff().performClick().assertIsOn()
                assertTrue(f.model.animateConversationBackground)
                compose.onNodeWithTag("settings-conversation-motion").performClick().assertIsOff()
                f.relaunch(service::model)
                assertFalse("Appearance choice survives a new model over the private store", f.model.animateConversationBackground)
                service.assertNoPurchase()
            } catch (error: Throwable) { runCatching { f.capture("failure") }; throw error }
            finally { f.stopActivity(); service.close() }
        }
    }
}
