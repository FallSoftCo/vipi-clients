package co.fallsoft.vipi.core

import org.junit.Assert.*
import org.junit.Test

/** Source-arithmetic regressions; ranges are explicit, NOT Android segmentation proof. */
class ReferenceCompositionTest {
    private fun joined(source: String, language: String = "en"): String? {
        val last = source.indexOf("下周见。")
        return ReferenceComposition.compose(source, listOf(0 until 3, last until last + 4), language) {
            when (it) { "你好。" -> if (language == "ja") "こんにちは。" else "Hello."
                "下周见。" -> if (language == "ja") "来週会いましょう。" else "See you next week."
                else -> null }
        }
    }
    @Test fun adjacentKnownSentencesHaveATargetSentenceBoundary() {
        assertEquals("Hello. See you next week.", joined("你好。下周见。"))
    }
    @Test fun spacesNewlinesAndLeadingTrailingGapsRemainExact() {
        assertEquals("Hello. See you next week.", joined("你好。 下周见。"))
        assertEquals("Hello.\nSee you next week.", joined("你好。\n下周见。"))
        assertEquals("Hello.\tSee you next week.", joined("你好。\t下周见。"))
    }
    @Test fun cjkTargetDoesNotGainLatinSpacing() {
        assertEquals("こんにちは。来週会いましょう。", joined("你好。下周见。", "ja"))
    }
    @Test fun unknownSentenceOrNonWhitespaceGapCannotInventAWholeTranslation() {
        assertNull(ReferenceComposition.compose("你好。unknown", listOf(0 until 3, 3 until 10), "en") {
            if (it == "你好。") "Hello." else null })
        assertNull(ReferenceComposition.compose("你好。X下周见。", listOf(0 until 3, 4 until 8), "en") { "known" })
    }
    @Test fun exactValuesAreNotNormalizedOrCaseFolded() {
        val values = mapOf("你好。" to "Cafe\u0301!", "下周见。" to "See you.")
        assertEquals("Cafe\u0301! See you.", ReferenceComposition.compose("你好。下周见。", listOf(0 until 3,3 until 7),"en",values::get))
    }
}
