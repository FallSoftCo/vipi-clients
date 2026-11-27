package co.fallsoft.vipi

import android.speech.tts.TextToSpeech
import android.speech.tts.Voice
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.security.MessageDigest
import java.util.Locale
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ExpandedLanguageDeviceTest {
    private val context
        get() = InstrumentationRegistry.getInstrumentation().targetContext

    @Test
    fun pickerMatchesReadingAndActualOfflineVoiceWhileKeepingSavedTargets() = runBlocking {
        assertEquals("en" to "fa", restoredLanguagePair(null, "fa", "en-US"))
        assertEquals("he" to "en", restoredLanguagePair("iw", null, "en-US"))
        assertEquals("es" to "en", restoredLanguagePair(null, "en", "en-US"))
        assertEquals("no" to "tl", restoredLanguagePair("nb", "fil", "es-MX"))
        val bundled = BundledVoiceData.voices(context)
        val installed = withContext(Dispatchers.Main) { installedPracticeVoices(context) }
        val held = setOf("he", "fa", "ur", "th")
        val systemOnly = setOf("gl", "tl")
        assertEquals(59, translationCodes.size)
        assertEquals(translationCodes - systemOnly, bundled.keys)
        assertEquals("cmn", bundled["zh"])
        assertEquals("nb", bundled["no"])
        assertEquals(
            setOf("no", "tl", "id", "he", "zh"),
            listOf("nb-NO", "fil-PH", "in-ID", "iw-IL", "cmn-CN")
                .mapNotNull(::translationCode)
                .toSet(),
        )
        fun voice(tag: String, network: Boolean, features: Set<String> = emptySet()) =
            Voice(
                tag,
                Locale.forLanguageTag(tag),
                Voice.QUALITY_NORMAL,
                Voice.LATENCY_NORMAL,
                network,
                features,
            )
        assertEquals("tl", voice("fil-PH", false).installedPracticeCode())
        assertEquals("gl", voice("gl-ES", false).installedPracticeCode())
        assertNull(voice("gl-ES", true).installedPracticeCode())
        assertNull(
            voice("fil-PH", false, setOf(TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED))
                .installedPracticeCode()
        )
        assertNull(voice("zh-HK", false).installedPracticeCode())
        val options = PracticeOptions(bundled.keys, installed)
        for (source in translationCodes) {
            val expected = translationCodes - held - (systemOnly - installed) - source
            assertEquals(source, expected, options.targets(source, null).map { it.code }.toSet())
            for (saved in (held + systemOnly) - source) assertTrue(
                options.targets(source, saved).any { it.code == saved }
            )
        }
        assertEquals(55, PracticeOptions(bundled.keys, systemOnly).targets(null, null).size)
        File(context.filesDir, "expanded-language-picker.json")
            .writeText(
                JSONObject()
                    .put("installed_system", JSONArray(installed.sorted()))
                    .put(
                        "targets_before_source_exclusion",
                        JSONArray(options.targets(null, null).map { it.code }),
                    )
                    .put("sources", JSONArray(translationCodes.sorted()))
                    .toString(2)
            )
    }

    @Test
    fun addedScriptReadingsPreserveLiteralsAndRejectUnresolvedOutput() {
        val samples =
            mapOf(
                "be" to "Добрай раніцы",
                "bg" to "Добро утро",
                "bn" to "সুপ্রভাত",
                "el" to "Καλημέρα",
                "gu" to "સુપ્રભાત",
                "hi" to "शुभ प्रभात",
                "ka" to "დილა მშვიდობისა",
                "kn" to "ಶುಭೋದಯ",
                "mk" to "Добро утро",
                "mr" to "शुभ प्रभात",
                "ru" to "Доброе утро",
                "ta" to "காலை வணக்கம்",
                "te" to "శుభోదయం",
                "uk" to "Доброго ранку",
            )
        val results = JSONObject()
        val literal = "https://example.test/資料 user@例子.test `文件`"
        for ((code, sample) in samples) {
            val reading = FullMessageReadings.read(context, "$sample $literal", code)
            assertEquals(
                "$code $sample: $reading",
                FullMessageReadingStatus.AVAILABLE,
                reading.status,
            )
            assertTrue(reading.text!!.endsWith(" $literal"))
            val rendered = reading.text.removeSuffix(" $literal")
            assertTrue(
                rendered.any {
                    Character.UnicodeScript.of(it.code) == Character.UnicodeScript.LATIN
                }
            )
            assertEquals(
                FullMessageReadingStatus.UNAVAILABLE,
                FullMessageReadings.read(context, "$sample 漢", code).status,
            )
            results.put(code, JSONObject().put("surface", sample).put("reading", rendered))
        }
        assertEquals("Dobroho ranku", results.getJSONObject("uk").getString("reading"))
        assertEquals("Dobroye utro", results.getJSONObject("ru").getString("reading"))
        val mixed = "Привет $literal"
        val guide = FullMessageReadings.read(context, mixed, "ru").text!!
        val marks = FullMessageReadings.spokenAlignment(context, mixed, guide, "ru")
        assertTrue(
            marks.any {
                mixed.substring(it.script).startsWith("https://") &&
                    guide.substring(it.reading!!) == mixed.substring(it.script)
            }
        )
        for (broken in listOf("Привет \u0301", "Привет \ufffd", "Привет ◌")) assertEquals(
            FullMessageReadingStatus.UNAVAILABLE,
            FullMessageReadings.read(context, broken, "ru").status,
        )
        File(context.filesDir, "expanded-language-readings.json").writeText(results.toString(2))
    }

    @Test
    fun everyBundledVoiceRendersNonSilentLocalizedText() = runBlocking {
        val voices = BundledVoiceData.voices(context)
        val reports = JSONObject()
        for ((language, engineName) in voices.toSortedMap()) {
            val text = OnboardingPreviewSource.text(language)
            val file = File.createTempFile("language-", ".wav", context.cacheDir)
            try {
                val speech =
                    SwahiliSpeech.render(context, text, file, SwahiliSpeech.Job(), language)
                val wave = PcmWave.read(file)
                assertTrue("$language silent", wave.samples.any { it != 0.toByte() })
                assertTrue("$language duration", wave.durationMs > 0)
                reports.put(
                    language,
                    JSONObject()
                        .put("text", text)
                        .put("voice", engineName)
                        .put("duration_ms", wave.durationMs)
                        .put("sample_rate", speech.sampleRate)
                        .put(
                            "sha256",
                            MessageDigest.getInstance("SHA-256")
                                .digest(file.readBytes())
                                .joinToString("") { "%02x".format(it) },
                        ),
                )
            } finally {
                file.delete()
            }
        }
        assertEquals(57, reports.length())
        File(context.filesDir, "expanded-language-pcm.json").writeText(reports.toString(2))
    }
}
