package co.fallsoft.vipi

import android.content.Intent
import android.os.SystemClock
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.SpeechSpan
import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class SpeechPlaybackDeviceTest {
    @Test fun paragraphStartsProgressivelyAndFinishesWithoutUnderruns(): Unit = runBlocking {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val scenario = ActivityScenario.launch<MainActivity>(Intent(context, MainActivity::class.java).putExtra("vipi_screen", "welcome"))
        val fixture = JSONObject(File(context.filesDir, "immersion-qa/speech-lengths.json").readText()).getJSONArray("spans")
        val spans = (0 until fixture.length()).map { fixture.getJSONObject(it).let { x -> SpeechSpan(x.getString("text"), x.getString("language")) } }
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        val controller = withContext(Dispatchers.Main) { SpeechPlayback(context, "en", "es", scope) }
        val report = JSONObject().put("evidence", "progressive_native_output_not_acoustic_or_listening_acceptance")
        suspend fun awaitState(expected: SpeechState) = withTimeout(45_000) {
            while (withContext(Dispatchers.Main) { controller.state } != expected) {
                check(withContext(Dispatchers.Main) { controller.error } == null); delay(20)
            }
        }
        try {
            withContext(Dispatchers.Main) { controller.prepare(mapOf("en" to "Hello.", "es" to "Hola.")) }
            awaitState(SpeechState.READY)
            val start = SystemClock.elapsedRealtimeNanos()
            withContext(Dispatchers.Main) { controller.toggle("paragraph", spans) }
            awaitState(SpeechState.PLAYING)
            report.put("request_to_player_started_ms", (SystemClock.elapsedRealtimeNanos() - start) / 1_000_000.0)
            awaitState(SpeechState.READY)
            report.put("feeding_underruns", controller.outputUnderruns).put("end_of_stream_underruns", controller.endOfStreamUnderruns).put("completion", "passed")
            assertEquals(0, controller.outputUnderruns)
        } finally {
            File(context.filesDir, "speech-qa/progressive-001.json").writeText(report.toString(2))
            withContext(Dispatchers.Main) { controller.close() }; scope.cancel(); scenario.close()
        }
    }

    @Test fun actualPlayerCompletesAndCancelledRequestsNeverStartLater(): Unit = runBlocking {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val scenario = ActivityScenario.launch<MainActivity>(Intent(context, MainActivity::class.java).putExtra("vipi_screen", "welcome"))
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        val controller = withContext(Dispatchers.Main) { SpeechPlayback(context, "en", "es", scope) }
        val report = JSONObject().put("evidence", "actual_player_callbacks_not_acoustic_or_listening_acceptance")
        suspend fun awaitState(expected: SpeechState) = withTimeout(15_000) {
            while (withContext(Dispatchers.Main) { controller.state } != expected) {
                val error = withContext(Dispatchers.Main) { controller.error }
                check(error == null) { error.orEmpty() }; delay(20)
            }
        }
        try {
            withContext(Dispatchers.Main) { controller.prepare(mapOf("en" to "Hello.", "es" to "Hola.")) }
            awaitState(SpeechState.READY)
            val spans = immersionPreview.speech("en", "es")
            var start = SystemClock.elapsedRealtimeNanos()
            withContext(Dispatchers.Main) { controller.toggle("mixed", spans) }
            awaitState(SpeechState.PLAYING)
            report.put("request_to_player_started_ms", (SystemClock.elapsedRealtimeNanos() - start) / 1_000_000.0)
            awaitState(SpeechState.READY)
            report.put("completion", "passed")
            // Cancel before the coroutine can render or install a player.
            withContext(Dispatchers.Main) { controller.toggle("cancel-before-render", spans); controller.stop() }
            delay(500)
            assertEquals(SpeechState.READY, withContext(Dispatchers.Main) { controller.state })
            assertNull(withContext(Dispatchers.Main) { controller.activeMessage })
            report.put("cancel_before_render", "passed")
            withContext(Dispatchers.Main) { controller.toggle("replay", spans) }
            awaitState(SpeechState.PLAYING)
            start = SystemClock.elapsedRealtimeNanos()
            withContext(Dispatchers.Main) { controller.stop() }
            report.put("stop_return_ms", (SystemClock.elapsedRealtimeNanos() - start) / 1_000_000.0)
            delay(500)
            assertEquals(SpeechState.READY, withContext(Dispatchers.Main) { controller.state })
            report.put("cancel_during_playback", "passed")
        } finally {
            File(context.filesDir, "speech-qa/player-001.json").writeText(report.toString(2))
            withContext(Dispatchers.Main) { controller.close() }
            scope.cancel(); scenario.close()
        }
    }
}
