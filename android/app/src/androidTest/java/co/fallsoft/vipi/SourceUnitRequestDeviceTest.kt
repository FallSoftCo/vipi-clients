package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.*
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test
import java.io.IOException

/** Actual native catalog/cache/lifecycle; provider error/delay responses are explicitly synthetic. */
class SourceUnitRequestDeviceTest {
    private val text = "I need water. Did you finish the report?"
    private val reference = "Ninahitaji maji. Je, umemaliza ripoti?"
    private fun context() = InstrumentationRegistry.getInstrumentation().targetContext.also {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
    }
    private class Controlled(val response: suspend (Int) -> String) : LanguageTranslation {
        var calls = 0
        override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = error("No downloads")
        override suspend fun translate(text: String, source: String, target: String): String = response(++calls)
        override fun close() = Unit
    }
    private suspend fun partial(engine: ConversationImmersion, id: String? = null): PartialImmersionResult {
        if (id != null) engine.selectInputLanguage(id, "en")
        val value = engine.presentation(text, "en", id)
        assertTrue(value is PartialImmersionResult);assertNull(value!!.translation);assertTrue(value.spans.isNotEmpty())
        return value as PartialImmersionResult
    }
    @Test fun pendingFullReferenceDoesNotBlockAnotherApprovedPartial(): Unit = runBlocking {
        val entered = CompletableDeferred<Unit>(); val release = CompletableDeferred<String>()
        val provider = Controlled { entered.complete(Unit); release.await() }
        ConversationImmersion(context(), "en", "sw", .25, provider).use { engine ->
            partial(engine); engine.checkDownloads()
            val pending = async { engine.fullTranslation(text, "en", null, engine.newFullTranslationEpoch()) }
            entered.await()
            try {
                val reentered = withTimeout(2_000) { engine.presentation(text, "en") }
                assertTrue(reentered is PartialImmersionResult); assertNull(reentered!!.translation)
                val other = withTimeout(2_000) { engine.presentation("Did you finish the report? I need water.", "en") }
                assertTrue(other is PartialImmersionResult); assertNull(other!!.translation)
                assertTrue(other.spans.isNotEmpty()); assertEquals(1, provider.calls)
                assertEquals("unmeasured", engine.lexicalPreparation)
            } finally { release.complete(reference); pending.await() }
        }
    }
    @Test fun partialCacheWorksWithoutModelsAndAfterReadinessChange(): Unit = runBlocking {
        val provider = Controlled { error("Automatic partial must not translate") }
        ConversationImmersion(context(), "en", "sw", .25, provider).use { engine ->
            val value = partial(engine);assertNull(engine.ready);assertEquals(0,provider.calls)
            val missing = engine.fullTranslation(text,"en",null,engine.newFullTranslationEpoch())
            assertEquals(ImmersionStatus.MODEL_NOT_READY,missing.fallbackStatus);assertEquals(value,missing.result)
            engine.checkDownloads();assertEquals(true,engine.ready)
            assertEquals(value,engine.presentation(text,"en"));assertEquals(true,engine.lastOutcome?.cacheHit)
            assertEquals(0,provider.calls);assertEquals("unmeasured",engine.lexicalPreparation)
        }
    }
    @Test fun simultaneousFullRequestsShareOneProviderTaskAndCompleteCache(): Unit = runBlocking {
        val entered=CompletableDeferred<Unit>();val release=CompletableDeferred<String>()
        val provider=Controlled { entered.complete(Unit);release.await() }
        ConversationImmersion(context(),"en","sw",.25,provider).use { engine ->
            val value=partial(engine);engine.checkDownloads();assertEquals(true,engine.ready)
            val epoch=engine.newFullTranslationEpoch()
            val first=async { engine.fullTranslation(text,"en",null,epoch) };entered.await()
            val duplicate=async { engine.fullTranslation(text,"en",null,epoch) };yield();assertEquals(1,provider.calls)
            release.complete(reference)
            val results=awaitAll(first,duplicate)
            assertEquals(1,provider.calls);assertEquals(1,results.count { it.cacheHit })
            for(result in results) { assertEquals(reference,result.result?.translation);assertEquals(value.spans,result.result?.spans) }
            val repeated=engine.fullTranslation(text,"en",null,engine.newFullTranslationEpoch())
            assertEquals(true,repeated.cacheHit);assertEquals(1,provider.calls);assertEquals("unmeasured",engine.lexicalPreparation)
        }
    }
    @Test fun failedAttemptIsCoalescedAndOnlyNewExplicitEpochRetries(): Unit = runBlocking {
        val provider=Controlled { if(it==1) throw IOException("Synthetic provider failure") else reference }
        ConversationImmersion(context(),"en","sw",.25,provider).use { engine ->
            val value=partial(engine);engine.checkDownloads()
            val epoch=engine.newFullTranslationEpoch()
            val first=engine.fullTranslation(text,"en",null,epoch)
            val duplicate=engine.fullTranslation(text,"en",null,epoch)
            assertEquals(ImmersionStatus.ERROR,first.fallbackStatus);assertEquals(value,first.result)
            assertTrue(duplicate.cacheHit);assertEquals(1,provider.calls)
            assertEquals(value,engine.presentation(text,"en"));assertEquals(1,provider.calls)
            val retry=engine.fullTranslation(text,"en",null,engine.newFullTranslationEpoch())
            assertEquals(reference,retry.result?.translation);assertEquals(value.spans,retry.result?.spans);assertEquals(2,provider.calls)
        }
    }
    @Test fun canceledAttemptCannotBeRestartedByQueuedDuplicateOrPublishLate(): Unit = runBlocking {
        val entered=CompletableDeferred<Unit>();val release=CompletableDeferred<String>()
        val provider=Controlled { entered.complete(Unit);release.await() }
        ConversationImmersion(context(),"en","sw",.25,provider).use { engine ->
            val value=partial(engine);engine.checkDownloads();val epoch=engine.newFullTranslationEpoch()
            val job=async { engine.fullTranslation(text,"en",null,epoch) };entered.await();job.cancelAndJoin()
            release.complete(reference)
            val duplicate=engine.fullTranslation(text,"en",null,epoch)
            assertEquals(ImmersionStatus.STALE,duplicate.status);assertNull(duplicate.result);assertEquals(1,provider.calls)
            assertEquals(value,engine.presentation(text,"en"))
            val retry=engine.fullTranslation(text,"en",null,engine.newFullTranslationEpoch())
            assertEquals(reference,retry.result?.translation);assertEquals(2,provider.calls)
        }
    }
    @Test fun changedInputLanguageRejectsLateResultAndDoesNotShareOldSlots(): Unit = runBlocking {
        val entered=CompletableDeferred<Unit>();val release=CompletableDeferred<String>()
        val provider=Controlled { entered.complete(Unit);release.await() }
        ConversationImmersion(context(),"en","sw",.25,provider).use { engine ->
            partial(engine,"owned-message");engine.checkDownloads()
            val job=async { engine.fullTranslation(text,"en","owned-message",engine.newFullTranslationEpoch()) };entered.await()
            engine.selectInputLanguage("owned-message","sw");release.complete(reference)
            val stale=job.await();assertEquals(ImmersionStatus.STALE,stale.status);assertNull(stale.result)
            assertNull(engine.cachedPresentation(text,"owned-message"));assertEquals(1,provider.calls)
        }
    }
    @Test fun actualThirtySecondDeadlineRetainsPartialAndDoesNotAutoRetry(): Unit = runBlocking {
        val provider=Controlled { delay(35_000);reference }
        ConversationImmersion(context(),"en","sw",.25,provider).use { engine ->
            val value=partial(engine);engine.checkDownloads();val epoch=engine.newFullTranslationEpoch()
            val began=android.os.SystemClock.elapsedRealtime()
            val outcome=engine.fullTranslation(text,"en",null,epoch)
            val elapsed=android.os.SystemClock.elapsedRealtime()-began
            assertTrue("Actual bounded coroutine deadline",elapsed in 29_000L..34_000L)
            assertEquals(ImmersionStatus.TIMEOUT,outcome.fallbackStatus);assertEquals(value,outcome.result)
            assertTrue(engine.fullTranslation(text,"en",null,epoch).cacheHit)
            assertEquals(value,engine.presentation(text,"en"));assertEquals(1,provider.calls)
        }
    }
}
