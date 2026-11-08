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

/** Injected source evidence and fixed retained provider text; no new language data/model calls. */
class SourceConstraintRoutingDeviceTest {
    private val text = "I am reading a country music book."
    private val reference = "Ninasoma kitabu cha muziki cha nchi."
    private val identity = "constraint-routing:1:known0"
    private fun recognition() = SourceRecognition("country_music", "a".repeat(64), SourceLookupRange(15, 28),
        SourceLookupRange(15, 28), SourceAtomicMode.HEAD_BACKOFF,
        listOf(SourceApprovedOutput("music", SourceLookupRange(23, 28))))
    private class Translation(private val value: String) : LanguageTranslation {
        var calls = 0
        override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = error("No downloads")
        override suspend fun translate(text: String, source: String, target: String): String { calls++; return value }
        override fun close() {}
    }
    private class Provider(override var cacheIdentity: String,
        private val produce: suspend (String, String, String, Double) -> SourceLookupEvidence) : SourceLookupProvider {
        var calls = 0
        override suspend fun lookup(original: String, source: String, target: String, density: Double): SourceLookupEvidence {
            calls++; return produce(original, source, target, density)
        }
    }
    private fun evidence(original: String = text, id: String = identity, partial: PartialImmersionResult? = null) =
        SourceLookupEvidence(original, "en", "sw", id, partial, listOf(recognition()))
    private fun capture(value: ImmersionPresentation?) = value?.let { JSONObject().put("original", it.original)
        .put("translation", it.translation ?: JSONObject.NULL).put("spans", JSONArray(it.spans.map { s -> JSONObject()
            .put("original", s.original).put("target", s.translated).put("range_utf16", JSONArray(listOf(s.start, s.end))) })) } ?: JSONObject.NULL

    @Test fun sourceConstraintsReachActualConversationRouting(): Unit = runBlocking {
        val ins = InstrumentationRegistry.getInstrumentation()
        require(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        require(android.os.Build.MODEL.contains("sdk_gphone") || android.os.Build.FINGERPRINT.contains("generic"))
        val context = ins.targetContext; val output = File(context.filesDir, "source-constraints-001.json"); check(!output.exists())
        val rows = JSONArray(); val report = JSONObject().put("complete", false).put("cases", rows)
            .put("provider_calls_are_scripted", true).put("model_downloads", 0).put("default_catalog_provider", "absent")
            .put("reference_provenance", "Unchanged actual en-sw provider output retained in NLP spot r91; scripted here to isolate routing.")
        fun save() { output.writeText(report.toString(2)) }
        try {
            val baselineTranslation = Translation(reference)
            val baseline = ConversationImmersion(context, "en", "sw", 1.0, translator = baselineTranslation, qaModelsReady = true).use { engine ->
                engine.checkDownloads(); requireNotNull(engine.presentation(text, "en"))
            }
            assertTrue("Retain actual baseline masked leak", baseline.spans.any { it.original == "country" })
            val provider = Provider(identity) { original, _, _, _ -> evidence(original) }; val translation = Translation(reference)
            ConversationImmersion(context, "en", "sw", 1.0, translator = translation, qaModelsReady = true, sourceLookup = provider).use { engine ->
                engine.checkDownloads(); val result = requireNotNull(engine.presentation(text, "en"))
                assertEquals(reference, result.translation)
                assertEquals(baseline.spans.filter { it.end <= 15 || it.start >= 28 }, result.spans)
                assertEquals(1, provider.calls); assertEquals(1, translation.calls); assertNotNull(engine.lastOutcome!!.sourceEvidence)
                engine.presentation(text, "en"); assertEquals(1, provider.calls); assertEquals(1, translation.calls)
                assertEquals(0, engine.lastInvocation.sourceRecognition)
                rows.put(JSONObject().put("case", "legacy_overlap_filtered_unmasked_and_full_retained")
                    .put("baseline", capture(baseline)).put("constrained", capture(result)).put("warm_source_calls", engine.lastInvocation.sourceRecognition)); save()
                provider.cacheIdentity = "constraint-routing:1:known1"
                assertNull(engine.cachedPresentation(text)); assertNull(engine.presentation(text, "en"))
                assertEquals(ImmersionStatus.STALE, engine.lastOutcome!!.status); assertEquals(1, translation.calls)
                rows.put(JSONObject().put("case", "changed_known_identity_cannot_reuse_cached_result")); save()
            }
            val wholeText = "I need water."
            val wholeProvider = Provider(identity) { original, from, to, _ ->
                SourceLookupEvidence(original, from, to, identity, null, listOf(SourceRecognition("water", "b".repeat(64),
                    SourceLookupRange(0, original.length), SourceLookupRange(7, 12), SourceAtomicMode.ATOMIC, emptyList()))) }
            val noTranslation = Translation("must not be called")
            ConversationImmersion(context, "en", "sw", 1.0, translator = noTranslation, qaModelsReady = false, sourceLookup = wholeProvider).use { engine ->
                engine.checkDownloads(); val result = requireNotNull(engine.presentation(wholeText, "en"))
                assertEquals(ImmersionOrigin.LOOKUP_REFERENCE, engine.lastOutcome!!.origin)
                assertNotNull(result.translation); assertTrue(result.spans.none { it.start < 12 && it.end > 7 })
                assertEquals(1, wholeProvider.calls); assertEquals(0, noTranslation.calls)
                rows.put(JSONObject().put("case", "accepted_whole_reference_still_acquires_constraints").put("presentation", capture(result))); save()
            }
            val partial = requireNotNull(SourceReferencePresentation.create(text, "sw", listOf(SourceReferenceUnit(23, 28,
                "music", "muziki", null, "synthetic-approved-proof", "a".repeat(64), 1, "music")), .25, LocalImmersion.words(text, "en").size))
            val partialProvider = Provider(identity) { original, _, _, _ -> evidence(original, partial = partial) }
            val full = Translation(reference)
            ConversationImmersion(context, "en", "sw", .25, translator = full, qaModelsReady = true, sourceLookup = partialProvider).use { engine ->
                engine.checkDownloads(); val first = requireNotNull(engine.presentation(text, "en"))
                assertNull(first.translation); assertEquals(listOf("music"), first.spans.map { it.original })
                assertEquals(0, full.calls); assertEquals(0, engine.lastInvocation.heavyAlignment)
                val extended = requireNotNull(engine.fullTranslation(text, "en", null, engine.newFullTranslationEpoch()).result)
                assertEquals(first.spans, extended.spans); assertEquals(reference, extended.translation)
                assertEquals(1, full.calls); assertEquals(0, engine.lastInvocation.heavyAlignment)
                rows.put(JSONObject().put("case", "explicit_approved_head_and_full_extension").put("partial", capture(first)).put("full", capture(extended))); save()
            }
            val entered = CompletableDeferred<Unit>(); val released = CompletableDeferred<Unit>()
            val delayed = Provider(identity) { original, _, _, _ -> entered.complete(Unit); released.await(); evidence(original) }
            val never = Translation(reference)
            ConversationImmersion(context, "en", "sw", .25, translator = never, qaModelsReady = true, sourceLookup = delayed).use { engine ->
                engine.checkDownloads(); engine.selectInputLanguage("message", "en")
                val pending = async { engine.presentation(text, "en", "message") }
                withTimeout(5_000) { entered.await() }; engine.selectInputLanguage("message", "sw"); released.complete(Unit)
                assertNull(withTimeout(5_000) { pending.await() }); assertEquals(ImmersionStatus.STALE, engine.lastOutcome!!.status)
                assertNull(engine.lastOutcome!!.sourceEvidence); assertEquals(0, never.calls); assertNull(engine.cachedPresentation(text, "message"))
                rows.put(JSONObject().put("case", "language_change_rejects_late_evidence")); save()
            }
            val reverse = Provider(identity) { _, _, _, _ -> error("Forward provider must not run for explicit target input") }
            ConversationImmersion(context, "en", "sw", .25, translator = Translation("I like music."), qaModelsReady = true, sourceLookup = reverse).use { engine ->
                engine.checkDownloads(); engine.presentation("Ninapenda muziki.", "sw")
                assertEquals(0, reverse.calls); assertNull(engine.lastOutcome!!.sourceEvidence)
                rows.put(JSONObject().put("case", "explicit_target_input_has_no_forward_constraints")); save()
            }
            assertEquals(6, rows.length()); report.put("complete", true)
        } finally { save() }
    }
}
