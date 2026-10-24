package co.fallsoft.vipi

import android.content.Intent
import android.graphics.Point
import android.os.SystemClock
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Configurator
import androidx.test.uiautomator.BySelector
import androidx.test.uiautomator.UiObject2
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class SpeechInteractionDeviceTest {
    @Test fun nativeListenStopsWhenVisibleReadingChanges() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = instrumentation.targetContext
        val device = UiDevice.getInstance(instrumentation)
        // Playback is deliberately transient. UiAutomator's implicit idle wait
        // can outlast cached audio and skip the entire Stop state.
        val configuration = Configurator.getInstance()
        val previousIdleTimeout = configuration.waitForIdleTimeout
        configuration.waitForIdleTimeout = 0
        val directory = File(context.filesDir, "speech-ui-002").apply { mkdirs() }
        File(directory, "report.json").delete()
        val scenario = ActivityScenario.launch<MainActivity>(Intent(context, MainActivity::class.java).putExtra("vipi_screen", "welcome"))
        fun fresh(selector: BySelector): UiObject2? {
            // AndroidView removal/reinsertion can leave UiAutomation's cache
            // reporting Listen while the rendered control already says Stop.
            instrumentation.uiAutomation.clearCache()
            return device.findObject(selector)
        }
        fun waitFor(value: String): UiObject2 {
            val deadline = SystemClock.elapsedRealtime() + 20_000
            while (SystemClock.elapsedRealtime() < deadline) {
                fresh(By.text(value))?.let { return it }
                SystemClock.sleep(50)
            }
            error("Missing $value")
        }
        fun tap(value: String) { waitFor(value).click() }
        try {
            checkNotNull(device.wait(Until.findObject(By.desc("Pause word switching")), 5000)).click()
            waitFor("Listen"); device.takeScreenshot(File(directory, "ready.png"))
            tap("Listen"); waitFor("Stop")
            tap("See the whole thought in Spanish"); waitFor("Listen")
            waitFor("¿Café mañana? Conozco un pequeño lugar junto al río.")
            tap("Listen"); waitFor("Stop")
            tap("Back to a little Spanish"); waitFor("Listen")
            assertNotNull(device.wait(Until.findObject(By.desc("Café mañana? I know a little place by the río.")), 3000))
            tap("Listen"); waitFor("Stop")
            var point = Point()
            scenario.onActivity { activity ->
                val text = activity.window.decorView.findViewWithTag<StableImmersionText>("immersionText")
                val offset = text.text.toString().indexOf("mañana") + 2
                assertTrue(offset > 1)
                val line = text.layout.getLineForOffset(offset)
                val location = IntArray(2); text.getLocationOnScreen(location)
                point = Point(location[0] + text.layout.getPrimaryHorizontal(offset).toInt(), location[1] + (text.layout.getLineTop(line) + text.layout.getLineBottom(line)) / 2)
            }
            device.click(point.x, point.y)
            assertNotNull(device.wait(Until.findObject(By.desc("Café tomorrow? I know a little place by the río.")), 3000))
            waitFor("Listen"); device.takeScreenshot(File(directory, "revealed.png"))
            // Resume continuous mode, then playback must freeze the complete
            // visible language snapshot until the player finishes.
            checkNotNull(device.findObject(By.desc("Resume word switching"))).click()
            tap("Listen"); waitFor("Stop")
            val captured = checkNotNull(device.findObject(By.descContains("I know a little place"))).contentDescription
            val deadline = SystemClock.elapsedRealtime() + 15_000
            var samples = 0
            while (fresh(By.text("Stop")) != null && SystemClock.elapsedRealtime() < deadline) {
                assertEquals(captured, checkNotNull(fresh(By.descContains("I know a little place"))).contentDescription)
                samples++; SystemClock.sleep(100)
            }
            assertTrue("No active audio snapshot sampled", samples > 0)
            waitFor("Listen")
            tap("Find your language"); waitFor("I already speak")
            assertFalse(device.hasObject(By.text("TRY A LITTLE SPANISH")))
            File(directory, "report.json").writeText(JSONObject().put("status", "passed").put("audioSnapshotSamples", samples)
                .put("evidence", "native_touch_cancel_and_continuous_state_freeze_not_acoustic_or_screen_reader_acceptance").toString(2))
        } catch (failure: Throwable) {
            device.takeScreenshot(File(directory, "failure.png"))
            device.dumpWindowHierarchy(File(directory, "failure.xml"))
            throw failure
        } finally { scenario.close(); configuration.waitForIdleTimeout = previousIdleTimeout }
    }
}
