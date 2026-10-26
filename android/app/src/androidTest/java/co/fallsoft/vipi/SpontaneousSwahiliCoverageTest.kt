package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.ImmersionResult
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest

/** Public speech transcripts staged only into the dedicated debug app's files. */
@RunWith(AndroidJUnit4::class)
class SpontaneousSwahiliCoverageTest {
    @Test fun reservedTurnsThroughAutomaticAndExplicitLanguagePaths() = runBlocking {
        val arguments = InstrumentationRegistry.getArguments()
        check(arguments.getString("vipiDedicatedEmulator") == "true")
        val revision = (arguments.getString("vipiSpontaneousCoverageRun") ?: "001").also { require(it.matches(Regex("[0-9]{3}"))) }
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val input = File(context.filesDir, "liva-swahili-probe-001.json").readBytes()
        val corpus = JSONObject(input.toString(Charsets.UTF_8))
        check(corpus.getString("schema") == "vipi-liva-swahili-probe-1" && corpus.getString("source") == "sw")
        val output = File(context.filesDir, "spontaneous-swahili-coverage-$revision.json"); check(!output.exists())
        fun hash(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
        fun capture(result: ImmersionResult?): Any = result?.let {
            assertEquals(it.original, it.speech("sw", "unused", it.spans.map { span -> span.id }.toSet()).joinToString("") { span -> span.text })
            JSONObject().put("baseline", it.original).put("translation", it.translation).put("spans", JSONArray(it.spans.map { span ->
                JSONObject().put("start", span.start).put("end", span.end).put("original", span.original)
                    .put("translated", span.translated).put("targetStart", span.targetStart).put("targetEnd", span.targetEnd)
                    .put("reading", span.romanization ?: JSONObject.NULL)
            }))
        } ?: JSONObject.NULL
        val rows = JSONArray(); val cases = corpus.getJSONArray("cases"); val targets = corpus.getJSONArray("targets")
        val report = JSONObject().put("schema", "vipi-spontaneous-swahili-coverage-1").put("platform", "android")
            .put("corpus_sha256", hash(input)).put("catalog_sha256", hash(context.assets.open("immersion/catalog.json").use { it.readBytes() }))
            .put("semantic_acceptance", false).put("rows", rows)
        for (targetIndex in 0 until targets.length()) {
            val target = targets.getString(targetIndex)
            val immersion = ConversationImmersion(context, "sw", target, 1.0)
            try {
                immersion.checkDownloads(); assertEquals(true, immersion.ready)
                for (index in 0 until cases.length()) {
                    val case = cases.getJSONObject(index); val original = case.getJSONObject("text").getString("sw")
                    val start = System.nanoTime(); val automatic = immersion.result(original)
                    val automaticMs = (System.nanoTime()-start)/1e6
                    val explicitStart = System.nanoTime(); val explicit = immersion.result(original, inputLanguage = "sw")
                    val explicitMs = (System.nanoTime()-explicitStart)/1e6
                    if (explicit != null) assertEquals(original, explicit.original)
                    if (automatic != null) assertTrue(automatic.original == original || automatic.translation == original)
                    rows.put(JSONObject().put("id", case.getString("id")).put("source", "sw").put("target", target)
                        .put("original", original).put("automatic", capture(automatic)).put("explicit_sw", capture(explicit))
                        .put("automatic_elapsed_ms", automaticMs).put("explicit_elapsed_ms", explicitMs))
                }
                output.writeText(report.toString(2))
            } finally { immersion.close() }
        }
        assertEquals(cases.length()*targets.length(), rows.length())
    }
}
