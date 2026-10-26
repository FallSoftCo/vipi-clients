package co.fallsoft.vipi.core

import org.junit.Assert.*
import org.junit.Test

class ContextFrameTest {
    @Test fun finitePossessorsRemainOutsideFocus() {
        val parts=listOf(ContextPart.Slot(listOf("my ","your ","their ")),ContextPart.Focus("dog"))
        assertEquals(6..8,ContextMappingMatcher.focus("their dog",parts))
        assertNull(ContextMappingMatcher.focus("her dog",parts))
        assertNull(ContextMappingMatcher.focus("dog",listOf(ContextPart.Focus("dog"))))
        assertNull(ContextMappingMatcher.focus(" dog",listOf(ContextPart.Slot(listOf(" ","\n")),ContextPart.Focus("dog"))))
    }
    private val original="🙂 I am reading a book now."
    private val translation="🙂 Estoy leyendo un libro ahora. Otro libro."
    private fun range(text:String,phrase:String)=text.indexOf(phrase) until text.indexOf(phrase)+phrase.length
    private fun frame(id:String="book",meaning:String="a book being read")=ContextFrame(id,meaning,"en","es",
        listOf(ContextPart.Slot(listOf("read","reading")),ContextPart.Literal(" a "),ContextPart.Focus("book")),
        listOf(ContextPart.Literal("leyendo un "),ContextPart.Focus("libro")))
    private fun hit(value:ContextFrame=frame(),targets:List<IntRange> = listOf(range(translation,"leyendo un libro")))=
        ContextFrameHit(value,listOf(range(original,"reading a book")),targets)
    private fun entries(hits:List<ContextFrameHit>)=ContextFrameMatcher.entries(original,translation,"en","es",hits)
    @Test fun bothMatchedContextsBindOnlyTheirLexicalFocus() {
        val values=entries(listOf(hit()));assertEquals(1,values.size)
        val result=ImmersionEngine().align(original,translation,values,1.0,"es")
        assertEquals(1,result.spans.size);assertEquals("book",result.spans.single().original)
        assertEquals(translation.indexOf("libro"),result.spans.single().targetStart)
        assertEquals(listOf("libro"),result.speech("en","es").filter{it.language=="es"}.map{it.text})
    }
    @Test fun missingTargetCannotEraseAContrarySourceMeaning() {
        assertTrue(entries(listOf(hit(targets=emptyList()))).isEmpty())
        assertTrue(entries(listOf(hit(),hit(frame("rival","an unrelated sense"),emptyList()))).isEmpty())
    }
    @Test fun repeatedMatchedTargetAndOverflowAbstain() {
        val repeated="leyendo un libro y leyendo un libro"
        assertTrue(ContextFrameMatcher.entries(original,repeated,"en","es",listOf(hit(targets=listOf(0..15,19..34)))).isEmpty())
        assertTrue(entries((0..256).map{hit(frame("book-$it"))}).isEmpty())
    }
    @Test fun indexHitMustActuallyMatchTheBoundedPattern() {
        assertTrue(entries(listOf(ContextFrameHit(frame(),listOf(0..3),emptyList()))).isEmpty())
        assertTrue(entries(listOf(hit(targets=listOf(999..1003)))).isEmpty())
    }
}
