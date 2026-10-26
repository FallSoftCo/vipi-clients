package co.fallsoft.vipi.core

import org.junit.Assert.*
import org.junit.Test

class TargetScopeTest {
    private val source="🙂 I read a book."
    private val target="🙂 Leo un libro. Ese libro es nuevo."
    private fun entry(start:Int=10,end:Int=15,translation:String=target)=VocabularyEntry("book",listOf("libro"),
        sourceScope=VocabularySourceScope(source,12,16),targetScope=VocabularyTargetScope(translation,start,end))
    @Test fun boundTargetSelectsOnlyItsMatchedOccurrence() {
        val result=ImmersionEngine().align(source,target,listOf(entry()),1.0,"es")
        assertEquals(1,result.spans.size);assertEquals(10,result.spans.single().targetStart)
        assertEquals("book",result.spans.single().original)
    }
    @Test fun changedTranslationInvalidRangeOrMissingSourceScopeNeverFallsBack() {
        for(value in listOf(entry(9,14),entry(translation="Different translation"),entry().copy(sourceScope=null)))
            assertTrue(ImmersionEngine().align(source,target,listOf(value),1.0).spans.isEmpty())
        assertTrue(ImmersionEngine().align("Changed "+source,target,listOf(entry()),1.0).spans.isEmpty())
    }
    @Test fun conflictingMatchedTargetsStillAbstain() {
        assertTrue(ImmersionEngine().align(source,target,listOf(entry(),entry(21,26)),1.0).spans.isEmpty())
    }
    @Test fun sharedIdeographRetainsQualifiedTargetReadingAndSpeechLanguage() {
        val entry=VocabularyEntry("水",listOf("水"),mapOf("水" to listOf("mizu")),
            sourceScope=VocabularySourceScope("水",0,1),targetScope=VocabularyTargetScope("水",0,1))
        val result=ImmersionEngine().align("水","水",listOf(entry),1.0,"ja")
        assertEquals("mizu",result.spans.single().romanization);assertEquals(listOf(SpeechSpan("水","ja")),result.speech("zh","ja"))
        assertTrue(ImmersionEngine().align("水","水",listOf(entry.copy(sourceScope=null,targetScope=null)),1.0,"ja").spans.isEmpty())
        assertTrue(ImmersionEngine().align("水","水",listOf(entry.copy(romanizations=emptyMap())),1.0,"ja").spans.isEmpty())
    }
}
