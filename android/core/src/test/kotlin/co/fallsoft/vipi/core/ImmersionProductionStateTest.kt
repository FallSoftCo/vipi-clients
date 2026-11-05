package co.fallsoft.vipi.core

import java.util.concurrent.CancellationException
import kotlin.coroutines.*
import org.junit.Assert.*
import org.junit.Test

/** Production-used state/cache logic. No Compose scheduler/device/SDK claim. */
class ImmersionProductionStateTest {
    private fun <T> immediate(block: suspend () -> T): T {
        var result: Result<T>? = null
        block.startCoroutine(object : Continuation<T> {
            override val context = EmptyCoroutineContext
            override fun resumeWith(value: Result<T>) { result = value }
        })
        return checkNotNull(result).getOrThrow()
    }
    private val owner=Any()
    private fun request(id:String="a", input:String?="en", configuration:Any=owner) =
        ImmersionPresentationRequest(id,"Hello. Unknown.","en","es",input,configuration)
    private val full=ImmersionResult("Hello. Unknown.","Hola. Desconocido.",emptyList())
    private fun partial()=requireNotNull(SourceReferencePresentation.create("Hello. Unknown.","es",
        listOf(SourceReferenceUnit(0,6,"Hello.","Hola.",null,"r","a".repeat(64),1)),.25,2))
    @Test fun languageChangeWhilePausedInvalidatesVisibleAndWaitingBeforeResume() {
        val old=request();val next=request(input="es")
        val pending=ImmersionPresentationState(old,full).accept(old,full,true)
        assertTrue(pending.hasWaiting)
        val rebound=pending.bind(next)
        assertNull(rebound.visible);assertNull(rebound.waiting);assertFalse(rebound.hasWaiting)
        assertEquals(rebound,rebound.resume(old));assertEquals(rebound,rebound.accept(old,full,false))
        assertNull(rebound.resume(next).visible)
    }
    @Test fun sameTextDifferentMessageOrConfigurationCannotReusePendingActions() {
        val old=request();val pending=ImmersionPresentationState(old,full).accept(old,full,true)
        for(next in listOf(request(id="b"),request(configuration=Any()),request(input=null))) {
            val rebound=pending.bind(next);assertNull(rebound.visible);assertFalse(rebound.hasWaiting)
            assertEquals(rebound,rebound.accept(old,full,true));assertEquals(rebound,rebound.resume(old))
        }
    }
    @Test fun currentPendingNullClearsFullTargetAndCurrentPartialResumesExactly() {
        val key=request();val held=ImmersionPresentationState(key,full).accept(key,null,true)
        assertNull(held.resume(key).visible)
        val partial=partial();val changed=held.accept(key,partial,true).resume(key)
        assertEquals(partial,changed.visible);assertNull(changed.visible!!.translation)
    }
    @Test fun everyPartialInsertionStaysBoundedEvenWhenTranslationCancels129Times() {
        val cache=BoundedImmersionCache<LookupFirstOutcome>(128);val partial=partial();var cancellations=0
        repeat(129) { i ->
            try {
                immediate { LookupFirst.resolve(LookupFirstRequest(partial.original,"en","es","en"),{true},
                    reference={_,_,_->null},identify={"en"},modelsReady={true},
                    translate={_,_,_->throw CancellationException("synthetic cancellation")},
                    align={_,_->error("must not align after cancellation")},partialReference={_,_,_->partial},
                    onPartial={cache["$i"]=LookupFirstOutcome(it,ImmersionOrigin.SOURCE_REFERENCE_PARTIAL,ImmersionStatus.PARTIAL,0)
                        assertTrue(cache.size<=128)}) }
                fail("cancellation must propagate")
            } catch (_:CancellationException) { cancellations++ }
        }
        assertEquals(129,cancellations);assertEquals(128,cache.size);assertNull(cache["0"]);assertNotNull(cache["128"])
    }
    @Test fun cacheHitRecordsZeroNewTranslationCallsAndRetainsOriginalProvenance() {
        val cache=BoundedImmersionCache<LookupFirstOutcome>(1)
        cache["x"]=LookupFirstOutcome(full,ImmersionOrigin.LOCAL_FULL_CONTEXT,ImmersionStatus.READY,1)
        val hit=requireNotNull(cache["x"]).cachedInvocation()
        assertEquals(0,hit.localTranslationCalls);assertTrue(hit.cacheHit)
        assertEquals(ImmersionOrigin.LOCAL_FULL_CONTEXT,hit.origin);assertEquals(full,hit.result)
    }
    @Test fun nativePerUnitCostsControlCjkDensityAndAtomicFallback() {
        // Explicit synthetic native token geometry, not a live ICU tokenization claim.
        val text="一緒。昼飯。"
        val units=listOf(SourceReferenceUnit(0,3,"一緒。","Together.",null,"r1","a".repeat(64),2),
            SourceReferenceUnit(3,6,"昼飯。","Lunch.",null,"r2","a".repeat(64),2))
        assertEquals(1,SourceReferencePresentation.create(text,"en",units,.5,4)!!.spans.size)
        assertEquals(2,SourceReferencePresentation.create(text,"en",units,1.0,4)!!.spans.size)
        assertEquals(1,SourceReferencePresentation.create(text,"en",units,.25,4)!!.spans.size)
        assertNull(SourceReferencePresentation.create(text,"en",units,0.0,4))
        assertNull(SourceReferencePresentation.create(text,"en",units.map {it.copy(nativeSourceTokens=null)},.5,4))
    }
    @Test fun malformedPartialCannotBypassReferenceLocalRangeValidation() {
        val partial=partial();val malformed=partial.copy(spans=partial.spans.map {it.copy(targetStart=1)})
        assertFalse(SourceReferencePresentation.isAnchored(malformed,"es"))
        val outcome=immediate { LookupFirst.resolve(LookupFirstRequest(partial.original,"en","es","en"),{true},
            reference={_,_,_->null},identify={"en"},modelsReady={error("invalid partial must stop first")},
            translate={_,_,_->error("no calls")},align={_,_->error("no align")},partialReference={_,_,_->malformed}) }
        assertEquals(ImmersionStatus.INVALID_RESULT,outcome.status);assertNull(outcome.result)
    }
}
