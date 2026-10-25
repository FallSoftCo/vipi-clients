package co.fallsoft.vipi.core

import org.junit.Test
import org.junit.Assert.*

class ContextEvidenceTest {
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
