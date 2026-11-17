package co.fallsoft.vipi

import androidx.compose.material3.Text
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test

class EmbeddedSpeechStopDeviceTest {
    @get:Rule val compose = createComposeRule()

    @Test fun activeEmbeddedMessageOffersDirectStop() {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        lateinit var speech: SpeechPlayback
        compose.runOnIdle { speech = SpeechPlayback(context, "en", "es", scope); speech.prepare(mapOf("en" to "Hello.", "es" to "Hola.")) }
        try {
            compose.waitUntil(30_000) { speech.state == SpeechState.READY || speech.state == SpeechState.UNAVAILABLE }
            check(speech.state == SpeechState.READY) { speech.error.orEmpty() }
            val result = ConversationExamples.result(context, "en", "es")
            compose.setContent { VipiTheme(Appearance.LIGHT) {
                ImmersionBubble(result, ReadingMode.ORIGINAL, speech, "en", "es", "embedded-test", embedded = true, metadata = { Text("Message") })
            } }
            compose.runOnIdle { speech.toggle("embedded-test", listOf(co.fallsoft.vipi.core.SpeechSpan("This is a longer message to make the stop control available while it is spoken.", "en"))) }
            compose.waitUntil(10_000) { speech.activeMessage == "embedded-test" }
            compose.onNodeWithText("Stop").assertIsDisplayed().performClick()
            compose.runOnIdle { assertNull(speech.activeMessage) }
        } finally { compose.runOnIdle { speech.close() }; scope.cancel() }
    }
}
