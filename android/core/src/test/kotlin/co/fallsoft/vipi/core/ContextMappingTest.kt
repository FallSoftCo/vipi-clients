package co.fallsoft.vipi.core

import org.junit.Assert.*
import org.junit.Test

class ContextMappingTest {
    @Test fun typographicApostrophesMatchWithoutChangingStoredText() {
        val result=ImmersionEngine().align("I work today.","Je travaille aujourd'hui.",listOf(VocabularyEntry("today",listOf("aujourd’hui"))),1.0,"fr")
        assertEquals("aujourd'hui",result.spans.single().translated)
        assertEquals("Je travaille aujourd'hui.",result.translation)
    }

    @Test fun targetParticlesRequireAnExplicitAttestedFormAndExactSourceContext() {
        val text="I read a book."
        val mapping=ContextMapping("book-en","reading material","en","ko",listOf(ContextPart.Literal("I read a "),
            ContextPart.Focus("book"),ContextPart.Literal(".")),listOf("책"),mapOf("책" to listOf("chaek")),
            listOf(VocabularyTargetForm("책을","책",0,1)))
        val entries=ContextMappingMatcher.entries(text,"en","ko",listOf(mapping))
        fun align(translation:String,rows:List<VocabularyEntry> = entries)=ImmersionEngine().align(text,translation,rows,1.0,"ko",targetBoundaries=setOf(0,2,translation.length))
        assertEquals("chaek",align("책을 읽어요.").spans.single().romanization)
        assertEquals("책",align("책을 읽어요.").spans.single().translated)
        assertTrue(align("책상 위에 있어요.").spans.isEmpty())
        assertTrue(align("책을 읽어요.",listOf(entries.single().copy(sourceScope=null))).spans.isEmpty())
        assertTrue(align("책을 읽어요.",listOf(entries.single().copy(targetForms=listOf(VocabularyTargetForm("책을","책",0,2))))).spans.isEmpty())
    }

    @Test fun exactKoreanFocusPreservesParticleAndCannotEscapeItsContext() {
        val text="책을 읽고 있어요."
        val mapping=ContextMapping("book-ko","book as reading material","ko","en",
            listOf(ContextPart.Focus("책"),ContextPart.Literal("을 읽고 있어요.")),listOf("book"))
        val entries=ContextMappingMatcher.entries(text,"ko","en",listOf(mapping))
        val engine=ImmersionEngine()
        val result=engine.align(text,"I am reading a book.",entries,1.0,"en",sourceBoundaries=setOf(0,2,text.length))
        assertEquals("book을 읽고 있어요.",result.speech("ko","en").joinToString(""){it.text})
        assertTrue(engine.align(text,"I am reading a book.",listOf(VocabularyEntry("책",listOf("book"))),1.0,"en",sourceBoundaries=setOf(0,2,text.length)).spans.isEmpty())
        assertTrue(engine.align("책상 위에 있어요.","It is on the desk with a book.",entries,1.0,"en").spans.isEmpty())
        assertTrue(engine.align(text,"I am reading a book.",listOf(entries.single().copy(sourceScope=VocabularySourceScope(text,0,2))),1.0,"en").spans.isEmpty())
    }

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
