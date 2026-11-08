package co.fallsoft.vipi

import android.content.ContextWrapper
import android.content.Intent
import android.graphics.Rect
import android.os.Looper
import android.os.SystemClock
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
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
import java.security.KeyStore
import java.util.UUID
import java.util.concurrent.atomic.AtomicInteger

/** Production ChatScreens/LazyColumn with an isolated synthetic transport and a
 * delayed actual authored lookup. Existing user session/history are untouched. */
@OptIn(androidx.compose.ui.ExperimentalComposeUiApi::class)
class FullReadingConversationDeviceTest {
    @Test fun delayedAuthoredReadingPreservesProductionHistoryAnchor() {
        val instrumentation = InstrumentationRegistry.getInstrumentation(); val args = InstrumentationRegistry.getArguments()
        check(args.getString("vipiDedicatedEmulator") == "true")
        val run = args.getString("vipiReadingChatRun") ?: "001"; require(run.matches(Regex("[0-9]{3}")))
        val base = instrumentation.targetContext; val device = UiDevice.getInstance(instrumentation)
        val out = File(base.filesDir, "full-reading-chat-$run"); check(!out.exists()); check(out.mkdirs())
        val root = File(base.cacheDir, "reading-chat-${UUID.randomUUID()}").apply { mkdirs() }
        val context = object : ContextWrapper(base) {
            override fun getFilesDir() = File(root, "files").apply { mkdirs() }
            override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() }
        }
        val account = UUID.randomUUID(); val peer = UUID.randomUUID()
        val transport = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject = when {
                path == "/v1/me" -> ChatProfile(account, "reading_qa", "Reading QA").json()
                path == "/v1/devices" -> JSONObject().put("id", requireNotNull(body).getString("device_id")).put("active", true)
                path == "/v1/keys" -> JSONObject().put("revision", 1).put("remaining", 20)
                path == "/v1/people/alex" -> ChatProfile(peer, "alex", "Alex").json()
                path == "/v1/messages/pending" -> JSONObject().put("messages", JSONArray()).put("next_cursor", JSONObject.NULL)
                path.startsWith("/v1/blocks/") -> JSONObject().put("blocked", false)
                else -> throw ServiceFailure(0, "offline")
            }
        }
        val reference = "私は音楽が好きです。"; val expected = "Watashi wa ongaku ga suki desu."
        val started = CompletableDeferred<Unit>(); val release = CompletableDeferred<Unit>(); val calls = AtomicInteger()
        val readings by lazy { SentenceReadings(base) }
        val producer: suspend (String, String) -> FullReading? = { text, language ->
            check(Looper.myLooper() != Looper.getMainLooper())
            if (text == reference) { calls.incrementAndGet(); started.complete(Unit); release.await() }
            readings.reading(text, language)?.let { FullReading(it, FullReading.Provenance.AUTHORED) }
        }
        val report = JSONObject().put("complete", false).put("production_chat_screens", true)
            .put("synthetic_contact_and_transport", true).put("synthetic_reading_delay", true).put("authored_assets_only", true)
            .put("no_peer_traffic", true).put("system_font_scale", base.resources.configuration.fontScale)
            .put("density_dpi", base.resources.displayMetrics.densityDpi).put("bounded_viewport_width_dp", 300)
        fun save() = File(out, "receipt.json").writeText(report.toString(2))
        fun await(name: String, condition: () -> Boolean) {
            val end = SystemClock.elapsedRealtime() + 25_000
            while (SystemClock.elapsedRealtime() < end) { if (condition()) return; SystemClock.sleep(60) }
            error("Timed out waiting for $name")
        }
        fun nodes(selector: BySelector): List<UiObject2> { instrumentation.uiAutomation.clearCache(); return device.findObjects(selector) }
        fun node(selector: BySelector): UiObject2 {
            var found: UiObject2? = null; await("native control $selector") { found = nodes(selector).firstOrNull(); found != null }; return requireNotNull(found)
        }
        val configuration = Configurator.getInstance(); val oldIdle = configuration.waitForIdleTimeout; configuration.waitForIdleTimeout = 0
        var chat: ChatSession? = null; var scenario: ActivityScenario<MainActivity>? = null
        save()
        try {
            runBlocking { withContext(Dispatchers.Main) {
                chat = ChatSession(context, transport, "reading-${UUID.randomUUID()}").also { value ->
                    value.start(); check(value.ready); value.find("alex")
                    repeat(30) { index -> value.send(if (index == 11) "I like music." else "I need water.", peer); SystemClock.sleep(2) }
                }
            } }
            scenario = ActivityScenario.launch<MainActivity>(Intent(base, MainActivity::class.java).putExtra("vipi_screen", "welcome"))
            scenario.onActivity { activity -> activity.setContent { Box(Modifier.width(300.dp).fillMaxHeight().semantics { testTagsAsResourceId = true }) {
                VipiTheme(Appearance.LIGHT) { FriendConversationScreen(requireNotNull(chat), peer, "en", "ja", 1.0, qaReadingProducer = producer) {} }
            } } }
            node(By.res("message-input")); node(By.res("conversation-timeline")); SystemClock.sleep(700)
            // Exercise ordinary history scrolling. ACTION_SCROLL_TO_POSITION is
            // not exposed by this runtime's native accessibility node.
            val focusSelector = By.desc(java.util.regex.Pattern.compile("I like (?:ongaku|music)\\."))
            var gestures = 0
            while (nodes(focusSelector).isEmpty() && gestures < 12) {
                val bounds = node(By.res("conversation-timeline")).visibleBounds
                device.swipe(bounds.centerX(), bounds.top + bounds.height() / 3, bounds.centerX(), bounds.top + bounds.height() * 4 / 5, 80)
                gestures++; SystemClock.sleep(250)
            }
            val focusBounds = node(focusSelector).visibleBounds
            report.put("history_scroll_gestures", gestures).put("focus_inline_bounds", focusBounds.toShortString()); save()
            node(By.desc("Jump to latest messages")); await("held authored reading") { started.isCompleted }
            val options = nodes(By.desc("Reading options")).filter { it.visibleBounds.centerY() >= focusBounds.bottom }
                .minByOrNull { it.visibleBounds.centerY() - focusBounds.bottom }
            requireNotNull(options).click(); node(By.text("Japanese")).click()
            val scriptBounds = node(By.text(reference)).visibleBounds
            val timelineBefore = node(By.res("conversation-timeline")).visibleBounds
            check(device.takeScreenshot(File(out, "history-script-before.png")))
            report.put("script_bounds", scriptBounds.toShortString()).put("timeline_before", timelineBefore.toShortString()); save()
            release.complete(Unit); val readingBounds = node(By.text(expected)).visibleBounds
            SystemClock.sleep(500); val settled = node(By.text(expected)).visibleBounds
            node(By.desc("Jump to latest messages")); val timelineAfter = node(By.res("conversation-timeline")).visibleBounds
            assertEquals(timelineBefore, timelineAfter); assertEquals(scriptBounds.top, settled.top)
            assertEquals(readingBounds, settled); assertEquals(1, calls.get())
            assertTrue("The delayed reading must actually grow this bounded viewport row", settled.height() > scriptBounds.height())
            check(device.takeScreenshot(File(out, "history-reading-after.png")))
            report.put("reading_bounds", settled.toShortString()).put("timeline_after", timelineAfter.toShortString())
                .put("row_height_grew", settled.height() > scriptBounds.height()).put("history_anchor_unchanged", true)
                .put("remained_in_history", true).put("producer_calls", calls.get()).put("complete", true); save()
        } catch (failure: Throwable) {
            report.put("failure_class", failure.javaClass.simpleName).put("failure_message", failure.message); save()
            device.takeScreenshot(File(out, "failure.png")); throw failure
        } finally {
            release.complete(Unit); save(); scenario?.close()
            chat?.let { value -> runBlocking { withContext(Dispatchers.Main) { value.close() } } }
            root.deleteRecursively(); KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
            configuration.waitForIdleTimeout = oldIdle
        }
    }
}
