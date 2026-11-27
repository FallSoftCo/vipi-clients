package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class KoreanReadingsDeviceTest {
    @Test
    fun shortReadingsPreserveLiteralUnicodeAndCompleteSourceRanges() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val rows = JSONArray()
        for (text in
            listOf(
                "한글",
                "한글 cafe\u0301 \uD83D\uDE42 https://example.test/9",
                "https://example.test/한글",
            )) {
            val value = KoreanReadings.resolve(text)
            assertEquals(text, value.pieces.joinToString("") { it.source })
            assertTrue(value.pieces.isNotEmpty())
            assertEquals(0, value.pieces.first().startUTF16)
            assertEquals(text.length, value.pieces.last().endUTF16)
            assertTrue(value.pieces.zipWithNext().all { (a, b) -> a.endUTF16 == b.startUTF16 })
            value.pieces.forEach { piece ->
                assertEquals(piece.source, text.substring(piece.startUTF16, piece.endUTF16))
                for (edge in listOf(piece.startUTF16, piece.endUTF16)) if (
                    edge in 1 until text.length
                )
                    assertFalse(text[edge - 1].isHighSurrogate() && text[edge].isLowSurrogate())
                if (piece.kind == "opaque") assertEquals(piece.source, piece.rendered)
            }
            if (text == "한글") assertEquals("hangeul", value.reading)
            else if (text.startsWith("한글")) {
                assertTrue(requireNotNull(value.reading).startsWith("hangeul"))
                for (literal in
                    listOf("cafe\u0301", "\uD83D\uDE42", "https://example.test/9")) assertTrue(
                    value.reading!!.contains(literal)
                )
            } else {
                assertNull(value.reading)
                assertEquals(text, value.inspection)
            }
            assertTrue(value.issues.isEmpty())
            rows.put(
                JSONObject()
                    .put("original", text)
                    .put("reading", value.reading ?: JSONObject.NULL)
                    .put("issues", JSONArray(value.issues))
            )
        }
        readingRegressionFile(context, "korean-short-readings-native.json")
            .writeText(JSONObject().put("passed", true).put("cases", rows).toString(2))
    }
}
