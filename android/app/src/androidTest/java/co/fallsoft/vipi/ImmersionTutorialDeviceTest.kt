package co.fallsoft.vipi

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import java.io.File
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

/**
 * Actual local ML Kit/TTS path in a fresh, isolated QA application. No account, transport, canned
 * translation, reading or speech boundary.
 */
class ImmersionTutorialDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()

    @Test
    fun actualPairChangesInPlaceAndOptionalContinuePreservesModeAndInvitation() {
        MainActivityJourneyFixture("tutorial-real-local", { VipiModel(it) }).use { f ->
            val audioEvents = CopyOnWriteArrayList<JSONObject>()
            MessageAudioQualification.attach { audioEvents += it }
            fun capture(name: String) {
                compose.waitForIdle()
                val settled = CountDownLatch(1)
                f.instrumentation.runOnMainSync {
                    val view = f.paragraphs().single()
                    view.postOnAnimation { view.postOnAnimation { settled.countDown() } }
                }
                assertTrue(
                    "Two actual native display frames must settle before screenshot",
                    settled.await(3, TimeUnit.SECONDS),
                )
                f.capture(name)
            }
            val source = ImmersionTutorialSource.text("en")
            fun drawn(): String {
                var value = ""
                f.instrumentation.runOnMainSync {
                    value = f.paragraphs().singleOrNull()?.text?.toString().orEmpty()
                }
                return value
            }
            fun awaitPractice() =
                compose.waitUntil(180_000) { drawn().isNotBlank() && drawn() != source }
            try {
                compose.runOnIdle {
                    f.model.selectKnown("en")
                    f.model.selectTarget("es")
                    f.model.selectImmersionMode(ImmersionMode.NEW_WORD)
                    assertTrue(
                        f.model.acceptInvitation("https://api.mambovipi.app/invite/qa_friend")
                    )
                    f.model.navigate(Screen.LANGUAGE)
                }
                f.launch()
                compose.onNodeWithText(f.base.getString(R.string.continue_action)).performClick()
                compose.waitUntil { f.model.screen == Screen.TUTORIAL }
                compose.onNodeWithTag("tutorial-title").assertIsDisplayed()
                // Continue is enabled before a model/voice completes.
                compose.onNodeWithText(f.base.getString(R.string.continue_action)).assertIsEnabled()
                compose.onNodeWithTag("tutorial-mode-NEW_WORD").assertIsDisplayed()
                compose.onNodeWithTag("tutorial-mode-FULL_MESSAGES").assertIsDisplayed()
                awaitPractice()
                val shallow = drawn()
                capture("01-real-shallow")
                compose.onNodeWithTag("tutorial-mode-FULL_MESSAGES").performClick()
                awaitPractice()
                compose.waitUntil(180_000) { drawn() != shallow && drawn() != source }
                val deep = drawn()
                capture("02-real-deep")
                // Hold reveals the exact authored source through the real surface.
                compose.onNodeWithTag("tutorial-message").performTouchInput {
                    down(center)
                    advanceEventTime(1_200)
                }
                compose.waitUntil(5_000) { drawn() == source }
                capture("03-held-original")
                compose.onNodeWithTag("tutorial-message").performTouchInput { up() }
                compose.waitUntil(5_000) { drawn() == deep }
                compose.onNodeWithTag("tutorial-message").performTouchInput { click(center) }
                // The UI test owns a virtual double-tap timeout. Advance that
                // input dispatcher; synthesis and AudioTrack timing remain real.
                compose.mainClock.advanceTimeBy(400)
                compose.waitForIdle()
                var actualPlayback = audioEvents.any { it.optString("stage") == "pcm_started" }
                val end = System.currentTimeMillis() + 10_000
                while (System.currentTimeMillis() < end && !actualPlayback) {
                    f.instrumentation.runOnMainSync {
                        actualPlayback =
                            actualPlayback ||
                                f.paragraphs().any { it.playing } ||
                                audioEvents.any { it.optString("stage") == "pcm_started" }
                    }
                    if (!actualPlayback) Thread.sleep(16)
                }
                capture(if (actualPlayback) "04-real-playing" else "04-voice-state")
                assertTrue(
                    "Real selected-pair voice should play or expose an honest unavailable/retry action",
                    actualPlayback ||
                        compose
                            .onAllNodesWithText(f.base.getString(R.string.try_again))
                            .fetchSemanticsNodes()
                            .isNotEmpty(),
                )
                compose.onNodeWithTag("tutorial-mode-NEW_WORD").performClick()
                compose.waitUntil(15_000) { drawn() == shallow }
                capture("05-shallow-plan-preserved")
                assertEquals("qa_friend", f.model.invitationUsername)
                assertNull(f.model.chat)
                compose.onNodeWithText(f.base.getString(R.string.continue_action)).performClick()
                compose.waitUntil { f.model.screen == Screen.ACCOUNT }
                assertEquals("qa_friend", f.model.invitationUsername)
                assertEquals(ImmersionMode.NEW_WORD, f.model.immersionMode)
                f.relaunch { VipiModel(it) }
                compose.waitUntil { f.model.screen == Screen.ACCOUNT }
                assertEquals(ImmersionMode.NEW_WORD, f.model.immersionMode)
                assertEquals("qa_friend", f.model.invitationUsername)
                assertNull(f.model.chat)
                compose.runOnIdle { f.model.navigate(Screen.SETTINGS) }
                compose.onNodeWithTag("settings-help").performScrollTo().performClick()
                compose.onNodeWithTag("tutorial-reentry").performScrollTo().performClick()
                compose.waitUntil { f.model.screen == Screen.TUTORIAL }
                compose.onNodeWithText(f.base.getString(R.string.continue_action)).performClick()
                compose.waitUntil { f.model.screen == Screen.HELP }
                File(f.output, "result.json")
                    .writeText(
                        JSONObject()
                            .put("real_local_translation", true)
                            .put("actual_voice_started", actualPlayback)
                            .put("source", source)
                            .put("shallow", shallow)
                            .put("deep", deep)
                            .put("same_shallow_plan", true)
                            .put("invitation_preserved", true)
                            .put("account_or_transport_created", false)
                            .toString(2)
                    )
            } catch (failure: Throwable) {
                runCatching { f.capture("failure") }
                throw failure
            } finally {
                MessageAudioQualification.attach(null)
                File(f.output, "audio-events.json")
                    .writeText(org.json.JSONArray(audioEvents.toList()).toString(2))
            }
        }
    }
}
