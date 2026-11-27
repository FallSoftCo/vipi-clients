package co.fallsoft.vipi

import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.SpeechSpan
import java.io.File
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SpeechLengthDeviceTest {
    @Test
    fun measureParagraphBufferingLatency(): Unit = runBlocking {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val fixture =
            JSONObject(File(context.filesDir, "immersion-qa/speech-lengths.json").readText())
        val base =
            fixture.getJSONArray("spans").let { a ->
                (0 until a.length()).map {
                    a.getJSONObject(it).let { x ->
                        SpeechSpan(x.getString("text"), x.getString("language"))
                    }
                }
            }
        val pair = withContext(Dispatchers.Main) { LocalSpeechPair(context, "en", "es") }
        val rows = JSONArray()
        try {
            pair.prepare(mapOf("en" to "Hello.", "es" to "Hola."))
            for (repeat in listOf(1, 3, 8)) {
                val spans = (1..repeat).flatMap { base }
                val start = SystemClock.elapsedRealtimeNanos()
                val result = pair.render(spans)
                rows.put(
                    JSONObject()
                        .put("characters", spans.sumOf { it.text.length })
                        .put("segments", spans.size)
                        .put(
                            "render_ms",
                            (SystemClock.elapsedRealtimeNanos() - start) / 1_000_000.0,
                        )
                        .put("audio_ms", result.milliseconds)
                )
                File(context.filesDir, "speech-qa/lengths-001.json")
                    .writeText(
                        JSONObject()
                            .put(
                                "evidence",
                                "prepared_pair_paragraph_render_timing_not_player_latency",
                            )
                            .put("cases", rows)
                            .toString(2)
                    )
            }
        } finally {
            withContext(Dispatchers.Main) { pair.close() }
        }
    }
}
