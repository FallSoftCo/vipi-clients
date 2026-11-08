package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.*
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.async
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.util.concurrent.CancellationException

class InvalidTranslationCacheLifecycleDeviceTest {
    private val text = "Send @alice a message."
    private class Counting(private val answer: suspend (String) -> String = { "Tuma ujumbe kwa @bob." }) : LanguageTranslation {
        var calls = 0
        override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = error("No downloads")
        override suspend fun translate(text: String, source: String, target: String): String { calls++; return answer(text) }
        override fun close() {}
    }
    // Invokes the same private readiness transition used by checkDownloads;
    // does not mutate real installed models or add a production testing API.
    private fun readiness(engine: ConversationImmersion, value: Boolean) {
        ConversationImmersion::class.java.getDeclaredMethod("updateReadiness", Boolean::class.javaPrimitiveType).apply { isAccessible = true }.invoke(engine, value)
    }
    @Test fun invalidationBoundednessAndTransientFailures(): Unit = runBlocking {
        val ins = InstrumentationRegistry.getInstrumentation()
        require(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = ins.targetContext; val output = File(context.filesDir, "invalid-result-cache-lifecycle-001.json"); check(!output.exists())
        val rows = JSONArray(); val report = JSONObject().put("complete", false).put("cases", rows).put("provider", "scripted")
            .put("model_readiness", "Synthetic transitions via actual private setter; no installed model changes.")
        fun passed(name: String, calls: Int) { rows.put(JSONObject().put("case", name).put("calls", calls)); output.writeText(report.toString(2)) }
        try {
            val counter = Counting()
            ConversationImmersion(context, "en", "sw", .25, translator = counter, qaModelsReady = true).use { engine ->
                engine.checkDownloads(); engine.selectInputLanguage("m", "en")
                repeat(2) { assertNull(engine.presentation(text, "en", "m")) }; assertEquals(1, counter.calls)
                engine.selectInputLanguage("m", "sw"); engine.selectInputLanguage("m", "en")
                engine.presentation(text, "en", "m"); assertEquals(2, counter.calls)
                engine.presentation("Send @alice another message.", "en", "m"); assertEquals(3, counter.calls)
                readiness(engine, false); assertNull(engine.presentation(text, "en", "m")); assertEquals(ImmersionStatus.MODEL_NOT_READY, engine.lastOutcome!!.status)
                assertEquals(3, counter.calls); readiness(engine, true)
                repeat(2) { engine.presentation(text, "en", "m") }; assertEquals(4, counter.calls)
                engine.checkDownloads(); engine.presentation(text, "en", "m"); assertEquals(4, counter.calls)
                passed("exact_text_language_epoch_and_observed_readiness_invalidate_only_negatives", counter.calls)
            }
            val entered = CompletableDeferred<Unit>(); val release = CompletableDeferred<Unit>()
            val delayed = Counting { entered.complete(Unit); release.await(); "Tuma ujumbe kwa @bob." }
            ConversationImmersion(context, "en", "sw", .25, translator = delayed, qaModelsReady = true).use { engine ->
                engine.checkDownloads(); val pending = async { engine.presentation(text, "en") }
                withTimeout(5_000) { entered.await() }; readiness(engine, false); readiness(engine, true); release.complete(Unit)
                withTimeout(5_000) { pending.await() }; engine.presentation(text, "en"); engine.presentation(text, "en")
                assertEquals(2, delayed.calls); passed("inflight_rejection_retains_original_readiness_revision", delayed.calls)
            }
            val partialText = "I need water. Send @alice a message."; val partialProvider = Counting()
            ConversationImmersion(context, "en", "sw", .25, translator = partialProvider, qaModelsReady = true).use { engine ->
                engine.checkDownloads(); val first = requireNotNull(engine.presentation(partialText, "en")); assertTrue(first.spans.isNotEmpty())
                readiness(engine, false); readiness(engine, true); assertEquals(first, engine.presentation(partialText, "en")); assertEquals(0, partialProvider.calls)
                val failure = engine.fullTranslation(partialText, "en", null, engine.newFullTranslationEpoch())
                assertEquals(ImmersionStatus.PARTIAL, failure.status); assertEquals(ImmersionStatus.INVALID_RESULT, failure.fallbackStatus)
                assertEquals(first.spans, failure.result!!.spans); assertEquals(first.spans, engine.presentation(partialText, "en")!!.spans)
                assertEquals(1, partialProvider.calls); passed("partial_success_survives_readiness_and_invalid_full_extension", partialProvider.calls)
            }
            for (kind in listOf("error", "timeout", "cancellation")) {
                val transient = Counting { when (kind) {
                    "timeout" -> throw ImmersionTranslationTimeout()
                    "cancellation" -> throw CancellationException("synthetic cancellation")
                    else -> error("synthetic transient")
                } }
                ConversationImmersion(context, "en", "sw", .25, translator = transient, qaModelsReady = true).use { engine ->
                    engine.checkDownloads()
                    repeat(2) {
                        try { engine.presentation(text, "en"); assertNotEquals("cancellation must propagate", "cancellation", kind) }
                        catch (_: CancellationException) { assertEquals("cancellation", kind) }
                    }
                    assertEquals(2, transient.calls); passed("transient_${kind}_not_negative_cached", transient.calls)
                }
            }
            val bounded = Counting()
            ConversationImmersion(context, "en", "sw", .25, translator = bounded, qaModelsReady = true).use { engine ->
                engine.checkDownloads()
                repeat(129) { engine.presentation("Send @alice message $it.", "en") }
                val cache = ConversationImmersion::class.java.getDeclaredField("cache").apply { isAccessible = true }.get(engine) as BoundedImmersionCache<*>
                assertEquals(128, cache.size); assertEquals(129, bounded.calls)
                engine.presentation("Send @alice message 128.", "en"); assertEquals(129, bounded.calls)
                engine.presentation("Send @alice message 0.", "en"); assertEquals(130, bounded.calls); assertEquals(128, cache.size)
                passed("negative_entries_use_existing_128_bound_and_eviction", bounded.calls)
            }
            var identity = "negative-cache:known0"
            val provider = object : SourceLookupProvider {
                override val cacheIdentity get() = identity
                override suspend fun lookup(original: String, source: String, target: String, density: Double) =
                    SourceLookupEvidence(original, source, target, identity, null, emptyList())
            }
            val catalogCounter = Counting()
            ConversationImmersion(context, "en", "sw", .25, translator = catalogCounter, qaModelsReady = true, sourceLookup = provider).use { engine ->
                engine.checkDownloads(); repeat(2) { engine.presentation(text, "en") }; assertEquals(1, catalogCounter.calls)
                identity = "negative-cache:known1"; engine.presentation(text, "en")
                assertEquals(ImmersionStatus.STALE, engine.lastOutcome!!.status); assertEquals(1, catalogCounter.calls)
            }
            ConversationImmersion(context, "en", "sw", .25, translator = catalogCounter, qaModelsReady = true, sourceLookup = provider).use { engine ->
                engine.checkDownloads(); repeat(2) { engine.presentation(text, "en") }; assertEquals(2, catalogCounter.calls)
                passed("new_catalog_known_identity_requires_new_engine_and_new_attempt", catalogCounter.calls)
            }
            assertEquals(8, rows.length()); report.put("complete", true)
        } finally { output.writeText(report.toString(2)) }
    }
}
