package co.fallsoft.vipi.core

import org.junit.Assert.*
import org.junit.Test
import kotlin.coroutines.*

/** Real production routing function, with deterministic callback witnesses (not SDK inference). */
class LookupFirstTest {
    private fun <T> run(block: suspend () -> T): T {
        var result: Result<T>? = null
        block.startCoroutine(object : Continuation<T> {
            override val context = EmptyCoroutineContext
            override fun resumeWith(value: Result<T>) { result = value }
        })
        return checkNotNull(result).getOrThrow()
    }
    private inner class Work {
        val events = mutableListOf<String>()
        var valid = true; var ready = true; var known: String? = null; var reverse: String? = null
        var translated = "Hola."; var detected: String? = "en"; var partial: PartialImmersionResult? = null
        var invalidate: String? = null; var invalidAlignment = false; var translationFailure: Exception? = null
        fun event(s: String) { events += s; if (s == invalidate) valid = false }
        fun resolve(input: String? = "en", original: String = "Hello.", intent: ImmersionIntent = ImmersionIntent.AUTOMATIC_IMMERSION) = this@LookupFirstTest.run {
            LookupFirst.resolve(LookupFirstRequest(original,"en","es",input,intent), {valid},
                reference={_,a,_-> event("reference:$a"); if(a=="en")known else reverse},
                identify={ event("identify"); detected }, modelsReady={ event("models");ready },
                translate={_,a,b->event("translate:$a-$b"); translationFailure?.let { throw it }; translated},
                align={a,b->event("align");ImmersionResult(if(invalidAlignment)"wrong" else a,b,emptyList())},
                partialReference={_,_,_->event("partial");partial}, onPartial={event("show_partial")})
        }
    }
    @Test fun fullyKnownNeverChecksModelsOrTranslates() {
        val w=Work();w.known="Hola.";w.ready=false
        val result=w.resolve();assertEquals(ImmersionStatus.READY,result.status)
        assertEquals(ImmersionOrigin.LOOKUP_REFERENCE,result.origin);assertEquals(0,result.localTranslationCalls)
        assertEquals(listOf("reference:en","align"),w.events)
    }
    @Test fun explicitUnknownMakesOnlyOneFullContextLocalRequest() {
        val w=Work();val result=w.resolve();assertEquals(1,result.localTranslationCalls)
        assertEquals(listOf("reference:en","partial","models","translate:en-es","align"),w.events)
        assertEquals("Hello.",result.result!!.original)
    }
    @Test fun noKnownAndMissingModelsPreservesReadableOriginalAtCaller() {
        val w=Work();w.ready=false;val result=w.resolve();assertNull(result.result)
        assertEquals(ImmersionStatus.MODEL_NOT_READY,result.status);assertEquals(0,result.localTranslationCalls)
    }
    @Test fun knownPlusUnknownSurvivesMissingModelsWithoutFakeTranslation() {
        val w=Work();w.ready=false
        w.partial=SourceReferencePresentation.create("Hello. Unknown.","es",listOf(SourceReferenceUnit(0,6,"Hello.","Hola.",null,"r1","a".repeat(64), nativeSourceTokens = 1)),.25,2)
        val result=w.resolve(original="Hello. Unknown.");assertEquals(ImmersionStatus.PARTIAL,result.status)
        assertNull(result.result!!.translation);assertEquals("Hello. Unknown.",result.result!!.original)
        assertEquals("Hola. Unknown.",ImmersionText.project(result.result!!));assertEquals(0,result.localTranslationCalls)
    }
    @Test fun explicitFullRequestKeepsPartialFacesAndSkipsDiscardedAlignment() {
        val w=Work();w.partial=SourceReferencePresentation.create("Hello. Unknown.","es",listOf(SourceReferenceUnit(0,6,"Hello.","Hola.",null,"r1","a".repeat(64), nativeSourceTokens = 1)),1.0,2)
        val result=w.resolve(original="Hello. Unknown.", intent=ImmersionIntent.FULL_TRANSLATION);assertEquals(1,result.localTranslationCalls)
        assertTrue(w.events.indexOf("show_partial") < w.events.indexOf("translate:en-es"))
        assertTrue(result.result is PartialImmersionResult)
        assertEquals(ImmersionOrigin.SOURCE_REFERENCE_PARTIAL,result.origin)
        assertEquals("Hola.",result.result!!.translation) // actual callback result, not a fabricated mixed sentence
        assertEquals("Hola. Unknown.",ImmersionText.project(result.result!!))
        assertEquals(ImmersionStatus.READY,result.fallbackStatus)
        assertFalse("align" in w.events)
    }
    @Test fun staleAtEveryAwaitBoundaryNeverAppliesOrCachesOutput() {
        for(point in listOf("reference:en","partial","translate:en-es","align")) {
            val w=Work();w.invalidate=point;val result=w.resolve()
            assertEquals(point,ImmersionStatus.STALE,result.status);assertNull(result.result)
        }
    }
    @Test fun reverseKnownKeepsCanonicalRangesAndOriginalIncomingTarget() {
        val w=Work();w.reverse="Hello.";w.ready=false;val result=w.resolve("es","Hola.")
        assertEquals("Hello.",result.result!!.original);assertEquals("Hola.",result.result!!.translation)
        assertEquals(listOf("reference:es","align"),w.events);assertEquals(0,result.localTranslationCalls)
    }
    @Test fun badLanguageOrInvalidResultCannotBecomeImmersion() {
        val w=Work();assertEquals(ImmersionStatus.INVALID_INPUT,w.resolve("de").status)
        val x=Work();x.detected="de";assertEquals(ImmersionStatus.INVALID_LANGUAGE,x.resolve(null).status)
        val y=Work();y.invalidAlignment=true;assertEquals(ImmersionStatus.INVALID_RESULT,y.resolve().status)
    }
    @Test fun changedUnicodeIdentifiersRejectBeforeAlignment() {
        val w=Work();w.translated="Hola @cafe\u0300";val result=w.resolve(original="Hello @cafe\u0301")
        assertEquals(ImmersionStatus.INVALID_RESULT,result.status);assertFalse("align" in w.events)
    }
    @Test fun emptySpansAreNotAUsefulImmersionPass() {
        val w=Work();val result=w.resolve();assertEquals(ImmersionStatus.READY,result.status)
        assertTrue(result.result!!.spans.isEmpty()) // routing ready != coverage/depth/meaning
    }
    private fun partial(text: String = "Hello. Unknown.") = checkNotNull(SourceReferencePresentation.create(text,"es",
        listOf(SourceReferenceUnit(0,6,"Hello.","Hola.",null,"r1","a".repeat(64), nativeSourceTokens = 1)),.25,2))
    @Test fun approvedAutomaticPartialDoesNotCheckModelsTranslateOrAlign() {
        for (ready in listOf(true, false)) {
            val w=Work();w.ready=ready;w.partial=partial()
            val result=w.resolve(original="Hello. Unknown.")
            assertEquals(listOf("reference:en","partial","show_partial"),w.events)
            assertEquals(0,result.localTranslationCalls);assertNull(result.result!!.translation)
            assertEquals(w.partial,result.result);assertEquals(ImmersionStatus.PARTIAL,result.status)
        }
    }
    @Test fun missingModelsOnExplicitRequestKeepsTheUsefulPartial() {
        val w=Work();w.ready=false;w.partial=partial()
        val result=w.resolve(original="Hello. Unknown.",intent=ImmersionIntent.FULL_TRANSLATION)
        assertEquals(w.partial,result.result);assertEquals(ImmersionStatus.MODEL_NOT_READY,result.fallbackStatus)
        assertEquals(0,result.localTranslationCalls);assertFalse("align" in w.events)
    }
    @Test fun invalidFullReferenceOrProviderTimeoutCannotEraseApprovedFaces() {
        val text="Hello. Unknown @cafe\u0301."
        for (timeout in listOf(false,true)) {
            val w=Work();w.partial=partial(text)
            if(timeout) w.translationFailure=ImmersionTranslationTimeout() else w.translated="Hola @cafe\u0300."
            val result=w.resolve(original=text,intent=ImmersionIntent.FULL_TRANSLATION)
            assertEquals(w.partial,result.result)
            assertEquals(if(timeout) ImmersionStatus.TIMEOUT else ImmersionStatus.INVALID_RESULT,result.fallbackStatus)
            assertEquals(1,result.localTranslationCalls);assertFalse("align" in w.events)
        }
    }
    @Test fun callbackInvalidationAndEmptyOrWronglyAnchoredPartialsFailClosed() {
        val stale=Work();stale.partial=partial();stale.invalidate="show_partial"
        assertEquals(ImmersionStatus.STALE,stale.resolve(original="Hello. Unknown.").status)
        assertFalse("models" in stale.events)
        val empty=Work();empty.partial=PartialImmersionResult("Hello. Unknown.",emptyList(),emptyList(),nativeSourceTokenCount=2,targetLanguage="es")
        assertEquals(ImmersionStatus.INVALID_RESULT,empty.resolve(original="Hello. Unknown.").status)
        assertFalse("models" in empty.events)
        val wrong=Work();wrong.partial=partial().copy(original="Changed. Unknown.")
        assertEquals(ImmersionStatus.INVALID_RESULT,wrong.resolve(original="Hello. Unknown.").status)
    }
    @Test fun targetLanguageInputNeverUsesForwardSourcePartial() {
        val w=Work();w.partial=partial();w.translated="Hello."
        val result=w.resolve("es","Hola.")
        assertEquals("Hello.",result.result!!.original);assertEquals("Hola.",result.result!!.translation)
        assertFalse("partial" in w.events);assertEquals(1,result.localTranslationCalls)
        assertTrue("translate:es-en" in w.events);assertTrue("align" in w.events)
    }

}
