package co.fallsoft.vipi

import android.content.Context
import android.content.Intent
import android.graphics.Rect
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.view.inspector.WindowInspector
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.*
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.io.IOException
import java.time.Instant
import java.util.concurrent.atomic.AtomicInteger

/** Real native row, frame clock, ML Kit and player. Delay/error gates are explicitly synthetic. */
class SourceUnitUIDeviceTest {
    private val original = "I need water. Did you finish the report?"
    private val mixed = "Ninahitaji maji. Did you finish the report?"
    private val reference = "Ninahitaji maji. Je, umemaliza ripoti?"
    private data class Face(val text: String, val bounds: Rect, val anchors: List<Pair<Float, Int>>) {
        fun json() = JSONObject().put("text", text).put("bounds", bounds.toShortString())
            .put("anchors", JSONArray(anchors.map { JSONArray(listOf(it.first, it.second)) }))
            .put("elapsed_ms", SystemClock.elapsedRealtime())
    }
    @Test fun explicitFullActionPreservesImmersionAcrossCancelErrorAndRetry() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("vipiDedicatedEmulator") == "true")
        val run = args.getString("vipiRoutingUIRun") ?: "001"; require(run.matches(Regex("[0-9]{3}")))
        val context = instrumentation.targetContext; val device = UiDevice.getInstance(instrumentation)
        val out = File(context.filesDir, "source-unit-ui-$run");check(!out.exists());check(out.mkdirs())
        val report = JSONObject().put("complete",false).put("started_at",Instant.now().toString())
            .put("isolated_native_row",true).put("synthetic_delay_error_gates",true).put("no_peer_traffic",true)
            .put("original",original).put("expected_approved_partial",mixed)
        val events = JSONArray();report.put("events",events)
        fun save() = File(out,"receipt.json").writeText(report.toString(2))
        fun event(name:String) { events.put(JSONObject().put("name",name).put("elapsed_ms",SystemClock.elapsedRealtime()));save() }
        val attempts = AtomicInteger();val actual = AtomicInteger();val gates = List(3) { CompletableDeferred<Unit>() }
        val native = LocalTranslation()
        val provider = object : LanguageTranslation {
            override suspend fun prepare(source:String,target:String,cellularAllowed:Boolean) = error("No downloads in this qualification")
            override suspend fun translate(text:String,source:String,target:String):String {
                assertEquals(original,text);assertEquals("en",source);assertEquals("sw",target)
                val index=attempts.getAndIncrement();check(index in gates.indices)
                gates[index].await()
                if(index==1) throw IOException("Synthetic provider failure")
                actual.incrementAndGet()
                return native.translate(text,source,target).also { assertEquals(reference,it) }
            }
            override fun close() { native.close() }
        }
        val engine=ConversationImmersion(context,"en","sw",.25,provider)
        val id="source-routing-isolated-row"
        runBlocking { engine.selectInputLanguage(id,"en");engine.checkDownloads();assertEquals(true,engine.ready) }
        val scope=CoroutineScope(SupervisorJob()+Dispatchers.Main)
        lateinit var speech:SpeechPlayback
        instrumentation.runOnMainSync { speech=SpeechPlayback(context,"en","sw",scope);speech.prepare(mapOf("en" to "I need water.","sw" to "Ninahitaji maji.")) }
        val config=Configurator.getInstance();val oldIdle=config.waitForIdleTimeout;config.waitForIdleTimeout=0
        val scenario=ActivityScenario.launch<MainActivity>(Intent(context,MainActivity::class.java).putExtra("vipi_screen","welcome"))
        scenario.onActivity { activity -> activity.setContent { VipiTheme(Appearance.LIGHT) {
            Surface(Modifier.fillMaxSize()) { Column(Modifier.fillMaxWidth().padding(24.dp)) {
                Text("Reading a message", style=MaterialTheme.typography.titleLarge)
                Spacer(Modifier.height(24.dp))
                ConversationImmersionText(original,id,engine,speech,false,{},onTranslationSetup={ error("Unexpected model setup") }) {
                    Text("Local reference check",style=MaterialTheme.typography.labelSmall)
                }
            } }
        } } }
        fun nativeViews(view:View):List<StableImmersionText> = when(view) {
            is StableImmersionText -> listOf(view)
            is ViewGroup -> (0 until view.childCount).flatMap { nativeViews(view.getChildAt(it)) }
            else -> emptyList()
        }
        fun face():Face? {
            var result:Face?=null
            instrumentation.runOnMainSync {
                val views=WindowInspector.getGlobalWindowViews().flatMap(::nativeViews)
                    .filter { it.text.toString()==original && it.getGlobalVisibleRect(Rect()) }
                if(views.size==1) { val view=views.single();val bounds=Rect();view.getGlobalVisibleRect(bounds)
                    view.layout?.let { layout -> result=Face(view.visibleText(),bounds,(0..original.length).map {
                        layout.getPrimaryHorizontal(it) to layout.getLineBaseline(layout.getLineForOffset(it)) }) }
                }
            };return result
        }
        fun await(name:String,seconds:Long=20,condition:()->Boolean) {
            val end=SystemClock.elapsedRealtime()+seconds*1000
            while(SystemClock.elapsedRealtime()<end) { if(condition()) return;SystemClock.sleep(60) }
            error("Timed out waiting for $name")
        }
        fun fresh(selector:BySelector):List<UiObject2> { instrumentation.uiAutomation.clearCache();return device.findObjects(selector) }
        fun node(selector:BySelector):UiObject2 {
            var found:UiObject2?=null;await("native control") { found=fresh(selector).lastOrNull();found!=null };return requireNotNull(found)
        }
        fun menu() { node(By.desc("Reading options")).click() }
        fun choose(title:String) { menu();node(By.text(title)).click() }
        fun capture(name:String) { SystemClock.sleep(300);check(device.takeScreenshot(File(out,"$name.png")));face()?.let { events.put(it.json().put("name",name));save() } }
        fun changes(count:Int,name:String) {
            await("inline face") { face()!=null };val first=requireNotNull(face());var prior=first.text;var changes=0
            val end=SystemClock.elapsedRealtime()+25_000
            while(changes<count && SystemClock.elapsedRealtime()<end) {
                face()?.let { value ->
                    assertEquals(first.bounds,value.bounds);assertEquals(first.anchors,value.anchors)
                    assertTrue(value.text==original || value.text==mixed)
                    if(value.text!=prior) { prior=value.text;changes++;events.put(value.json().put("name",name));save() }
                };SystemClock.sleep(60)
            };assertEquals("Automatic transitions $name",count,changes)
        }
        save()
        try {
            await("first approved partial",30) { face()?.text==mixed };capture("initial-partial")
            assertEquals(0,attempts.get());assertEquals("unmeasured",engine.lexicalPreparation)
            changes(2,"initial-continuous")
            choose("Swahili");await("first gated request") { attempts.get()==1 };event("full_request_1_pending")
            changes(2,"continuous-while-full-pending")
            menu();node(By.text("Translating to Swahili…"));capture("loading-menu")
            node(By.text("Cancel full translation")).click();gates[0].complete(Unit)
            SystemClock.sleep(500);assertEquals(0,actual.get());assertEquals(1,attempts.get());assertNull(engine.cachedPresentation(original,id)?.translation)
            capture("cancel-keeps-partial");changes(1,"continuous-after-cancel")
            choose("Swahili");await("second gated request") { attempts.get()==2 };gates[1].complete(Unit)
            await("synthetic failure") { engine.lastOutcome?.fallbackStatus==co.fallsoft.vipi.core.ImmersionStatus.ERROR }
            menu();node(By.text("Try Swahili again"));capture("error-menu");node(By.text("Try Swahili again")).click()
            await("third gated request") { attempts.get()==3 };assertEquals(0,actual.get());gates[2].complete(Unit)
            node(By.text(reference));event("actual_mlkit_reference_visible");capture("full-reference")
            assertEquals(1,actual.get());assertEquals("unmeasured",engine.lexicalPreparation)
            assertEquals(1,engine.cachedPresentation(original,id)?.spans?.size)
            choose("Copy original message")
            var copied:String?=null;instrumentation.runOnMainSync { copied=(context.getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager).primaryClip?.getItemAt(0)?.text?.toString() }
            assertEquals(original,copied);event("copy_preserved_exact_original")
            await("prepared voices",40) { speech.state==SpeechState.READY }
            choose("Listen");val listenStart=SystemClock.elapsedRealtime();await("actual player start",25) { speech.state==SpeechState.PLAYING }
            report.put("observed_player_start_bound_ms",SystemClock.elapsedRealtime()-listenStart);event("full_reference_native_player_started")
            node(By.text(reference));await("player completion",35) { speech.activeMessage==null };assertNull(speech.error)
            choose("Immersed");await("restored partial") { face()!=null };changes(2,"continuous-after-full-view")
            choose("Swahili");node(By.text(reference));assertEquals(1,actual.get());assertEquals(3,attempts.get());capture("cached-full-reference")
            choose("English");node(By.text(original));event("exact_original_view")
            report.put("complete",true).put("provider_attempts",attempts.get()).put("actual_mlkit_calls",actual.get())
                .put("download_calls",0).put("full_translation",reference).put("lexical_preparation",engine.lexicalPreparation)
                .put("finished_at",Instant.now().toString());save()
        } finally {
            save();scenario.close();instrumentation.runOnMainSync { speech.close() };scope.cancel();engine.close();config.waitForIdleTimeout=oldIdle
        }
    }
}
