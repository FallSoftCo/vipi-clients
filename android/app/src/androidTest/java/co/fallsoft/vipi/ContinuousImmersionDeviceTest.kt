package co.fallsoft.vipi

import android.content.Intent
import android.os.SystemClock
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import org.json.JSONObject
import org.json.JSONArray

@RunWith(AndroidJUnit4::class)
class ContinuousImmersionDeviceTest {
    @Test fun repeatsWithoutTapsPreservesGeometryAndResumesAfterPause() {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val device = UiDevice.getInstance(instrumentation)
        val output = File(context.filesDir, "continuous-001").apply { mkdirs() }
        File(output, "report.json").delete()
        val observations = JSONArray()
        val scenario = ActivityScenario.launch<MainActivity>(Intent(context, MainActivity::class.java).putExtra("vipi_screen", "welcome"))
        fun waitFor(value: String) = checkNotNull(device.wait(Until.findObject(By.desc(value)), 10_000)) { "Missing visible phase: $value" }
        try {
            val target = "Café mañana? I know a little place by the río."
            val original = "Coffee tomorrow? I know a little place by the river."
            val first = waitFor(target).visibleBounds
            repeat(6) { index ->
                val phase = if (index % 2 == 0) original else target
                val node = waitFor(phase)
                assertEquals(first, node.visibleBounds)
                observations.put(JSONObject().put("phase", phase).put("elapsedMs", SystemClock.elapsedRealtime()).put("bounds", node.visibleBounds.toShortString()))
                device.takeScreenshot(File(output, "phase-$index.png"))
            }
            checkNotNull(device.findObject(By.desc("Pause word switching"))).click()
            val held = checkNotNull(device.findObject(By.descContains("I know a little place"))).contentDescription
            val until = SystemClock.elapsedRealtime() + 8000
            while (SystemClock.elapsedRealtime() < until) {
                assertEquals(held, checkNotNull(device.findObject(By.descContains("I know a little place"))).contentDescription)
                SystemClock.sleep(200)
            }
            checkNotNull(device.findObject(By.desc("Resume word switching"))).click()
            waitFor(if (held == original) target else original)
            checkNotNull(device.findObject(By.text("Show original message"))).click()
            assertNotNull(device.wait(Until.findObject(By.text("Coffee tomorrow? I know a little place by the river.")), 3000))
            File(output, "report.json").writeText(JSONObject().put("status", "passed").put("observations", observations)
                .put("proof", "six_real_time_transitions_without_taps_stable_bubble_bounds_natural_paragraphs_pause_resume").toString(2))
        } finally { scenario.close() }
    }
}
