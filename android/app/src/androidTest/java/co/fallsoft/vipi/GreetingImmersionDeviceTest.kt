package co.fallsoft.vipi

import android.content.res.Configuration
import android.view.View
import android.view.ViewGroup
import android.view.inspector.WindowInspector
import androidx.compose.material3.Text
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File

class GreetingImmersionDeviceTest {
    @get:Rule val compose = createComposeRule()
    @Test fun longGreetingAlternatesWithoutMovingAtLargeText() {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val base = instrumentation.targetContext
        val context = base.createConfigurationContext(Configuration(base.resources.configuration).apply { fontScale = 2f })
        val device = UiDevice.getInstance(instrumentation)
        val output = File(base.filesDir, "greeting-immersion-002"); check(!output.exists()); output.mkdirs()
        val visible = mutableStateOf(true)
        val paused = mutableStateOf(false)
        fun paragraphs(view: View): List<StableImmersionText> = when (view) {
            is StableImmersionText -> listOf(view)
            is ViewGroup -> (0 until view.childCount).flatMap { paragraphs(view.getChildAt(it)) }
            else -> emptyList()
        }
        data class Face(val text: String, val height: Int, val y: Int, val right: Int)
        fun face(): Face? {
            var value: Face? = null
            instrumentation.runOnMainSync {
                WindowInspector.getGlobalWindowViews().flatMap { paragraphs(it) }.lastOrNull()?.let {
                    val point = IntArray(2); it.getLocationOnScreen(point)
                    value = Face(it.visibleText(), it.height, point[1], point[0] + it.width)
                }
            }
            return value
        }
        compose.setContent {
            if (visible.value) CompositionLocalProvider(LocalContext provides context,
                LocalDensity provides Density(base.resources.displayMetrics.density, 2f)) {
                VipiTheme(Appearance.LIGHT) {
                    val scope = rememberCoroutineScope()
                    val owner = remember { ConversationImmersion(context, "en", "sw", 0.25) }
                    val speech = remember { SpeechPlayback(context, "en", "sw", scope) }
                    DisposableEffect(Unit) { onDispose { owner.close(); speech.close() } }
                    Box(Modifier.fillMaxSize().safeDrawingPadding().padding(16.dp)) {
                        ConversationImmersionText("Thank you very much.", "greeting-qa", owner, speech, paused.value, {}, metadata = { Text("A message") })
                    }
                }
            }
        }
        try {
            compose.waitUntil(20_000) { face()?.text == "Asante sana." }
            val target = requireNotNull(face())
            assertTrue(target.height > 0); assertTrue(target.right <= device.displayWidth)
            compose.waitUntil(10_000) { face()?.text == "Thank you very much." }
            val original = requireNotNull(face())
            assertEquals(target.height, original.height); assertEquals(target.y, original.y)
            compose.runOnIdle { paused.value = true }
            compose.waitForIdle()
            assertEquals("Thank you very much.", face()?.text)
            check(device.takeScreenshot(File(output, "android-greeting-large-original.png")))
            compose.runOnIdle { paused.value = false }
            compose.waitUntil(10_000) { face()?.text == "Asante sana." }
            compose.runOnIdle { paused.value = true }
            compose.waitForIdle()
            assertEquals("Asante sana.", face()?.text)
            check(device.takeScreenshot(File(output, "android-greeting-large-target.png")))
            compose.onNodeWithContentDescription("Reading options").performClick()
            compose.onNodeWithText("Swahili").performClick()
            compose.onNodeWithText("Asante sana.").assertIsDisplayed()
            compose.onNodeWithContentDescription("Reading options").performClick()
            compose.onNodeWithText("English").performClick()
            compose.onNodeWithText("Thank you very much.").assertIsDisplayed()
        } finally { compose.runOnIdle { visible.value = false }; compose.waitForIdle() }
    }
}
