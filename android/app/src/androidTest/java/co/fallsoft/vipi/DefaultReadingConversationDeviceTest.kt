package co.fallsoft.vipi

import android.content.ClipboardManager
import android.content.Context
import android.content.ContextWrapper
import android.content.Intent
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
import java.util.UUID

/** Actual ChatScreens and default packaged reader, with isolated synthetic peers.
 * Korean has an explicit fixed-reference QA provider; Japanese uses installed MT. */
@OptIn(androidx.compose.ui.ExperimentalComposeUiApi::class)
class DefaultReadingConversationDeviceTest {
    private data class Screen(val chat: ChatSession, val peer: UUID, val language: String,
                              val provider: LanguageTranslation, val fixed: Boolean)
    @Test fun defaultReadingsPreserveScriptCopyAudioAndConversationState() {
        val ins = InstrumentationRegistry.getInstrumentation(); check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val base = ins.targetContext; val device = UiDevice.getInstance(ins)
        fun sha(b: ByteArray) = MessageDigest.getInstance("SHA-256").digest(b).joinToString("") { "%02x".format(it) }
        val bytes = File(base.filesDir, "android-default-reading-chat-plan-r01.json").readBytes()
        assertEquals("8fcd49364cd11df8920ee609c4e8ae829c6a04dd34acb6b096d92573fc5ba9d6", sha(bytes))
        val cases = JSONObject(bytes.toString(Charsets.UTF_8)).getJSONArray("cases"); assertEquals(5, cases.length())
        val run = InstrumentationRegistry.getArguments().getString("vipiDefaultReadingRun") ?: "001"; require(run.matches(Regex("[0-9]{3}")))
        val out = File(base.filesDir, "android-default-reading-chat-$run"); check(!out.exists()); check(out.mkdirs())
        val rows = JSONArray(); val report = JSONObject().put("complete", false).put("plan_sha256", sha(bytes)).put("cases", rows)
            .put("default_reading_producer", true).put("reading_override", false).put("production_chat_ui", true)
            .put("synthetic_peer_and_transport", true).put("no_model_downloads", true).put("physical_acoustic_quality", false)
        fun save() = File(out, "receipt.json").writeText(report.toString(2))
        fun nodes(selector: BySelector): List<UiObject2> { ins.uiAutomation.clearCache(); return device.findObjects(selector) }
        fun node(selector: BySelector): UiObject2 {
            val until = SystemClock.elapsedRealtime() + 25_000
            while (SystemClock.elapsedRealtime() < until) { nodes(selector).lastOrNull()?.let { return it }; SystemClock.sleep(80) }
            error("Missing native control $selector")
        }
        fun choose(label: String) { node(By.desc("Reading options")).click(); node(By.text(label)).click() }
        fun wavs() = File(base.cacheDir, "vipi-speech").walkTopDown().filter { it.isFile && it.name.matches(Regex("[a-f0-9]{64}\\.wav")) }
            .associate { it.absolutePath to sha(it.readBytes()) }
        val screen = mutableStateOf<Screen?>(null); val conf = Configurator.getInstance(); val oldIdle = conf.waitForIdleTimeout; conf.waitForIdleTimeout = 0
        val clipboard = base.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        var oldClip: android.content.ClipData? = null; ins.runOnMainSync { oldClip = clipboard.primaryClip }
        val scenario = ActivityScenario.launch<MainActivity>(Intent(base, MainActivity::class.java).putExtra("vipi_screen", "welcome"))
        scenario.onActivity { activity -> activity.setContent { Box(Modifier.fillMaxSize().semantics { testTagsAsResourceId = true }) {
            screen.value?.let { s -> key(s.peer) { VipiTheme(Appearance.LIGHT) {
                FriendConversationScreen(s.chat, s.peer, "en", s.language, .5, qaTranslator = s.provider,
                    qaModelsReady = if (s.fixed) true else null) {}
            } } }
        } } }; save()
        try {
            for (i in 0 until cases.length()) {
                val sample = cases.getJSONObject(i); val text = sample.getString("text"); val language = sample.getString("language")
                val name = if (language == "ja") "Japanese" else "Korean"; val id = sample.getString("id"); val expected = sample.getString("reading")
                val fixed = sample.getString("provider") == "fixed-reference-qa"
                val row = JSONObject(sample.toString()).put("complete", false).put("readiness_override", fixed); rows.put(row); save()
                val root = File(base.cacheDir, "default-reading-${UUID.randomUUID()}").apply { mkdirs() }
                val context = object : ContextWrapper(base) {
                    override fun getFilesDir() = File(root, "files").apply { mkdirs() }
                    override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() }
                }
                val account = UUID.randomUUID(); val peer = UUID.randomUUID(); var chat: ChatSession? = null
                val calls = JSONArray(); val native = LocalTranslation()
                val provider = object : LanguageTranslation {
                    override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = error("No download permitted")
                    override suspend fun translate(value: String, source: String, target: String): String {
                        val start = SystemClock.elapsedRealtimeNanos()
                        val result = if (fixed) {
                            check(value == text && source == language && target == "en"); sample.getString("fixed_reference")
                        } else native.translate(value, source, target)
                        synchronized(calls) { calls.put(JSONObject().put("text", value).put("source", source).put("target", target)
                            .put("translated", result).put("fixed_qa_reference", fixed).put("elapsed_ms", (SystemClock.elapsedRealtimeNanos() - start) / 1e6)) }
                        return result
                    }
                    override fun close() { native.close() }
                }
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
                    runBlocking { withContext(Dispatchers.Main) { chat = ChatSession(context, transport, "default-reading-${UUID.randomUUID()}").also {
                        it.start(); check(it.ready); it.find("alex"); it.send(text, peer)
                    } } }
                    scenario.onActivity { screen.value = Screen(requireNotNull(chat), peer, language, provider, fixed) }
                    node(By.res("message-input")); choose("Message language"); node(By.text("Detect automatically")); node(By.text(name)).click(); SystemClock.sleep(1000)
                    choose(name); val shown = node(By.text(expected)); row.put("reading_bounds", shown.visibleBounds.toShortString())
                    check(device.takeScreenshot(File(out, "$id-reading.png")))
                    choose("Show original script"); node(By.text(text)); check(device.takeScreenshot(File(out, "$id-script.png")))
                    choose("Show transliteration"); node(By.text(expected))
                    choose("Copy original message"); var copied: String? = null
                    ins.runOnMainSync { copied = clipboard.primaryClip?.getItemAt(0)?.text?.toString() }; assertEquals(text, copied)
                    choose("English"); choose(name); node(By.text(expected)); row.put("reentry_display_exact", true).put("copy_original_exact", true)
                    if (sample.getBoolean("audio")) {
                        val before = wavs(); choose("Listen"); var started: Long? = null; var samples = 0; val began = SystemClock.elapsedRealtime()
                        while (SystemClock.elapsedRealtime() < began + 25_000) {
                            val playing = device.executeShellCommand("dumpsys audio").lineSequence().any { "AudioPlaybackConfiguration" in it && "u/pid:${base.applicationInfo.uid}/" in it && "state:started" in it }
                            if (playing) { if (started == null) started = SystemClock.elapsedRealtime(); samples++ } else if (started != null) break
                            SystemClock.sleep(60)
                        }
                        assertNotNull("Native playback start", started); val after = wavs(); var probeName: String? = null
                        runBlocking { withContext(Dispatchers.Main) { LocalSpeechPair(base, "en", language).use { pair ->
                            val example = ConversationExamples.result(base, "en", language); pair.prepare(mapOf("en" to example.original, language to example.translation))
                            probeName = pair.render(listOf(SpeechSpan(text, language))).file.name
                        } } }
                        val path = after.keys.single { File(it).name == requireNotNull(probeName) }; assertEquals(after[path], wavs()[path])
                        val file = File(path); file.copyTo(File(out, "ko-original-script.wav")); val pcm = PcmWave.read(file)
                        row.put("audio", JSONObject().put("original_script", text).put("native_cache_identity_matches", true).put("created_by_ui", path !in before)
                            .put("observed_player_bound_ms", started!! - began).put("active_samples", samples).put("sha256", sha(file.readBytes()))
                            .put("milliseconds", pcm.durationMs).put("sample_rate", pcm.sampleRate).put("acoustic_acceptance", false))
                    }
                    row.put("complete", true)
                } catch (failure: Throwable) { row.put("failure", failure.javaClass.simpleName).put("message", failure.message); device.takeScreenshot(File(out, "$id-failure.png")); throw failure }
                finally {
                    synchronized(calls) { row.put("provider_calls", JSONArray(calls.toString())) }; save()
                    scenario.onActivity { screen.value = null }; SystemClock.sleep(100)
                    chat?.let { c -> runBlocking { withContext(Dispatchers.Main) { c.close() } } }; provider.close()
                    root.deleteRecursively(); KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
                }
            }
            report.put("complete", true); save()
        } finally { save(); scenario.close(); conf.waitForIdleTimeout = oldIdle; ins.runOnMainSync { oldClip?.let(clipboard::setPrimaryClip) ?: clipboard.clearPrimaryClip() } }
    }
}
