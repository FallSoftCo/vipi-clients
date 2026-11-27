package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.SpeechSpan
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.CopyOnWriteArrayList
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** Actual local voice, WAV decode and PCM stream; no mock renderer. */
class FullMessageSpeechTailDeviceTest {
    @Test
    fun punctuationOnlyMiddleChunkDoesNotOmitFollowingSpokenWords(): Unit = runBlocking {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        check(BuildConfig.DEBUG && BuildConfig.APPLICATION_ID == "co.fallsoft.vipi.sourcecontextqa")
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = instrumentation.targetContext
        val run = InstrumentationRegistry.getArguments().getString("vipiJourneyRun") ?: "001"
        require(run.matches(Regex("[0-9]{3}")))
        val output = File(context.filesDir, "full-message-speech-tail-$run.json")
        check(!output.exists())
        val text = "Hello " + ".".repeat(320) + " These trailing words must also be spoken."
        val chunks = SpeechChunks.plan(listOf(SpeechSpan(text, "en")))
        assertEquals(text, chunks.flatten().joinToString("") { it.text })
        assertTrue(
            chunks.any {
                it.all { span -> span.text.all { char -> char == '.' || char.isWhitespace() } }
            }
        )
        val pair = withContext(Dispatchers.Main) { LocalSpeechPair(context, "en", "en") }
        val events = CopyOnWriteArrayList<JSONObject>()
        val renders = JSONArray()
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        var speech: SpeechPlayback? = null
        MessageAudioQualification.attach { events += it }
        try {
            pair.prepare(mapOf("en" to "Hello."))
            for ((index, chunk) in chunks.withIndex()) {
                val rendered = pair.render(chunk)
                val wave = withContext(Dispatchers.IO) { PcmWave.read(rendered.file) }
                val spoken = chunk.any { span -> span.text.any(Char::isLetterOrDigit) }
                if (spoken)
                    assertTrue(
                        "Actual spoken chunk must contain PCM, including the tail",
                        wave.samples.any { it.toInt() != 0 },
                    )
                else {
                    assertEquals(100.0, wave.durationMs, 0.001)
                    assertTrue(wave.samples.all { it.toInt() == 0 })
                }
                renders.put(
                    JSONObject()
                        .put("index", index)
                        .put("text", chunk.joinToString("") { it.text })
                        .put("path", rendered.file.absolutePath)
                        .put("bytes", rendered.file.length())
                        .put(
                            "sha256",
                            MessageDigest.getInstance("SHA-256")
                                .digest(rendered.file.readBytes())
                                .joinToString("") { "%02x".format(it) },
                        )
                        .put("pcm_ms", wave.durationMs)
                        .put("spoken_pcm", spoken)
                )
            }
            assertTrue(chunks.last().joinToString("") { it.text }.contains("trailing words"))
            withContext(Dispatchers.Main) {
                speech =
                    SpeechPlayback(context, "en", scope).also {
                        it.prepare(mapOf("en" to "Hello."))
                    }
            }
            withTimeout(120_000) { while (speech!!.state == SpeechState.PREPARING) delay(10) }
            assertEquals(SpeechState.READY, speech!!.state)
            withContext(Dispatchers.Main) {
                speech!!.toggle("punctuation-tail", listOf(SpeechSpan(text, "en")))
            }
            withTimeout(60_000) {
                while (
                    events.none {
                        it.optString("stage") == "pcm_completed" &&
                            it.optString("id") == "punctuation-tail"
                    } && speech!!.error == null
                ) delay(10)
            }
            assertNull(speech!!.error)
            assertEquals(1, events.count { it.optString("stage") == "pcm_started" })
            assertEquals(1, events.count { it.optString("stage") == "pcm_completed" })
            assertTrue(events.none { it.optString("stage") == "speech_failure" })
            assertEquals(
                text,
                events
                    .single { it.optString("stage") == "speech_request" }
                    .getString("practice_text"),
            )
        } finally {
            output.writeText(
                JSONObject()
                    .put("text", text)
                    .put("actual_native_voice", true)
                    .put("acoustic_quality_claimed", false)
                    .put("renders", renders)
                    .put("events", JSONArray(events))
                    .toString(2)
            )
            MessageAudioQualification.attach(null)
            withContext(Dispatchers.Main) {
                speech?.close()
                pair.close()
                scope.cancel()
            }
        }
    }
}
