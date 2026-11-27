package co.fallsoft.vipi

import android.net.ConnectivityManager
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.SpeechSpan
import java.io.File
import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class SwahiliFallbackDeviceTest {
    private val instrumentation
        get() = InstrumentationRegistry.getInstrumentation()

    private fun shell(value: String) =
        instrumentation.uiAutomation.executeShellCommand(value).use {
            java.io.FileInputStream(it.fileDescriptor).bufferedReader().use { input ->
                input.readText()
            }
        }

    @Test
    fun bundledFallbackAndPreparedMixedPairRenderWithNetworkAbsent(): Unit = runBlocking {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        check(
            android.os.Build.FINGERPRINT.contains("generic") ||
                android.os.Build.MODEL.contains("sdk_gphone")
        )
        val context = instrumentation.targetContext
        val revision =
            InstrumentationRegistry.getArguments().getString("vipiSpeechFallbackRun") ?: "001"
        require(revision.matches(Regex("[0-9]{3}")))
        val directory = File(context.filesDir, "swahili-fallback-$revision")
        check(!directory.exists())
        directory.mkdirs()
        val wifi = shell("settings get global wifi_on").trim() == "1"
        val mobile = shell("settings get global mobile_data").trim() == "1"
        val network = context.getSystemService(ConnectivityManager::class.java)
        val report =
            JSONObject()
                .put(
                    "evidence",
                    "actual_offline_native_synthesis_and_mixed_pcm_not_listening_acceptance",
                )
        try {
            shell("svc wifi disable")
            shell("svc data disable")
            withTimeout(15_000) { while (network.activeNetwork != null) delay(100) }
            assertNull(network.activeNetwork)
            var began = System.nanoTime()
            report
                .put("fallback_voice", SwahiliSpeech.prepare(context))
                .put("prepare_ms", (System.nanoTime() - began) / 1e6)
            began = System.nanoTime()
            val output =
                SwahiliSpeech.render(
                    context,
                    "Habari! Ninakunywa maji sasa. Tutakutana kesho.",
                    File(directory, "swahili.wav"),
                    SwahiliSpeech.Job(),
                )
            val wave = PcmWave.read(output.file)
            assertTrue(wave.samples.any { it != 0.toByte() })
            assertTrue(output.milliseconds > 1000)
            report
                .put("fallback_render_ms", (System.nanoTime() - began) / 1e6)
                .put("fallback_audio_ms", output.milliseconds)
                .put("fallback_sample_rate", output.sampleRate)
            val cancelled = SwahiliSpeech.Job().apply { cancel() }
            try {
                SwahiliSpeech.render(
                    context,
                    "Habari.",
                    File(directory, "cancelled.wav"),
                    cancelled,
                )
                fail("Cancelled speech rendered")
            } catch (_: CancellationException) {
                assertFalse(File(directory, "cancelled.wav").exists())
            }
            report.put("pre_cancelled_job_produced_no_file", true)
            val active = SwahiliSpeech.Job()
            val during = File(directory, "cancelled-during.wav")
            val rendering =
                async(Dispatchers.Default) {
                    SwahiliSpeech.render(
                        context,
                        "Ninakunywa maji sasa. ".repeat(500),
                        during,
                        active,
                    )
                }
            withTimeout(5000) {
                while (active.generatedFrames() == 0 && !rendering.isCompleted) delay(1)
            }
            assertTrue(active.generatedFrames() > 0)
            assertFalse(rendering.isCompleted)
            report.put("frames_before_mid_utterance_cancel", active.generatedFrames())
            active.cancel()
            try {
                rendering.await()
                fail("Cancelled active speech completed")
            } catch (_: CancellationException) {
                assertFalse(during.exists())
            }
            report.put("mid_utterance_cancel_removed_output", true)
            val pair = withContext(Dispatchers.Main) { LocalSpeechPair(context, "en", "sw") }
            try {
                began = System.nanoTime()
                pair.prepare(mapOf("en" to "Hello.", "sw" to "Habari."))
                report.put("pair_prepare_ms", (System.nanoTime() - began) / 1e6)
                began = System.nanoTime()
                val rendered =
                    pair.render(
                        listOf(
                            SpeechSpan("We can meet ", "en"),
                            SpeechSpan("kesho", "sw"),
                            SpeechSpan(". Bring a book.", "en"),
                        )
                    )
                rendered.file.copyTo(File(directory, "en-sw-mixed.wav"))
                report
                    .put("mixed_render_ms", (System.nanoTime() - began) / 1e6)
                    .put("mixed_audio_ms", rendered.milliseconds)
                    .put("mixed_sample_rate", rendered.sampleRate)
                    .put("mixed_channels", rendered.channels)
                assertTrue(rendered.milliseconds > 500)
            } finally {
                withContext(Dispatchers.Main) { pair.close() }
            }
            assertNull(network.activeNetwork)
            report.put("complete", true).put("active_network", "none")
        } finally {
            if (wifi) shell("svc wifi enable")
            if (mobile) shell("svc data enable")
            File(directory, "receipt.json").writeText(report.toString(2))
        }
    }
}
