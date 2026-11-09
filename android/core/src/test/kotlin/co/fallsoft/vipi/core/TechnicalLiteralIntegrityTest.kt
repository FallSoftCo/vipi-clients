package co.fallsoft.vipi.core

import org.junit.Assert.*
import org.junit.Test

class TechnicalLiteralIntegrityTest {
    @Test fun technicalTokensPreserveBytesAndRepeatedOccurrences() {
        for (token in listOf("coffee_today.txt", "music_notes", "_music_notes", "music__notes", "music.txt_notes", ".music_notes", "music_notes_", "music..notes_", "music.txt", "family-notes.json", "music.tar.gz", "music.JPG", "music.vipihistory", "cafe\u0301_notes.txt", "家族_notes.pdf")) {
            assertEquals(token, mapOf(token to 1), TranslationIntegrity.identifiers(token))
            assertTrue(token, TranslationIntegrity.preservesIdentifiers("Send $token.", "送る $token。"))
            assertFalse(token, TranslationIntegrity.preservesIdentifiers("Send $token.", "送る renamed_$token。"))
            assertFalse(token, TranslationIntegrity.preservesIdentifiers("$token $token", token))
        }
        assertFalse(TranslationIntegrity.preservesIdentifiers("coffee_today.txt", "コーヒー_today.txt"))
        assertFalse(TranslationIntegrity.preservesIdentifiers("cafe\u0301_notes.txt", "caf\u00e9_notes.txt"))
        assertTrue(TranslationIntegrity.preservesIdentifiers("music.txt, family_notes.json", "family_notes.json、music.txt。"))
    }
    @Test fun ordinaryTextAndExistingLiteralPrecedence() {
        assertTrue(TranslationIntegrity.preservesIdentifiers("Have coffee after work.", "仕事の後でコーヒーを飲む。"))
        assertTrue(TranslationIntegrity.preservesIdentifiers("back.big dogs", "戻る。大きな犬"))
        assertTrue(TranslationIntegrity.preservesIdentifiers("Meet at 12:30. Pay 1.25.", "12.30に会う。1,25を払う。"))
        assertEquals(mapOf("`music_notes.txt`" to 1, "@music_notes" to 1, "music_notes@example.test" to 1, "https://example.test/music_notes.txt" to 1), TranslationIntegrity.identifiers("`music_notes.txt` @music_notes music_notes@example.test https://example.test/music_notes.txt"))
    }
}
