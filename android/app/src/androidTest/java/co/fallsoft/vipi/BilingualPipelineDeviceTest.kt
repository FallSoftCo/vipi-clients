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
    private data class CapturedSample(val original: String, val translation: String, val status: String)
    private data class Capture(val sha256: String, val pairs: Map<String, Map<String, CapturedSample>>)
    private fun readCapture(file: File): Capture {
        val bytes = file.readBytes()
        val values = JSONObject(bytes.toString(Charsets.UTF_8)).getJSONArray("results")
        val pairs = (0 until values.length()).associate { index ->
            val pair = values.getJSONObject(index)
            val samples = pair.getJSONArray("samples")
            (pair.getString("source") + "-" + pair.getString("target")) to
                (0 until samples.length()).associate { sampleIndex ->
                    val sample = samples.getJSONObject(sampleIndex)
                    sample.getString("id") to CapturedSample(sample.getString("original"), sample.getString("translation"), sample.getString("status"))
                }
        }
        return Capture(java.security.MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }, pairs)
    }
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
        val capturedName = arguments.getString("vipiTranslationReport")
        val captured = capturedName?.let {
            require(it.matches(Regex("[a-z0-9-]+\\.json")))
            readCapture(File(context.filesDir, "bilingual-qa/$it"))
        }
        val capturedPairs = captured?.pairs
        val codes = corpus.getJSONArray("languages").let { list -> (0 until list.length()).map { list.getString(it) } }
        val cases = corpus.getJSONArray("cases")
        val isolated = File(context.cacheDir, "bilingual-qa-${UUID.randomUUID()}").apply { mkdirs() }
        val qaContext = object : ContextWrapper(context) {
            override fun getFilesDir() = File(isolated, "files").apply { mkdirs() }
            override fun getNoBackupFilesDir() = File(isolated, "no-backup").apply { mkdirs() }
        }
        val store = VocabularyPackStore(qaContext, mapOf("bilingual-qualification-$runID" to File(packs, "signing-public-key.der").readBytes()))
        var completedPairs = 0
        val report = JSONObject().put("schema", 1).put("platform", "Android").put("provider", "MLKit 17.0.3")
            .put("corpus", corpus.getString("version"))
            .put("evidence", "actual_offline_translation_and_signed_dictionary_alignment_pending_semantic_review")
            .put("linguistic_acceptance", false)
        if (corpus.has("attribution")) report.put("attribution", corpus.getJSONObject("attribution"))
        if (captured != null) {
            report.put("evidence", "actual_offline_alignment_on_captured_mlkit_translations_not_new_translation_execution")
            report.put("translation_capture_sha256", captured.sha256)
        }
        val receipt = File(context.filesDir, reportName)
        check(!receipt.exists()) { "Preserve existing qualification receipts" }
        // Keep only one pair in memory. A large corpus plus the Japanese model
        // must not require retaining two complete token/span JSON trees.
        val output = receipt.bufferedWriter()
        output.write(report.toString(2).dropLast(1) + ",\n\"results\": [\n")
        fun save(pair: JSONObject) {
            if (completedPairs > 0) output.write(",\n")
            output.write(pair.toString(2)); output.flush(); completedPairs++
        }
        val wifi = shell("settings get global wifi_on").trim() == "1"
        val mobile = shell("settings get global mobile_data").trim() == "1"
        var failures = 0
        var networkWasAbsent = false
        try {
            shell("svc wifi disable"); shell("svc data disable")
            val network = context.getSystemService(ConnectivityManager::class.java)
            withTimeout(15_000) { while (network.activeNetwork != null) delay(100) }
            assertNull(network.activeNetwork)
            networkWasAbsent = true
            LocalTranslation().use { translator ->
                for (source in codes) for (target in codes.filter { it != source }) {
                    val id = "$source-$target"; val folder = File(packs, id)
                    val pair = JSONObject().put("source", source).put("target", target)
                    val samples = JSONArray(); pair.put("samples", samples)
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
                                val translation = if (capturedPairs == null) withTimeout(45_000) { translator.translate(original, source, target) }
                                else {
                                    val saved = requireNotNull(capturedPairs[id])
                                    val observed = requireNotNull(saved[item.getString("id")])
                                    check(observed.original == original && observed.status == "executed")
                                    observed.translation
                                }
                                sample.put("translation_reused", capturedPairs != null)
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
                    finally { store.remove(id); save(pair) }
                }
            }
        } finally {
            output.write("\n],\n\"completed_pairs\": $completedPairs,\n\"network_absence_verified\": $networkWasAbsent\n}\n"); output.close()
            if (wifi) shell("svc wifi enable")
            if (mobile) shell("svc data enable")
            isolated.deleteRecursively()
        }
        assertEquals(90, completedPairs)
        assertEquals("Execution failures; semantic quality is evaluated separately", 0, failures)
    }
}
