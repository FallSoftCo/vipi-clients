package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.*
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File

/** External finite candidate catalog capture; never enables production assets. */
class AllPairSourceFrameCandidateTest {
    @Test fun captureCandidateOutcomesAndNativeBoundaries() = runBlocking {
        val inst = InstrumentationRegistry.getInstrumentation()
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("vipiDedicatedEmulator") == "true")
        val name = requireNotNull(args.getString("vipiCandidateRun"))
        require(name.matches(Regex("all-pair-starter-candidate-r[0-9]{2}")))
        val useBundledDefault = args.getString("vipiUseBundledDefault") == "true"
        check(!useBundledDefault || BundledStarterLookup.ALL_PAIR_PROMOTION_ENABLED)
        val context = inst.targetContext
        val root = File(context.filesDir, name)
        val suffix = args.getString("vipiCaptureSuffix").orEmpty()
        require(suffix.isEmpty() || suffix.matches(Regex("-(remaining|default)-[0-9]{2}")))
        val out = File(context.filesDir, "$name-android$suffix.json")
        val pairDirectory = File(context.filesDir, "$name-android$suffix-pairs")
        check(!out.exists() && !pairDirectory.exists())
        check(pairDirectory.mkdir())
        val review = JSONObject(File(root, "review-manifest.json").readText())
        check(!review.getBoolean("runtime_promotion"))
        val fixtureDocument = JSONObject(File(root, "native-fixtures.json").readText())
        val fixtures = fixtureDocument.getJSONArray("cases")
        val authoredControls = fixtureDocument.getJSONArray("controls")
        val errors = JSONArray(File(root, "cld2-errors.json").readText())
        val catalog = BundledImmersionCatalog(context)
        val owners = mutableMapOf<Pair<String, String>, SourceFrameLookup>()
        val candidates = mutableMapOf<Pair<String, String>, SourceLookupProvider>()
        val languages = listOf("en", "es", "fr", "de", "it", "pt", "ar", "zh", "ja", "ko", "sw")
        val selectedSources = args.getString("vipiCaptureSources")?.split(",")?.toSet() ?: languages.toSet()
        require(selectedSources.isNotEmpty() && selectedSources.all { it in languages })
        for (source in languages) for (target in languages) if (source != target) {
            val baseline = object : SourceLookupProvider {
                override val cacheIdentity = "candidate-empty-v1"
                override suspend fun lookup(original: String, source: String, target: String, density: Double) =
                    SourceLookupEvidence(original, source, target, cacheIdentity, null, emptyList())
            }
            val manifest = File(root, "packs/source-frames-$source-$target-catalog.json").readBytes()
            val filename = JSONObject(manifest.toString(Charsets.UTF_8)).getString("file")
            require(filename.matches(Regex("source-frames-$source-$target-[0-9]{3}\\.json")))
            val owner = SourceFrameLookup(File(root, "packs/$filename").readBytes(), manifest, target, baseline.cacheIdentity, source)
            owners[source to target] = owner
            candidates[source to target] = owner.provider(baseline, emptySet(), { emptyList() }, catalog)
        }
        assertEquals(110, candidates.size)
        // Shipped English providers retain priority; candidate files never enter bundled loading.
        val composed = requireNotNull(BundledStarterLookup.compose(
            JapaneseStarterLookup.bundledIfPromoted(context, emptySet()),
            SwahiliStarterLookup.bundledIfPromoted(context, emptySet()), candidates))
        val report = JSONObject().put("schema", "vipi-all-pair-android-candidate-segmented-1")
            .put("runtime_promotion", BundledStarterLookup.ALL_PAIR_PROMOTION_ENABLED).put("linguistic_acceptance", false)
            .put("actual_default_provider", useBundledDefault).put("bundled_index_sha256", BundledSourceFrameCatalog.INDEX_SHA256)
            .put("direct_density", 0.5).put("conversation_density", 0.25)
        var rows = JSONArray(); var controls = JSONArray()
        val pairFiles = JSONArray(); val negativeFailures = JSONArray(); val forbiddenFailures = JSONArray()
        var totalCases = 0; var totalControls = 0; var activePair = ""
        report.put("pair_files", pairFiles).put("selected_sources", JSONArray(selectedSources.toList()))
            .put("negative_control_failures", negativeFailures).put("forbidden_source_failures", forbiddenFailures)
        fun save() { report.put("captured_cases", totalCases).put("captured_controls", totalControls); out.writeText(report.toString(2)) }
        fun savePair(pair: String) {
            val rejectedControls = (0 until controls.length()).map { controls.getJSONObject(it) }.filter {
                it.getString("kind") == "authored_boundary_or_ambiguity" &&
                    it.getJSONObject("fixture").optBoolean("expected_no_spans", false) &&
                    listOf("direct", "automatic", "explicit_source").any { key -> it.getJSONObject(key).getJSONArray("spans").length() > 0 }
            }
            val forbiddenRows = (0 until rows.length()).map { rows.getJSONObject(it) }.filter { row ->
                val forbidden = row.getJSONObject("fixture").optJSONArray("forbidden_sources")
                val values = if (forbidden == null) emptySet() else (0 until forbidden.length()).map { forbidden.getString(it) }.toSet()
                listOf("direct", "automatic", "explicit_source").any { key ->
                    val spans = row.getJSONObject(key).getJSONArray("spans")
                    (0 until spans.length()).any { spans.getJSONObject(it).getString("original") in values }
                }
            }
            rejectedControls.forEach { negativeFailures.put(it) }
            forbiddenRows.forEach { forbiddenFailures.put(it) }
            val runtime = Runtime.getRuntime()
            val bytes = JSONObject().put("pair", pair).put("cases", rows).put("controls", controls)
                .put("harness_heap_used_bytes", runtime.totalMemory() - runtime.freeMemory()).put("heap_limit_bytes", runtime.maxMemory())
                .toString().toByteArray(Charsets.UTF_8)
            val file = File(pairDirectory, "$pair.json"); check(!file.exists()); file.writeBytes(bytes)
            pairFiles.put(JSONObject().put("pair", pair).put("file", file.name).put("bytes", bytes.size)
                .put("sha256", JapaneseStarterLookup.sha(bytes)).put("cases", rows.length()).put("controls", controls.length()))
            totalCases += rows.length(); totalControls += controls.length()
            rows = JSONArray(); controls = JSONArray(); save()
        }
        fun presentation(value: ImmersionPresentation?, original: String): JSONObject {
            val spans = JSONArray()
            value?.spans?.forEach { span ->
                assertEquals(original.substring(span.start, span.end), span.original)
                spans.put(JSONObject().put("start", span.start).put("end", span.end)
                    .put("original", span.original).put("translated", span.translated)
                    .put("reading", span.romanization ?: JSONObject.NULL))
            }
            val mixed = StringBuilder(original)
            value?.spans?.asReversed()?.forEach { mixed.replace(it.start, it.end, it.translated) }
            assertTrue(TranslationIntegrity.preservesIdentifiers(original, mixed.toString()))
            return JSONObject().put("mixed", mixed.toString()).put("spans", spans)
                .put("full_translation", value?.translation ?: JSONObject.NULL)
        }
        suspend fun route(immersion: ConversationImmersion, text: String, manual: String?): JSONObject {
            val started = android.os.SystemClock.elapsedRealtimeNanos()
            val value = immersion.presentation(text, inputLanguage = manual)
            return presentation(value, text).put("elapsed_ms", (android.os.SystemClock.elapsedRealtimeNanos() - started) / 1_000_000.0).put("status", immersion.lastOutcome?.status.toString())
                .put("origin", immersion.lastOutcome?.origin.toString())
                .put("local_translation_calls", immersion.lastOutcome?.localTranslationCalls ?: 0)
        }
        try {
            for ((pair, provider) in candidates) {
                val (source, target) = pair
                if (source !in selectedSources) continue
                activePair = "$source-$target"
                val owner = requireNotNull(owners[pair])
                val immersion = if (useBundledDefault) ConversationImmersion(context, source, target, 0.25)
                    else ConversationImmersion(context, source, target, 0.25, sourceLookup = composed)
                try {
                    var first: String? = null
                    for (i in 0 until fixtures.length()) {
                        val fixture = fixtures.getJSONObject(i)
                        if (fixture.getString("pair") != "$source-$target") continue
                        val original = fixture.getString("original")
                        if (first == null) first = original
                        val evidence = provider.lookup(original, source, target, 0.5)
                        val focus = fixture.getJSONArray("focus_utf16")
                        evidence.partial?.spans?.filter { it.start == focus.getInt(0) && it.end == focus.getInt(1) }?.forEach {
                            assertEquals(fixture.getString("id"), fixture.getString("expected_target"), it.translated)
                            if (target in setOf("ar", "zh", "ja", "ko"))
                                assertEquals(fixture.getString("id"), fixture.getString("reading"), it.romanization)
                        }
                        val direct = presentation(evidence.partial, original)
                        val geometry = owner.geometry(original)
                        val trace = owner.trace
                        rows.put(JSONObject().put("fixture", fixture).put("density", 0.5)
                            .put("exact_reference", catalog.reference(original, source, target) != null)
                            .put("native_words", JSONArray(LocalImmersion.words(original, source).map {
                                JSONObject().put("text", original.substring(it)).put("start", it.first).put("end", it.last + 1)
                            })).put("geometry", geometry).put("trace", trace).put("direct", direct)
                            .put("automatic", route(immersion, original, null))
                            .put("explicit_source", route(immersion, original, source)))
                    }
                    check(first != null)
                    for (i in 0 until authoredControls.length()) {
                        val control = authoredControls.getJSONObject(i)
                        if (control.getString("pair") != "$source-$target") continue
                        val original = control.getString("original")
                        val evidence = provider.lookup(original, source, target, 0.5)
                        controls.put(JSONObject().put("kind", "authored_boundary_or_ambiguity").put("pair", "$source-$target")
                            .put("fixture", control).put("direct", presentation(evidence.partial, original))
                            .put("geometry", owner.geometry(original)).put("trace", owner.trace)
                            .put("native_words", JSONArray(LocalImmersion.words(original, source).map {
                                JSONObject().put("text", original.substring(it)).put("start", it.first).put("end", it.last + 1)
                            })).put("automatic", route(immersion, original, null))
                            .put("explicit_source", route(immersion, original, source)))
                    }
                    val protected = "```\n$first\n```"
                    val literalEvidence = provider.lookup(protected, source, target, 0.5)
                    assertNull(literalEvidence.partial)
                    controls.put(JSONObject().put("kind", "protected_literal").put("pair", "$source-$target")
                        .put("result", presentation(literalEvidence.partial, protected)))
                    for (i in 0 until errors.length()) {
                        val error = errors.getJSONObject(i)
                        controls.put(JSONObject().put("kind", "known_detector_false_positive").put("pair", "$source-$target")
                            .put("fixture", error).put("result", route(immersion, error.getString("text"), null)))
                    }
                } finally { immersion.close() }
                savePair(activePair)
            }
            assertEquals(selectedSources.size * 10, pairFiles.length())
            assertEquals((0 until fixtures.length()).count { fixtures.getJSONObject(it).getString("source_language") in selectedSources }, totalCases)
            report.put("complete", true); save()
            assertEquals("Authored ambiguity/compound controls must abstain", 0, negativeFailures.length())
            assertEquals("Rejected context must not contribute an output", 0, forbiddenFailures.length())
        } catch (error: Throwable) {
            File(pairDirectory, "incomplete.json").writeText(JSONObject().put("pair", activePair).put("cases", rows).put("controls", controls).toString())
            report.put("complete", false).put("error", error.toString()); save(); throw error
        }
    }
}
