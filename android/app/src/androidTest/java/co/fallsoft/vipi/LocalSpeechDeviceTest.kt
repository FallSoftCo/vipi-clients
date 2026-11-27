package co.fallsoft.vipi

import android.net.ConnectivityManager
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.SpeechSpan
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class LocalSpeechDeviceTest {
    private val instrumentation
        get() = InstrumentationRegistry.getInstrumentation()

    private fun shell(command: String) =
        instrumentation.uiAutomation.executeShellCommand(command).use { descriptor ->
            java.io.FileInputStream(descriptor.fileDescriptor).bufferedReader().use {
                it.readText()
            }
        }

    @Test
    fun recordActualOfflineAudioAndPreparedPairTiming() = runBlocking {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        check(
            android.os.Build.FINGERPRINT.contains("generic") ||
                android.os.Build.MODEL.contains("sdk_gphone")
        )
        val context = instrumentation.targetContext
        val corpus = JSONObject(File(context.filesDir, "immersion-qa/corpus.json").readText())
        val codes =
            corpus.getJSONArray("languages").let { a ->
                (0 until a.length()).map { a.getString(it) }
            }
        val samples = corpus.getJSONArray("cases").getJSONObject(0).getJSONObject("text")
        val directory = File(context.filesDir, "speech-qa").apply { mkdirs() }
        val outputs = JSONArray()
        val report =
            JSONObject()
                .put("evidence", "offline_synthesis_not_yet_listening_or_ui_acceptance")
                .put("languages", outputs)
        val revision = InstrumentationRegistry.getArguments().getString("vipiReceipt") ?: "001"
        require(revision.matches(Regex("[0-9]{3}")))
        val receipt = File(directory, "speech-$revision.json")
        val wifi = shell("settings get global wifi_on").trim() == "1"
        val mobile = shell("settings get global mobile_data").trim() == "1"
        try {
            shell("svc wifi disable")
            shell("svc data disable")
            val network = context.getSystemService(ConnectivityManager::class.java)
            withTimeout(15_000) { while (network.activeNetwork != null) delay(100) }
            assertNull(network.activeNetwork)
            report.put("activeNetwork", "none")
            for (code in codes) {
                val row = JSONObject().put("language", code)
                val voice = withContext(Dispatchers.Main) { LocalVoice(context, code) }
                try {
                    row.put("voice", voice.select())
                    val started = SystemClock.elapsedRealtimeNanos()
                    val rendered =
                        voice.render(samples.getString(code), File(directory, "$code.wav"))
                    row.put("status", "synthesized")
                        .put(
                            "render_ms",
                            (SystemClock.elapsedRealtimeNanos() - started) / 1_000_000.0,
                        )
                        .put("audio_ms", rendered.milliseconds)
                        .put("sample_rate", rendered.sampleRate)
                        .put("channels", rendered.channels)
                        .put(
                            "word_markers",
                            JSONArray(
                                rendered.marks.map {
                                    JSONObject()
                                        .put("start", it.start)
                                        .put("end", it.end)
                                        .put("frame", it.frame)
                                }
                            ),
                        )
                        .put("rejected_markers", rendered.rejectedMarks)
                } catch (error: Exception) {
                    row.put("status", "failed").put("error_type", error.javaClass.simpleName)
                } finally {
                    withContext(Dispatchers.Main) { voice.close() }
                }
                outputs.put(row)
                receipt.writeText(report.toString(2))
            }
            val pair = withContext(Dispatchers.Main) { LocalSpeechPair(context, "en", "es") }
            val pairReport = JSONObject()
            report.put("en_es_pair", pairReport)
            try {
                var start = SystemClock.elapsedRealtimeNanos()
                pair.prepare(mapOf("en" to "Hello.", "es" to "Hola."))
                pairReport.put(
                    "prepare_ms",
                    (SystemClock.elapsedRealtimeNanos() - start) / 1_000_000.0,
                )
                val spans =
                    listOf(
                        SpeechSpan("Coffee ", "en"),
                        SpeechSpan("mañana", "es"),
                        SpeechSpan("? I know a little place by the ", "en"),
                        SpeechSpan("río", "es"),
                    )
                start = SystemClock.elapsedRealtimeNanos()
                val rendered = pair.render(spans)
                pairReport.put(
                    "first_render_ms",
                    (SystemClock.elapsedRealtimeNanos() - start) / 1_000_000.0,
                )
                rendered.file.copyTo(File(directory, "en-es-mixed.wav"), overwrite = true)
                start = SystemClock.elapsedRealtimeNanos()
                val replay = pair.render(spans)
                pairReport
                    .put(
                        "cached_render_ms",
                        (SystemClock.elapsedRealtimeNanos() - start) / 1_000_000.0,
                    )
                    .put("audio_ms", rendered.milliseconds)
                    .put("status", "single_pcm_file_rendered")
                assertEquals(rendered.file, replay.file)
            } catch (error: Exception) {
                pairReport.put("status", "failed").put("error_type", error.javaClass.simpleName)
            } finally {
                withContext(Dispatchers.Main) { pair.close() }
                receipt.writeText(report.toString(2))
            }
        } finally {
            if (wifi) shell("svc wifi enable")
            if (mobile) shell("svc data enable")
        }
        assertEquals(10, outputs.length())
    }
}
