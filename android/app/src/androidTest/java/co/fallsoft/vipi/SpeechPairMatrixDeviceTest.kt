package co.fallsoft.vipi

import android.net.ConnectivityManager
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.SpeechSpan
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.abs

@RunWith(AndroidJUnit4::class)
class SpeechPairMatrixDeviceTest {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private fun shell(command: String) = instrumentation.uiAutomation.executeShellCommand(command).use {
        java.io.FileInputStream(it.fileDescriptor).bufferedReader().use { stream -> stream.readText() }
    }
    @Test fun prepareAndRenderEveryDirectedPairOffline() = runBlocking {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        check(android.os.Build.FINGERPRINT.contains("generic") || android.os.Build.MODEL.contains("sdk_gphone"))
        val context = instrumentation.targetContext
        val fixture = JSONObject(File(context.filesDir, "immersion-qa/speech.json").readText())
        val languages = fixture.getJSONArray("languages").let { a -> (0 until a.length()).map(a::getString) }
        assertEquals(initialLanguages.map { it.code }.toSet(), languages.toSet())
        val directory = File(context.filesDir, "speech-matrix-110-20261116").apply { check(!exists()); mkdirs() }
        val rows = JSONArray()
        val report = JSONObject().put("evidence", "offline_pair_rendering_not_linguistic_or_listening_acceptance").put("directions", rows)
        fun save() { File(directory, "report.json").writeText(report.toString(2)) }
        val wifi = shell("settings get global wifi_on").trim() == "1"
        val mobile = shell("settings get global mobile_data").trim() == "1"
        try {
            shell("svc wifi disable"); shell("svc data disable")
            val network = context.getSystemService(ConnectivityManager::class.java)
            withTimeout(15_000) { while (network.activeNetwork != null) delay(100) }
            report.put("activeNetwork", "none")
            for (source in languages) for (target in languages.filter { it != source }) {
                val row = JSONObject().put("source", source).put("target", target)
                val pair = withContext(Dispatchers.Main) { LocalSpeechPair(context, source, target) }
                try {
                    var start = SystemClock.elapsedRealtimeNanos()
                    pair.prepare(mapOf(source to fixture.getJSONObject("warmup").getString(source), target to fixture.getJSONObject("warmup").getString(target)))
                    row.put("prepare_ms", (SystemClock.elapsedRealtimeNanos() - start) / 1_000_000.0)
                    val spans = listOf(SpeechSpan(fixture.getJSONObject("coffee").getString(source), source), SpeechSpan(fixture.getJSONObject("tomorrow").getString(target), target),
                        SpeechSpan(fixture.getJSONObject("tomorrow").getString(source), source), SpeechSpan(fixture.getJSONObject("coffee").getString(target), target))
                    start = SystemClock.elapsedRealtimeNanos()
                    val rendered = pair.render(spans)
                    row.put("render_ms", (SystemClock.elapsedRealtimeNanos() - start) / 1_000_000.0)
                    rendered.file.copyTo(File(directory, "$source-$target.wav"), overwrite = true)
                    val wave = PcmWave.read(rendered.file)
                    row.put("audio_ms", wave.durationMs).put("boundary_frames", JSONArray(rendered.boundaryFrames))
                    // Diagnostic only: silence touching each join at -60 dBFS.
                    val pcm = ByteBuffer.wrap(wave.samples).order(ByteOrder.LITTLE_ENDIAN).asShortBuffer()
                    fun quiet(frame: Int) = (0 until wave.channels).all { abs(pcm[frame * wave.channels + it].toInt()) <= 32 }
                    val frames = pcm.limit() / wave.channels
                    val gaps = rendered.boundaryFrames.map { boundary ->
                        var left = boundary; var right = boundary
                        while (left > 0 && quiet(left - 1)) left--
                        while (right < frames && quiet(right)) right++
                        (right - left) * 1000.0 / wave.sampleRate
                    }
                    row.put("join_silence_ms_at_minus60db", JSONArray(gaps))
                    start = SystemClock.elapsedRealtimeNanos(); pair.render(spans)
                    row.put("replay_ms", (SystemClock.elapsedRealtimeNanos() - start) / 1_000_000.0).put("status", "rendered")
                } catch (cancelled: CancellationException) { throw cancelled }
                catch (error: Exception) { row.put("status", "failed").put("error", error.javaClass.simpleName) }
                finally { withContext(Dispatchers.Main) { pair.close() }; rows.put(row); save() }
            }
        } finally { if (wifi) shell("svc wifi enable"); if (mobile) shell("svc data enable") }
        assertEquals(languages.size * (languages.size - 1), rows.length())
        assertEquals(languages.size * (languages.size - 1), (0 until rows.length()).count { rows.getJSONObject(it).getString("status") == "rendered" })
    }
}
