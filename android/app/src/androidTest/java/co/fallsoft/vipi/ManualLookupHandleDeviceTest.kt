package co.fallsoft.vipi

import android.content.ClipboardManager
import android.graphics.Rect
import android.os.SystemClock
import android.view.InputDevice
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.inspector.WindowInspector
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.dp
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import co.fallsoft.vipi.core.ImmersionPresentation
import co.fallsoft.vipi.core.ImmersionSpan
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.util.concurrent.CopyOnWriteArrayList

/** Actual native long press and external PopupWindow selection-handle input.
 * Delayed translation qualifies callback lifecycle, not translation quality. */
class ManualLookupHandleDeviceTest {
    @get:Rule val compose = createComposeRule()

    @Test fun actualLongPressHandleReleaseTranslatesOnceAndCopiesExactSelection() {
        val ins = InstrumentationRegistry.getInstrumentation()
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("vipiDedicatedEmulator") == "true")
        val context = ins.targetContext
        check(context.packageName == "co.fallsoft.vipi.uxqa")
        val run = args.getString("vipiHandleRun") ?: "001"
        check(run.matches(Regex("[0-9]{3}")))
        val output = File(context.filesDir, "manual-native-handles-$run")
        check(!output.exists()); check(output.mkdirs())
        val device = UiDevice.getInstance(ins)
        val source = "The marmot hums near the river."
        val fixture = object : ImmersionPresentation {
            override val original = source
            override val translation: String? = null
            override val spans = emptyList<ImmersionSpan>()
        }
        val calls = CopyOnWriteArrayList<JSONObject>()
        val trace = CopyOnWriteArrayList<JSONObject>()
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        lateinit var owner: ConversationImmersion
        lateinit var speech: SpeechPlayback
        lateinit var manual: ManualLookupInteraction
        val provider = object : LanguageTranslation {
            override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = error("No model downloads")
            override suspend fun translate(text: String, source: String, target: String): String {
                assertEquals("The marmot hums near the river.", text)
                calls += JSONObject().put("uptime", SystemClock.uptimeMillis()).put("source", text)
                awaitCancellation()
            }
            override fun close() { }
        }
        fun descendants(view: View): List<View> = listOf(view) + if (view is ViewGroup)
            (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) } else emptyList()
        fun views() = WindowInspector.getGlobalWindowViews().flatMap(::descendants)
        fun native() = views().filterIsInstance<StableImmersionText>().single()
        fun bounds(view: View): Rect { val location = IntArray(2); view.getLocationOnScreen(location); return Rect(location[0], location[1], location[0]+view.width, location[1]+view.height) }
        fun record(event: String) = compose.runOnIdle {
            val view = native()
            trace += JSONObject().put("event", event).put("uptime", SystemClock.uptimeMillis())
                .put("selectionStart", view.selectionStart).put("selectionEnd", view.selectionEnd)
                .put("calls", calls.size).put("requestStart", manual.request?.startUTF16 ?: -1)
                .put("requestEnd", manual.request?.endUTF16 ?: -1)
                .put("windows", WindowInspector.getGlobalWindowViews().size)
        }
        fun pointer(action: Int, x: Float, y: Float, down: Long) {
            val event = MotionEvent.obtain(down, SystemClock.uptimeMillis(), action, x, y, 0)
            event.source = InputDevice.SOURCE_TOUCHSCREEN
            try { assertTrue(ins.uiAutomation.injectInputEvent(event, true)) } finally { event.recycle() }
        }
        val report = JSONObject().put("complete", false).put("provider", "delayed lifecycle fixture; no model or audio quality claim")
        fun save() { File(output,"report.json").writeText(report.put("calls",JSONArray(calls)).put("trace",JSONArray(trace)).toString(2)) }
        compose.runOnIdle {
            owner = ConversationImmersion(context,"en","es",0.0,translator=provider,qaModelsReady=true,sourceLookup=null)
            owner.selectInputLanguage("native-handle-fixture","en")
            speech = SpeechPlayback(context,"en","es",scope)
            manual = ManualLookupInteraction(owner,speech,"native-handle-fixture",source,scope)
        }
        try {
            compose.setContent { VipiTheme(Appearance.LIGHT) {
                Column(Modifier.fillMaxSize().safeDrawingPadding().padding(18.dp)) {
                    ImmersionBubble(fixture,ReadingMode.IMMERSED,speech,"en","es","native-handle-fixture",
                        embedded=true,metadata={Text("3:15 PM")},manual=manual)
                }
                ManualLookupPopup(manual)
            } }
            lateinit var word: Rect
            compose.runOnIdle { word = native().sourceRangeRect(4,10) }
            val longDown = SystemClock.uptimeMillis()
            pointer(MotionEvent.ACTION_DOWN,word.centerX().toFloat(),word.centerY().toFloat(),longDown)
            SystemClock.sleep(750)
            record("long_press_held")
            assertEquals("No translation while long press remains down",0,calls.size)
            pointer(MotionEvent.ACTION_UP,word.centerX().toFloat(),word.centerY().toFloat(),longDown)
            compose.waitUntil(5_000) { calls.size == 1 && manual.request != null }
            record("initial_word_released")
            compose.runOnIdle { assertEquals(4,native().selectionStart); assertEquals(10,native().selectionEnd) }
            device.takeScreenshot(File(output,"long-press-selection.png"))
            lateinit var handle: Rect
            lateinit var destination: Rect
            compose.runOnIdle {
                val handles = views().filter { it.javaClass.name.contains("SelectionHandleView") && it.isShown && it.width > 0 }
                report.put("nativeHandles",JSONArray(handles.map { JSONObject().put("class",it.javaClass.name).put("bounds",bounds(it).toShortString()) }))
                check(handles.size >= 2) { "Expected native external selection handle views; found ${handles.size}" }
                handle = bounds(handles.maxBy { bounds(it).centerX() })
                destination = native().sourceRangeRect(14,15)
            }
            record("before_handle_down"); save()
            val dragDown = SystemClock.uptimeMillis()
            pointer(MotionEvent.ACTION_DOWN,handle.centerX().toFloat(),handle.centerY().toFloat(),dragDown)
            val targetX=destination.right.toFloat()
            val targetY=handle.centerY().toFloat() + (destination.bottom-word.bottom)
            for (step in 1..8) {
                pointer(MotionEvent.ACTION_MOVE,handle.centerX()+(targetX-handle.centerX())*step/8f,handle.centerY()+(targetY-handle.centerY())*step/8f,dragDown)
                SystemClock.sleep(70)
            }
            record("handle_drag_held"); save()
            assertEquals("No translation during native handle dragging",1,calls.size)
            pointer(MotionEvent.ACTION_UP,targetX,targetY,dragDown)
            val releaseAt=SystemClock.uptimeMillis()
            compose.waitUntil(5_000) { calls.size == 2 && manual.request != null }
            SystemClock.sleep(400)
            record("handle_released")
            var expectedCopy=""
            compose.runOnIdle {
                val view=native();val start=minOf(view.selectionStart,view.selectionEnd);val end=maxOf(view.selectionStart,view.selectionEnd)
                assertEquals(4,start);assertTrue("Native handle must extend the selected word",end>=15)
                assertEquals(start,manual.request?.startUTF16);assertEquals(end,manual.request?.endUTF16)
                assertEquals(2,calls.size);assertTrue(calls.last().getLong("uptime")>=releaseAt)
                expectedCopy=view.visibleText(start,end)
                report.put("finalSelectionStart",start).put("finalSelectionEnd",end).put("selectedText",expectedCopy)
                    .put("releaseUptime",releaseAt).put("noTranslationDuringDrag",true).put("oneRequestAfterRelease",true)
            }
            device.takeScreenshot(File(output,"handle-released.png"))
            val copy=device.wait(Until.findObject(By.text(context.getString(android.R.string.copy))),5_000)
            checkNotNull(copy) { "Native Copy menu unavailable after handle release" }.click()
            compose.runOnIdle {
                val copied=context.getSystemService(ClipboardManager::class.java).primaryClip?.getItemAt(0)?.text?.toString()
                assertEquals(expectedCopy,copied);assertNull(manual.request);assertNull(speech.activeMessage)
                report.put("copiedText",copied).put("copyExact",true)
            }
            report.put("complete",true).put("passed",true);save()
            device.takeScreenshot(File(output,"copied.png"))
        } catch(error:Throwable) {
            report.put("passed",false).put("error",error.toString());record("failure");save()
            device.takeScreenshot(File(output,"failure.png"));throw error
        } finally { compose.runOnIdle { manual.cancel();owner.close();speech.close() };scope.cancel();save() }
    }
}
