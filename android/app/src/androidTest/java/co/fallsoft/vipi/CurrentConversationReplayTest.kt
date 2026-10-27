package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.TranslationIntegrity
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest

/** Current app catalog on fixed, previously captured native translations.
 * This does not rerun translation or classification, or certify meaning. */
@RunWith(AndroidJUnit4::class)
class CurrentConversationReplayTest {
    @Test fun replaySevenDiagnosticSourceLanguagesWithoutChangingTheirCaptures() {
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("vipiDedicatedEmulator") == "true")
        val run = requireNotNull(args.getString("vipiConversationReplayRun"))
        require(run.matches(Regex("[0-9]{3}")))
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
        val manifestBytes = File(context.filesDir, "conversation-replay-input-001/manifest.json").readBytes()
        val manifest = JSONObject(manifestBytes.toString(Charsets.UTF_8))
        check(manifest.getString("schema") == "vipi-captured-conversation-input-1")
        val catalog = BundledImmersionCatalog(context)
        val report = JSONObject().put("schema", "vipi-current-conversation-replay-1")
            .put("catalog_sha256", sha(context.assets.open("immersion/catalog.json").use { it.readBytes() }))
            .put("input_manifest_sha256", sha(manifestBytes)).put("density", 1.0)
            .put("translation_reused", true).put("classification_exercised", false)
            .put("independent_semantic_acceptance", false).put("release_ready", false)
        val output = File(context.filesDir, "current-conversation-replay-$run.json"); check(!output.exists())
        val datasets = JSONArray(); report.put("datasets", datasets)
        val sourceLanguages = mutableSetOf<String>(); var total = 0
        val files = manifest.getJSONArray("files")
        for (index in 0 until files.length()) {
            val entry = files.getJSONObject(index)
            val name = entry.getString("file"); require(name.matches(Regex("[a-z0-9-]+\\.json")))
            val bytes = File(context.filesDir, "conversation-replay-input-001/$name").readBytes()
            check(sha(bytes) == entry.getString("sha256"))
            val dataset = JSONObject(bytes.toString(Charsets.UTF_8)); val inputPairs = dataset.getJSONArray("pairs")
            val pairs = JSONArray(); val summary = JSONObject().put("name", dataset.getString("name"))
                .put("capture_sha256", dataset.getString("capture_sha256")).put("corpus_sha256", dataset.getString("corpus_sha256"))
                .put("pairs", pairs); datasets.put(summary)
            for (pairIndex in 0 until inputPairs.length()) {
                val pair = inputPairs.getJSONObject(pairIndex)
                val source = pair.getString("source"); val target = pair.getString("target"); sourceLanguages += source
                val samples = pair.getJSONArray("samples"); val outcomes = JSONArray()
                val pairReport = JSONObject().put("source", source).put("target", target).put("cases", samples.length()).put("outcomes", outcomes)
                pairs.put(pairReport)
                var withImmersion = 0; var spans = 0; var protected = 0; var references = 0; var invalid = 0
                for (sampleIndex in 0 until samples.length()) {
                    val sample = samples.getJSONObject(sampleIndex); check(sample.getString("status") == "executed")
                    val original = sample.getString("original"); val captured = sample.getString("translation")
                    val start = System.nanoTime()
                    val reference = catalog.reference(original, source, target)
                    val translation = reference ?: captured
                    val bounded = original.isNotBlank() && original.length <= 16_384
                    val intact = TranslationIntegrity.preservesIdentifiers(original, translation)
                    if (!bounded) invalid++ else if (!intact) protected++
                    if (reference != null) references++
                    val result = if (bounded && intact) catalog.result(original, translation, source, target, 1.0) else null
                    if (result != null) {
                        assertEquals(original, result.original)
                        assertEquals(original, result.speech(source, target, result.spans.map { it.id }.toSet()).joinToString("") { it.text })
                        if (target in setOf("ar", "zh", "ja", "ko")) assertTrue(result.spans.all { !it.romanization.isNullOrBlank() })
                    }
                    val count = result?.spans?.size ?: 0
                    if (count > 0) withImmersion++; spans += count
                    outcomes.put(JSONObject().put("id", sample.getString("id")).put("selected", count)
                        .put("reference_used", reference != null).put("identifier_guard", intact)
                        .put("elapsed_ms", (System.nanoTime()-start)/1e6))
                }
                total += samples.length()
                pairReport.put("with_immersion", withImmersion).put("selected_spans", spans)
                    .put("identifier_abstentions", protected).put("invalid_inputs", invalid).put("exact_references", references)
                output.writeText(report.toString(2))
            }
        }
        assertEquals(9900, total); assertEquals(setOf("en", "zh", "ar", "fr", "it", "ja", "ko"), sourceLanguages)
        report.put("cases", total).put("source_languages", JSONArray(sourceLanguages.sorted()))
        output.writeText(report.toString(2))
    }
}
