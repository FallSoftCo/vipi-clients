package co.fallsoft.vipi

import android.content.ContextWrapper
import android.net.ConnectivityManager
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.UUID

/** Real downloaded dictionaries + actual offline ML Kit output. This exports
 * every replacement for semantic review; execution is not linguistic approval. */
@RunWith(AndroidJUnit4::class)
class BilingualPipelineDeviceTest {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private fun shell(command: String) = instrumentation.uiAutomation.executeShellCommand(command).use { descriptor ->
        java.io.FileInputStream(descriptor.fileDescriptor).bufferedReader().use { it.readText() }
    }
    @Test fun recordAllActualOfflinePairsWithSignedDictionaries() = runBlocking {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        check(android.os.Build.FINGERPRINT.contains("generic") || android.os.Build.MODEL.contains("sdk_gphone"))
        val context = instrumentation.targetContext
        val arguments = InstrumentationRegistry.getArguments()
        val runID = arguments.getString("vipiRunID") ?: "001"
        require(runID.matches(Regex("[0-9]{3}")))
        val packs = File(context.filesDir, if (runID == "001") "bilingual-qa/packs" else "bilingual-qa/packs-$runID")
        val corpusName = arguments.getString("vipiCorpusFile") ?: "corpus.json"
        val reportName = arguments.getString("vipiReportName") ?: "bilingual-pipeline-$runID.json"
        require(corpusName.matches(Regex("[a-z0-9-]+\\.json")) && reportName.matches(Regex("[a-z0-9-]+\\.json")))
        val corpus = JSONObject(File(context.filesDir, "immersion-qa/$corpusName").readText())
        val codes = corpus.getJSONArray("languages").let { list -> (0 until list.length()).map { list.getString(it) } }
        val cases = corpus.getJSONArray("cases")
        val isolated = File(context.cacheDir, "bilingual-qa-${UUID.randomUUID()}").apply { mkdirs() }
        val qaContext = object : ContextWrapper(context) {
            override fun getFilesDir() = File(isolated, "files").apply { mkdirs() }
            override fun getNoBackupFilesDir() = File(isolated, "no-backup").apply { mkdirs() }
        }
        val store = VocabularyPackStore(qaContext, mapOf("bilingual-qualification-$runID" to File(packs, "signing-public-key.der").readBytes()))
        val results = JSONArray()
        val report = JSONObject().put("schema", 1).put("platform", "Android").put("provider", "MLKit 17.0.3")
            .put("corpus", corpus.getString("version"))
            .put("evidence", "actual_offline_translation_and_signed_dictionary_alignment_pending_semantic_review")
            .put("linguistic_acceptance", false).put("results", results)
        if (corpus.has("attribution")) report.put("attribution", corpus.getJSONObject("attribution"))
        val receipt = File(context.filesDir, reportName)
        fun save() { receipt.writeText(report.toString(2)) }
        val wifi = shell("settings get global wifi_on").trim() == "1"
        val mobile = shell("settings get global mobile_data").trim() == "1"
        var failures = 0
        try {
            shell("svc wifi disable"); shell("svc data disable")
            val network = context.getSystemService(ConnectivityManager::class.java)
            withTimeout(15_000) { while (network.activeNetwork != null) delay(100) }
            assertNull(network.activeNetwork); report.put("activeNetwork", "none")
            LocalTranslation().use { translator ->
                for (source in codes) for (target in codes.filter { it != source }) {
                    val id = "$source-$target"; val folder = File(packs, id)
                    val pair = JSONObject().put("source", source).put("target", target)
                    val samples = JSONArray(); pair.put("samples", samples); results.put(pair)
                    try {
                        val started = SystemClock.elapsedRealtimeNanos()
                        store.install(File(folder, "manifest.json").readBytes(), File(folder, "manifest.sig").readBytes(), File(folder, "vocabulary.sqlite").readBytes())
                        pair.put("install_ms", (SystemClock.elapsedRealtimeNanos() - started) / 1_000_000.0)
                        pair.put("pack_sha256", JSONObject(File(folder, "manifest.json").readText()).getString("sha256"))
                        repeat(cases.length()) { index ->
                            val item = cases.getJSONObject(index); val original = item.getJSONObject("text").getString(source)
                            val sample = JSONObject().put("id", item.getString("id")).put("original", original)
                                .put("reference", item.getJSONObject("text").getString(target))
                            samples.put(sample)
                            try {
                                val begin = SystemClock.elapsedRealtimeNanos()
                                val translation = withTimeout(45_000) { translator.translate(original, source, target) }
                                sample.put("translation_ms", (SystemClock.elapsedRealtimeNanos() - begin) / 1_000_000.0)
                                sample.put("translation", translation)
                                val lookup = SystemClock.elapsedRealtimeNanos()
                                val entries = store.entries(id, original)
                                val result = LocalImmersion.align(original, translation, entries, 0.3, source, target)
                                sample.put("lookup_alignment_ms", (SystemClock.elapsedRealtimeNanos() - lookup) / 1_000_000.0)
                                sample.put("candidate_senses", entries.size).put("status", "executed")
                                fun words(text: String, language: String) = JSONArray(LocalImmersion.words(text, language).map {
                                    JSONObject().put("text", text.substring(it)).put("start", it.first).put("end", it.last + 1)
                                })
                                sample.put("source_words", words(original, source)).put("target_words", words(translation, target))
                                sample.put("spans", JSONArray(result.spans.map { span -> JSONObject()
                                    .put("start", span.start).put("end", span.end).put("original", span.original)
                                    .put("translated", span.translated).put("reading", span.romanization ?: JSONObject.NULL)
                                    .put("targetStart", span.targetStart).put("targetEnd", span.targetEnd) }))
                                sample.put("speech", JSONArray(result.speech(source, target).map { JSONObject().put("text", it.text).put("language", it.language) }))
                            } catch (error: Exception) { failures++; sample.put("status", "failed").put("error_type", error.javaClass.simpleName) }
                        }
                        pair.put("status", "executed")
                    } catch (error: Exception) { failures++; pair.put("status", "failed").put("error_type", error.javaClass.simpleName) }
                    finally { store.remove(id); save() }
                }
            }
        } finally {
            if (wifi) shell("svc wifi enable")
            if (mobile) shell("svc data enable")
            isolated.deleteRecursively()
        }
        assertEquals(90, results.length())
        assertEquals("Execution failures; semantic quality is evaluated separately", 0, failures)
    }
}
