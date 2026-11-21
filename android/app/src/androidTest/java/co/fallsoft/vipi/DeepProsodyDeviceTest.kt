package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.SpeechSpan
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.File

class DeepProsodyDeviceTest {
    @Test fun realOfflinePcmWithNativeAndMissingMarks(): Unit = runBlocking {
        val args = InstrumentationRegistry.getArguments()
        require(args.getString("vipiDedicatedEmulator") == "true" && BuildConfig.DEBUG)
        val ctx = InstrumentationRegistry.getInstrumentation().targetContext
        val output = File(ctx.filesDir, "prosody-" + args.getString("vipiJourneyRun"))
        check(output.mkdir())
        val report = JSONArray()
        for ((language, text) in mapOf(
            "en" to "Can't we meet at six? I'll bring the coffee. See you there!",
            "es" to "¿Nos vemos a las seis? Llevaré el café. ¡Hasta luego!",
            "zh" to "我们六点见面吗？我会带咖啡。到时候见！")) {
            val pair = withContext(Dispatchers.Main) { LocalSpeechPair(ctx, language, language) }
            val voice = withContext(Dispatchers.Main) { LocalVoice(ctx, language) }
            try {
                val voiceId = voice.select()
                pair.prepare(mapOf(language to "1"))
                val value = FullMessageTranslation(text, text, text, language, language, language, mode = ImmersionMode.FULL_MESSAGES)
                val projection = SpeechProjection.build(ctx, value)
                suspend fun play(): List<TimedPcm> {
                    val channel = Channel<TimedPcm>(Channel.UNLIMITED)
                    val timed = TimedSpeech(pair, language, projection, fullUtterance = true)
                    for (piece in MessageSpeech.pieces(value)) timed.enqueue(piece, channel)
                    channel.close()
                    val packets = mutableListOf<TimedPcm>()
                    for (packet in channel) packets += packet
                    return packets
                }
                val cold = play()
                val native = pair.render(listOf(SpeechSpan(text, language)))
                val wave = PcmWave.read(native.file)
                assertArrayEquals(wave.samples, cold.single().wave.samples)
                for (withoutMarks in listOf(false, true)) {
                    val label = if (withoutMarks) "missing" else "native"
                    if (withoutMarks) wave.copy(marks = emptyList()).write(native.file)
                    val packets = play()
                    val pcm = ByteArrayOutputStream()
                    packets.forEach { pcm.write(it.wave.samples) }
                    val result = wave.copy(samples = pcm.toByteArray(), marks = emptyList())
                    result.write(File(output, "$language-$label.wav"))
                    report.put(JSONObject().put("language", language).put("voice", voiceId)
                        .put("marks", if (withoutMarks) 0 else wave.marks.size).put("type", label)
                        .put("pieces", packets.size).put("cues", packets.sumOf { it.cues.size })
                        .put("coldPackets", cold.size).put("cacheFile", native.file.name)
                        .put("originalMs", wave.durationMs).put("playedMs", result.durationMs)
                        .put("originalPcm", wave.samples.contentEquals(result.samples)))
                    assertArrayEquals("Use the actual full-utterance PCM even with incomplete timings", wave.samples, result.samples)
                }
                wave.write(native.file)
            } finally { withContext(Dispatchers.Main) { voice.close(); pair.close() } }
        }
        File(output, "report.json").writeText(report.toString(2))
    }
}
