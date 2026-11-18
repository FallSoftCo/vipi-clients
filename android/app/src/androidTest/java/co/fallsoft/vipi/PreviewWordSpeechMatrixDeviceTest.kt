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
import java.security.MessageDigest
import java.util.concurrent.CopyOnWriteArrayList

/** Exhaustive native gesture integration for the shipped authored preview.
 * Separate from the fast smoke test and from ordinary conversation/linguistic acceptance. */
class PreviewWordSpeechMatrixDeviceTest {
    @get:Rule val compose = createComposeRule()
    private data class Preview(val result: ImmersionResult, val speech: SpeechPlayback, val source: String, val target: String, val id: String)

    @Test fun all110DirectedPreviewsRenderSpeakAndStopTheSameNativeWord() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = instrumentation.targetContext
        val run = InstrumentationRegistry.getArguments().getString("vipiPreviewMatrixRun") ?: "001"
        require(run.matches(Regex("[0-9]{3}")))
        val output = File(context.filesDir, "preview-word-matrix-110-$run")
        check(!output.exists()) { "Use a new vipiPreviewMatrixRun to preserve earlier evidence" }; check(output.mkdirs())
        val bytes = context.assets.open("immersion-preview.json").use { it.readBytes() }
        val fixture = JSONObject(bytes.toString(Charsets.UTF_8)).getJSONObject("languages")
        val languages = initialLanguages.map { it.code }
        assertEquals(languages.toSet(), fixture.keys().asSequence().toSet())
        assertEquals(11, languages.size)
        val rows = JSONArray()
        val report = JSONObject().put("scope", "authored shipped previews; actual native touch, production bubble and local SpeechPlayback")
            .put("source_asset_sha256", MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) })
            .put("expected_directions", 110).put("directions", rows).put("complete", false)
            .put("ordinary_conversation_coverage", false).put("linguistic_acceptance", false).put("physical_or_acoustic_acceptance", false)
            .put("model_downloads_requested", false)
        fun save() { File(output, "report.json").writeText(report.toString(2)) }
        val shown = mutableStateOf<Preview?>(null)
        val device = UiDevice.getInstance(instrumentation)
        var savedFailures = 0
        compose.setContent { shown.value?.let { value -> key(value.id) {
            VipiTheme(Appearance.LIGHT) {
                Column(Modifier.fillMaxSize().safeDrawingPadding().padding(18.dp)) {
                    ImmersionBubble(value.result, ReadingMode.IMMERSED, value.speech, value.source, value.target, value.id)
                }
            }
        } } }
        save()
        for (source in languages) for (target in languages.filter { it != source }) {
            val id = "matrix-$source-$target"
            val row = JSONObject().put("source", source).put("target", target).put("status", "started")
            rows.put(row); save()
            val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
            val accepted = CopyOnWriteArrayList<Pair<String, List<SpeechSpan>>>()
            var speech: SpeechPlayback? = null
            try {
                val result = ConversationExamples.result(context, source, target)
                assertTrue("Authored preview must provide a tappable word: $source->$target", result.spans.isNotEmpty())
                val word = result.spans.maxBy { it.translated.length }
                assertEquals(fixture.getJSONObject(source).getString("text"), result.original)
                assertEquals(fixture.getJSONObject(target).getString("text"), result.translation)
                if (target in setOf("ja", "zh", "ar", "ko")) {
                    assertTrue("Non-Latin target needs its Latin guide", result.spans.all { !it.romanization.isNullOrBlank() })
                    assertNotEquals(word.translated, word.displayedTarget)
                }
                if (target == "zh") {
                    val tones = "āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ"
                    assertTrue("Every shipped Chinese preview word must retain marked pinyin", result.spans.all { span -> span.romanization!!.any { it in tones } })
                }
                lateinit var current: SpeechPlayback
                compose.runOnIdle {
                    current = SpeechPlayback(context, source, target, scope); speech = current
                    current.qualificationInput = { message, spans -> accepted += message to spans.toList() }
                    current.prepare(mapOf(source to result.original, target to result.translation))
                }
                compose.waitUntil(30_000) { current.state != SpeechState.PREPARING }
                compose.runOnIdle {
                    assertEquals(current.error.orEmpty(), SpeechState.READY, current.state)
                    shown.value = Preview(result, current, source, target, id)
                }
                compose.waitForIdle()
                lateinit var bounds: Rect
                compose.runOnIdle {
                    val native = paragraph(result.original)
                    assertTrue(native.visibleText().contains(word.displayedTarget))
                    bounds = native.sourceRangeRect(word.start, word.end)
                    assertTrue("Word must be inside the visible native paragraph", Rect().also { native.getGlobalVisibleRect(it) }.contains(bounds))
                    row.put("visible_before_tap", native.visibleText()).put("displayed_word", word.displayedTarget)
                        .put("target_script", word.translated).put("word_bounds", bounds.toShortString())
                }
                val began = SystemClock.elapsedRealtime()
                assertTrue(device.click(bounds.centerX(), bounds.centerY()))
                compose.waitUntil(15_000) { current.state == SpeechState.PLAYING || current.error != null }
                assertEquals(current.error.orEmpty(), SpeechState.PLAYING, current.state)
                row.put("tap_to_playing_ms", SystemClock.elapsedRealtime() - began)
                // Inspect the actual controller input while its real AudioTrack is playing.
                assertEquals(1, accepted.size)
                assertEquals("word-$id-${word.id}", accepted.single().first)
                assertEquals(listOf(SpeechSpan(word.translated, target)), accepted.single().second)
                assertTrue(device.click(bounds.centerX(), bounds.centerY()))
                compose.waitUntil(3_000) { current.activeMessage == null }
                SystemClock.sleep(300)
                compose.runOnIdle {
                    assertNull("Same native word must stop without rebound", current.activeMessage)
                    assertEquals(SpeechState.READY, current.state)
                    assertEquals("Same native word must not enqueue another render", 1, accepted.size)
                    assertNull(current.error)
                    row.put("visible_after_stop", paragraph(result.original).visibleText())
                }
                row.put("status", "passed").put("native_playing_observed", true)
                    .put("accepted_script", accepted.single().second.single().text).put("accepted_language", accepted.single().second.single().language)
                    .put("same_word_stop", true).put("no_rebound", true)
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (failure: Throwable) {
                row.put("status", "failed").put("failure_class", failure.javaClass.simpleName).put("failure", failure.message)
                    .put("accepted_requests", accepted.size).put("speech_state", speech?.state?.name).put("active_message", speech?.activeMessage)
                if (savedFailures < 5) {
                    val capture = "$source-$target-failure.png"
                    if (device.takeScreenshot(File(output, capture))) row.put("capture", capture)
                    savedFailures++
                }
            } finally {
                compose.runOnIdle { shown.value = null }; compose.waitForIdle()
                speech?.let { current -> compose.runOnIdle { current.close() } }; scope.cancel(); save()
            }
        }
        val passed = (0 until rows.length()).count { rows.getJSONObject(it).getString("status") == "passed" }
        report.put("complete", true).put("passed_directions", passed).put("failed_directions", rows.length() - passed); save()
        assertEquals(110, rows.length())
        assertEquals("Every supported direction must complete the native visible word gesture; inspect report.json for failures", 110, passed)
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
