package co.fallsoft.vipi

import android.content.Context
import android.content.res.Configuration
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
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File

/** Actual native renderer with words cropped from shipped authored previews.
 * This is font/line-geometry evidence, not arbitrary conversation/linguistic QA. */
class NativeLineMetricDeviceTest {
    @get:Rule val compose = createComposeRule()
    private data class Sample(val id: String, val context: Context, val value: ImmersionPresentation, val revealed: Set<Int>, val showScript: Boolean = false)
    private data class Geometry(val baseline: Int, val lineHeight: Int, val viewHeight: Int, val textSize: Float, val slotWidth: Int) {
        fun json() = JSONObject().put("baseline", baseline).put("line_height", lineHeight)
            .put("view_height", viewHeight).put("text_size_px", textSize.toDouble()).put("source_selection_width", slotWidth)
    }

    @Test fun pendingOriginalAndPreparedLatinPinyinJapaneseArabicKeepBaselineThroughRepeatedFlips() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val base = instrumentation.targetContext
        val run = InstrumentationRegistry.getArguments().getString("vipiLineMetricRun")
            ?: InstrumentationRegistry.getArguments().getString("vipiJourneyRun") ?: "001"
        require(run.matches(Regex("[0-9]{3}")))
        val output = File(base.filesDir, "native-line-metrics-$run").apply { check(!exists()); check(mkdirs()) }
        val shown = mutableStateOf<Sample?>(null)
        var native: StableImmersionText? = null
        compose.setContent { shown.value?.let { sample -> key(sample.id) {
            VipiTheme(Appearance.LIGHT) {
                val accent = MaterialTheme.colorScheme.primary.toArgb()
                val ink = MaterialTheme.colorScheme.onSurface.toArgb()
                Column(Modifier.fillMaxSize().safeDrawingPadding().padding(16.dp)) {
                    AndroidView(factory = { StableImmersionText(sample.context).also { native = it } },
                        modifier = Modifier.fillMaxWidth(), update = { it.bind(sample.value, sample.revealed, sample.showScript, accent, ink) })
                }
            }
        } } }
        val rows = JSONArray()
        val report = JSONObject().put("complete", false).put("cases", rows)
            .put("scope", "same-line native pending/prepared/repeated-flip metrics from actual shipped authored words")
            .put("arbitrary_conversation_or_linguistic_acceptance", false).put("device_font_settings_changed", false)
        fun save() = File(output, "report.json").writeText(report.toString(2))
        fun geometry(): Geometry {
            compose.waitForIdle()
            var result: Geometry? = null
            compose.runOnIdle {
                val view = requireNotNull(native); val layout = requireNotNull(view.layout)
                assertEquals("Qualification word must occupy one native line", 1, layout.lineCount)
                assertTrue("Native ascent must be inside the paragraph", layout.getLineBaseline(0) + layout.getLineAscent(0) >= 0)
                assertTrue("Native descent must be inside the paragraph", layout.getLineBaseline(0) + layout.getLineDescent(0) <= view.height)
                result = Geometry(layout.getLineBaseline(0), layout.getLineBottom(0) - layout.getLineTop(0), view.height,
                    view.textSize, view.sourceRangeRect(0, view.displayedOriginal.length).width())
            }
            return requireNotNull(result)
        }
        fun same(expected: Geometry, actual: Geometry) {
            assertEquals("Native source-line baseline moved", expected.baseline.toDouble(), actual.baseline.toDouble(), 1.0)
            assertEquals("Native line height changed", expected.lineHeight.toDouble(), actual.lineHeight.toDouble(), 1.0)
            assertEquals("Native paragraph height changed", expected.viewHeight.toDouble(), actual.viewHeight.toDouble(), 1.0)
            assertEquals("Text size must remain unchanged", expected.textSize, actual.textSize, 0f)
        }
        val device = UiDevice.getInstance(instrumentation)
        val directions = listOf("latin" to ("en" to "sw"), "marked-pinyin" to ("en" to "zh"),
            "japanese-source" to ("ja" to "en"), "arabic-source" to ("ar" to "en"))
        save()
        for (scale in listOf(1f, 1.6f)) for ((label, pair) in directions) {
            val id = "$label-${if (scale == 1f) "normal" else "enlarged"}"
            val row = JSONObject().put("id", id).put("source", pair.first).put("target", pair.second)
                .put("font_scale", scale.toDouble()).put("status", "started")
            rows.put(row); save()
            try {
                val context = base.createConfigurationContext(Configuration(base.resources.configuration).apply { fontScale = scale })
                val authored = ConversationExamples.result(context, pair.first, pair.second)
                val word = authored.spans.minBy { maxOf(it.original.length, it.displayedTarget.length) }
                val cropped = word.copy(start = 0, end = word.original.length, targetStart = 0, targetEnd = word.translated.length)
                val prepared = ImmersionResult(word.original, word.translated, listOf(cropped))
                val pending = object : ImmersionPresentation {
                    override val original = word.original
                    override val translation: String? = null
                    override val spans = emptyList<co.fallsoft.vipi.core.ImmersionSpan>()
                }
                if (label == "marked-pinyin") {
                    assertTrue("Use the actual authored marked guide", word.displayedTarget.any { it in "āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ" })
                    assertNotEquals(word.translated, word.displayedTarget)
                }
                if (pair.first == "ja") assertTrue(word.original.any { Character.UnicodeScript.of(it.code) in
                    setOf(Character.UnicodeScript.HAN, Character.UnicodeScript.HIRAGANA, Character.UnicodeScript.KATAKANA) })
                if (pair.first == "ar") assertTrue(word.original.any { Character.UnicodeScript.of(it.code) == Character.UnicodeScript.ARABIC })
                compose.runOnIdle { shown.value = Sample(id, context, pending, emptySet()) }
                val initial = geometry()
                row.put("original", word.original).put("target_script", word.translated).put("target_guide", word.displayedTarget)
                    .put("initial", initial.json())
                compose.runOnIdle { assertEquals(word.original, requireNotNull(native).visibleText()) }
                assertTrue(device.takeScreenshot(File(output, "$id-pending.png")))
                compose.runOnIdle { shown.value = Sample(id, context, prepared, emptySet()) }
                val firstPrepared = geometry(); row.put("first_prepared", firstPrepared.json()); same(initial, firstPrepared)
                val flips = JSONArray()
                repeat(6) { index ->
                    val original = index % 2 == 0
                    compose.runOnIdle { shown.value = Sample(id, context, prepared, if (original) setOf(cropped.id) else emptySet()) }
                    val actual = geometry(); same(initial, actual)
                    compose.runOnIdle { assertEquals(if (original) word.original else word.displayedTarget, requireNotNull(native).visibleText()) }
                    flips.put(actual.json().put("face", if (original) "original" else "target"))
                }
                row.put("flips", flips)
                assertTrue(device.takeScreenshot(File(output, "$id-prepared.png")))
                if (word.displayedTarget != word.translated) {
                    //The explicit native-script preference may use its actual
                    //fallback height, but its fixed slot width must not change.
                    compose.runOnIdle { shown.value = Sample(id, context, prepared, emptySet(), showScript = true) }
                    val script = geometry()
                    assertEquals("All three forms retain the same slot width", firstPrepared.slotWidth, script.slotWidth)
                    compose.runOnIdle { assertEquals(word.translated, requireNotNull(native).visibleText()) }
                    row.put("explicit_native_script", script.json())
                    assertTrue(device.takeScreenshot(File(output, "$id-native-script.png")))
                    repeat(4) { index ->
                        val original = index % 2 == 0
                        compose.runOnIdle { shown.value = Sample(id, context, prepared,
                            if (original) setOf(cropped.id) else emptySet(), showScript = true) }
                        val actual = geometry(); same(script, actual)
                        assertEquals(script.slotWidth, actual.slotWidth)
                        compose.runOnIdle { assertEquals(if (original) word.original else word.translated, requireNotNull(native).visibleText()) }
                    }
                    compose.runOnIdle { shown.value = Sample(id, context, prepared, emptySet()) }
                    val restoredGuide = geometry(); same(initial, restoredGuide)
                    assertEquals(firstPrepared.slotWidth, restoredGuide.slotWidth)
                    compose.runOnIdle { assertEquals(word.displayedTarget, requireNotNull(native).visibleText()) }
                    row.put("restored_guide", restoredGuide.json())
                }
                row.put("status", "passed")
            } catch (failure: Throwable) {
                row.put("status", "failed").put("failure", failure.toString())
                device.takeScreenshot(File(output, "$id-failed.png"))
            } finally {
                compose.runOnIdle { shown.value = null }; compose.waitForIdle(); native = null; save()
            }
        }
        val passed = (0 until rows.length()).count { rows.getJSONObject(it).getString("status") == "passed" }
        report.put("complete", true).put("passed_cases", passed).put("expected_cases", 8); save()
        assertEquals("Inspect native-line-metrics report and screenshots", 8, passed)
    }
}
