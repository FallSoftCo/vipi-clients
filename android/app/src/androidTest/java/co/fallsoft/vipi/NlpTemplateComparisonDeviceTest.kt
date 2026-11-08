package co.fallsoft.vipi

import android.os.Debug
import android.os.SystemClock
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.ImmersionText
import co.fallsoft.vipi.core.PartialImmersionResult
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.time.Instant

/** Frozen authored controls first, then reused TRAIN. No translator or model is instantiated. */
class NlpTemplateComparisonDeviceTest {
    private fun ranges(values: List<IntRange>) = JSONArray(values.map { JSONArray(listOf(it.first, it.last + 1)) })
    private fun partial(value: PartialImmersionResult?): Any = value?.let { result -> JSONObject()
        .put("complete_translation", JSONObject.NULL).put("mixed", ImmersionText.project(result))
        .put("spans", JSONArray(result.spans.map { span -> JSONObject().put("source_range_utf16", JSONArray(listOf(span.start, span.end)))
            .put("original", span.original).put("target", span.translated).put("reading", span.romanization ?: JSONObject.NULL) }))
    } ?: JSONObject.NULL
    private fun candidate(value: NlpTemplateSelection.Candidate) = JSONObject()
        .put("output_id", value.outputID).put("face_id", value.face.id).put("concept_id", value.face.conceptID)
        .put("source_range_utf16", value.scope.json()).put("target", value.face.target)
        .put("reading", value.face.reading ?: JSONObject.NULL).put("native_cost", value.nativeCost)
        .put("context_range_utf16", value.context.json()).put("context_native_cost", value.contextCost)
        .put("rule_id", value.ruleID).put("primary_ref", value.face.primaryRef)
    private fun recognition(value: NlpTemplateSelection.Recognition, catalog: NlpTemplateQaCatalog) = JSONObject()
        .put("rule_id", value.pattern.id).put("meaning_id", value.pattern.meaningID)
        .put("context_range_utf16", value.parse.context.json()).put("context_native_cost", value.contextCost)
        .put("record_sha256", value.pattern.recordSha256).put("evidence_ref", value.pattern.evidenceRef)
        .put("atomic_range_utf16", value.mask?.json() ?: JSONObject.NULL).put("atomic_mode", value.pattern.atomicMode)
        .put("reason", value.pattern.atomicReason)
        .put("allowed_inner_outputs", JSONArray(value.approved.map { (id, scope) -> JSONObject().put("output_id", id).put("source_range_utf16", scope.json()) }))
        .put("bindings", JSONArray(value.parse.bindings.map { binding -> JSONObject().put("name", binding.name).put("kind", binding.kind)
            .put("source_range_utf16", binding.scope.json()).put("original", binding.original).put("form_id", binding.formID ?: JSONObject.NULL)
            .put("morphological_analyses", binding.formID?.let(catalog.forms::get)?.let { form -> JSONObject()
                .put("lexeme_id", form.lexemeID).put("pos", form.pos).put("features", JSONArray(form.features))
                .put("retained_analyses", form.analysesJSON?.let(::JSONArray) ?: JSONObject.NULL).put("primary_ref", form.primaryRef) } ?: JSONObject.NULL) }))

    @Test fun captureFrozenComparison() {
        val ins = InstrumentationRegistry.getInstrumentation(); val args = InstrumentationRegistry.getArguments()
        require(args.getString("vipiDedicatedEmulator") == "true")
        require(android.os.Build.MODEL.contains("sdk_gphone") || android.os.Build.FINGERPRINT.contains("generic"))
        val dataset = requireNotNull(args.getString("vipiNlpDataset")).also { require(it in setOf("authored", "train")) }
        val run = requireNotNull(args.getString("vipiNlpRun")).also { require(it.matches(Regex("[0-9]{3}"))) }
        val context = ins.targetContext; val inputRoot = File(context.filesDir, "nlp-template-inputs-r01")
        val payload = File(inputRoot, "payload.json").readBytes(); val semantics = File(inputRoot, "semantics.json").readBytes()
        val payloadSha = "5c6a1c513a68f861ca28fd8c45b99b347e130940a29e6898bcc811fcfb47e5bc"
        val inputName = if (dataset == "authored") "authored-cases.json" else "train-source-protocol.json"
        val inputSha = if (dataset == "authored") "736be225fc4b6615e04efdfe8566bdf2e65681817377031ba61380c3f45f4f4f" else "4f0102f6a74dd79c60a770e24ed502bcc8c53158f070fdbe9545bdc0214507b3"
        val input = File(inputRoot, inputName).readBytes(); assertEquals(inputSha, NlpTemplateQaCatalog.sha(input))
        val casesRoot = JSONObject(input.toString(Charsets.UTF_8)); assertEquals(NlpTemplateQaCatalog.CONTRACT_SHA, casesRoot.getString("contract_sha256"))
        val cases = casesRoot.getJSONArray("cases"); assertEquals(if (dataset == "authored") 121 else 9535, cases.length())
        val directory = File(context.filesDir, "nlp-template-$dataset-$run"); check(directory.mkdir())
        val output = File(directory, "rows.jsonl"); val summary = File(directory, "summary.json")
        val started = SystemClock.elapsedRealtime()
        val report = JSONObject().put("schema", "vipi-android-nlp-template-comparison-1").put("complete", false)
            .put("dataset", dataset).put("production", false).put("input_sha256", inputSha).put("payload_sha256", payloadSha)
            .put("contract_sha256", NlpTemplateQaCatalog.CONTRACT_SHA).put("semantics_sha256", NlpTemplateQaCatalog.SEMANTICS_SHA)
            .put("started_at", Instant.now().toString()).put("provider_calls", 0).put("model_downloads", 0)
            .put("expected_count", cases.length()).put("captured_count", 0).put("finite_state_morphology_optional", "not_run_no_qualified_native_toolchain")
            .put("reference_control_limit", "Explicit-source existing catalog reference/partial functions only; automatic language identification and provider/alignment remain separate spot checks.")
            .put("compact_decision_columns", JSONArray(listOf("density", "known_snapshot_id", "native_budget", "selected_candidate_indexes", "rejection_indexes", "elapsed_ns")))
        val memory = JSONArray(); report.put("memory", memory)
        fun sample(stage: String) { val m = Debug.MemoryInfo(); Debug.getMemoryInfo(m)
            memory.put(JSONObject().put("stage", stage).put("pss_kib", m.totalPss).put("elapsed_ms", SystemClock.elapsedRealtime() - started)) }
        fun save() { val temp = File(directory, "summary.json.tmp"); temp.writeText(report.toString(2)); check(temp.renameTo(summary)) }
        sample("start"); save()
        val initialization = SystemClock.elapsedRealtimeNanos()
        val catalog = NlpTemplateQaCatalog(payload, semantics, payloadSha)
        report.put("catalog_initialization_ms", (SystemClock.elapsedRealtimeNanos() - initialization) / 1e6)
        val reference = BundledImmersionCatalog(context); val readings = SentenceReadings(context)
        val armIDs = listOf("exact_top_down", "existing_finite_slots", "typed_slots_attested_morphology")
        val knownIDs = catalog.knownSnapshots.keys.sorted(); val densities = listOf(.10, .25, .50)
        val totals = linkedMapOf<String, JSONObject>(); val unmatched = JSONArray(); report.put("unmatched_ids", unmatched)
        var writtenBytes = 0L
        try {
            output.outputStream().buffered().use { stream ->
                for (index in 0 until cases.length()) {
                    check(SystemClock.elapsedRealtime() - started < 600_000) { "Bounded comparison timeout" }
                    val inputCase = cases.getJSONObject(index); val id = inputCase.getString("id"); val text = inputCase.getString("text")
                    val source = inputCase.getString("source_language"); val targets = NlpTemplatePatternMatcher.strings(inputCase.getJSONArray("target_languages"))
                    val geometryAt = SystemClock.elapsedRealtimeNanos(); val native = catalog.source(text, source)
                    val row = JSONObject().put("id", id).put("text", text).put("source_language", source)
                        .put("stratum", inputCase.optString("stratum")).put("native_source_word_ranges_utf16", ranges(native.words))
                        .put("source_geometry_elapsed_ns", SystemClock.elapsedRealtimeNanos() - geometryAt)
                        .put("protected_scopes", JSONArray(native.literals.map { JSONObject().put("kind", it.kind).put("source_range_utf16", it.scope.json()) }))
                        .put("provider_calls", 0)
                    val sharedRecognitions = JSONArray(); val recognitionIndexes = linkedMapOf<String, Int>(); val arms = JSONArray()
                    row.put("recognitions", sharedRecognitions).put("arms", arms)
                    var hasWork = native.literals.isNotEmpty()
                    for (armID in armIDs) {
                        val firstAt = SystemClock.elapsedRealtimeNanos(); val arm = catalog.recognize(native, armID)
                        val firstNS = SystemClock.elapsedRealtimeNanos() - firstAt
                        val warmAt = SystemClock.elapsedRealtimeNanos(); val warm = catalog.recognize(native, armID)
                        val warmNS = SystemClock.elapsedRealtimeNanos() - warmAt
                        assertEquals(arm.recognitions, warm.recognitions)
                        assertEquals(arm.parserRejections.toString(), warm.parserRejections.toString())
                        val indexes = arm.recognitions.map { value -> val json = recognition(value, catalog); val key = json.toString()
                            recognitionIndexes.getOrPut(key) { sharedRecognitions.length().also { sharedRecognitions.put(json) } } }
                        val armRow = JSONObject().put("arm", armID).put("recognition_indexes", JSONArray(indexes))
                            .put("parser_rejections", arm.parserRejections).put("first_ns", firstNS).put("warm_ns", warmNS)
                            .put("attempted_patterns", arm.attemptedPatterns).put("attempted_windows", arm.attemptedWindows).put("peak_states", arm.peakStates)
                        arms.put(armRow); val targetRows = JSONArray(); armRow.put("targets", targetRows)
                        hasWork = hasWork || arm.recognitions.isNotEmpty() || arm.parserRejections.length() > 0
                        for (target in targets) {
                            val candidates = JSONArray(); val candidateIndexes = linkedMapOf<String, Int>(); val rejections = JSONArray(); val rejectionIndexes = linkedMapOf<String, Int>()
                            val decisions = JSONArray(); targetRows.put(JSONObject().put("target", target).put("candidates", candidates)
                                .put("rejections", rejections).put("decisions", decisions))
                            for (density in densities) for (known in knownIDs) {
                                val at = SystemClock.elapsedRealtimeNanos(); val result = catalog.select(native, arm, target, density, known)
                                val elapsed = SystemClock.elapsedRealtimeNanos() - at
                                val selected = result.selected.map { value -> val json = candidate(value); val key = json.toString()
                                    candidateIndexes.getOrPut(key) { candidates.length().also { candidates.put(json) } } }
                                // Retain candidates rejected before selection too, not just the successful display.
                                result.candidates.forEach { value -> val json = candidate(value); val key = json.toString()
                                    candidateIndexes.getOrPut(key) { candidates.length().also { candidates.put(json) } } }
                                val refused = (0 until result.rejections.length()).map { i -> val json = result.rejections.getJSONObject(i); val key = json.toString()
                                    rejectionIndexes.getOrPut(key) { rejections.length().also { rejections.put(json) } } }
                                decisions.put(JSONArray(listOf(density, known, result.budget, JSONArray(selected), JSONArray(refused), elapsed)))
                                if (dataset == "authored") decisions.getJSONArray(decisions.length() - 1).put(partial(result.partial))
                                hasWork = hasWork || result.candidates.isNotEmpty() || result.rejections.length() > 0
                                val key = "$armID|$target|$density|$known"
                                val total = totals.getOrPut(key) { JSONObject().put("arm", armID).put("target", target).put("density", density)
                                    .put("known_snapshot_id", known).put("messages", 0).put("messages_with_selected_spans", 0).put("selected_native_tokens", 0)
                                    .put("source_native_tokens", 0).put("selected_concepts", JSONArray()) }
                                total.put("messages", total.getInt("messages") + 1)
                                total.put("messages_with_selected_spans", total.getInt("messages_with_selected_spans") + if (selected.isEmpty()) 0 else 1)
                                total.put("selected_native_tokens", total.getInt("selected_native_tokens") + result.selected.sumOf { it.nativeCost })
                                total.put("source_native_tokens", total.getInt("source_native_tokens") + native.words.size)
                                val concepts = total.getJSONArray("selected_concepts"); val existing = (0 until concepts.length()).map(concepts::getString).toSet()
                                result.selected.map { it.face.conceptID }.distinct().filterNot { it in existing }.forEach(concepts::put)
                            }
                        }
                    }
                    val referenceRows = JSONArray(); row.put("existing_reference_route", referenceRows)
                    for (target in targets) {
                        val at = SystemClock.elapsedRealtimeNanos(); val whole = reference.reference(text, source, target)
                        val partials = densities.map { density -> density to reference.partial(text, source, target, density, readings) }
                        referenceRows.put(JSONObject().put("target", target).put("whole_reference", whole ?: JSONObject.NULL)
                            .put("partials", JSONArray(partials.map { (density, value) -> JSONObject().put("density", density).put("presentation", partial(value)) }))
                            .put("elapsed_ns", SystemClock.elapsedRealtimeNanos() - at))
                        hasWork = hasWork || whole != null || partials.any { it.second != null }
                    }
                    if (dataset == "authored" || hasWork) {
                        val encoded = (row.toString() + "\n").toByteArray(Charsets.UTF_8)
                        check(writtenBytes + encoded.size <= 20L * 1024 * 1024) { "Native trace cap reached" }
                        stream.write(encoded); writtenBytes += encoded.size
                    } else unmatched.put(id)
                    report.put("captured_count", index + 1).put("output_bytes", writtenBytes)
                    if ((index + 1) % 250 == 0) { stream.flush(); sample("case-${index + 1}"); save() }
                }
            }
            report.put("complete", true)
        } finally {
            report.put("totals", JSONArray(totals.values.toList())).put("output_bytes", writtenBytes)
                .put("finished_at", Instant.now().toString()).put("elapsed_ms", SystemClock.elapsedRealtime() - started)
            if (dataset == "authored") report.getJSONArray("compact_decision_columns").put("actual_native_partial")
            sample("finish"); save()
        }
    }
}
