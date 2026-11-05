package co.fallsoft.vipi.core
import org.junit.Assert.*
import org.junit.Test

class SourceReferencePresentationTest {
    private val original="Hello. Unknown."
    private fun unit()=SourceReferenceUnit(0,6,"Hello.","Hola.",null,"catalog:1","a".repeat(64), nativeSourceTokens = 1)
    @Test fun partialUsesOnlyKnownWholeUnitAtDefaultAndFullDensity() {
        for(density in listOf(.25,1.0)) {
            val result=requireNotNull(SourceReferencePresentation.create(original,"es",listOf(unit()),density,2))
            assertNull(result.translation);assertEquals(original,result.original)
            assertEquals("Hola. Unknown.",ImmersionText.project(result))
            assertEquals(original,ImmersionText.project(result,setOf(0)))
            assertEquals(unit(),result.references.single());assertEquals(0,result.spans.single().targetStart)
            assertEquals(5,result.spans.single().targetEnd)
        }
    }
    @Test fun offNoKnownMissingReadingAndWrongSourceNeverForceCoverage() {
        assertNull(SourceReferencePresentation.create(original,"es",listOf(unit()),0.0,2))
        assertNull(SourceReferencePresentation.create(original,"es",emptyList(),1.0,2))
        assertNull(SourceReferencePresentation.create(original,"es",listOf(unit().copy(original="wrong")),1.0,2))
        assertNull(SourceReferencePresentation.create(original,"ja",listOf(unit().copy(translated="こんにちは。")),1.0,2))
    }
    @Test fun protectedIdentifiersAndNumbersCannotBeAWholeReplacementUnit() {
        for(text in listOf("Hello 42.","Hello @Ana.","https://example.test")) {
            val u=SourceReferenceUnit(0,text.length,text,text.replace("Hello","Hola"),null,"r","a".repeat(64), nativeSourceTokens = 1)
            assertNull(SourceReferencePresentation.create(text,"es",listOf(u),1.0,2))
        }
    }
    @Test fun nonRomanKnownReadingUsesExactUnitAndOriginalAnchors() {
        val result=requireNotNull(SourceReferencePresentation.create(original,"ja",listOf(unit().copy(translated="こんにちは。",reading="konnichiwa.")),.25,2))
        assertEquals("konnichiwa. Unknown.",ImmersionText.project(result))
        assertEquals("こんにちは。 Unknown.",ImmersionText.project(result,showScript=true))
        assertEquals(original,result.original)
    }
}
