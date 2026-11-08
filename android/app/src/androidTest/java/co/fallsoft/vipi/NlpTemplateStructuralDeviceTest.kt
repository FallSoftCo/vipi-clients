package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.NlpTemplatePatternMatcher.Binding
import co.fallsoft.vipi.NlpTemplatePatternMatcher.Output
import co.fallsoft.vipi.NlpTemplatePatternMatcher.Parse
import co.fallsoft.vipi.NlpTemplatePatternMatcher.Pattern
import co.fallsoft.vipi.NlpTemplatePatternMatcher.RangeSpec
import co.fallsoft.vipi.NlpTemplatePatternMatcher.Scope
import co.fallsoft.vipi.NlpTemplateSelection.Recognition
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File

/** Synthetic eligibility collisions only, never language data or TRAIN coverage. */
class NlpTemplateStructuralDeviceTest {
    private fun scope(value: JSONArray) = Scope(value.getInt(0), value.getInt(1))
    private fun part(name: String) = RangeSpec("part", name, null, null)

    @Test fun masksAndMeaningConflictsSurviveOuterContexts() {
        val ins = InstrumentationRegistry.getInstrumentation()
        require(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        require(android.os.Build.MODEL.contains("sdk_gphone") || android.os.Build.FINGERPRINT.contains("generic"))
        val root = File(ins.targetContext.filesDir, "nlp-template-inputs-r01")
        val fixtureBytes = File(root, "structural-overlap-controls.json").readBytes()
        val fixtureSha = "4f5f9b4e0b6823ed0aaa7807ac962003c09b96f99f728b23df7ae690d8d88c8c"
        assertEquals(fixtureSha, NlpTemplateQaCatalog.sha(fixtureBytes))
        val fixture = JSONObject(fixtureBytes.toString(Charsets.UTF_8))
        val catalog = NlpTemplateQaCatalog(File(root, "payload.json").readBytes(), File(root, "semantics.json").readBytes(), fixture.getString("payload_sha256"))
        val output = File(ins.targetContext.filesDir, "nlp-template-structural-001.json"); check(!output.exists())
        val rows = JSONArray()
        val report = JSONObject().put("complete", false).put("production", false).put("linguistic_authority", false)
            .put("fixture_sha256", fixtureSha).put("provider_calls", 0).put("model_downloads", 0).put("cases", rows)
            .put("diagnostic_id_normalization", "Only display trace labels: diagnostic-fallback:<face_id> becomes diagnostic:<concept_id> for frozen expected IDs.")
        try {
            val cases = fixture.getJSONArray("cases")
            for (i in 0 until cases.length()) {
                val input = cases.getJSONObject(i); val text = input.getString("text")
                val native = catalog.source(text, "en")
                val recognized = catalog.recognize(native, "typed_slots_attested_morphology")
                val originals = input.getJSONArray("original_recognitions")
                val retained = (0 until originals.length()).map { index ->
                    val original = originals.getJSONObject(index)
                    recognized.recognitions.single { it.pattern.id == original.getString("rule_id") && it.parse.context == scope(original.getJSONArray("context_range_utf16")) }
                }
                val rawSynthetic = input.getJSONArray("synthetic_recognitions")
                val metadata = JSONArray()
                val synthetic = (0 until rawSynthetic.length()).map { index ->
                    val raw = rawSynthetic.getJSONObject(index); val context = scope(raw.getJSONArray("context_range_utf16"))
                    val bindings = mutableListOf<Binding>()
                    fun bind(name: String, range: Scope): RangeSpec {
                        require(range.start >= 0 && range.end <= text.length && range.length > 0)
                        bindings += Binding(name, "synthetic_scope_only", range, text.substring(range.start, range.end), null)
                        return part(name)
                    }
                    val mask = if (raw.isNull("atomic_range_utf16")) null else bind("mask", scope(raw.getJSONArray("atomic_range_utf16")))
                    val rawOutputs = raw.getJSONArray("outputs")
                    val outputs = (0 until rawOutputs.length()).map { n -> val value = rawOutputs.getJSONObject(n)
                        Output(value.getString("id"), bind("output$n", scope(value.getJSONArray("source_range_utf16"))), null,
                            NlpTemplatePatternMatcher.stringMap(value.getJSONObject("resolved_face_ids")), value.getString("concept_id")) }
                    val cost = native.words.count { it.first >= context.start && it.last < context.end }
                    metadata.put(JSONObject().put("rule_id", raw.getString("rule_id")).put("supplied_adversarial_cost", raw.getInt("context_native_words"))
                        .put("actual_native_context_cost", cost).put("context_range_utf16", context.json()))
                    val pattern = Pattern(raw.getString("rule_id"), "structural_test_only", "en", setOf("exact_top_down"), emptyList(),
                        raw.getString("atomic_mode"), mask, raw.getString("reason"), outputs, raw.getString("meaning_id"), raw.getInt("priority"),
                        "frozen synthetic eligibility fixture", fixtureSha)
                    Recognition(pattern, Parse(context, bindings), cost)
                }
                val combined = recognized.copy(recognitions = retained + synthetic)
                val expected = input.getJSONObject("expected")
                val keep = NlpTemplatePatternMatcher.strings(expected.getJSONArray("keep_output_ids")).toSet()
                val reject = NlpTemplatePatternMatcher.strings(expected.getJSONArray("reject_output_ids")).toSet()
                for (target in listOf("sw", "ja", "es")) {
                    val result = catalog.select(native, combined, target, .50, "none")
                    fun label(id: String): String = if (id.startsWith("diagnostic-fallback:")) {
                        "diagnostic:" + requireNotNull(catalog.faces[id.removePrefix("diagnostic-fallback:")]).conceptID
                    } else id
                    val selected = result.selected.map { label(it.outputID) }.toSet()
                    val refused = (0 until result.rejections.length()).map { label(result.rejections.getJSONObject(it).getString("output_id")) }.toSet()
                    rows.put(JSONObject().put("id", input.getString("id")).put("target", target).put("text", text)
                        .put("selected_ids", JSONArray(selected.toList().sorted())).put("rejected_ids", JSONArray(refused.toList().sorted()))
                        .put("rejections", result.rejections).put("synthetic_metadata", metadata).put("native_budget", result.budget)
                        .put("native_source_word_ranges_utf16", JSONArray(native.words.map { JSONArray(listOf(it.first, it.last + 1)) }))
                        .put("recognition_count", combined.recognitions.size).put("retained_masks", JSONArray(combined.recognitions.mapNotNull { it.mask?.json() })))
                    assertTrue("${input.getString("id")}/$target missing approved output", selected.containsAll(keep))
                    assertTrue("${input.getString("id")}/$target leaked rejected output", selected.intersect(reject).isEmpty())
                    assertTrue("${input.getString("id")}/$target missing rejection evidence", refused.containsAll(reject))
                }
            }
            assertEquals(9, rows.length()); report.put("complete", true)
        } finally { output.writeText(report.toString(2)) }
    }
}
