package co.fallsoft.vipi

import android.net.ConnectivityManager
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.SpeechSpan
import java.io.File
import java.security.MessageDigest
import java.time.Instant
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ElevenLanguageSpeechTest {
    @Test
    fun originalScriptsPrepareAndRenderJoinedPairsOffline(): Unit = runBlocking {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        check(
            android.os.Build.FINGERPRINT.contains("generic") ||
                android.os.Build.MODEL.contains("sdk_gphone")
        )
        val context = instrumentation.targetContext
        fun shell(command: String) =
            instrumentation.uiAutomation.executeShellCommand(command).use {
                java.io.FileInputStream(it.fileDescriptor).bufferedReader().use { stream ->
                    stream.readText()
                }
            }
        val directory = File(context.filesDir, "eleven-language-speech-001")
        check(!directory.exists())
        directory.mkdirs()
        val wifi = shell("settings get global wifi_on").trim()
        val mobile = shell("settings get global mobile_data").trim()
        val network = context.getSystemService(ConnectivityManager::class.java)
        val rows = JSONArray()
        val report =
            JSONObject()
                .put("complete", false)
                .put("started_at", Instant.now().toString())
                .put(
                    "evidence",
                    "offline original-script synthesis and joined pairs; not acoustic/pronunciation/physical acceptance",
                )
                .put("new_model_downloads_invoked", false)
                .put("pairs", rows)
        fun save() = File(directory, "receipt.json").writeText(report.toString(2))
        fun sha(file: File) =
            MessageDigest.getInstance("SHA-256").digest(file.readBytes()).joinToString("") {
                "%02x".format(it)
            }
        save()
        try {
            shell("svc wifi disable")
            shell("svc data disable")
            withTimeout(15_000) { while (network.activeNetwork != null) delay(100) }
            assertNull(network.activeNetwork)
            val original = "水を飲みます。"
            val rangesBefore =
                NativeJapaneseTokenizer.tokens(original).map { it.position to it.surface }
            assertEquals("ミズヲノミマス。", JapaneseSpeechReading.convert(original))
            assertEquals(
                rangesBefore,
                NativeJapaneseTokenizer.tokens(original).map { it.position to it.surface },
            )
            assertEquals("水を飲みます。", original)
            val controls = JSONArray()
            for (text in listOf("こんにちは。コーヒーをください。", original, "Vipi 123。")) {
                val converted = JapaneseSpeechReading.convert(text)
                val destination = File(directory, "ja-control-${controls.length()}.wav")
                val speech =
                    SwahiliSpeech.render(context, text, destination, SwahiliSpeech.Job(), "ja")
                assertTrue(PcmWave.read(destination).samples.any { it != 0.toByte() })
                controls.put(
                    JSONObject()
                        .put("original", text)
                        .put("spoken_kana", converted)
                        .put("audio_ms", speech.milliseconds)
                        .put("sha256", sha(destination))
                )
            }
            val unknown = File(directory, "unknown-han.wav")
            try {
                SwahiliSpeech.render(context, "𠮷", unknown, SwahiliSpeech.Job(), "ja")
                fail("Unknown Han must not be guessed")
            } catch (error: OfflineVoiceUnavailable) {
                assertEquals("ja", error.language)
                assertFalse(unknown.exists())
            }
            report.put("japanese_controls", controls).put("unknown_han_rejected", true)
            withTimeout(480_000) {
                for (language in initialLanguages.map { it.code }.filter { it != "en" }) {
                    assertNull(network.activeNetwork)
                    val originalText = "Hello. Thank you."
                    val translatedText = SpeechProviderFixtures.text.getValue(language)
                    val row =
                        JSONObject()
                            .put("source", "en")
                            .put("target", language)
                            .put("original", originalText)
                            .put("target_text", translatedText)
                    if (language == "ja")
                        row.put("spoken_kana", JapaneseSpeechReading.convert(translatedText))
                    val pair =
                        withContext(Dispatchers.Main) { LocalSpeechPair(context, "en", language) }
                    try {
                        var began = System.nanoTime()
                        pair.prepare(mapOf("en" to originalText, language to translatedText))
                        row.put("prepare_ms", (System.nanoTime() - began) / 1e6)
                        val spans =
                            listOf(
                                SpeechSpan(originalText + " ", "en"),
                                SpeechSpan(translatedText, language),
                            )
                        began = System.nanoTime()
                        val rendered = pair.render(spans)
                        row.put("render_ms", (System.nanoTime() - began) / 1e6)
                        val wave = PcmWave.read(rendered.file)
                        assertEquals(24_000, wave.sampleRate)
                        assertEquals(1, wave.channels)
                        assertTrue(wave.samples.any { it != 0.toByte() })
                        assertEquals(1, rendered.boundaryFrames.size)
                        val retained = File(directory, "en-$language.wav")
                        rendered.file.copyTo(retained)
                        began = System.nanoTime()
                        val warm = pair.render(spans)
                        assertEquals(rendered.file, warm.file)
                        row.put("warm_ms", (System.nanoTime() - began) / 1e6)
                            .put("audio_ms", wave.durationMs)
                            .put("sha256", sha(retained))
                            .put("status", "joined_pcm")
                    } finally {
                        withContext(Dispatchers.Main) { pair.close() }
                        assertNull(network.activeNetwork)
                        rows.put(row)
                        save()
                    }
                }
            }
            assertEquals(10, rows.length())
            report.put("complete", true)
        } finally {
            if (wifi == "1") shell("svc wifi enable")
            if (mobile == "1") shell("svc data enable")
            report
                .put("finished_at", Instant.now().toString())
                .put("restored_wifi", shell("settings get global wifi_on").trim())
                .put("restored_mobile", shell("settings get global mobile_data").trim())
            save()
        }
    }
}
