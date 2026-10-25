package co.fallsoft.vipi.core

import org.junit.Test
import org.junit.Assert.*

class ContextEvidenceTest {
    @Test fun unmappedOrConflictingEvidenceCannotBeOverruledByAnotherCue() {
        val entries = listOf(VocabularyEntry("bank", listOf("banco"), contextHints = listOf("institution"), requiresContext = true),
            VocabularyEntry("bank", emptyList(), contextHints = listOf("river"), requiresContext = true))
        assertEquals(1, ImmersionEngine().align("The bank is an institution.", "banco", entries, 1.0).spans.size)
        for (text in listOf("Walk by the river bank.", "The institution is by the river bank.", "Go to the bank.")) {
            assertTrue(ImmersionEngine().align(text, "banco", entries, 1.0).spans.isEmpty())
        }
    }
    @Test fun multipleMeaningsNeedSentenceLocalEvidence() {
        val engine = ImmersionEngine()
        val entries = listOf(
            VocabularyEntry("period", listOf("período"), contextHints = listOf("time"), requiresContext = true),
            VocabularyEntry("period", listOf("punto"), contextHints = listOf("punctuation"), requiresContext = true))
        for (text in listOf("The period ends this sentence.", "The period ends here. Another time.", "The period uses `time`.", "The period has https://example.test/time")) {
            assertTrue(engine.align(text, "período", entries, 1.0).spans.isEmpty())
        }
        assertEquals(1, engine.align("A period of time.", "período", entries, 1.0).spans.size)
        assertTrue(engine.align("A period is punctuation.", "período", entries, 1.0).spans.isEmpty())
        assertEquals(1, engine.align("A period is punctuation.", "punto", entries, 1.0).spans.size)
        assertTrue(engine.align("A period of time.", "período punto", entries, 1.0).spans.isEmpty())
    }
    @Test fun competingSourceContextVetoesMistranslatedPolysemy() {
        for ((word, cue, wrong, right) in listOf(listOf("bank", "river", "banco", "orilla"), listOf("mouse", "computer", "ratón animal", "ratón informático"), listOf("crane", "construction", "grulla", "grúa"))) {
            val entries = listOf(VocabularyEntry(word, listOf(wrong), contextHints = listOf("animal", "institution")), VocabularyEntry(word, listOf(right), contextHints = listOf(cue)))
            assertTrue(ImmersionEngine().align("The $word is beside the $cue.", wrong, entries, 1.0).spans.isEmpty())
            assertEquals(1, ImmersionEngine().align("The $word is beside the $cue.", right, entries, 1.0).spans.size)
        }
    }
    @Test fun cuesDoNotCrossSentencesOrComeFromProtectedIdentifiers() {
        val entries = listOf(VocabularyEntry("bank", listOf("banco"), contextHints = listOf("institution")), VocabularyEntry("bank", listOf("orilla"), contextHints = listOf("river")))
        for (text in listOf("Go to the bank. Then see the river.", "The bank has https://example.test/river", "The bank uses `river`.")) {
            assertEquals(1, ImmersionEngine().align(text, "banco", entries, 1.0).spans.size)
        }
        assertTrue(ImmersionEngine().align("The bank is by the river.", "banco orilla", entries, 1.0).spans.isEmpty())
    }
    @Test fun arabicVowelsPreserveOriginalRangesAndReadingUncertainty() {
        val entry = VocabularyEntry("coffee", listOf("قَهْوَة"), mapOf("قَهْوَة" to listOf("qahwa")))
        for (value in listOf("قهوة", "قَهْوَة", "قَـهْوَة")) {
            val result = ImmersionEngine().align("coffee", value, listOf(entry), 1.0, "ar")
            assertEquals(value, result.spans.single().translated)
            assertEquals("qahwa", result.spans.single().displayedTarget)
            assertEquals(value, result.speech("en", "ar").single().text)
        }
        val uncertain = VocabularyEntry("flag", listOf("عَلَم", "عِلْم"), mapOf("عَلَم" to listOf("alam"), "عِلْم" to listOf("ilm")))
        assertTrue(ImmersionEngine().align("flag", "علم", listOf(uncertain), 1.0, "ar").spans.isEmpty())
        assertNotEquals(ImmersionEngine.lookupKey("أمل"), ImmersionEngine.lookupKey("امل"))
    }
}
