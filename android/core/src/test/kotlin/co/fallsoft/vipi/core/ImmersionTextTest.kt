package co.fallsoft.vipi.core

import org.junit.Assert.*
import org.junit.Test

/** Pure projection regressions. No matcher, Android view, clipboard, model or UI execution. */
class ImmersionTextTest {
    private fun pair(left: String, right: String, gap: String = "", leftReading: String? = null,
                     rightReading: String? = null) = ImmersionResult("甲${gap}乙", "diagnostic target not an oracle", listOf(
        ImmersionSpan(0, 1, "甲", left, romanization = leftReading),
        ImmersionSpan(1 + gap.length, 2 + gap.length, "乙", right, romanization = rightReading)))
    private fun captured() = ImmersionResult("明日、一緒に昼ご飯を食べませんか。",
        "Tomorrow, do you eat lunch together?", listOf(
            ImmersionSpan(0, 2, "明日", "Tomorrow", 0, 8),
            ImmersionSpan(3, 6, "一緒に", "together", 27, 35),
            ImmersionSpan(6, 9, "昼ご飯", "lunch", 21, 26)))

    @Test fun capturedAdjacentJapaneseSlotsKeepLogicalLatinWordsDistinct() {
        assertEquals("Tomorrow、together lunchを食べませんか。", ImmersionText.project(captured()))
    }
    @Test fun capturedAllRevealedIsByteExactOriginal() {
        val r = captured()
        assertEquals(r.original, ImmersionText.project(r, r.spans.map { it.id }.toSet()))
        assertEquals(r.original, ImmersionText.project(r, r.spans.map { it.id }.toSet(), true))
    }
    @Test fun mixedCapturedRevealDoesNotDisableOtherAdjacentBoundaries() {
        assertEquals("明日、together lunchを食べませんか。", ImmersionText.project(captured(), setOf(0)))
        assertEquals("Tomorrow、一緒にlunchを食べませんか。", ImmersionText.project(captured(), setOf(3)))
        assertEquals("Tomorrow、together昼ご飯を食べませんか。", ImmersionText.project(captured(), setOf(6)))
    }
    @Test fun readingAndScriptFacesRemainDistinctPolicies() {
        val r = pair("咖啡", "茶", leftReading = "café", rightReading = "tea")
        assertEquals("café tea", ImmersionText.project(r))
        assertEquals("咖啡茶", ImmersionText.project(r, showScript = true))
        assertEquals("甲tea", ImmersionText.project(r, setOf(0)))
        assertEquals("café乙", ImmersionText.project(r, setOf(1)))
        assertEquals(r.original, ImmersionText.project(r, setOf(0, 1), true))
    }
    @Test fun mixedLatinRevealPreservesOriginalFacesButSeparatesImportedNeighbor() {
        val r = ImmersionResult("ab", "unused", listOf(
            ImmersionSpan(0, 1, "a", "hello"), ImmersionSpan(1, 2, "b", "world")))
        assertEquals("hello world", ImmersionText.project(r))
        assertEquals("a world", ImmersionText.project(r, setOf(0)))
        assertEquals("hello b", ImmersionText.project(r, setOf(1)))
        assertEquals("ab", ImmersionText.project(r, setOf(0, 1)))
    }
    @Test fun existingSourceWhitespaceIsNeverNormalizedOrDuplicated() {
        for (gap in listOf(" ", "  ", "\t", "\n", "\u00a0", "\u2009")) {
            val r = pair("hello", "world", gap)
            assertEquals("hello${gap}world", ImmersionText.project(r))
            assertEquals(r.original, ImmersionText.project(r, r.spans.map { it.id }.toSet()))
        }
    }
    @Test fun sourcePunctuationStaysExactWithoutNewSpaces() {
        for (gap in listOf(",", "、", ".", "؟", "—", "()"))
            assertEquals("hello${gap}world", ImmersionText.project(pair("hello", "world", gap)))
    }
    @Test fun displayWhitespaceOrPunctuationAlreadyProvidesBoundary() {
        for ((left, right) in listOf("hello " to "world", "hello" to " world", "hello-" to "world",
            "hello," to "world", "hello" to "(world)", "hello" to "\nworld"))
            assertEquals(left + right, ImmersionText.project(pair(left, right)))
    }
    @Test fun digitRTLGreekCyrillicAndEmojiEdgesAreNotRewritten() {
        for ((left, right) in listOf("hello" to "2", "2" to "world", "v2" to "world",
            "hello" to "2nd", "hello" to "العربية", "عربي" to "world", "hello" to "中文",
            "α" to "world", "hello" to "б", "🙂" to "world", "hello" to "🙂"))
            assertEquals(left + right, ImmersionText.project(pair(left, right)))
    }
    @Test fun LatinAndCombiningFacesPreserveTheirExactEncoding() {
        for ((left, right) in listOf("café" to "déjà", "cafe\u0301" to "lunch", "ø" to "Łódź"))
            assertEquals(left + " " + right, ImmersionText.project(pair(left, right)))
    }
    @Test fun standaloneLeadingMarksAndJoinerClustersAreNotSplitBySeparator() {
        for ((left, right) in listOf("hello" to "\u0301word", "\u0301" to "word", "a\u200d" to "word"))
            assertEquals(left + right, ImmersionText.project(pair(left, right)))
    }
    @Test fun combiningSourcePrefixAndSurrogateSuffixAndSpanOffsetsRemainExact() {
        val source = "e\u0301中文🙂"
        val spans = listOf(ImmersionSpan(2, 3, "中", "hello", 0, 5), ImmersionSpan(3, 4, "文", "world", 6, 11))
        val r = ImmersionResult(source, "hello world", spans)
        assertEquals("e\u0301hello world🙂", ImmersionText.project(r))
        assertEquals(source, ImmersionText.project(r, setOf(2, 3)))
        assertEquals(listOf(2 to 3, 3 to 4), spans.map { it.start to it.end })
        assertEquals(listOf(0 to 5, 6 to 11), spans.map { it.targetStart to it.targetEnd })
        assertEquals(source, r.original)
    }
    @Test fun selectedRangeOnlySeparatesSlotsActuallyIncludedInSelection() {
        val r = ImmersionResult("甲乙丙", "unused", listOf(
            ImmersionSpan(0, 1, "甲", "hello"), ImmersionSpan(1, 2, "乙", "world"), ImmersionSpan(2, 3, "丙", "friend")))
        assertEquals("world friend", ImmersionText.project(r, start = 1, end = 3))
        assertEquals("hello", ImmersionText.project(r, start = 0, end = 1))
        assertEquals("", ImmersionText.project(r, start = 1, end = 1))
    }
    @Test fun revealedPartialSelectionKeepsOnlyExactSelectedOriginalCodeUnits() {
        val r = ImmersionResult("ab", "unused", listOf(ImmersionSpan(0, 2, "ab", "hello")))
        assertEquals("b", ImmersionText.project(r, setOf(0), start = 1, end = 2))
        assertEquals("hello", ImmersionText.project(r, start = 1, end = 2))
    }
    @Test fun revealedPartialCombiningSourceSelectionIsNotNormalized() {
        val r = ImmersionResult("e\u0301Q", "unused", listOf(
            ImmersionSpan(0, 2, "e\u0301", "coffee"), ImmersionSpan(2, 3, "Q", "tea")))
        assertEquals(r.original.substring(1, 3), ImmersionText.project(r, setOf(0, 2), start = 1, end = 3))
    }
    @Test fun casingCompoundOrderIdentifiersAndDTOsAreNotRewritten() {
        val r = ImmersionResult("My phone battery is almost dead.", "Mi batería de teléfono está casi muerta.", listOf(
            ImmersionSpan(3, 8, "phone", "teléfono", 14, 22), ImmersionSpan(9, 16, "battery", "batería", 3, 10),
            ImmersionSpan(20, 26, "almost", "casi", 28, 32)))
        val before = r.copy(spans = r.spans.toList())
        assertEquals("My teléfono batería is casi dead.", ImmersionText.project(r))
        assertEquals(before, r)
        val case = ImmersionResult("I hardly know him.", "Apenas lo conozco.", listOf(ImmersionSpan(2, 8, "hardly", "Apenas", 0, 6)))
        assertEquals("I Apenas know him.", ImmersionText.project(case))
        val plain = ImmersionResult("ID123 https://example.test/#a", "unused", emptyList())
        assertEquals(plain.original, ImmersionText.project(plain))
    }
}
