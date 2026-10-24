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

@RunWith(AndroidJUnit4::class)
class LanguageReadingDeviceTest {
    @Test fun nonRomanPreviewsHaveReadingAndScriptWithoutStackedText() {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val device = UiDevice.getInstance(instrumentation)
        val output = File(context.filesDir, "language-reading-001").apply { mkdirs() }
        File(output, "passed.txt").delete()
        context.getSharedPreferences("preferences", 0).edit().putString("readingPace", "balanced").apply()
        for (target in listOf("ja", "zh", "ar", "ko")) {
            val result = ConversationExamples.result(context, "en", target)
            val marker = result.spans.first().displayedTarget
            val scenario = ActivityScenario.launch<MainActivity>(Intent(context, MainActivity::class.java).putExtra("vipi_screen", "language").putExtra("vipi_source", "en").putExtra("vipi_target", target))
            try {
                device.waitForIdle()
                device.swipe(device.displayWidth / 2, device.displayHeight * 3 / 4, device.displayWidth / 2, device.displayHeight / 3, 30)
                val text = checkNotNull(device.wait(Until.findObject(By.descContains(marker)), 12_000)) { "Missing $target reading" }
                checkNotNull(device.findObject(By.desc("Pause word switching"))).click()
                assertTrue(text.contentDescription.contains(marker))
                device.takeScreenshot(File(output, "en-$target-reading.png"))
                checkNotNull(device.findObject(By.desc("Reading options"))).click()
                checkNotNull(device.wait(Until.findObject(By.text("Show original script")), 2000)).click()
                assertNotNull(device.wait(Until.findObject(By.descContains(result.spans.first().translated)), 3000))
                device.takeScreenshot(File(output, "en-$target-script.png"))
                checkNotNull(device.findObject(By.desc("Reading options"))).click()
                checkNotNull(device.wait(Until.findObject(By.text("Show transliteration")), 2000)).click()
                device.waitForIdle()
                checkNotNull(device.wait(Until.findObject(By.text("See the whole thought in ${languageName(target)}")), 3000)).click()
                val reading = checkNotNull(ConversationExamples.reading(context, target))
                assertNotNull(device.wait(Until.findObject(By.text(reading)), 3000))
                device.takeScreenshot(File(output, "en-$target-grammar.png"))
            } catch (failure: Throwable) {
                device.takeScreenshot(File(output, "failure-$target.png"))
                device.dumpWindowHierarchy(File(output, "failure-$target.xml"))
                throw failure
            } finally { scenario.close() }
        }
        File(output, "passed.txt").writeText("Four actual native previews: default transliteration, original script and whole-thought reading. Authored examples, not live translation acceptance.\n")
    }
}
