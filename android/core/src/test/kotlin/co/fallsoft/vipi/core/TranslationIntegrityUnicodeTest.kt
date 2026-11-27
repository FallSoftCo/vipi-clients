package co.fallsoft.vipi.core

import org.junit.Assert.*
import org.junit.Test

/** Literal-integrity regressions only; not independent meaning-quality evidence. */
class TranslationIntegrityUnicodeTest {
    @Test
    fun decomposedMentionsAndTagsAreCapturedWhole() {
        assertEquals(
            mapOf("@cafe\u0301" to 1, "#man\u0303ana" to 1),
            TranslationIntegrity.identifiers("See @cafe\u0301 #man\u0303ana"),
        )
    }

    @Test
    fun changingOnlyAnIdentifierCombiningMarkIsRejected() {
        assertFalse(
            TranslationIntegrity.preservesIdentifiers(
                "Hello @cafe\u0301",
                "Hola @cafe\u0300",
            )
        )
    }

    @Test
    fun textAfterAnIdentifierCombiningMarkIsStillProtected() {
        assertFalse(
            TranslationIntegrity.preservesIdentifiers(
                "Hello @ma\u0301ria",
                "Hola @ma\u0301rio",
            )
        )
        assertFalse(
            TranslationIntegrity.preservesIdentifiers(
                "Hello @ma",
                "Hola @ma\u0301ria",
            )
        )
    }

    @Test
    fun aDecomposedEmailLocalPartCannotBeRewritten() {
        assertEquals(
            mapOf("cafe\u0301@example.test" to 1),
            TranslationIntegrity.identifiers("Email cafe\u0301@example.test"),
        )
        assertFalse(
            TranslationIntegrity.preservesIdentifiers(
                "Email cafe\u0301@example.test",
                "Correo otra\u0301@example.test",
            )
        )
    }

    @Test
    fun aCombiningMarkInADomainOrTldCannotBeChanged() {
        for (address in listOf("a@cafe\u0301.test", "a@example.cafe\u0301")) {
            assertEquals(mapOf(address to 1), TranslationIntegrity.identifiers(address))
            assertFalse(
                TranslationIntegrity.preservesIdentifiers(
                    address,
                    address.replace('\u0301', '\u0300'),
                )
            )
        }
    }

    @Test
    fun exactUnicodeLiteralsMayReorderWithoutNormalization() {
        val nfd = "@cafe\u0301"
        val nfc = "@caf\u00e9"
        assertTrue(
            TranslationIntegrity.preservesIdentifiers(
                "🙂 $nfd $nfc #明日",
                "#明日 $nfc $nfd 👩🏽‍💻",
            )
        )
        // Exact-literal comparison deliberately does not normalize distinct bytes.
        assertFalse(TranslationIntegrity.preservesIdentifiers(nfd, nfc))
        assertFalse(TranslationIntegrity.preservesIdentifiers("$nfd $nfd", nfd))
    }

    @Test
    fun codeContainingCombiningMarksRemainsExact() {
        val code = "`val cafe\u0301 = 1`"
        assertTrue(TranslationIntegrity.preservesIdentifiers("Run $code", "Ejecuta $code"))
        assertFalse(
            TranslationIntegrity.preservesIdentifiers(code, code.replace('\u0301', '\u0300'))
        )
    }
}
