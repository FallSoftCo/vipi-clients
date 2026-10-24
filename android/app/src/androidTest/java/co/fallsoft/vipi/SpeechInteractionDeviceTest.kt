package co.fallsoft.vipi

import android.content.Intent
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import org.junit.Rule
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.click
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.text.TextLayoutResult

@RunWith(AndroidJUnit4::class)
class SpeechInteractionDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()
    @Test fun nativeListenStopsWhenVisibleReadingChanges() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = instrumentation.targetContext
        val device = UiDevice.getInstance(instrumentation)
        val directory = File(context.filesDir, "speech-ui-001").apply { mkdirs() }
        val scenario = ActivityScenario.launch<MainActivity>(Intent(context, MainActivity::class.java).putExtra("vipi_screen", "welcome"))
        fun waitFor(text: String) {
            compose.waitUntil(timeoutMillis = 20_000) {
                runCatching { compose.onAllNodesWithText(text).fetchSemanticsNodes().isNotEmpty() }.getOrDefault(false)
            }
        }
        fun tap(text: String) { compose.onNodeWithText(text).performClick() }
        try {
            // Use Compose's clock/idling for Compose UI. Waiting through
            // UiAutomator alone freezes recomposition under a Compose rule.
            waitFor("Listen")
            compose.waitForIdle(); device.takeScreenshot(File(directory, "ready.png"))
            tap("Listen"); waitFor("Stop")
            device.takeScreenshot(File(directory, "playing.png"))
            tap("See the whole thought in Spanish"); waitFor("Listen")
            waitFor("¿Café mañana? Conozco un pequeño lugar junto al río.")
            tap("Listen"); waitFor("Stop")
            tap("Back to a little Spanish"); waitFor("Listen")
            tap("Listen"); waitFor("Stop")
            val text = "Café mañana? I know a little place by the río."
            val node = compose.onNodeWithText(text)
            val layout = mutableListOf<TextLayoutResult>()
            node.performSemanticsAction(SemanticsActions.GetTextLayoutResult) { it(layout) }
            assertEquals(1, layout.size)
            val word = layout.single().getBoundingBox(text.indexOf("mañana") + 2)
            node.performTouchInput { click(word.center) }
            waitFor("Café tomorrow? I know a little place by the río."); waitFor("Listen")
            compose.waitForIdle(); device.takeScreenshot(File(directory, "revealed.png"))
            tap("Find your language")
            compose.waitForIdle()
            assertTrue(compose.onAllNodesWithText("Listen").fetchSemanticsNodes().isEmpty())
            File(directory, "report.json").writeText(JSONObject().put("status", "passed").put("evidence", "actual_native_touch_and_state_not_screen_reader_or_listening_acceptance").toString(2))
        } finally {
            device.takeScreenshot(File(directory, "last-state.png"))
            device.dumpWindowHierarchy(File(directory, "last-state.xml"))
            scenario.close()
        }
    }
}
