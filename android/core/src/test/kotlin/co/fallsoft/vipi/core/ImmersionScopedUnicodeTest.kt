package co.fallsoft.vipi.core

import org.junit.Assert.*
import org.junit.Test

/** Scope safety, not translation quality. Every rejection has an intact-scope control. */
class ImmersionScopedUnicodeTest {
    private fun align(original: String, translation: String, entry: VocabularyEntry): ImmersionResult =
        ImmersionEngine().align(
            original, translation, listOf(entry), 1.0, "es",
            setOf(0, original.length), setOf(0, translation.length), 1
        )

    private fun scopedSource(original: String, focus: String, end: Int, target: String = "coffee") =
        VocabularyEntry(focus, listOf(target), sourceScope = VocabularySourceScope(original, 0, end))

    private fun scopedTarget(translation: String, focus: String, end: Int, original: String = "coffee") =
        VocabularyEntry(original, listOf(focus), sourceScope = VocabularySourceScope(original, 0, original.length),
            targetScope = VocabularyTargetScope(translation, 0, end))

    @Test fun sourceScopeCannotDropATrailingCombiningMark() {
        val original = "cafe\u0301"
        val intact = align(original, "coffee", scopedSource(original, original, original.length))
        assertEquals(1, intact.spans.size)
        assertEquals(original, intact.original)
        assertEquals(original, ImmersionText.project(intact, setOf(0)))
        val split = align(original, "coffee", scopedSource(original, "cafe", 4))
        assertEquals(original, split.original)
        assertTrue("source scope split before accent must be rejected", split.spans.isEmpty())
        assertEquals(original, ImmersionText.project(split))
    }

    @Test fun targetScopeCannotDropATrailingCombiningMark() {
        val translation = "cafe\u0301"
        val intact = align("coffee", translation, scopedTarget(translation, translation, translation.length))
        assertEquals(1, intact.spans.size)
        assertEquals(translation, intact.spans.single().translated)
        val split = align("coffee", translation, scopedTarget(translation, "cafe", 4))
        assertEquals("coffee", split.original)
        assertTrue("target scope split before accent must be rejected", split.spans.isEmpty())
        assertEquals("coffee", ImmersionText.project(split))
    }

    @Test fun sourceScopeCannotSplitAnEmojiZwjSequence() {
        val original = "👩\u200d💻"
        val intact = align(original, "developer", scopedSource(original, original, original.length, "developer"))
        assertEquals(1, intact.spans.size)
        assertEquals(original, ImmersionText.project(intact, setOf(0)))
        val split = align(original, "developer", scopedSource(original, "👩", 2, "developer"))
        assertTrue("valid UTF16 endpoint inside ZWJ grapheme is not a valid scope", split.spans.isEmpty())
        assertEquals(original, split.original)
        assertEquals(original, ImmersionText.project(split))
    }

    @Test fun targetScopeCannotSplitAnEmojiZwjSequence() {
        val translation = "👩\u200d💻"
        val intact = align("developer", translation, scopedTarget(translation, translation, translation.length, "developer"))
        assertEquals(1, intact.spans.size)
        val split = align("developer", translation, scopedTarget(translation, "👩", 2, "developer"))
        assertTrue("valid UTF16 endpoint inside ZWJ grapheme is not a valid scope", split.spans.isEmpty())
        assertEquals("developer", ImmersionText.project(split))
    }

    @Test fun targetFormCannotDropATrailingCombiningMark() {
        val translation = "cafe\u0301"
        val intact = align("coffee", translation, VocabularyEntry(
            "coffee", listOf(translation), sourceScope = VocabularySourceScope("coffee", 0, 6),
            targetForms = listOf(VocabularyTargetForm(translation, translation, 0, translation.length))
        ))
        assertEquals(1, intact.spans.size)
        val split = align("coffee", translation, VocabularyEntry(
            "coffee", listOf("cafe"), sourceScope = VocabularySourceScope("coffee", 0, 6),
            targetForms = listOf(VocabularyTargetForm(translation, "cafe", 0, 4))
        ))
        assertTrue("target-form focus split before accent must be rejected", split.spans.isEmpty())
        assertEquals("coffee", split.original)
        assertEquals("coffee", ImmersionText.project(split))
    }

    @Test fun intentionalKoreanSourceAndTargetCarrierScopesStillWork() {
        val source = align("책을", "book", VocabularyEntry(
            "책", listOf("book"), sourceScope = VocabularySourceScope("책을", 0, 1)
        ))
        assertEquals(1, source.spans.size)
        assertEquals(0, source.spans.single().start)
        assertEquals(1, source.spans.single().end)
        assertEquals("책을", source.original)
        assertEquals("책을", ImmersionText.project(source, setOf(0)))
        val target = align("book", "책을", VocabularyEntry(
            "book", listOf("책"), sourceScope = VocabularySourceScope("book", 0, 4),
            targetScope = VocabularyTargetScope("책을", 0, 1)
        ))
        assertEquals(1, target.spans.size)
        assertEquals("책", target.spans.single().translated)
        assertEquals("book", ImmersionText.project(target, setOf(0)))
    }
}
