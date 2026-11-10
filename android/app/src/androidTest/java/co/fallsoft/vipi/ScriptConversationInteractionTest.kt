package co.fallsoft.vipi

import android.content.ContextWrapper
import android.content.Intent
import androidx.activity.compose.setContent
import androidx.test.core.app.ActivityScenario
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import android.graphics.Rect
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.view.inspector.WindowInspector
import androidx.compose.runtime.*
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.By
import androidx.test.uiautomator.BySelector
import androidx.test.uiautomator.UiObject2
import androidx.test.uiautomator.Configurator
import co.fallsoft.vipi.core.ImmersionPresentation
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.KeyStore
import java.security.MessageDigest
import java.time.Instant
import java.util.UUID

/** Curated existing references, actual conversation UI, isolated synthetic transport. */
@OptIn(androidx.compose.ui.ExperimentalComposeUiApi::class)
class ScriptConversationInteractionTest {
    private data class Screen(val chat: ChatSession, val peer: UUID, val source: String, val target: String, val dark: Boolean)
    private data class Snapshot(val visible: String, val bounds: Rect, val width: Int, val height: Int,
        val anchors: List<Pair<Float, Int>>, val layoutHeight: Int, val textSize: Float) {
        fun json() = JSONObject().put("visible", visible).put("bounds", bounds.toShortString())
            .put("width", width).put("height", height).put("layout_height", layoutHeight).put("text_size_px", textSize)
            .put("source_anchors", JSONArray(anchors.map { JSONArray(listOf(it.first, it.second)) }))
            .put("elapsed_ms", SystemClock.elapsedRealtime())
    }
    @Test fun continuousScriptRowsRespectDraftScrollAndCachedAudio() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("vipiDedicatedEmulator") == "true")
        val family = requireNotNull(args.getString("vipiScriptFamily")); require(family in setOf("forward", "reverse"))
        val run = args.getString("vipiScriptRun") ?: "001"; require(run.matches(Regex("[0-9]{3}")))
        val base = instrumentation.targetContext; val device = UiDevice.getInstance(instrumentation)
        val protocolFile = File(base.filesDir, "script-interaction-protocol-r01.json")
        val protocol = JSONObject(protocolFile.readText()); val cases = protocol.getJSONArray("cases")
        val onlyCase = args.getString("vipiScriptCase")
        val selected = (0 until cases.length()).map { cases.getJSONObject(it) }.filter {
            (it.getString("source") == "en") == (family == "forward") && (onlyCase == null || it.getString("id") == onlyCase)
        }
        assertEquals(if (onlyCase == null) 4 else 1, selected.size)
        val output = File(base.filesDir, "script-conversation-$family-$run"); check(!output.exists()); output.mkdirs()
        val report = JSONObject().put("complete", false).put("started_at", Instant.now().toString())
            .put("synthetic_contact_and_transport", true).put("production_conversation_renderer_and_speech", true)
            .put("display_width_px", device.displayWidth).put("display_height_px", device.displayHeight)
            .put("density_dpi", base.resources.displayMetrics.densityDpi).put("system_font_scale", base.resources.configuration.fontScale)
            .put("scope", protocol.getString("scope")).put("protocol_sha256", MessageDigest.getInstance("SHA-256").digest(protocolFile.readBytes()).joinToString("") { "%02x".format(it) })
        val rows = JSONArray(); report.put("cases", rows)
        fun save() = File(output, "receipt.json").writeText(report.toString(2))
        val screen = mutableStateOf<Screen?>(null)
        val configuration = Configurator.getInstance()
        val previousIdleTimeout = configuration.waitForIdleTimeout
        configuration.waitForIdleTimeout = 0
        val scenario = ActivityScenario.launch<MainActivity>(Intent(base, MainActivity::class.java).putExtra("vipi_screen", "welcome"))
        scenario.onActivity { activity -> activity.setContent {
            Box(Modifier.fillMaxSize().semantics { testTagsAsResourceId = true }) {
                screen.value?.let { value -> key(value.peer) { VipiTheme(if (value.dark) Appearance.DARK else Appearance.LIGHT) {
                    FriendConversationScreen(value.chat, value.peer, value.source, value.target, .5) {}
                } } }
            }
        } }
        fun fresh(selector: BySelector): List<UiObject2> {
            instrumentation.uiAutomation.clearCache(); return device.findObjects(selector)
        }
        fun node(selector: BySelector): UiObject2 {
            val until = SystemClock.elapsedRealtime() + 20_000
            while (SystemClock.elapsedRealtime() < until) {
                fresh(selector).lastOrNull()?.let { return it }; SystemClock.sleep(80)
            }
            error("Missing native UI control")
        }
        fun native(view: View): List<StableImmersionText> = when (view) {
            is StableImmersionText -> listOf(view)
            is ViewGroup -> (0 until view.childCount).flatMap { native(view.getChildAt(it)) }
            else -> emptyList()
        }
        save()
        try { for (case in selected) {
            val source = case.getString("source"); val target = case.getString("target"); val original = case.getString("original")
            val row = JSONObject(case.toString()).put("complete", false).put("observations", JSONArray()); rows.put(row); save()
            val root = File(base.cacheDir, "script-chat-${UUID.randomUUID()}").apply { mkdirs() }
            val context = object : ContextWrapper(base) {
                override fun getFilesDir() = File(root, "files").apply { mkdirs() }
                override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() }
            }
            val account = UUID.randomUUID(); val peer = UUID.randomUUID(); var chat: ChatSession? = null
            fun snapshot(): Snapshot? {
                var answer: Snapshot? = null
                instrumentation.runOnMainSync {
                    val views = WindowInspector.getGlobalWindowViews().flatMap(::native)
                        .filter { it.text.toString() == original && it.getGlobalVisibleRect(Rect()) }
                    if (views.size == 1) {
                        val view = views.single(); val bounds = Rect(); view.getGlobalVisibleRect(bounds)
                        // setText invalidates Layout until the next native measure pass.
                        // A pending layout is not a displayed phase observation.
                        val layout = view.layout
                        if (layout != null) answer = Snapshot(view.visibleText(), bounds, view.width, view.height,
                            (0..original.length).map { offset -> layout.getPrimaryHorizontal(offset) to layout.getLineBaseline(layout.getLineForOffset(offset)) },
                            layout.height, view.textSize)
                    }
                }
                return answer
            }
            fun awaitVisible(expected: String): Snapshot {
                val end = SystemClock.elapsedRealtime() + 45_000
                while (SystemClock.elapsedRealtime() < end) { snapshot()?.takeIf { it.visible == expected }?.let { return it }; SystemClock.sleep(80) }
                error("Missing expected native face for $source/$target")
            }
            fun settled(stage: String): Snapshot {
                val began = SystemClock.elapsedRealtime(); val until = began + 8_000
                var previous: Snapshot? = null; var matching = 0
                while (SystemClock.elapsedRealtime() < until) {
                    val current = snapshot()
                    if (current != null && previous?.let { it.bounds == current.bounds && it.width == current.width &&
                        it.height == current.height && it.anchors == current.anchors } == true) matching++ else matching = 0
                    if (current != null && matching >= 4) {
                        row.put("${stage}_settled_ms", SystemClock.elapsedRealtime() - began); save(); return current
                    }
                    previous = current; SystemClock.sleep(150)
                }
                error("Native row geometry did not settle after $stage")
            }
            fun stable(a: Snapshot, b: Snapshot) {
                assertEquals(a.width, b.width); assertEquals(a.height, b.height); assertEquals(a.anchors, b.anchors)
                assertEquals(a.bounds, b.bounds); assertTrue(b.layoutHeight <= b.height)
            }
            fun capture(name: String) {
                val before = snapshot(); check(device.takeScreenshot(File(output, "${case.getString("id")}-$name.png")))
                row.put("capture_$name", JSONObject().put("before", before?.json()).put("after", snapshot()?.json())); save()
            }
            fun changes(count: Int, stage: String) {
                val start = checkNotNull(snapshot()); var previous = start.visible; var changes = 0
                val observations = row.getJSONArray("observations"); observations.put(start.json().put("stage", stage))
                val until = SystemClock.elapsedRealtime() + 35_000
                while (changes < count && SystemClock.elapsedRealtime() < until) {
                    snapshot()?.let { current ->
                        stable(start, current)
                        if (current.visible != previous) {
                            previous = current.visible; changes++; observations.put(current.json().put("stage", stage))
                            if (stage == "continuous") capture("phase-$changes")
                        }
                    }; SystemClock.sleep(80)
                }
                assertEquals("Automatic changes for $source/$target $stage", count, changes); save()
            }
            fun menu() { node(By.desc("Reading options")).click() }
            fun waveFiles() = File(base.cacheDir, "vipi-speech").walkTopDown().filter { it.isFile && it.name.matches(Regex("[a-f0-9]{64}\\.wav")) }
                .associate { it.absolutePath to (it.length() to it.lastModified()) }
            try {
                assertEquals(case.getDouble("font_scale").toFloat(), base.resources.configuration.fontScale, .01f)
                var calls = 0
                val referenceOnly = object : LanguageTranslation {
                    override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) { error("No downloads in this UI qualification") }
                    override suspend fun translate(text: String, source: String, target: String): String { calls++; error("Expected existing catalog reference") }
                    override fun close() = Unit
                }
                val result: ImmersionPresentation = runBlocking {
                    ConversationImmersion(base, source, target, .5, referenceOnly).use { probe ->
                        val focus = checkNotNull(probe.presentation(original, source))
                        val filler = probe.presentation(case.getString("filler"), source)
                        row.put("filler_preflight", JSONObject().put("selected_spans", filler?.spans?.size ?: 0)
                            .put("full_reference", filler?.translation).put("status", probe.lastOutcome?.status.toString())
                            .put("origin", probe.lastOutcome?.origin.toString()))
                        focus
                    }
                }
                assertEquals(0, calls); assertTrue("No useful curated spans", result.spans.isNotEmpty())
                if (target != "en") assertTrue("Missing mandatory transliteration", result.spans.all { !it.romanization.isNullOrBlank() })
                fun face(script: Boolean) = result.spans.sortedByDescending { it.start }.fold(result.original) { text, span ->
                    text.replaceRange(span.start, span.end, if (script) span.translated else span.displayedTarget)
                }
                val mixed = face(false)
                row.put("preflight_translation_calls", calls).put("expected_mixed", mixed).put("expected_script", face(true))
                    .put("selected_spans", JSONArray(result.spans.map { JSONObject().put("source", it.original).put("target", it.translated)
                        .put("reading", it.romanization).put("start", it.start).put("end", it.end) }))
                val transport = object : ChatTransport {
                    override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject = when {
                        path == "/v1/me" -> ChatProfile(account, "script_qa", "Script QA").json()
                        path == "/v1/devices" -> JSONObject().put("id", requireNotNull(body).getString("device_id")).put("active", true)
                        path == "/v1/keys" -> JSONObject().put("revision", 1).put("remaining", 20)
                        path == "/v1/people/alex" -> ChatProfile(peer, "alex", "Alex").json()
                        path == "/v1/messages/pending" -> JSONObject().put("messages", JSONArray()).put("next_cursor", JSONObject.NULL)
                        path.startsWith("/v1/blocks/") -> JSONObject().put("blocked", false)
                        else -> throw ServiceFailure(0, "offline")
                    }
                }
                runBlocking { withContext(Dispatchers.Main) {
                    chat = ChatSession(context, transport, "script-${UUID.randomUUID()}").also { value ->
                        value.start(); check(value.ready); value.find("alex")
                        repeat(18) { value.send(case.getString("filler"), peer); SystemClock.sleep(2) }
                        value.send(original, peer)
                    }
                } }
                scenario.onActivity { screen.value = Screen(requireNotNull(chat), peer, source, target, family == "reverse") }
                awaitVisible(mixed); val first = settled("initial"); row.put("first_native", first.json()); capture("reading")
                row.put("stage", "continuous"); save()
                changes(4, "continuous")
                if (target != "en") {
                    row.put("stage", "script"); save()
                    val scriptBaseline = checkNotNull(snapshot())
                    menu(); node(By.text("Show original script")).click()
                    stable(scriptBaseline, awaitVisible(face(true))); capture("script")
                    menu(); node(By.text("Show Latin letters")).click(); stable(scriptBaseline, awaitVisible(mixed))
                }
                val audio = JSONArray(); var afterFirst: Map<String, Pair<Long, Long>>? = null
                row.put("stage", "audio"); save()
                repeat(2) { index ->
                    awaitVisible(mixed); menu(); node(By.text("Listen"))
                    val beforeFiles = waveFiles(); val at = SystemClock.elapsedRealtime(); node(By.text("Listen")).click()
                    var started: Long? = null; var samples = 0; val until = at + 20_000
                    while (SystemClock.elapsedRealtime() < until) {
                        val active = device.executeShellCommand("dumpsys audio").lineSequence().any { "AudioPlaybackConfiguration" in it && "u/pid:${base.applicationInfo.uid}/" in it && "state:started" in it }
                        if (active) { if (started == null) started = SystemClock.elapsedRealtime(); samples++; assertEquals(mixed, snapshot()?.visible) }
                        else if (started != null) break
                        SystemClock.sleep(60)
                    }
                    assertNotNull("No actual AudioTrack start observed", started); assertTrue(samples > 0)
                    val after = waveFiles()
                    if (index == 0) { assertTrue(after.isNotEmpty()); afterFirst = after }
                    else assertEquals("Cached audio should reuse the same unchanged files", afterFirst, after)
                    audio.put(JSONObject().put("play", index + 1).put("first_observed_start_ms", requireNotNull(started) - at)
                        .put("active_samples", samples).put("new_cache_files", after.keys.minus(beforeFiles.keys).size)
                        .put("cached_files_unchanged", index == 1))
                }
                row.put("audio", audio); save()
                row.put("stage", "draft"); save()
                node(By.res("message-input")).click(); node(By.res("message-input")).text = "A draft"
                val held = settled("keyboard_open"); val until = SystemClock.elapsedRealtime() + 8_000
                while (SystemClock.elapsedRealtime() < until) { val current = checkNotNull(snapshot()); assertEquals(held.visible, current.visible); stable(held, current); SystemClock.sleep(80) }
                capture("draft-paused"); row.put("draft_paused", true)
                row.put("stage", "empty_composer"); save()
                node(By.res("message-input")).text = ""; settled("draft_cleared")
                changes(2, "empty_focused_composer"); row.put("empty_composer_resumed", true)
                row.put("stage", "scroll"); save()
                device.pressBack(); settled("keyboard_closed")
                val timeline = node(By.res("conversation-timeline")).visibleBounds
                device.swipe(timeline.centerX(), timeline.top + timeline.height()/3, timeline.centerX(), timeline.top + timeline.height()*4/5, 160)
                node(By.desc("Jump to latest messages")); capture("scroll-history")
                node(By.desc("Jump to latest messages")).click(); awaitVisible(mixed); settled("returned_latest")
                changes(2, "scroll_return"); row.put("scroll_reentry_resumed", true)
                runBlocking { withContext(Dispatchers.Main) { assertEquals(original, requireNotNull(chat).messages(peer).maxBy { it.cursor }.text) } }
                row.put("original_unchanged", true).put("complete", true).put("stage", "complete"); save()
                println("VIPI_SCRIPT_CASE_PASSED ${case.getString("id")}")
            } catch (error: Throwable) {
                row.put("failure_class", error.javaClass.simpleName).put("failure_message", error.message); capture("failure"); throw error
            } finally {
                scenario.onActivity { screen.value = null }; SystemClock.sleep(150)
                chat?.let { value -> runBlocking { withContext(Dispatchers.Main) { value.close() } } }
                root.deleteRecursively(); KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
                save()
            }
        }
        report.put("complete", true).put("finished_at", Instant.now().toString()); save()
        } finally { scenario.close(); configuration.waitForIdleTimeout = previousIdleTimeout }
    }
}
