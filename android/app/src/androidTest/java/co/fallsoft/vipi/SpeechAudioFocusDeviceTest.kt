package co.fallsoft.vipi

import android.os.ParcelFileDescriptor
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.SpeechSpan
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test

/** Real PCM and the Android 15 emulator's active audio-focus stack. */
class SpeechAudioFocusDeviceTest {
    @Test
    fun speechRequestsDuckingAndReleasesFocusOnCompletionAndStop(): Unit = runBlocking {
        val inst = InstrumentationRegistry.getInstrumentation()
        val context = inst.targetContext
        assumeTrue(BuildConfig.APPLICATION_ID == "co.fallsoft.vipi.sourcecontextqa")
        assumeTrue(
            InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true"
        )

        fun activeFocus(): List<String> {
            val dump = inst.uiAutomation.executeShellCommand("dumpsys audio")
            return ParcelFileDescriptor.AutoCloseInputStream(dump).bufferedReader().use { reader ->
                val text = reader.readText()
                assertTrue(
                    "Android audio focus stack missing",
                    text.contains("Audio Focus stack entries"),
                )
                text
                    .lineSequence()
                    .filter {
                        it.trimStart().startsWith("source:") &&
                            it.contains(" -- pack: ${context.packageName} -- ")
                    }
                    .toList()
            }
        }

        val activity = ActivityScenario.launch(MainActivity::class.java)
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        val speech = withContext(Dispatchers.Main) { SpeechPlayback(context, "en", scope) }
        suspend fun awaitState(state: SpeechState) =
            withTimeout(90_000) {
                while (withContext(Dispatchers.Main) { speech.state } != state) {
                    assertNull(speech.error)
                    delay(20)
                }
            }
        try {
            withContext(Dispatchers.Main) { speech.prepare(mapOf("en" to "hello")) }
            awaitState(SpeechState.READY)
            assertTrue(activeFocus().isEmpty())
            for (id in listOf("completion", "stop")) {
                withContext(Dispatchers.Main) {
                    speech.toggle(
                        id,
                        listOf(
                            SpeechSpan(
                                "We can keep listening to music while this sentence plays.",
                                "en",
                            )
                        ),
                    )
                }
                awaitState(SpeechState.PLAYING)
                val entry = activeFocus().single()
                assertTrue(entry, entry.contains(" -- gain: GAIN_TRANSIENT_MAY_DUCK -- "))
                if (id == "stop") withContext(Dispatchers.Main) { speech.stop() }
                awaitState(SpeechState.READY)
                assertNull(speech.error)
                assertTrue(activeFocus().isEmpty())
            }
        } finally {
            withContext(Dispatchers.Main) {
                speech.close()
                scope.cancel()
            }
            activity.close()
        }
    }
}
