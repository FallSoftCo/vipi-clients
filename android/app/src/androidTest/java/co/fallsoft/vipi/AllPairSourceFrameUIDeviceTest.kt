package co.fallsoft.vipi

import android.content.Intent
import android.graphics.Rect
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.view.inspector.WindowInspector
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File

class AllPairSourceFrameUIDeviceTest {
    private data class Face(val text: String, val bounds: Rect, val anchors: List<Pair<Float, Int>>) {
        fun json() = JSONObject().put("text", text).put("bounds", bounds.toShortString())
            .put("anchors", JSONArray(anchors.map { JSONArray(listOf(it.first, it.second)) })).put("elapsed_ms", SystemClock.elapsedRealtime())
    }
    @Test fun automaticDefaultKeepsNativeSlotsStableAndShowsNonLatinReadings() {
        val inst = InstrumentationRegistry.getInstrumentation(); val args = InstrumentationRegistry.getArguments()
        check(args.getString("vipiDedicatedEmulator") == "true")
        val run = args.getString("vipiAllPairUIRun") ?: "001"; require(run.matches(Regex("[0-9]{3}")))
        val context = inst.targetContext; val device = UiDevice.getInstance(inst)
        val cases = JSONArray(File(context.filesDir, "all-pair-ui-cases-r01.json").readText())
        fun nativeViews(view: View): List<StableImmersionText> = when (view) {
            is StableImmersionText -> listOf(view)
            is ViewGroup -> (0 until view.childCount).flatMap { nativeViews(view.getChildAt(it)) }
            else -> emptyList()
        }
        fun face(original: String): Face? {
            var value: Face? = null
            inst.runOnMainSync {
                val views = WindowInspector.getGlobalWindowViews().flatMap(::nativeViews).filter { it.text.toString() == original && it.getGlobalVisibleRect(Rect()) }
                if (views.size == 1) {
                    val view = views.single(); val bounds = Rect(); view.getGlobalVisibleRect(bounds)
                    view.layout?.let { layout -> value = Face(view.visibleText(), bounds, (0..original.length).map { layout.getPrimaryHorizontal(it) to layout.getLineBaseline(layout.getLineForOffset(it)) }) }
                }
            }
            return value
        }
        fun await(description: String, seconds: Long = 20, condition: () -> Boolean) {
            val end = SystemClock.elapsedRealtime() + seconds * 1000
            while (SystemClock.elapsedRealtime() < end) { if (condition()) return; SystemClock.sleep(80) }
            error("Timed out: $description")
        }
        fun clickDescription(value: String) {
            inst.uiAutomation.clearCache(); val node = device.wait(Until.findObject(By.desc(value)), 5000); requireNotNull(node).click()
        }
        fun clickText(value: String) { requireNotNull(device.wait(Until.findObject(By.text(value)), 5000)).click() }
        val config = Configurator.getInstance(); val priorIdle = config.waitForIdleTimeout; config.waitForIdleTimeout = 0
        try {
            for (i in 0 until cases.length()) {
                val row = cases.getJSONObject(i); val source = row.getString("source"); val target = row.getString("target")
                val original = row.getString("original"); val latin = row.getString("latin"); val native = row.getString("native")
                val out = File(context.filesDir, "all-pair-ui-$run-$source-$target"); check(!out.exists()); check(out.mkdirs())
                val events = JSONArray(); val report = JSONObject().put("complete", false).put("source", source).put("target", target).put("events", events)
                fun save() { File(out, "observations.json").writeText(report.toString(2)) }
                val scenario = ActivityScenario.launch<AllPairRouteQualificationActivity>(Intent(context, AllPairRouteQualificationActivity::class.java)
                    .putExtra("case_id", row.getString("id")).putExtra("run", run))
                try {
                    await("default row") { File(out, "proof.json").exists() && face(original) != null }
                    val proof = JSONObject(File(out, "proof.json").readText()); assertTrue(proof.getBoolean("default_provider")); assertEquals(0, proof.getInt("translation_calls"))
                    val first = requireNotNull(face(original)); var prior = first.text; var transitions = 0
                    val end = SystemClock.elapsedRealtime() + 40_000
                    while (transitions < 6 && SystemClock.elapsedRealtime() < end) {
                        face(original)?.let { current ->
                            assertEquals(first.bounds, current.bounds); assertEquals(first.anchors, current.anchors)
                            assertTrue(current.text == original || current.text == latin)
                            if (current.text != prior) {
                                prior = current.text; transitions++; events.put(current.json())
                                if (current.text == latin) check(device.takeScreenshot(File(out, "latin.png")))
                            }
                        }; SystemClock.sleep(100)
                    }
                    assertEquals("Continuous automatic flips", 6, transitions)
                    if (target in setOf("ar", "zh", "ja", "ko")) {
                        assertNotEquals(latin, native)
                        clickDescription("Reading options"); clickText("Show original script")
                        await("native script") { face(original)?.text == native }; check(device.takeScreenshot(File(out, "native-script.png")))
                        val scripted = requireNotNull(face(original)); assertEquals(first.bounds, scripted.bounds); assertEquals(first.anchors, scripted.anchors)
                        events.put(scripted.json().put("mode", "native-script"))
                        clickDescription("Reading options"); clickText("Show Latin letters")
                        await("Latin reading restored") { face(original)?.text == latin }
                        events.put(requireNotNull(face(original)).json().put("mode", "latin-restored"))
                    }
                    report.put("complete", true).put("automatic_transitions", transitions).put("source_anchors_stable", true)
                } catch (error: Throwable) { report.put("error", error.toString()); throw error }
                finally { save(); device.dumpWindowHierarchy(File(out, "hierarchy.xml")); scenario.close() }
            }
        } finally { config.waitForIdleTimeout = priorIdle }
    }
}
