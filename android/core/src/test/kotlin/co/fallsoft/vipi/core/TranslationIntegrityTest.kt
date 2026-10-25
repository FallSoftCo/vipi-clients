package co.fallsoft.vipi.core

import org.junit.Assert.*
import org.junit.Test

class TranslationIntegrityTest {
    @Test fun translationsMayReorderExactLiteralsAndLocalizePunctuation() {
        assertTrue(TranslationIntegrity.preservesIdentifiers(
            "Send `open()` to Ana+Work@example.test. See https://example.test/a_(b)?x=1#here, @Ana #明日.",
            "@Ana #明日 https://example.test/a_(b)?x=1#here。 Ana+Work@example.test に `open()` を送る。"))
        assertTrue(TranslationIntegrity.preservesIdentifiers("Meet at 12:30 tomorrow.", "Mañana a las 12.30."))
        assertEquals(mapOf("https://example.test/a_(b)" to 1), TranslationIntegrity.identifiers("(https://example.test/a_(b))."))
    }
    @Test fun omissionMutationDuplicationAndInventedIdentifiersFail() {
        val original = "Email Ana+Work@example.test. Open https://example.test/Case?x=1. Run `open()`. @Ana #明日"
        for ((from, to) in listOf("Ana+Work" to "ana+work", "/Case" to "/case", "?x=1" to "?x=2",
            "`open()`" to "`abrir()`", "@Ana" to "@ana", "#明日" to "#mañana", "Ana+Work@example.test" to "")) {
            assertFalse(from, TranslationIntegrity.preservesIdentifiers(original, original.replace(from, to)))
        }
        assertFalse(TranslationIntegrity.preservesIdentifiers(original, "$original https://invented.test"))
        assertFalse(TranslationIntegrity.preservesIdentifiers(original, "$original @Ana"))
    }
    @Test fun fencedAndUnclosedCodeStaysLiteralIncludingWhitespace() {
        for (code in listOf("```kotlin\nval x = 1\n```", "```kotlin\nval x = 1", "`x = 1")) {
            assertTrue(TranslationIntegrity.preservesIdentifiers("Run $code", "Exécuter $code"))
            assertFalse(TranslationIntegrity.preservesIdentifiers("Run $code", "Exécuter ${code.replace("x =", "x=")}"))
        }
        assertTrue(TranslationIntegrity.preservesIdentifiers("`mail@example.test`", "`mail@example.test`"))
    }
    @Test fun repeatedUnicodeIdentifiersKeepTheirMultiplicity() {
        assertTrue(TranslationIntegrity.preservesIdentifiers("مرحبا @朋友 @朋友", "Hello @朋友 @朋友"))
        assertFalse(TranslationIntegrity.preservesIdentifiers("مرحبا @朋友 @朋友", "Hello @朋友"))
    }
}
