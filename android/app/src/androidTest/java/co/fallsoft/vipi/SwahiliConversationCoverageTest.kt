package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.TranslationIntegrity
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest

/** Frozen public evaluation turns. Never app resources or authoring examples. */
@RunWith(AndroidJUnit4::class)
class SwahiliConversationCoverageTest {
    @Test fun frozenTestTurnsThroughActualLocalTranslationAndBundledCatalog() = runBlocking {
        val arguments = InstrumentationRegistry.getArguments()
        check(arguments.getString("vipiDedicatedEmulator") == "true")
        val revision = (arguments.getString("vipiSwahiliCoverageRun") ?: "001").also { require(it.matches(Regex("[0-9]{3}"))) }
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val input = File(context.filesDir, "afriwoz-probe-001.json").readBytes()
        val corpus = JSONObject(input.toString(Charsets.UTF_8))
        check(corpus.getString("schema") == "vipi-afriwoz-probe-1" && corpus.getString("source") == "sw")
        val output = File(context.filesDir, "swahili-coverage-$revision.json"); check(!output.exists())
        val rows = JSONArray(); val catalog = BundledImmersionCatalog(context)
        val cases = corpus.getJSONArray("cases"); val targets = corpus.getJSONArray("targets")
        val report = JSONObject().put("schema", "vipi-swahili-live-catalog-coverage-1").put("platform", "android")
            .put("corpus_sha256", MessageDigest.getInstance("SHA-256").digest(input).joinToString("") { "%02x".format(it) })
            .put("catalog_sha256", MessageDigest.getInstance("SHA-256").digest(context.assets.open("immersion/catalog.json").use { it.readBytes() }).joinToString("") { "%02x".format(it) })
            .put("semantic_acceptance", false).put("rows", rows)
        LocalTranslation().use { translator ->
            for (targetIndex in 0 until targets.length()) {
                val target = targets.getString(targetIndex)
                // These models were explicitly installed in the Swahili native
                // qualification. Evaluation does not initiate model downloads.
                val prepared = ConversationImmersion(context, "sw", target, 1.0)
                try { prepared.checkDownloads(); assertEquals(true, prepared.ready) } finally { prepared.close() }
                for (index in 0 until cases.length()) {
                    val case = cases.getJSONObject(index)
                    val original = case.getJSONObject("text").getString("sw")
                    val start = System.nanoTime()
                    val exact = catalog.reference(original, "sw", target)
                    val translation = exact ?: translator.translate(original, "sw", target)
                    val preserves = TranslationIntegrity.preservesIdentifiers(original, translation)
                    val result = if (preserves) catalog.result(original, translation, "sw", target, 1.0) else null
                    if (result != null) assertEquals(original, result.speech("sw", target, result.spans.map { it.id }.toSet()).joinToString("") { it.text })
                    val spans = JSONArray(result?.spans?.map { span -> JSONObject()
                        .put("start", span.start).put("end", span.end).put("original", span.original)
                        .put("translated", span.translated).put("targetStart", span.targetStart).put("targetEnd", span.targetEnd)
                        .put("reading", span.romanization ?: JSONObject.NULL) } ?: emptyList<JSONObject>())
                    rows.put(JSONObject().put("id", case.getString("id")).put("source", "sw").put("target", target)
                        .put("original", original).put("translation", translation).put("exact_reference", exact != null)
                        .put("identifier_integrity", preserves).put("spans", spans).put("elapsed_ms", (System.nanoTime()-start)/1e6))
                }
                output.writeText(report.toString(2))
            }
        }
        assertEquals(cases.length()*targets.length(), rows.length())
    }
}
