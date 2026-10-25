package co.fallsoft.vipi.core

import org.junit.Assert.*
import org.junit.Test

class ContextMappingTest {
    private fun book(plural: Boolean = false) = ContextMapping("book", "book as reading material", "en", "es", listOf(
        ContextPart.Literal("Can "), ContextPart.Slot(listOf("you", "they", "we")),
        ContextPart.Literal(" bring "), ContextPart.Slot(listOf("my", "your", "their", "our")),
        ContextPart.Literal(" "), ContextPart.Focus(if (plural) "books" else "book"), ContextPart.Literal("?")
    ), listOf(if (plural) "libros" else "libro"))
    private fun result(original: String, translation: String, rows: List<ContextMapping> = listOf(book(), book(true))) =
        ImmersionEngine().align(original, translation, ContextMappingMatcher.entries(original,"en","es",rows),1.0,"es")

    @Test fun finitePersonAndPossessorVariantsReplaceOnlyTheBook() {
        for ((original, translated, expected) in listOf(
            Triple("Can you bring my book?", "¿Puedes traer mi libro?", "Can you bring my libro?"),
            Triple("Can you bring your book?", "¿Puedes traer tu libro?", "Can you bring your libro?"),
            Triple("Can they bring their books?", "¿Pueden traer sus libros?", "Can they bring their libros?")
        )) {
            val aligned = result(original,translated)
            assertEquals(1, aligned.spans.size)
            assertEquals(expected, aligned.speech("en","es").joinToString("") { it.text })
        }
    }
    @Test fun unknownContextWrongPairAndChangedNumberDoNotReuseAnExample() {
        assertTrue(result("Can you book my flight?", "¿Puedes reservar mi vuelo?").spans.isEmpty())
        assertTrue(result("Can you bring her book?", "¿Puedes traer su libro?").spans.isEmpty())
        assertTrue(result("Can you bring my books?", "¿Puedes traer mis libros?",listOf(book())).spans.isEmpty())
        assertTrue(ContextMappingMatcher.entries("Can you bring my book?","es","en",listOf(book())).isEmpty())
    }
    @Test fun competingMeaningAndMissingWholeTranslationEvidenceWithhold() {
        assertTrue(result("Can you bring my book?", "¿Puedes traer mi libro?",listOf(book(),book().copy(id="conflict",meaning="reservation"))).spans.isEmpty())
        assertTrue(result("Can you bring my book?", "¿Puedes traer mi cuaderno?").spans.isEmpty())
    }
    @Test fun nonRomanRequiresOneReadableTransliteration() {
        val original = "Can you bring my book?"; val translated = "私の本を持ってきてくれる？"
        fun align(record: ContextMapping) = ImmersionEngine().align(original, translated,
            ContextMappingMatcher.entries(original,"en","ja",listOf(record)),1.0,"ja",
            targetBoundaries=setOf(0,1,2,3,translated.length))
        val mapping = book().copy(targetLanguage="ja",targets=listOf("本"))
        assertTrue(align(mapping).spans.isEmpty())
        assertEquals("hon",align(mapping.copy(readings=mapOf("本" to listOf("hon")))).spans.single().romanization)
    }
    @Test fun ambiguousFocusParsingAndUnboundedSlotsAreRejected() {
        val ambiguous = ContextMapping("ambiguous","fixture","en","es",listOf(ContextPart.Literal("x"),
            ContextPart.Slot(listOf("a","aa")),ContextPart.Focus("a"),ContextPart.Slot(listOf("a","aa"))),listOf("b"))
        assertTrue(ContextMappingMatcher.entries("xaaaa","en","es",listOf(ambiguous)).isEmpty())
        val overflow = book().copy(parts=listOf(ContextPart.Literal("Can "),ContextPart.Slot(List(33) { "$it" }),ContextPart.Focus("book")))
        assertTrue(ContextMappingMatcher.entries("Can 1book","en","es",listOf(overflow)).isEmpty())
    }
}
