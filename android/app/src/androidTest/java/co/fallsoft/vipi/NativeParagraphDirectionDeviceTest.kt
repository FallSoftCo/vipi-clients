package co.fallsoft.vipi

import android.content.ClipboardManager
import android.content.Context
import android.content.res.Configuration
import android.text.Selection
import android.text.Spannable
import android.text.TextDirectionHeuristics
import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import co.fallsoft.vipi.core.ImmersionPresentation
import co.fallsoft.vipi.core.ImmersionResult
import co.fallsoft.vipi.core.ImmersionSpan
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File

/** Native paragraph direction/leading edge, using shipped authored lexical pairs.
 * Constructed mixed/newline layouts qualify rendering, not linguistic quality. */
class NativeParagraphDirectionDeviceTest {
    @get:Rule val compose = createComposeRule()
    private data class Shown(val scale: Float, val context: Context, val value: ImmersionPresentation, val revealed: Set<Int>)
    private data class Case(val name: String, val source: String, val spans: List<ImmersionSpan>)
    private data class Paragraph(val start: Int, val direction: Int, val leading: Float) {
        fun json() = JSONObject().put("source_start", start).put("direction", direction).put("leading_px", leading.toDouble())
    }

    @Test fun sourceParagraphDirectionAndLeadingEdgeSurvivePreparationFlipsAndRebind() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val base = instrumentation.targetContext
        val run = InstrumentationRegistry.getArguments().getString("vipiParagraphDirectionRun")
            ?: InstrumentationRegistry.getArguments().getString("vipiJourneyRun") ?: "001"
        require(run.matches(Regex("[0-9]{3}")))
        val output = File(base.filesDir, "native-paragraph-direction-$run").apply { check(!exists()); check(mkdirs()) }
        val shown = mutableStateOf<Shown?>(null)
        var native: StableImmersionText? = null
        compose.setContent { shown.value?.let { sample -> key(sample.scale) {
            VipiTheme(Appearance.LIGHT) {
                val accent = MaterialTheme.colorScheme.primary.toArgb()
                val ink = MaterialTheme.colorScheme.onSurface.toArgb()
                Column(Modifier.fillMaxSize().safeDrawingPadding().padding(16.dp)) {
                    AndroidView(factory = { StableImmersionText(sample.context).also { native = it } },
                        modifier = Modifier.fillMaxWidth(), update = { it.bind(sample.value, sample.revealed, false, accent, ink) })
                }
            }
        } } }
        val arabic = ConversationExamples.result(base, "ar", "en").spans.first { it.translated == "river" }
        val latin = ConversationExamples.result(base, "en", "ar").spans.first { it.original == "river" }
        assertEquals("Use the same actual authored reverse pair", arabic.original, latin.translated)
        assertEquals("Exercise indistinguishable masked paragraphs", arabic.original.length, latin.original.length)
        fun make(name: String, parts: List<Pair<String, ImmersionSpan?>>): Case {
            var source = ""; val spans = mutableListOf<ImmersionSpan>()
            for ((text, word) in parts) {
                if (word != null) {
                    assertEquals(word.original, text)
                    spans += word.copy(start = source.length, end = source.length + text.length)
                }
                source += text
            }
            return Case(name, source, spans)
        }
        val a = arabic.original to arabic; val l = latin.original to latin
        val cases = listOf(
            make("arabic", listOf(a)),
            make("arabic-before-unreplaced-latin", listOf(a, " river" to null)),
            make("latin-before-unreplaced-arabic", listOf(l, " ${arabic.original}" to null)),
            make("multiple-rtl-slots", listOf(a, " " to null, a)),
            make("numbers-punctuation", listOf("12: (" to null, a, "), river!" to null)),
            make("opposite-newlines", listOf(a, "\n" to null, l, "\n\n" to null, a, " river" to null)),
            make("reverse-rebind-newlines", listOf(l, "\n" to null, a, "\n\n" to null, l, " ${arabic.original}" to null))
        )
        val rows = JSONArray()
        val report = JSONObject().put("complete", false).put("cases", rows)
            .put("scope", "native source paragraph direction, leading edge, copy and source offsets; authored words in constructed mixed layouts")
            .put("arbitrary_conversation_or_linguistic_acceptance", false).put("device_font_settings_changed", false)
        fun save() = File(output, "report.json").writeText(report.toString(2))
        fun paragraphs(source: String): List<Paragraph> {
            compose.waitForIdle()
            var actual = emptyList<Paragraph>()
            compose.runOnIdle {
                val view = requireNotNull(native); val layout = requireNotNull(view.layout)
                assertEquals("No source code units or offsets may be inserted", source, view.text.toString())
                val starts = listOf(0) + source.indices.filter { source[it] == '\n' }.map { it + 1 }
                actual = starts.map { start ->
                    val line = layout.getLineForOffset(start)
                    val direction = layout.getParagraphDirection(line)
                    val leading = if (direction == -1) layout.getLineRight(line) else layout.getLineLeft(line)
                    Paragraph(start, direction, leading)
                }
            }
            return actual
        }
        fun assertDirections(source: String, actual: List<Paragraph>) {
            actual.forEach { paragraph ->
                val end = source.indexOf('\n', paragraph.start).let { if (it < 0) source.length else it }
                val expected = if (TextDirectionHeuristics.FIRSTSTRONG_LTR.isRtl(source, paragraph.start, end - paragraph.start)) -1 else 1
                assertEquals("Source paragraph direction at ${paragraph.start}", expected, paragraph.direction)
            }
        }
        fun copyFirst(case: Case) {
            compose.runOnIdle {
                val view = requireNotNull(native); val word = case.spans.first()
                assertEquals(word.original, view.text.subSequence(word.start, word.end).toString())
                assertFalse("Native source selection must remain available", view.sourceRangeRect(word.start, word.end).isEmpty)
                Selection.setSelection(view.text as Spannable, word.start, word.end)
                assertTrue(view.onTextContextMenuItem(android.R.id.copy))
                val clipboard = base.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                assertEquals(view.visibleText(word.start, word.end), clipboard.primaryClip!!.getItemAt(0).text.toString())
                Selection.removeSelection(view.text as Spannable)
            }
        }
        val device = UiDevice.getInstance(instrumentation)
        val clipboard = base.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        var priorClip: android.content.ClipData? = null
        compose.runOnIdle { priorClip = clipboard.primaryClip }
        save()
        try {
            for (scale in listOf(1f, 1.6f)) for (case in cases) {
                val id = "${case.name}-${if (scale == 1f) "normal" else "enlarged"}"
                val row = JSONObject().put("id", id).put("source", case.source).put("status", "started")
                rows.put(row); save()
                try {
                    val context = base.createConfigurationContext(Configuration(base.resources.configuration).apply { fontScale = scale })
                    val pending = ImmersionResult(case.source, "", emptyList())
                    val prepared = ImmersionResult(case.source, case.source, case.spans)
                    compose.runOnIdle { shown.value = Shown(scale, context, pending, emptySet()) }
                    val initial = paragraphs(case.source)
                    row.put("pending", JSONArray(initial.map { it.json() }))
                    assertDirections(case.source, initial)
                    assertTrue(device.takeScreenshot(File(output, "$id-pending.png")))
                    copyFirst(case)
                    val observations = JSONArray(); row.put("prepared_and_flips", observations)
                    repeat(7) { index ->
                        val revealed = if (index % 2 == 1) case.spans.map { it.id }.toSet() else emptySet()
                        compose.runOnIdle { shown.value = Shown(scale, context, prepared, revealed) }
                        val actual = paragraphs(case.source)
                        observations.put(JSONObject().put("face", if (revealed.isEmpty()) "target" else "source")
                            .put("paragraphs", JSONArray(actual.map { it.json() })))
                        assertDirections(case.source, actual)
                        initial.zip(actual).forEach { (before, after) ->
                            assertEquals(before.start, after.start)
                            assertEquals("Prepared source paragraph leading edge moved at ${before.start}",
                                before.leading.toDouble(), after.leading.toDouble(), 1.0)
                        }
                        if (case.name == "multiple-rtl-slots") compose.runOnIdle {
                            val view = requireNotNull(native)
                            assertTrue("RTL source word order must survive neutral replacement runs",
                                view.sourceRangeRect(case.spans[0].start, case.spans[0].end).left >
                                    view.sourceRangeRect(case.spans[1].start, case.spans[1].end).left)
                        }
                        if (index == 0) assertTrue(device.takeScreenshot(File(output, "$id-prepared.png")))
                        copyFirst(case)
                    }
                    row.put("status", "passed")
                } catch (failure: Throwable) {
                    row.put("status", "failed").put("failure", failure.toString())
                    device.takeScreenshot(File(output, "$id-failed.png"))
                } finally { save() }
            }
        } finally {
            compose.runOnIdle {
                priorClip?.let { clipboard.setPrimaryClip(it) } ?: clipboard.clearPrimaryClip()
                shown.value = null
            }
        }
        val passed = (0 until rows.length()).count { rows.getJSONObject(it).getString("status") == "passed" }
        report.put("complete", true).put("passed_cases", passed).put("expected_cases", 14); save()
        assertEquals("Inspect native-paragraph-direction report and screenshots", 14, passed)
    }
}
