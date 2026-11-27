package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SwahiliDeviceTest {
    private val revision: String
        get() =
            (InstrumentationRegistry.getArguments().getString("vipiSwahiliRun") ?: "001").also {
                require(it.matches(Regex("[0-9]{3}")))
            }

    @Test
    fun explicitPreparationAndLocalTranslationInTwentyDirections() = runBlocking {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val texts =
            mapOf(
                "en" to "I am drinking water now.",
                "es" to "Estoy bebiendo agua ahora.",
                "fr" to "Je bois de l’eau maintenant.",
                "de" to "Ich trinke gerade Wasser.",
                "it" to "Sto bevendo acqua adesso.",
                "pt" to "Estou bebendo água agora.",
                "ar" to "أنا أشرب الماء الآن.",
                "zh" to "我正在喝水。",
                "ja" to "今、水を飲んでいます。",
                "ko" to "지금 물을 마시고 있어요.",
                "sw" to "Ninakunywa maji sasa.",
            )
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val output = File(context.filesDir, "swahili-translations-$revision.json")
        check(!output.exists())
        val rows = JSONArray()
        LocalTranslation().use { translator ->
            for (other in texts.keys.sorted().filter { it != "sw" }) {
                for ((source, target) in listOf(other to "sw", "sw" to other)) {
                    translator.prepare(source, target, true)
                    val original = texts.getValue(source)
                    val start = System.nanoTime()
                    val translated = translator.translate(original, source, target)
                    assertTrue(translated.isNotBlank())
                    rows.put(
                        JSONObject()
                            .put("source", source)
                            .put("target", target)
                            .put("original", original)
                            .put("translation", translated)
                            .put("elapsed_ms", (System.nanoTime() - start) / 1e6)
                    )
                }
            }
        }
        assertEquals(20, rows.length())
        output.writeText(
            JSONObject()
                .put("schema", "vipi-swahili-translation-1")
                .put("provider", "Google ML Kit local Android")
                .put("semantic_acceptance", false)
                .put(
                    "network_disabled",
                    context
                        .getSystemService(android.net.ConnectivityManager::class.java)
                        .activeNetwork == null,
                )
                .put("rows", rows)
                .toString(2)
        )
    }

    @Test
    fun installedOfflineSwahiliVoiceRendersActualAudio() = runBlocking {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val output = File(context.filesDir, "swahili-speech-$revision.json")
        check(!output.exists())
        val voice = LocalVoice(context, "sw")
        try {
            val identifier = voice.select()
            val speech =
                voice.render(
                    "Habari! Ninakunywa maji sasa. Tutakutana kesho.",
                    File(context.filesDir, "swahili-speech-$revision.wav"),
                )
            assertTrue(speech.milliseconds > 500)
            output.writeText(
                JSONObject()
                    .put("voice", identifier)
                    .put("milliseconds", speech.milliseconds)
                    .put("sample_rate", speech.sampleRate)
                    .put("status", "rendered")
                    .put("listening_acceptance", false)
                    .toString(2)
            )
        } catch (error: OfflineVoiceUnavailable) {
            output.writeText(JSONObject().put("status", "offline_voice_unavailable").toString(2))
            throw error
        } finally {
            voice.close()
        }
    }
}
