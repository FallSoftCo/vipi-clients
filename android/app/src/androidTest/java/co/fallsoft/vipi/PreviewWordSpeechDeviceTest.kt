package co.fallsoft.vipi

import android.graphics.Rect
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.view.inspector.WindowInspector
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.dp
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import co.fallsoft.vipi.core.ImmersionResult
import co.fallsoft.vipi.core.SpeechSpan
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.util.concurrent.CopyOnWriteArrayList

/** The same real bubble, authored data and local player used by ConversationPreview.
 * Native pointer gestures, not callbacks or direct controller toggles. No acoustic claim. */
class PreviewWordSpeechDeviceTest {
    @get:Rule val compose = createComposeRule()
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private data class Preview(val result: ImmersionResult, val speech: SpeechPlayback, val target: String)

    @Test fun sameCoveredWordStopsAndAnotherTapReplaysOriginalScriptForNonRomanTargets() {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = instrumentation.targetContext
        val run = InstrumentationRegistry.getArguments().getString("vipiPreviewWordRun") ?: "001"
        require(run.matches(Regex("[0-9]{3}")))
        val out = File(context.filesDir, "preview-word-speech-$run"); check(!out.exists()); check(out.mkdirs())
        val shown = mutableStateOf<Preview?>(null)
        val rows = JSONArray()
        val device = UiDevice.getInstance(instrumentation)
        compose.setContent { shown.value?.let { value -> key(value.target) {
            VipiTheme(Appearance.LIGHT) {
                Column(Modifier.fillMaxSize().safeDrawingPadding().padding(18.dp)) {
                    ImmersionBubble(value.result, ReadingMode.IMMERSED, value.speech, "en", value.target, "preview-${value.target}")
                }
            }
        } } }
        for (target in listOf("ja", "zh", "ar", "ko")) {
            val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
            val accepted = CopyOnWriteArrayList<Pair<String, List<SpeechSpan>>>()
            lateinit var speech: SpeechPlayback
            var initialized = false
            val result = ConversationExamples.result(context, "en", target)
            val word = result.spans.maxBy { it.translated.length }
            val other = result.spans.first { it.id != word.id }
            try {
                compose.runOnIdle {
                    speech = SpeechPlayback(context, "en", target, scope); initialized = true
                    speech.qualificationInput = { message, spans -> accepted += message to spans.toList() }
                    speech.prepare(mapOf("en" to result.original, target to result.translation))
                }
                compose.waitUntil(30_000) { speech.state != SpeechState.PREPARING }
                compose.runOnIdle { assertEquals(speech.error.orEmpty(), SpeechState.READY, speech.state); shown.value = Preview(result, speech, target) }
                compose.waitForIdle()
                lateinit var bounds: Rect
                compose.runOnIdle {
                    val text = paragraph(result.original)
                    assertTrue("Default mixed text must expose its Latin reading", text.visibleText().contains(word.displayedTarget))
                    assertFalse(word.romanization.isNullOrBlank())
                    bounds = text.sourceRangeRect(word.start, word.end)
                }
                assertTrue(device.click(bounds.centerX(), bounds.centerY()))
                compose.waitUntil(15_000) { speech.state == SpeechState.PLAYING || speech.error != null }
                // UiDevice coordinate clicks do not wait for audio to become idle.
                assertEquals(SpeechState.PLAYING, speech.state)
                assertTrue(device.click(bounds.centerX(), bounds.centerY()))
                compose.waitUntil(3_000) { speech.activeMessage == null }
                SystemClock.sleep(250)
                compose.runOnIdle {
                    assertEquals("Same-word Stop must not enqueue a replacement", 1, accepted.size)
                    assertEquals(listOf(SpeechSpan(word.translated, target)), accepted.single().second)
                    assertNull(speech.activeMessage)
                }
                assertTrue(device.takeScreenshot(File(out, "en-$target-stopped.png")))
                assertTrue(device.click(bounds.centerX(), bounds.centerY()))
                compose.waitUntil(15_000) { accepted.size == 2 && speech.state == SpeechState.PLAYING }
                lateinit var otherBounds: Rect
                compose.runOnIdle { otherBounds = paragraph(result.original).sourceRangeRect(other.start, other.end) }
                assertTrue(device.click(otherBounds.centerX(), otherBounds.centerY()))
                compose.waitUntil(15_000) { accepted.size == 3 && speech.state == SpeechState.PLAYING }
                compose.runOnIdle {
                    assertEquals(listOf(SpeechSpan(word.translated, target)), accepted[1].second)
                    assertEquals(listOf(SpeechSpan(other.translated, target)), accepted[2].second)
                    speech.stop()
                }
                rows.put(JSONObject().put("source", "en").put("target", target).put("reading", word.displayedTarget)
                    .put("spoken_script", word.translated).put("same_word_stop", true).put("replay", true).put("different_word_once", true))
            } finally {
                compose.runOnIdle { shown.value = null }; compose.waitForIdle()
                if (initialized) compose.runOnIdle { speech.close() }
                scope.cancel()
                File(out, "report.json").writeText(JSONObject().put("cases", rows).put("evidence", "native preview taps and actual local AudioTrack state; no acoustic acceptance").toString(2))
            }
        }
        assertEquals(4, rows.length())
    }

    @Test fun sameWordCancelsPendingPreparationWithoutLateAudio() {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = instrumentation.targetContext
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        val accepted = CopyOnWriteArrayList<String>()
        lateinit var speech: SpeechPlayback
        val visible = mutableStateOf(true)
        val result = ConversationExamples.result(context, "en", "es")
        val word = result.spans.first()
        compose.runOnIdle {
            speech = SpeechPlayback(context, "en", "es", scope)
            speech.qualificationInput = { message, _ -> accepted += message }
        }
        compose.setContent { if (visible.value) VipiTheme(Appearance.LIGHT) {
            Column(Modifier.fillMaxSize().safeDrawingPadding().padding(18.dp)) {
                ImmersionBubble(result, ReadingMode.IMMERSED, speech, "en", "es", "pending-preview")
            }
        } }
        try {
            lateinit var bounds: Rect
            compose.runOnIdle { bounds = paragraph(result.original).sourceRangeRect(word.start, word.end) }
            val device = UiDevice.getInstance(instrumentation)
            assertTrue(device.click(bounds.centerX(), bounds.centerY()))
            compose.waitForIdle()
            assertTrue(device.click(bounds.centerX(), bounds.centerY()))
            compose.waitForIdle()
            compose.runOnIdle { speech.prepare(mapOf("en" to result.original, "es" to result.translation)) }
            compose.waitUntil(30_000) { speech.state != SpeechState.PREPARING }
            SystemClock.sleep(300)
            compose.runOnIdle {
                assertEquals(speech.error.orEmpty(), SpeechState.READY, speech.state)
                assertTrue("Stopped word cannot start when voice preparation finishes", accepted.isEmpty())
                assertNull(speech.activeMessage)
            }
        } finally {
            compose.runOnIdle { visible.value = false }; compose.waitForIdle()
            compose.runOnIdle { speech.close() }; scope.cancel()
        }
    }

    private fun paragraph(original: String): StableImmersionText {
        fun collect(view: View): List<StableImmersionText> = when (view) {
            is StableImmersionText -> listOf(view)
            is ViewGroup -> (0 until view.childCount).flatMap { collect(view.getChildAt(it)) }
            else -> emptyList()
        }
        return WindowInspector.getGlobalWindowViews().flatMap(::collect).single { it.isShown && it.displayedOriginal == original }
    }
}
