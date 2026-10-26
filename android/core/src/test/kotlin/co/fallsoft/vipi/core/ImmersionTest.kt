package co.fallsoft.vipi.core

import java.time.Instant
import org.junit.Assert.*
import org.junit.Test

class ImmersionTest {
    private val engine = ImmersionEngine()
    @Test fun nativeSourceEvidenceProtectsUnmappedCompoundsAndOmittedSenses() {
        val blue=VocabularyEntry("蓝",listOf("blue"))
        val herb=VocabularyEntry("板蓝根",emptyList(),protectInner=true)
        val bounds=setOf(0,1,2,3)
        assertEquals(1,engine.align("板蓝根","blue root",listOf(blue),1.0,sourceBoundaries=bounds).spans.size)
        assertTrue(engine.align("板蓝根","blue root",listOf(blue,herb),1.0,sourceBoundaries=bounds).spans.isEmpty())
        // A known whole-word mapping remains possible; nearby compounds do not
        // suppress an independent color occurrence.
        val whole=VocabularyEntry("板蓝根",listOf("herb"))
        assertEquals(1,engine.align("板蓝根","herb",listOf(whole,herb),1.0,sourceBoundaries=bounds).spans.size)
        assertEquals(1,engine.align("蓝 板蓝根","blue herb",listOf(blue,herb),1.0,sourceBoundaries=setOf(0,1,2,5)).spans.size)
        val moon=VocabularyEntry("满月",listOf("full moon"))
        val ambiguity=VocabularyEntry("满月",emptyList(),protectInner=true,unresolvedNativeSenses=true)
        assertTrue(engine.align("满月","full moon",listOf(moon,ambiguity),1.0).spans.isEmpty())
        // Only the separately reviewed, message-bound path can resolve it.
        val assessed=moon.copy(sourceScope=VocabularySourceScope("满月",0,2))
        assertEquals(1,engine.align("满月","full moon",listOf(assessed,ambiguity),1.0).spans.size)
    }
    @Test fun nativeWordBoundariesSupportUnspacedScriptsWithoutPartialMatches() {
        val entry = VocabularyEntry("coffee", listOf("咖啡"), mapOf("咖啡" to listOf("kafei")))
        val result = engine.align("Want coffee?", "明天喝咖啡。", listOf(entry), 1.0, "zh", targetBoundaries = setOf(0, 2, 3, 5))
        assertEquals("咖啡", result.spans.single().translated)
        val partial = VocabularyEntry("coffee", listOf("咖"), mapOf("咖" to listOf("ka")))
        assertTrue(engine.align("Want coffee?", "明天喝咖啡。", listOf(partial), 1.0, "zh", targetBoundaries = setOf(0, 2, 3, 5)).spans.isEmpty())
    }
    @Test fun protectedTargetIsNotContextEvidence() {
        for (translation in listOf("https://example.test/cafe", "`cafe`", "@cafe"))
            assertTrue(engine.align("coffee", translation, listOf(VocabularyEntry("coffee", listOf("cafe"))), 1.0).spans.isEmpty())
    }
    @Test fun mandatoryReadingIsSeparateFromSpeechAndMissingReadingsAbstain() {
        val entry = VocabularyEntry("coffee", listOf("咖啡"), mapOf("咖啡" to listOf("kafei")))
        val result = engine.align("Want coffee?", "咖啡", listOf(entry), 1.0, targetLanguage = "zh")
        assertEquals("kafei", result.spans.single().displayedTarget)
        assertEquals("咖啡", result.spans.single().translated)
        assertEquals("Want 咖啡?", result.speech("en", "zh").joinToString("") { it.text })
        assertEquals("Want coffee?", result.speech("en", "zh", setOf(result.spans.single().id)).joinToString("") { it.text })
        assertTrue(engine.align("coffee", "咖啡", listOf(entry.copy(romanizations = emptyMap())), 1.0, "zh").spans.isEmpty())
        assertTrue(engine.align("coffee", "咖啡", listOf(entry.copy(romanizations = mapOf("咖啡" to listOf("kafei", "wrong")))), 1.0, "zh").spans.isEmpty())
        assertTrue(engine.align("coffee", "咖啡", listOf(entry, entry.copy(romanizations = mapOf("咖啡" to listOf("other")))), 1.0, "zh").spans.isEmpty())
    }
    @Test fun duplicateEntriesCannotHideMultipleSenses() {
        val entries = listOf(VocabularyEntry("bank", listOf("banco")), VocabularyEntry("Bank", listOf("orilla")))
        assertTrue(engine.align("The bank is nearby.", "El banco está en la orilla.", entries, 1.0).spans.isEmpty())
        assertEquals(1, engine.align("coffee", "Café", listOf(VocabularyEntry("coffee", listOf("café", "Café"))), 1.0).spans.size)
    }
    @Test fun sentenceContextSelectsSense() {
        val words = listOf(VocabularyEntry("bank", listOf("banco", "orilla")))
        assertEquals(listOf("orilla"), engine.align("Meet at the river bank.", "Nos vemos en la orilla del río.", words, .3).spans.map { it.translated })
        assertEquals(listOf("banco"), engine.align("I am going to the bank.", "Voy al banco.", words, .3).spans.map { it.translated })
        assertTrue(engine.align("The bank is by the bank.", "El banco está junto a la orilla.", words, 1.0).spans.isEmpty())
        assertTrue(engine.align("The bank is nearby.", "El banco está en la orilla.", words, 1.0).spans.isEmpty())
    }
    @Test fun identifiersAndSubstringsStayUnchanged() {
        val entries = listOf(VocabularyEntry("cat", listOf("gato")))
        for (source in listOf("https://cat.example", "mycat@example.com", "`cat`", "@cat", "scatter")) {
            assertTrue(engine.align(source, "gato", entries, 1.0).spans.isEmpty())
        }
    }
    @Test fun unicodeSpeechMatchesVisibleRepresentation() {
        val result = engine.align("👩🏽‍💻 Want coffee?", "¿Quieres café?", listOf(VocabularyEntry("coffee", listOf("café"))), 1.0)
        assertEquals("👩🏽‍💻 Want café?", result.speech("en", "es").joinToString("") { it.text })
        assertEquals(listOf("en", "es", "en"), result.speech("en", "es").map { it.language })
        assertEquals(result.original, result.speech("en", "es", result.spans.map { it.id }.toSet()).joinToString("") { it.text })
    }
    @Test fun longerPhrasesDoNotOverlap() {
        val result = engine.align("See you in the morning.", "Nos vemos por la mañana.", listOf(VocabularyEntry("in the morning", listOf("por la mañana")), VocabularyEntry("morning", listOf("mañana"))), 1.0)
        assertEquals(listOf("in the morning"), result.spans.map { it.original })
    }
    @Test fun conflictingTargetAbstains() {
        val result = engine.align("A house and a home.", "Una casa.", listOf(VocabularyEntry("house", listOf("casa")), VocabularyEntry("home", listOf("casa"))), 1.0)
        assertTrue(result.spans.isEmpty())
    }
    @Test fun ineligibleEntriesStillPreserveAlignmentUncertainty() {
        val result = engine.align("Only the best way and best behavior.", "最好的方式和行为。", listOf(
            VocabularyEntry("only", listOf("最好的"), mapOf("最好的" to listOf("zuìhǎo de"))),
            VocabularyEntry("best", listOf("最好的"), mapOf("最好的" to listOf("zuìhǎo de")))
        ), 1.0, "zh", targetBoundaries = setOf(0,3,5,6,8))
        assertTrue(result.spans.isEmpty())
        val one = VocabularyEntry("read", listOf("読む"), mapOf("読む" to listOf("yomu")))
        val conflict = one.copy(romanizations = mapOf("読む" to listOf("yomu","doku")))
        assertTrue(engine.align("read", "読む", listOf(one,conflict), 1.0,"ja").spans.isEmpty())
        assertTrue(engine.align("bank", "banco orilla", listOf(VocabularyEntry("bank",listOf("banco")),VocabularyEntry("bank",listOf("banco","orilla"))),1.0).spans.isEmpty())
    }
    @Test fun expiresAtOriginalSeventyTwoHours() {
        val sent = Instant.ofEpochSecond(1_000_000)
        val window = DeliveryWindow(createdAt = sent)
        assertTrue(window.canRetry(sent.plusSeconds(259_199), DeliveryState.ACCEPTED))
        assertFalse(window.canRetry(sent.plusSeconds(259_200), DeliveryState.QUEUED))
        assertFalse(window.canRetry(sent, DeliveryState.DELIVERED))
    }
    @Test fun familiarLatinReadingsKeepAccentsButRejectPhoneticGlyphs() {
        val engine = ImmersionEngine()
        for (reading in listOf("kāfēi", "kōhī", "mu'jam", "sŏul")) {
            val entries = listOf(VocabularyEntry("coffee", listOf("咖啡"), mapOf("咖啡" to listOf(reading))))
            assertEquals(reading, engine.align("coffee", "咖啡", entries, 1.0, "zh").spans.single().displayedTarget)
        }
        for (reading in listOf("ɡa", "ʰa", "ᴀ", "...", "コーヒー", "kafei / other")) {
            val entries = listOf(VocabularyEntry("coffee", listOf("咖啡"), mapOf("咖啡" to listOf(reading))))
            assertTrue(engine.align("coffee", "咖啡", entries, 1.0, "zh").spans.isEmpty())
        }
    }
}
