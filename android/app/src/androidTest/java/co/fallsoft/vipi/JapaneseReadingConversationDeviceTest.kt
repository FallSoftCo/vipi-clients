package co.fallsoft.vipi

import android.content.ClipboardManager
import android.content.Context
import android.content.ContextWrapper
import android.content.Intent
import android.os.Looper
import android.os.SystemClock
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.*
import co.fallsoft.vipi.core.SpeechSpan
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

/** Explicit DEBUG-only composition of authored readings then the dormant Japanese
 * component. Default/release producers, message text and speech are unchanged. */
@OptIn(androidx.compose.ui.ExperimentalComposeUiApi::class)
class JapaneseReadingConversationDeviceTest {
    private data class Screen(val chat: ChatSession, val peer: UUID, val provider: LanguageTranslation,
                              val reader: suspend (String, String) -> FullReading?)
    @Test fun frozenCandidateUsesActualConversationAndOriginalScriptAudio() {
        val instrumentation = InstrumentationRegistry.getInstrumentation(); val args = InstrumentationRegistry.getArguments()
        check(args.getString("vipiDedicatedEmulator") == "true")
        val run = args.getString("vipiJapaneseReadingChatRun") ?: "001"; require(run.matches(Regex("[0-9]{3}")))
        val base = instrumentation.targetContext; val device = UiDevice.getInstance(instrumentation)
        fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
        val bytes = File(base.filesDir, "android-gated-japanese-chat-plan-r01.json").readBytes()
        assertEquals("4e4d2907fcd0c3bdc14772886a2b66d831177f6e8a4cb68edc89c9eae65e7a2e", sha(bytes))
        val cases = JSONObject(bytes.toString(Charsets.UTF_8)).getJSONArray("cases"); assertEquals(8, cases.length())
        val out = File(base.filesDir, "japanese-reading-chat-$run"); check(!out.exists()); check(out.mkdirs())
        val report = JSONObject().put("complete", false).put("started_at", Instant.now().toString()).put("plan_sha256", sha(bytes))
            .put("production_conversation_ui", true).put("synthetic_contact_and_transport", true).put("debug_candidate_only", true)
            .put("release_fallback_enabled", false).put("new_model_downloads", 0).put("remote_translation_calls", 0)
        val rows = JSONArray(); report.put("cases", rows)
        fun save() = File(out, "receipt.json").writeText(report.toString(2))
        fun await(name: String, seconds: Long = 25, condition: () -> Boolean) {
            val end = SystemClock.elapsedRealtime() + seconds * 1000
            while (SystemClock.elapsedRealtime() < end) { if (condition()) return; SystemClock.sleep(60) }
            error("Timed out waiting for $name")
        }
        fun nodes(selector: BySelector): List<UiObject2> { instrumentation.uiAutomation.clearCache(); return device.findObjects(selector) }
        fun node(selector: BySelector): UiObject2 {
            var found: UiObject2? = null; await("native control $selector") { found = nodes(selector).lastOrNull(); found != null }; return requireNotNull(found)
        }
        fun menu() { node(By.desc("Reading options")).click() }
        fun choose(label: String) { menu(); node(By.text(label)).click() }
        fun wavs() = File(base.cacheDir, "vipi-speech").walkTopDown().filter { it.isFile && it.name.matches(Regex("[a-f0-9]{64}\\.wav")) }
            .associate { it.absolutePath to (it.lastModified() to sha(it.readBytes())) }
        val screen = mutableStateOf<Screen?>(null); val config = Configurator.getInstance(); val oldIdle = config.waitForIdleTimeout; config.waitForIdleTimeout = 0
        val clipboard = base.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        var originalClipboard: android.content.ClipData? = null; instrumentation.runOnMainSync { originalClipboard = clipboard.primaryClip }
        val scenario = ActivityScenario.launch<MainActivity>(Intent(base, MainActivity::class.java).putExtra("vipi_screen", "welcome"))
        scenario.onActivity { activity -> activity.setContent { Box(Modifier.fillMaxSize().semantics { testTagsAsResourceId = true }) {
            screen.value?.let { value -> key(value.peer) { VipiTheme(Appearance.LIGHT) {
                FriendConversationScreen(value.chat, value.peer, "en", "ja", .5, qaReadingProducer = value.reader, qaTranslator = value.provider) {}
            } } }
        } } }
        save()
        try { for (index in 0 until cases.length()) {
            val sample = cases.getJSONObject(index); val text = sample.getString("text"); val id = sample.getString("id")
            val row = JSONObject(sample.toString()).put("complete", false); rows.put(row); save()
            val root = File(base.cacheDir, "japanese-reading-chat-${UUID.randomUUID()}").apply { mkdirs() }
            val context = object : ContextWrapper(base) {
                override fun getFilesDir() = File(root, "files").apply { mkdirs() }
                override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() }
            }
            val account = UUID.randomUUID(); val peer = UUID.randomUUID(); var chat: ChatSession? = null
            val traceLock = Any(); val providerCalls = mutableListOf<JSONObject>(); val readerCalls = mutableListOf<JSONObject>()
            val native = LocalTranslation()
            val provider = object : LanguageTranslation {
                override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = error("No model downloads in this qualification")
                override suspend fun translate(text: String, source: String, target: String): String {
                    val call = JSONObject().put("text", text).put("source", source).put("target", target)
                    synchronized(traceLock) { providerCalls += call }
                    val start = SystemClock.elapsedRealtimeNanos()
                    try { return native.translate(text, source, target).also { value -> synchronized(traceLock) { call.put("translation", value) } } }
                    catch (failure: Exception) { synchronized(traceLock) { call.put("error_class", failure.javaClass.simpleName) }; throw failure }
                    finally { synchronized(traceLock) { call.put("elapsed_ms", (SystemClock.elapsedRealtimeNanos() - start) / 1e6) } }
                }
                override fun close() { native.close() }
            }
            val authored by lazy { SentenceReadings(base) }
            val reader: suspend (String, String) -> FullReading? = { value, language ->
                check(Looper.myLooper() != Looper.getMainLooper()); val start = SystemClock.elapsedRealtimeNanos()
                val exact = authored.reading(value, language)
                val candidate = if (exact == null && language == "ja") JapaneseReadings.read(value) else null
                val reading = exact ?: candidate?.reading
                val provenance = if (exact != null) FullReading.Provenance.AUTHORED else FullReading.Provenance.LOCAL_TRANSLITERATION
                val trace = JSONObject().put("text", value).put("language", language).put("reading", reading ?: JSONObject.NULL)
                    .put("provenance", if (reading == null) "unavailable" else provenance.name).put("candidate_called", candidate != null)
                    .put("elapsed_ms", (SystemClock.elapsedRealtimeNanos() - start) / 1e6)
                    .put("issues", JSONArray(candidate?.issues?.map { it.name } ?: emptyList<String>()))
                candidate?.let { trace.put("pieces", JSONArray(it.pieces.map { piece -> JSONObject().put("start_utf16", piece.start).put("end_utf16", piece.end)
                    .put("original", piece.original).put("value", piece.value).put("kind", piece.kind.name) })) }
                synchronized(traceLock) { readerCalls += trace }
                reading?.let { FullReading(it, provenance) }
            }
            fun traces() { synchronized(traceLock) {
                row.put("actual_local_provider_calls", JSONArray(providerCalls.map { JSONObject(it.toString()) }))
                row.put("reading_producer_calls", JSONArray(readerCalls.map { JSONObject(it.toString()) }))
            }; save() }
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
            try {
                runBlocking { withContext(Dispatchers.Main) { chat = ChatSession(context, transport, "ja-reading-${UUID.randomUUID()}").also {
                    it.start(); check(it.ready); it.find("alex"); it.send(text, peer)
                } } }
                scenario.onActivity { screen.value = Screen(requireNotNull(chat), peer, provider, reader) }
                node(By.res("message-input")); menu(); node(By.text("Message language")).click()
                check(device.takeScreenshot(File(out, "$id-language-selection.png"))); node(By.text("Japanese")).click()
                row.put("explicit_message_language_selection", "ja"); save()
                // Allow current automatic work to settle before the explicit full-view action.
                SystemClock.sleep(1500); choose("Japanese")
                var trace: JSONObject? = null
                val until = SystemClock.elapsedRealtime() + 25_000
                while (SystemClock.elapsedRealtime() < until) {
                    trace = synchronized(traceLock) { readerCalls.lastOrNull { it.getString("text") == text }?.let { JSONObject(it.toString()) } }
                    if (trace != null) break
                    SystemClock.sleep(100)
                }
                if (trace != null) {
                    val value = trace!!
                    val reading = if (value.isNull("reading")) null else value.getString("reading")
                    node(By.text(reading ?: text)); row.put("displayed", reading ?: text).put("full_reference_available", true)
                    check(device.takeScreenshot(File(out, "$id-full-reading.png")))
                    if (reading != null) {
                        choose("Show original script"); node(By.text(text)); check(device.takeScreenshot(File(out, "$id-original-script.png")))
                        choose("Show transliteration"); node(By.text(reading))
                    } else {
                        menu(); assertTrue(nodes(By.text("Show transliteration")).isEmpty()); assertTrue(nodes(By.text("Show original script")).isEmpty()); device.pressBack()
                    }
                    choose("Copy original message"); var copied: String? = null
                    instrumentation.runOnMainSync { copied = clipboard.primaryClip?.getItemAt(0)?.text?.toString() }; assertEquals(text, copied); row.put("copy_original_exact", true)
                    val count = synchronized(traceLock) { readerCalls.count { it.getString("text") == text } }
                    choose("English"); choose("Japanese"); node(By.text(reading ?: text))
                    assertEquals(count, synchronized(traceLock) { readerCalls.count { it.getString("text") == text } }); row.put("reading_reentry_cached", true)
                    if (id == "authored-precedence") { assertEquals("AUTHORED", value.getString("provenance")); assertFalse(value.getBoolean("candidate_called")) }
                    if (id == "ja-mixed_unknown-2" && reading != null) {
                        val before = wavs(); menu(); node(By.text("Listen")).click()
                        var started: Long? = null; var samples = 0; val began = SystemClock.elapsedRealtime(); val stopAt = began + 25_000
                        while (SystemClock.elapsedRealtime() < stopAt) {
                            val playing = device.executeShellCommand("dumpsys audio").lineSequence().any { "AudioPlaybackConfiguration" in it && "u/pid:${base.applicationInfo.uid}/" in it && "state:started" in it }
                            if (playing) { if (started == null) started = SystemClock.elapsedRealtime(); samples++ } else if (started != null) break
                            SystemClock.sleep(60)
                        }
                        assertNotNull("Actual AudioTrack start", started); assertTrue(samples > 0)
                        val after = wavs(); val added = after.keys - before.keys
                        var probeName: String? = null
                        runBlocking { withContext(Dispatchers.Main) { LocalSpeechPair(base, "en", "ja").use { pair ->
                            val example = ConversationExamples.result(base, "en", "ja")
                            pair.prepare(mapOf("en" to example.original, "ja" to example.translation))
                            probeName = pair.render(listOf(SpeechSpan(text, "ja"))).file.name
                        } } }
                        // Each owner has a private directory. The basename binds
                        // exact native script/language/voice identity; comparing
                        // paths across owners would defeat that isolation.
                        val uiPath = after.keys.single { File(it).name == requireNotNull(probeName) }
                        assertEquals(after[uiPath], wavs()[uiPath])
                        val uiFile = File(uiPath); val wave = PcmWave.read(uiFile)
                        uiFile.copyTo(File(out, "original-script-audio.wav"), overwrite = false)
                        row.put("audio", JSONObject().put("observed_start_bound_ms", requireNotNull(started) - began).put("active_samples", samples)
                            .put("original_script", text).put("cache_basename_matched_original_script", true).put("created_by_this_ui_play", uiPath in added)
                            .put("cache_sha256", sha(uiFile.readBytes())).put("milliseconds", wave.durationMs).put("sample_rate", wave.sampleRate).put("channels", wave.channels)
                            .put("acoustic_quality_verified", false))
                    }
                } else {
                    // Pipeline/model/identifier abstention is not bypassed to make
                    // a reading fixture pass. Retain the actual current screen.
                    row.put("full_reference_available", false).put("reading_producer_called_for_source", false)
                    menu(); check(device.takeScreenshot(File(out, "$id-unavailable-menu.png"))); device.pressBack()
                }
                traces(); row.put("complete", true); save()
            } catch (failure: Throwable) {
                row.put("failure_class", failure.javaClass.simpleName).put("failure_message", failure.message); traces()
                device.takeScreenshot(File(out, "$id-failure.png")); throw failure
            } finally {
                scenario.onActivity { screen.value = null }; SystemClock.sleep(100)
                chat?.let { value -> runBlocking { withContext(Dispatchers.Main) { value.close() } } }; provider.close()
                root.deleteRecursively(); KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
            }
        }
            report.put("complete", true).put("finished_at", Instant.now().toString()); save()
        } finally {
            save(); scenario.close(); config.waitForIdleTimeout = oldIdle
            instrumentation.runOnMainSync { originalClipboard?.let(clipboard::setPrimaryClip) ?: clipboard.clearPrimaryClip() }
        }
    }
}
