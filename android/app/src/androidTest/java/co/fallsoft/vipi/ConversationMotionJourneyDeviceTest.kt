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
        val service = JourneyServices(profileRequired = false, accountDisplayName = "Alex", peerDisplayName = "Maya", expectedFriendPosts = 1,
            translationFactory = { object : LanguageTranslation {
                override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = Unit
                override suspend fun isReady(source: String, target: String) = true
                override suspend fun translate(text: String, source: String, target: String): String = when (text.lowercase(Locale.ROOT)) {
                    "coffee" -> "Café"; "yes" -> "Sí"
                    "coffee tonight?" -> "¿Tomamos un café esta noche?"
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
                fun paint(name: String) {
                    compose.mainClock.advanceTimeBy(400); compose.waitForIdle()
                    repeat(2) {
                        val committed = CountDownLatch(1)
                        f.instrumentation.runOnMainSync {
                            val root = ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).single().window.decorView
                            root.viewTreeObserver.registerFrameCommitCallback { committed.countDown() }; root.invalidate()
                        }
                        check(committed.await(3, TimeUnit.SECONDS)) { "Native frame must commit before screenshot" }
                    }
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
                assertTrue("Actual background changes while animation is enabled", movingPixels > 0)
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
