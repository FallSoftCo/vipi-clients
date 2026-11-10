package co.fallsoft.vipi

import android.content.Intent
import android.graphics.Rect
import android.os.Looper
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
import java.time.Instant
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicInteger

/** Actual Compose row/frame clock and authored assets. Only the first producer's
 * delay is synthetic; no translation/model download or peer traffic is allowed. */
class FullReadingCacheUIDeviceTest {
    @Test fun authoredReadingStaysOffRenderPathAndRejectsPreviousLanguageCompletion() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("vipiDedicatedEmulator") == "true")
        val run = args.getString("vipiReadingUIRun") ?: "001"; require(run.matches(Regex("[0-9]{3}")))
        val context = instrumentation.targetContext; val device = UiDevice.getInstance(instrumentation)
        val out = File(context.filesDir, "full-reading-ui-$run"); check(!out.exists()); check(out.mkdirs())
        val original = "I like music."; val id = "authored-reading-isolated-row"
        val report = JSONObject().put("complete", false).put("started_at", Instant.now().toString())
            .put("authored_assets_only", true).put("synthetic_first_producer_delay", true)
            .put("translation_calls", 0).put("download_calls", 0).put("no_peer_traffic", true)
        val events = JSONArray(); report.put("events", events)
        fun save() = File(out, "receipt.json").writeText(report.toString(2))
        fun event(name: String) { events.put(JSONObject().put("name", name).put("elapsed_ms", SystemClock.elapsedRealtime())); save() }
        val calls = ConcurrentHashMap<String, AtomicInteger>()
        val expected = ConcurrentHashMap<String, FullReading>()
        val references = ConcurrentHashMap<String, String>()
        val firstStarted = CompletableDeferred<Unit>(); val release = CompletableDeferred<Unit>(); val firstCompleted = CompletableDeferred<Unit>()
        val readings by lazy { SentenceReadings(context) }
        val producer: suspend (String, String) -> FullReading? = { text, language ->
            check(Looper.myLooper() != Looper.getMainLooper())
            val count = calls.computeIfAbsent(language) { AtomicInteger() }.incrementAndGet()
            if (language == "ja" && count == 1) {
                firstStarted.complete(Unit)
                withContext(NonCancellable) { release.await() }
            }
            val value = requireNotNull(readings.reading(text, language)).let { FullReading(it, FullReading.Provenance.AUTHORED) }
            references[language] = text; expected[language] = value
            if (language == "ja" && count == 1) firstCompleted.complete(Unit)
            value
        }
        val target = mutableStateOf("ja"); val nonce = mutableIntStateOf(0); val renders = AtomicInteger()
        val provider = object : LanguageTranslation {
            override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = error("Unexpected model download")
            override suspend fun translate(text: String, source: String, target: String): String = error("Unexpected translation")
            override fun close() {}
        }
        val config = Configurator.getInstance(); val oldIdle = config.waitForIdleTimeout; config.waitForIdleTimeout = 0
        val scenario = ActivityScenario.launch<MainActivity>(Intent(context, MainActivity::class.java).putExtra("vipi_screen", "welcome"))
        scenario.onActivity { activity -> activity.setContent { VipiTheme(Appearance.LIGHT) {
            val language = target.value; val metadata = nonce.intValue
            val scope = rememberCoroutineScope()
            val engine = remember(language) { ConversationImmersion(context, "en", language, 1.0, provider, qaReadingProducer = producer).also { it.selectInputLanguage(id, "en") } }
            val speech = remember(language) { SpeechPlayback(context, "en", language, scope) }
            DisposableEffect(engine, speech) { onDispose { engine.close(); speech.close() } }
            SideEffect { renders.incrementAndGet() }
            Surface(Modifier.fillMaxSize()) { Column(Modifier.fillMaxWidth().padding(24.dp)) {
                Text("Reading a message", style = MaterialTheme.typography.titleLarge)
                Spacer(Modifier.height(24.dp))
                ConversationImmersionText(original, id, engine, speech, false, {}, onTranslationSetup = { error("Unexpected setup") }) {
                    Text("Local reference check $metadata", style = MaterialTheme.typography.labelSmall)
                }
            } }
        } } }
        fun nativeViews(view: View): List<StableImmersionText> = when (view) {
            is StableImmersionText -> listOf(view)
            is ViewGroup -> (0 until view.childCount).flatMap { nativeViews(view.getChildAt(it)) }
            else -> emptyList()
        }
        data class Face(val text: String, val bounds: String, val anchors: List<Pair<Float, Int>>)
        fun face(): Face? {
            var found: Face? = null
            instrumentation.runOnMainSync {
                val views = WindowInspector.getGlobalWindowViews().flatMap(::nativeViews).filter { it.text.toString() == original && it.getGlobalVisibleRect(Rect()) }
                if (views.size == 1) { val view = views.single(); val bounds = Rect(); view.getGlobalVisibleRect(bounds)
                    view.layout?.let { layout -> found = Face(view.visibleText(), bounds.toShortString(), (0..original.length).map {
                        layout.getPrimaryHorizontal(it) to layout.getLineBaseline(layout.getLineForOffset(it)) }) }
                }
            }; return found
        }
        fun await(name: String, seconds: Long = 20, condition: () -> Boolean) {
            val end = SystemClock.elapsedRealtime() + seconds * 1000
            while (SystemClock.elapsedRealtime() < end) { if (condition()) return; SystemClock.sleep(60) }
            error("Timed out waiting for $name")
        }
        fun node(selector: BySelector): UiObject2 {
            var found: UiObject2? = null
            await("native control $selector") { instrumentation.uiAutomation.clearCache(); found = device.findObjects(selector).lastOrNull(); found != null }
            return requireNotNull(found)
        }
        fun choose(title: String) { node(By.desc("Reading options")).click(); node(By.text(title)).click() }
        fun capture(name: String) { check(device.takeScreenshot(File(out, "$name.png"))); event(name) }
        fun recompose() { repeat(20) { instrumentation.runOnMainSync { nonce.intValue++ }; SystemClock.sleep(40) } }
        save()
        try {
            await("first background producer") { firstStarted.isCompleted }
            await("actual inline Japanese") { face()?.text == "I like ongaku." }
            val initial = requireNotNull(face()); var prior = initial.text; var transitions = 0
            recompose(); val end = SystemClock.elapsedRealtime() + 25_000
            while (transitions < 2 && SystemClock.elapsedRealtime() < end) {
                face()?.let { current ->
                    assertEquals(initial.bounds, current.bounds); assertEquals(initial.anchors, current.anchors)
                    assertTrue(current.text == original || current.text == "I like ongaku.")
                    if (prior != current.text) { prior = current.text; transitions++; event("continuous_transition_$transitions") }
                }; SystemClock.sleep(60)
            }
            assertEquals(2, transitions); assertEquals(1, calls["ja"]!!.get()); assertTrue(renders.get() >= 20)
            capture("japanese-inline-reading-pending")
            instrumentation.runOnMainSync { target.value = "zh" }
            await("Chinese authored reading") { expected.containsKey("zh") }
            choose("Chinese"); node(By.text(expected["zh"]!!.text)); capture("chinese-authored-reading")
            release.complete(Unit); await("previous Japanese producer completed") { firstCompleted.isCompleted }
            SystemClock.sleep(500); recompose(); node(By.text(expected["zh"]!!.text))
            assertEquals(1, calls["ja"]!!.get()); assertEquals(1, calls["zh"]!!.get()); event("late_japanese_completion_not_published")
            choose("Show original script"); node(By.text(references["zh"]!!)); capture("chinese-original-script")
            choose("Show Latin letters"); node(By.text(expected["zh"]!!.text)); assertEquals(1, calls["zh"]!!.get())
            instrumentation.runOnMainSync { target.value = "ja" }
            await("fresh Japanese cache") { calls["ja"]?.get() == 2 }
            choose("Japanese"); node(By.text(expected["ja"]!!.text)); recompose(); node(By.text(expected["ja"]!!.text))
            assertEquals(2, calls["ja"]!!.get()); capture("japanese-authored-reading")
            choose("Show original script"); node(By.text(references["ja"]!!)); capture("japanese-original-script")
            report.put("complete", true).put("continuous_transitions", transitions).put("metadata_recompositions", 60)
                .put("observed_parent_compositions", renders.get()).put("ja_producer_calls", calls["ja"]!!.get()).put("zh_producer_calls", calls["zh"]!!.get())
                .put("producer_off_main_thread", true).put("late_language_completion_rejected", true)
                .put("references", JSONObject(references as Map<*, *>)).put("authored_readings", JSONObject(expected.mapValues { it.value.text }))
                .put("finished_at", Instant.now().toString()); save()
        } finally { release.complete(Unit); save(); scenario.close(); config.waitForIdleTimeout = oldIdle }
    }
}
