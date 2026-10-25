package co.fallsoft.vipi

import android.content.ContextWrapper
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.core.view.WindowInsetsCompat
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.security.KeyStore
import java.util.UUID

/** Native scrolling and real encrypted history; no real contact/network. */
class ChatTimelineDeviceTest {
    @get:Rule val compose = createComposeRule()
    @Test fun preserveReadingPositionAndExplicitlyReturnToLatest() {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
        val handwriting = device.executeShellCommand("settings get secure stylus_handwriting_enabled").trim()
        val run = InstrumentationRegistry.getArguments().getString("vipiTimelineRun") ?: "001"
        require(run.matches(Regex("[0-9]{3}")))
        val output = File(base.filesDir, "timeline-ui-$run"); check(!output.exists()); output.mkdirs()
        val root = File(base.cacheDir, "timeline-${UUID.randomUUID()}").apply { mkdirs() }
        val context = object : ContextWrapper(base) {
            override fun getFilesDir() = File(root, "files").apply { mkdirs() }
            override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() }
        }
        val account = UUID.randomUUID(); val peer = UUID.randomUUID()
        val transport = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject = when {
                path == "/v1/me" -> ChatProfile(account, "timeline_qa", "Timeline QA").json()
                path == "/v1/devices" -> JSONObject().put("id", requireNotNull(body).getString("device_id")).put("active", true)
                path == "/v1/keys" -> JSONObject().put("revision", 1).put("remaining", 20)
                path == "/v1/people/alex" -> ChatProfile(peer, "alex", "Alex").json()
                path == "/v1/messages/pending" -> JSONObject().put("messages", JSONArray()).put("next_cursor", JSONObject.NULL)
                path.startsWith("/v1/blocks/") -> JSONObject().put("blocked", false)
                else -> throw ServiceFailure(0, "offline")
            }
        }
        val visible = mutableStateOf(true); val appearance = mutableStateOf(Appearance.LIGHT)
        lateinit var chat: ChatSession
        var initialized = false
        fun anchor(): Pair<String, Float> {
            compose.waitForIdle()
            val viewport = compose.onNodeWithTag("conversation-timeline").fetchSemanticsNode().boundsInRoot
            val node = compose.onAllNodes(hasText("History message", substring = true)).fetchSemanticsNodes()
                .filter { it.boundsInRoot.top >= viewport.top && it.boundsInRoot.bottom <= viewport.bottom }
                .minBy { it.boundsInRoot.top }
            return node.config[SemanticsProperties.Text].joinToString("") { it.text } to node.boundsInRoot.top
        }
        fun capture(name: String) {
            compose.waitForIdle()
            android.os.SystemClock.sleep(350)
            check(UiDevice.getInstance(InstrumentationRegistry.getInstrumentation()).takeScreenshot(File(output, "$name.png")))
        }
        try {
            // Test the full software keyboard, not Gboard's floating stylus UI.
            device.executeShellCommand("settings put secure stylus_handwriting_enabled 0")
            runBlocking { withContext(Dispatchers.Main) {
                chat = ChatSession(context, transport, "timeline-${UUID.randomUUID()}"); initialized = true
                chat.start(); check(chat.ready); chat.find("alex")
                repeat(70) { index -> chat.send("History message ${index + 1}. We are making plans for tomorrow.", peer); android.os.SystemClock.sleep(2) }
            } }
            compose.setContent { if (visible.value) VipiTheme(appearance.value) { FriendConversationScreen(chat, peer) {} } }
            compose.onNodeWithText("History message 70. We are making plans for tomorrow.").assertIsDisplayed()
            compose.onNodeWithTag("conversation-timeline").performTouchInput { swipeDown() }
            compose.onNodeWithTag("conversation-timeline").performTouchInput { swipeDown() }
            compose.onNodeWithContentDescription("Jump to latest messages").assertIsDisplayed()
            val before = anchor()
            compose.runOnIdle { chat.send("Appended while reading earlier messages.", peer) }
            val after = anchor()
            assertEquals(before.first, after.first); assertEquals(before.second, after.second, 1f)
            capture("android-reading-preserved-light")
            compose.onNodeWithTag("message-input").performTouchInput { click() }
            compose.waitUntil(5_000) {
                var shown = false
                InstrumentationRegistry.getInstrumentation().runOnMainSync {
                    shown = android.view.inspector.WindowInspector.getGlobalWindowViews().any { view ->
                        view.rootWindowInsets?.let { WindowInsetsCompat.toWindowInsetsCompat(it).isVisible(WindowInsetsCompat.Type.ime()) } == true
                    }
                }
                shown
            }
            compose.onNodeWithTag("message-input").performTextInput("A draft while reading")
            compose.onNodeWithText(before.first).assertIsDisplayed()
            compose.onNodeWithContentDescription("Jump to latest messages").assertIsDisplayed()
            capture("android-reading-with-keyboard-light")
            compose.onNodeWithContentDescription("Send message").performClick()
            compose.onNodeWithText("A draft while reading").assertIsDisplayed()
            compose.onNodeWithContentDescription("Jump to latest messages").assertDoesNotExist()
            compose.runOnIdle {
                android.view.inspector.WindowInspector.getGlobalWindowViews().forEach { view ->
                    view.windowInsetsController?.hide(android.view.WindowInsets.Type.ime())
                }
            }
            compose.onNodeWithTag("conversation-timeline").performTouchInput { swipeDown() }
            compose.onNodeWithContentDescription("Jump to latest messages").assertIsDisplayed()
            compose.runOnIdle { appearance.value = Appearance.DARK }
            capture("android-jump-control-dark")
            compose.onNodeWithContentDescription("Jump to latest messages").performClick()
            compose.onNodeWithText("A draft while reading").assertIsDisplayed()
            compose.onNodeWithContentDescription("Jump to latest messages").assertDoesNotExist()
            compose.runOnIdle { chat.send("Appended while following latest.", peer) }
            compose.onNodeWithText("Appended while following latest.").assertIsDisplayed()
            capture("android-following-latest-dark")
            File(output, "receipt.json").writeText(JSONObject().put("synthetic_contact_and_transport", true)
                .put("initial_latest", true).put("append_preserved_anchor", true).put("keyboard_preserved_reading", true)
                .put("own_send_followed", true).put("explicit_jump_followed", true).put("followed_append", true).toString(2))
        } finally {
            device.executeShellCommand(if (handwriting == "null") "settings delete secure stylus_handwriting_enabled" else "settings put secure stylus_handwriting_enabled $handwriting")
            compose.runOnIdle { visible.value = false }; compose.waitForIdle()
            if (initialized) runBlocking { withContext(Dispatchers.Main) { chat.close() } }
            root.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
        }
    }
}
