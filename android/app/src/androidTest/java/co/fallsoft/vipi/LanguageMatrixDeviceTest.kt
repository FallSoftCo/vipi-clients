package co.fallsoft.vipi

import android.net.ConnectivityManager
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Execution evidence, not an assertion of linguistic quality or complete UX. */
@RunWith(AndroidJUnit4::class)
class LanguageMatrixDeviceTest {
    private val instrumentation
        get() = InstrumentationRegistry.getInstrumentation()

    private fun shell(command: String) =
        instrumentation.uiAutomation.executeShellCommand(command).use { descriptor ->
            java.io.FileInputStream(descriptor.fileDescriptor).bufferedReader().use {
                it.readText()
            }
        }

    @Test
    fun recordEveryDirectedPairOffline() = runBlocking {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        check(
            android.os.Build.FINGERPRINT.contains("generic") ||
                android.os.Build.MODEL.contains("sdk_gphone")
        )
        val context = instrumentation.targetContext
        val corpus = JSONObject(File(context.filesDir, "immersion-qa/corpus.json").readText())
        val codes =
            corpus.getJSONArray("languages").let { list ->
                (0 until list.length()).map { list.getString(it) }
            }
        val cases = corpus.getJSONArray("cases")
        val preparation = JSONArray()
        val results = JSONArray()
        val report =
            JSONObject()
                .put("schema", 1)
                .put("provider", "MLKit 17.0.3")
                .put("corpus", corpus.getString("version"))
                .put(
                    "evidence",
                    "translation_execution_only_immersion_and_transliteration_not_yet_qualified",
                )
                .put("preparation", preparation)
                .put("results", results)
        val receipt = File(context.filesDir, "language-matrix-001.json")
        fun save() {
            receipt.writeText(report.toString(2))
        }
        val wifi = shell("settings get global wifi_on").trim() == "1"
        val mobile = shell("settings get global mobile_data").trim() == "1"
        LocalTranslation().use { engine ->
            // ML Kit stores language models individually; prepare each language
            // against English before testing every actual directed pair offline.
            for (code in codes.filter { it != "en" }) {
                val result = JSONObject().put("language", code)
                try {
                    withTimeout(300_000) { engine.prepare("en", code, cellularAllowed = true) }
                    result.put("status", "prepared")
                } catch (error: Exception) {
                    result.put("status", "failed").put("error_type", error.javaClass.simpleName)
                }
                preparation.put(result)
                save()
            }
            try {
                shell("svc wifi disable")
                shell("svc data disable")
                val network = context.getSystemService(ConnectivityManager::class.java)
                withTimeout(15_000) { while (network.activeNetwork != null) delay(100) }
                assertNull(network.activeNetwork)
                report.put("activeNetwork", "none")
                for (source in codes) for (target in codes.filter { it != source }) {
                    val pair = JSONObject().put("source", source).put("target", target)
                    val samples = JSONArray()
                    for (index in 0 until cases.length()) {
                        val item = cases.getJSONObject(index)
                        val original = item.getJSONObject("text").getString(source)
                        val sample =
                            JSONObject().put("id", item.getString("id")).put("original", original)
                        val started = SystemClock.elapsedRealtimeNanos()
                        try {
                            val translated =
                                withTimeout(45_000) { engine.translate(original, source, target) }
                            sample
                                .put("translation", translated)
                                .put(
                                    "status",
                                    if (translated.isBlank()) "empty_output" else "executed",
                                )
                        } catch (error: Exception) {
                            sample
                                .put("status", "failed")
                                .put("error_type", error.javaClass.simpleName)
                        }
                        sample.put(
                            "latency_ms",
                            (SystemClock.elapsedRealtimeNanos() - started) / 1_000_000.0,
                        )
                        samples.put(sample)
                    }
                    pair
                        .put("samples", samples)
                        .put("ux_acceptance", "not_run")
                        .put("linguistic_review", "pending")
                    results.put(pair)
                    save()
                }
            } finally {
                if (wifi) shell("svc wifi enable")
                if (mobile) shell("svc data enable")
            }
        }
        assertEquals(90, results.length())
        // Failure counts stay in the receipt. Merely exporting 90 cells is not a
        // successful translation/immersion qualification.
    }
}
