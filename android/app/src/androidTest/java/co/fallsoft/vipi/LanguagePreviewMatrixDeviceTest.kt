package co.fallsoft.vipi

import android.graphics.Bitmap
import android.graphics.Canvas
import android.view.View
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

@RunWith(AndroidJUnit4::class)
class LanguagePreviewMatrixDeviceTest {
    @Test fun nativeTokenizationAndParagraphLayoutAcrossNinetyDirections() {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val output = File(context.filesDir, "reading-matrix-001").apply { mkdirs() }
        File(output, "report.json").delete()
        val rows = JSONArray()
        val languages = initialLanguages.map { it.code }
        for (source in languages) for (target in languages.filter { it != source }) {
            val result = ConversationExamples.result(context, source, target)
            assertTrue("No contextual preview vocabulary $source->$target", result.spans.isNotEmpty())
            if (target in listOf("ar", "zh", "ja", "ko")) assertTrue(result.spans.all { !it.romanization.isNullOrBlank() })
            val sourceSpeech = result.speech(source, target, result.spans.map { it.id }.toSet()).joinToString("") { it.text }
            assertEquals(result.original, sourceSpeech)
            val measurements = JSONArray()
            instrumentation.runOnMainSync {
                val view = StableImmersionText(context).apply { layoutParams = android.view.ViewGroup.LayoutParams(android.view.ViewGroup.LayoutParams.MATCH_PARENT, android.view.ViewGroup.LayoutParams.WRAP_CONTENT) }
                for (width in listOf(280, 360, 620)) for (scale in listOf(1f, 1.6f, 2.2f)) {
                    view.setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, 17 * scale)
                    var height: Int? = null
                    var anchors: List<Pair<Float, Int>>? = null
                    for ((face, revealed) in listOf("target" to emptySet<Int>(), "meaning" to result.spans.map { it.id }.toSet(), "script" to emptySet())) {
                        view.bind(result, revealed, face == "script", 0xff2b6142.toInt(), 0xff18251d.toInt())
                        val pixels = (width * context.resources.displayMetrics.density).toInt()
                        view.measure(View.MeasureSpec.makeMeasureSpec(pixels, View.MeasureSpec.EXACTLY), View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
                        view.layout(0, 0, view.measuredWidth, view.measuredHeight)
                        if (height == null) height = view.height else assertEquals("Bubble jumps $source->$target width=$width scale=$scale", height, view.height)
                        assertTrue("Clipped text $source->$target", view.layout.height <= view.height)
                        assertTrue(view.visibleText().isNotBlank())
                        val positions = (0..result.original.length).map { offset -> view.layout.getPrimaryHorizontal(offset) to view.layout.getLineBaseline(view.layout.getLineForOffset(offset)) }
                        if (anchors == null) anchors = positions else assertEquals("Inline text shifts $source->$target width=$width scale=$scale", anchors, positions)
                        if (face == "meaning") assertEquals(result.original, view.visibleText())
                        if (width == 360 && scale == 1f) {
                            val bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
                            Canvas(bitmap).apply { drawColor(0xffffffff.toInt()); view.draw(this) }
                            File(output, "$source-$target-$face.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }; bitmap.recycle()
                        }
                    }
                    measurements.put(JSONObject().put("widthDp", width).put("fontScale", scale).put("heightPx", height))
                }
            }
            rows.put(JSONObject().put("source", source).put("target", target).put("selected", result.spans.size)
                .put("readings", JSONArray(result.spans.map { it.displayedTarget })).put("measurements", measurements))
        }
        assertEquals(90, rows.length())
        File(output, "report.json").writeText(JSONObject().put("status", "passed").put("directions", rows)
            .put("evidence", "authored_preview_fixed_inline_blocks_native_tokenization_and_stable_glyph_positions_not_live_translation_or_linguistic_acceptance").toString(2))
    }
}
