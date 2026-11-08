package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicInteger

@RunWith(AndroidJUnit4::class)
class FullReadingCacheDeviceTest {
    @Test fun coalescesMissesAndKeepsIndependentWorkResponsive() = runBlocking {
        val started = CompletableDeferred<Unit>(); val release = CompletableDeferred<Unit>(); val calls = ConcurrentHashMap<String, AtomicInteger>()
        val cache = FullReadingCache("authored-test") { text, language ->
            calls.computeIfAbsent(text + language) { AtomicInteger() }.incrementAndGet()
            if (text == "held") { started.complete(Unit); release.await() }
            if (text == "unknown") null else FullReading(text + language, FullReading.Provenance.AUTHORED)
        }
        try {
            val first = async { cache.resolve("held", "ja") }; val second = async { cache.resolve("held", "ja") }
            withTimeout(2000) { started.await() }
            assertEquals("otherzh", withTimeout(1000) { cache.resolve("other", "zh") }?.text)
            repeat(3) { assertNull(cache.resolve("unknown", "ja")) }
            assertTrue(cache.hasResolved("unknown", "ja")); assertEquals(1, calls["unknownja"]!!.get())
            release.complete(Unit); assertEquals(first.await(), second.await()); assertEquals(1, calls["heldja"]!!.get()); assertEquals(3, cache.count)
        } finally { release.complete(Unit); cache.close() }
    }
    @Test fun cancellingWaiterKeepsSharedProducerAndAnotherRowAlive() = runBlocking {
        val started = CompletableDeferred<Unit>(); val release = CompletableDeferred<Unit>(); val calls = AtomicInteger()
        val cache = FullReadingCache("test") { text, _ -> calls.incrementAndGet(); started.complete(Unit); release.await(); FullReading(text, FullReading.Provenance.AUTHORED) }
        try {
            val first = async { cache.resolve("same", "ja") }; val second = async { cache.resolve("same", "ja") }
            withTimeout(2000) { started.await() }; yield(); first.cancelAndJoin()
            assertFalse(second.isCompleted); assertEquals(1, calls.get())
            release.complete(Unit); assertEquals("same", second.await()?.text); assertEquals("same", cache.cached("same", "ja")?.text)
        } finally { release.complete(Unit); cache.close() }
    }
    @Test fun resetRejectsNonCooperativeLateCompletionAndUsesFreshGeneration() = runBlocking {
        val starts = List(2) { CompletableDeferred<Unit>() }; val release = CompletableDeferred<Unit>(); val count = AtomicInteger()
        val cache = FullReadingCache("test") { _, _ ->
            val index = count.getAndIncrement(); starts[index].complete(Unit)
            withContext(NonCancellable) { release.await() }
            FullReading("generation-$index", FullReading.Provenance.AUTHORED)
        }
        try {
            val old = async { runCatching { cache.resolve("same", "ja") }.getOrNull() }
            withTimeout(2000) { starts[0].await() }; cache.removeAll()
            val fresh = async { cache.resolve("same", "ja") }; withTimeout(2000) { starts[1].await() }
            release.complete(Unit); assertNull(old.await()); assertEquals("generation-1", fresh.await()?.text)
            assertEquals("generation-1", cache.cached("same", "ja")?.text); assertEquals(1, cache.count)
        } finally { release.complete(Unit); cache.close() }
    }
    @Test fun exactEncodingLanguagePolicyAndBounds() = runBlocking {
        val calls = AtomicInteger()
        val cache = FullReadingCache("authored-v1") { text, language -> calls.incrementAndGet(); FullReading(text + language, FullReading.Provenance.AUTHORED) }
        val otherPolicy = FullReadingCache("future-v2") { _, _ -> FullReading("different-policy", FullReading.Provenance.LOCAL_TRANSLITERATION) }
        try {
            for (text in listOf("é", "e\u0301", "\ud800", "\ud801")) cache.resolve(text, "ja")
            cache.resolve("é", "zh"); assertEquals(5, cache.count); assertEquals(5, calls.get())
            assertEquals("different-policy", otherPolicy.resolve("é", "ja")?.text)
            assertEquals(FullReading.Provenance.AUTHORED, cache.cached("é", "ja")?.provenance)
            repeat(129) { cache.resolve("row-$it", "ko") }; assertEquals(128, cache.count); assertFalse(cache.hasResolved("é", "ja"))
            val before = calls.get(); assertNull(cache.resolve("字".repeat(16385), "zh")); assertNull(cache.resolve("hello", "en")); assertEquals(before, calls.get())
            cache.close(); assertNull(cache.resolve("row-128", "ko")); assertEquals(0, cache.count)
        } finally { cache.close(); otherPolicy.close() }
    }
    @Test fun limitsPendingAndRejectsOversizedOutput() = runBlocking {
        val release = CompletableDeferred<Unit>(); val count = AtomicInteger()
        val cache = FullReadingCache("test") { text, _ -> count.incrementAndGet(); release.await(); FullReading(if (text == "row-0") "x".repeat(65537) else text, FullReading.Provenance.AUTHORED) }
        try {
            val pending = (0 until 128).map { i -> async { cache.resolve("row-$i", "ja") } }
            withTimeout(4000) { while (count.get() < 128) delay(5) }
            assertNull(cache.resolve("overflow", "ja")); assertEquals(128, count.get())
            release.complete(Unit); pending.awaitAll(); assertTrue(cache.hasResolved("row-0", "ja")); assertNull(cache.cached("row-0", "ja")); assertEquals(128, cache.count)
        } finally { release.complete(Unit); cache.close() }
    }
}
