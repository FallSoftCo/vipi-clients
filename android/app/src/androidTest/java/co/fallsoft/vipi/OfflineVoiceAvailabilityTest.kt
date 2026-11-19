package co.fallsoft.vipi

import android.net.ConnectivityManager
import android.speech.tts.TextToSpeech
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.MessageDigest
import java.time.Instant

/** Availability audit only: advertised voices do not count as rendered audio. */
class OfflineVoiceAvailabilityTest {
    @Test fun auditAdvertisedAndActualVoicesWithoutDownloadingModels(): Unit = runBlocking {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        check(android.os.Build.FINGERPRINT.contains("generic") || android.os.Build.MODEL.contains("sdk_gphone"))
        val context = instrumentation.targetContext
        fun shell(command: String) = instrumentation.uiAutomation.executeShellCommand(command).use {
            java.io.FileInputStream(it.fileDescriptor).bufferedReader().use { stream -> stream.readText() }
        }
        val revision = InstrumentationRegistry.getArguments().getString("vipiVoiceAudit") ?: "001"
        require(revision.matches(Regex("[0-9]{3}")))
        val output = File(context.filesDir, "voice-availability-$revision"); check(!output.exists()); output.mkdirs()
        val wifi = shell("settings get global wifi_on").trim(); val mobile = shell("settings get global mobile_data").trim()
        val settings = listOf("tts_default_synth", "tts_default_rate", "tts_default_pitch", "tts_default_locale")
        val before = settings.associateWith { shell("settings get secure $it").trim() }
        val network = context.getSystemService(ConnectivityManager::class.java)
        val rows = JSONArray()
        val report = JSONObject().put("started_at", Instant.now().toString()).put("complete", false)
            .put("evidence", "actual offline voice availability/synthesis, not all-pair/player/physical/listening acceptance")
            .put("new_model_downloads_invoked", false).put("original_tts_settings", JSONObject(before)).put("languages", rows)
        fun save() = File(output, "receipt.json").writeText(report.toString(2))
        save()
        try {
            shell("svc wifi disable"); shell("svc data disable")
            withTimeout(15_000) { while (network.activeNetwork != null) delay(100) }; assertNull(network.activeNetwork)
            val ready = CompletableDeferred<Int>()
            val inventory = withContext(Dispatchers.Main) { TextToSpeech(context) { ready.complete(it) } }
            val advertised = try {
                assertEquals(TextToSpeech.SUCCESS, withTimeout(15_000) { ready.await() })
                inventory.voices.orEmpty().map { voice -> JSONObject().put("name", voice.name)
                    .put("locale", voice.locale.toLanguageTag()).put("language", voice.locale.language)
                    .put("network_required", voice.isNetworkConnectionRequired)
                    .put("not_installed_feature", TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED in voice.features.orEmpty())
                    .put("quality", voice.quality) }
            } finally { withContext(Dispatchers.Main) { inventory.shutdown() } }
            withTimeout(480_000) {
                for (language in initialLanguages.map { it.code }) {
                    assertNull(network.activeNetwork)
                    val text = SpeechProviderFixtures.text.getValue(language)
                    val row = JSONObject().put("language", language).put("text", text)
                        .put("advertised", JSONArray(advertised.filter { it.getString("language") == language }))
                    val voice = withContext(Dispatchers.Main) { LocalVoice(context, language) }
                    val destination = File(output, "$language.wav"); val began = System.nanoTime()
                    try {
                        row.put("selected_before_render", withTimeout(20_000) { voice.select() })
                        row.put("select_ms", (System.nanoTime() - began) / 1e6)
                        val renderBegan = System.nanoTime()
                        val rendered = withTimeout(35_000) { voice.render(text, destination) }
                        val wave = PcmWave.read(rendered.file)
                        assertTrue(wave.samples.any { it != 0.toByte() }); assertTrue(wave.durationMs > 0)
                        row.put("status", "rendered").put("render_ms", (System.nanoTime() - renderBegan) / 1e6)
                            .put("selected_after_render", voice.select()).put("audio_ms", wave.durationMs)
                            .put("sample_rate", wave.sampleRate).put("channels", wave.channels)
                            .put("sha256", MessageDigest.getInstance("SHA-256").digest(destination.readBytes()).joinToString("") { "%02x".format(it) })
                    } catch (timeout: TimeoutCancellationException) { currentCoroutineContext().ensureActive(); row.put("status", "timeout") }
                    catch (cancelled: CancellationException) { throw cancelled }
                    catch (error: Exception) { row.put("status", "unavailable").put("error_class", error.javaClass.simpleName); destination.delete() }
                    finally { withContext(Dispatchers.Main) { voice.close() }; assertNull(network.activeNetwork); rows.put(row); save() }
                }
            }
            assertEquals(11, rows.length())
            if (InstrumentationRegistry.getArguments().getString("vipiRequireAllVoices") == "true") {
                for (index in 0 until rows.length()) assertEquals(rows.getJSONObject(index).getString("language"), "rendered", rows.getJSONObject(index).getString("status"))
            }
            report.put("complete", true)
        } finally {
            if (wifi == "1") shell("svc wifi enable"); if (mobile == "1") shell("svc data enable")
            val after = settings.associateWith { shell("settings get secure $it").trim() }
            report.put("finished_at", Instant.now().toString()).put("final_tts_settings", JSONObject(after))
                .put("restored_wifi", shell("settings get global wifi_on").trim()).put("restored_mobile", shell("settings get global mobile_data").trim())
            save(); assertEquals(before, after)
        }
    }
}
