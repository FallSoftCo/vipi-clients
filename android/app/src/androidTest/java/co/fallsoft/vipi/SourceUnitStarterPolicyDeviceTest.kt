package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import java.io.File

/** Structural adversarial controls only; not conversation-coverage or meaning evidence. */
class SourceUnitStarterPolicyDeviceTest {
    private fun bytes():ByteArray {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator")=="true")
        return File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir,SourceUnitStarterDeviceTest.PACK_FILE).readBytes()
    }
    private fun reason(policy:ReviewedSourceUnitQa,id:String,reason:String):Boolean {
        val rejected=policy.lastDiagnostic.getJSONArray("rejected")
        return (0 until rejected.length()).map { rejected.getJSONObject(it) }.any { it.getString("id")==id && it.getString("reason")==reason }
    }
    @Test fun contractionsInflectionsAndUtf16RemainExact() {
        val policy=ReviewedSourceUnitQa(bytes())
        assertNull(policy.partial("I'm bewildered.","en","sw",.10))
        assertNull(policy.partial("musical.","en","sw",.10))
        val span=requireNotNull(policy.partial("🙂 music.","en","sw",.10)).spans.single()
        assertEquals("music",span.original);assertEquals(3,span.start);assertEquals(8,span.end)
    }
    @Test fun identifiersCodeAndMidSentenceCapitalsAreWithheld() {
        val policy=ReviewedSourceUnitQa(bytes())
        for(text in listOf("https://example.test/music","music@example.test","`music`")) {
            policy.partial(text,"en","sw",.10);assertTrue(text,reason(policy,"word-en-sw-music","protected_identifier_or_code"))
        }
        policy.partial("MUSIC","en","sw",.10);assertTrue(reason(policy,"word-en-sw-music","uppercase_identifier"))
        policy.partial("zorb Music.","en","sw",.10);assertTrue(reason(policy,"word-en-sw-music","mid_sentence_capital"))
    }
    @Test fun nounAndQuestionContextsAreLiteralAndBudgetCannotExpand() {
        val policy=ReviewedSourceUnitQa(bytes())
        policy.partial("Please nurse.","en","sw",.10);assertTrue(reason(policy,"word-en-sw-nurse","noun_context_absent"))
        assertEquals("nurse",requireNotNull(policy.partial("the nurse.","en","sw",.10)).spans.single().original)
        policy.partial("What kind of zorb?","en","sw",.10)
        assertTrue(reason(policy,"question-en-sw-what-kind","native_density_budget"))
        assertTrue(reason(policy,"question-en-sw-what","question_right_context_absent"))
        policy.partial("zorb what do glorp?","en","sw",.10)
        assertTrue(reason(policy,"question-en-sw-what","question_not_sentence_initial"))
        policy.partial("What, do glorp?","en","sw",.10)
        assertTrue(reason(policy,"question-en-sw-what","noncontiguous_question_context"))
    }
    @Test fun nativeWholeMessageLiteralGuardCoversResearchRegexGaps() {
        val policy=ReviewedSourceUnitQa(bytes())
        for(text in listOf("HTTPS://example.test/music","www.example.test/music","`music","#music","@music")) {
            policy.partial(text,"en","sw",.10)
            val rejected=policy.lastDiagnostic.getJSONArray("rejected")
            assertTrue(text,(0 until rejected.length()).map { rejected.getJSONObject(it) }.any {
                it.getString("id")=="word-en-sw-music" && it.getString("reason") in
                    setOf("full_message_literal_integrity","incomplete_native_source_word","protected_identifier_or_code") })
        }
    }
    @Test fun exactJapaneseReadingIsRequiredAndBoundToOriginalScript() {
        val value=requireNotNull(ReviewedSourceUnitQa(bytes()).partial("or","en","ja",.10))
        assertEquals("または",value.spans.single().translated);assertEquals("matawa",value.spans.single().romanization)
        assertEquals(ReviewedSourceUnitQa.SHA256,value.references.single().catalogSha256)
        assertNull(value.translation)
    }
    @Test fun changedPackAndUnqualifiedDensityFailClosed() {
        val corrupt=bytes();corrupt[corrupt.lastIndex]=(corrupt.last().toInt() xor 1).toByte()
        assertThrows(IllegalArgumentException::class.java) { ReviewedSourceUnitQa(corrupt) }
        val policy=ReviewedSourceUnitQa(bytes())
        assertThrows(IllegalArgumentException::class.java) { policy.partial("music","en","sw",.25) }
    }
}
