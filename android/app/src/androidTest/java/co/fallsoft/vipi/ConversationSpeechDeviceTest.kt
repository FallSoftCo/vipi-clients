package co.fallsoft.vipi

import androidx.compose.foundation.layout.Column
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.SpeechSpan
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

class ConversationSpeechDeviceTest {
    @get:Rule val compose = createComposeRule()

    @Test fun addingAnotherMessageDoesNotInterruptPlayingSpeech() {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        lateinit var speech: SpeechPlayback
        val second = mutableStateOf(false)
        val visible = mutableStateOf(true)
        runBlocking { withContext(Dispatchers.Main) {
            speech = SpeechPlayback(context, "en", "sw", scope)
            speech.prepare(mapOf("en" to "Hello.", "sw" to "Habari."))
        } }
        val catalog = BundledImmersionCatalog(context)
        val result = catalog.result("I like music.", "Ninapenda muziki.", "en", "sw", 1.0)
        try {
            compose.setContent { if (visible.value) VipiTheme(Appearance.LIGHT) {
                Column {
                    ImmersionBubble(result, ReadingMode.IMMERSED, speech, "en", "sw", "first", embedded = true)
                    if (second.value) ImmersionBubble(result, ReadingMode.IMMERSED, speech, "en", "sw", "second", embedded = true)
                }
            } }
            compose.waitUntil(20_000) { speech.state == SpeechState.READY }
            compose.runOnIdle {
                speech.toggle("first", listOf(SpeechSpan("We are talking about music, books, and plans for tomorrow. ".repeat(6), "en"), SpeechSpan("Ninapenda muziki.", "sw")))
            }
            compose.waitUntil(20_000) { speech.state == SpeechState.PLAYING }
            compose.runOnIdle { second.value = true }
            compose.waitForIdle()
            compose.runOnIdle {
                assertEquals("first", speech.activeMessage)
                assertEquals(SpeechState.PLAYING, speech.state)
            }
        } finally {
            compose.runOnIdle { visible.value = false }
            compose.waitForIdle()
            runBlocking { withContext(Dispatchers.Main) { speech.close() } }; scope.cancel()
        }
    }
}
