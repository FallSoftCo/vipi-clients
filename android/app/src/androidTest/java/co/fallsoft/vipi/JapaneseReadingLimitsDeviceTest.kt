package co.fallsoft.vipi

import android.os.SystemClock
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.MessageDigest

/** Bounded diagnostic only; the Japanese component remains dormant. */
class JapaneseReadingLimitsDeviceTest {
    @Test fun retainsSourceAtMaximumLiteralBoundaries() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val samples = linkedMapOf(
            "trailing-punctuation" to ("https://example.com/" + "a".repeat(8000) + ".".repeat(8000)),
            "trailing-brackets" to ("https://example.com/" + "a".repeat(8000) + ")".repeat(8000)),
            "balanced-brackets" to ("https://example.com/" + "(".repeat(8000) + ")".repeat(8000)),
            "alternating-kana-literals" to "カナ `id42` ".repeat(1500)
        )
        val rows = JSONArray()
        for ((id, text) in samples) {
            assertTrue(text.length <= 16384)
            val start = SystemClock.elapsedRealtimeNanos(); val value = JapaneseReadings.read(text)
            val elapsed = (SystemClock.elapsedRealtimeNanos() - start) / 1e6
            assertEquals(text, value.pieces.joinToString("") { it.original })
            assertTrue(value.pieces.all { text.substring(it.start, it.end) == it.original })
            val encoded = JSONObject().put("reading", value.reading ?: JSONObject.NULL)
                .put("pieces", JSONArray(value.pieces.map { JSONObject().put("start", it.start).put("end", it.end)
                    .put("original", it.original).put("value", it.value).put("kind", it.kind.name) }))
                .put("issues", JSONArray(value.issues.map { it.name })).toString()
            rows.put(JSONObject().put("id", id).put("input_utf16", text.length).put("elapsed_ms", elapsed)
                .put("exact_source_reconstruction", true).put("pieces", value.pieces.size)
                .put("output_sha256", MessageDigest.getInstance("SHA-256").digest(encoded.toByteArray()).joinToString("") { "%02x".format(it) }))
        }
        File(context.filesDir, "japanese-reading-limits.json").writeText(JSONObject().put("complete", true)
            .put("production_enabled", false).put("cases", rows).toString(2))
    }
}
