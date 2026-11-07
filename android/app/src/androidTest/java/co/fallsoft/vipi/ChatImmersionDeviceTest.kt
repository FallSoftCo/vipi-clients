package co.fallsoft.vipi

import android.content.ContextWrapper
import android.view.View
import android.view.ViewGroup
import android.view.inspector.WindowInspector
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.By
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

class ChatImmersionDeviceTest {
    @get:Rule val compose = createComposeRule()
    @Test fun messageWithoutVocabularyKeepsLanguageViewsAndUsefulActions() {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val mode = mutableStateOf(ReadingMode.IMMERSED)
        val result = co.fallsoft.vipi.core.ImmersionResult("I like music.", "Ninapenda muziki.", emptyList())
        compose.setContent { VipiTheme(Appearance.LIGHT) {
            ImmersionBubble(result, mode.value, source = "en", target = "sw", embedded = true,
                onModeChange = { mode.value = it }, originalMessage = result.original)
        } }
        compose.onNodeWithContentDescription("Reading options").performClick()
        for (title in listOf("Pause word switching", "Switching pace", "Show meanings now"))
            compose.onNodeWithText(title).assertDoesNotExist()
        compose.onNodeWithText("Copy original message").assertIsDisplayed()
        compose.onNodeWithText("Swahili").performClick()
        compose.onNodeWithText("Ninapenda muziki.").assertIsDisplayed()
        compose.onNodeWithContentDescription("Reading options").performClick()
        compose.onNodeWithText("English").performClick()
        compose.onNodeWithText("I like music.").assertIsDisplayed()
    }
    @Test fun continuousSwahiliAndWholeTranslationUseActualConversationRows() = qualify(false)
    @Test fun swahiliOriginalCanBeReadInEnglishAndCopiedWithoutRewriting() = qualify(true)
    private fun qualify(reversed: Boolean) {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val run = InstrumentationRegistry.getArguments().getString("vipiChatImmersionRun") ?: "001"
        require(run.matches(Regex("[0-9]{3}")))
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val base = instrumentation.targetContext
        val clipboard = base.getSystemService(android.content.Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
        val priorClipboard = clipboard.primaryClip
        val output = File(base.filesDir, "chat-immersion-$run" + if (reversed) "-reverse" else ""); check(!output.exists()); output.mkdirs()
        val root = File(base.cacheDir, "immersion-chat-${UUID.randomUUID()}").apply { mkdirs() }
        val context = object : ContextWrapper(base) {
            override fun getFilesDir() = File(root, "files").apply { mkdirs() }
            override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() }
        }
        val account = UUID.randomUUID(); val peer = UUID.randomUUID()
        val transport = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject = when {
                path == "/v1/me" -> ChatProfile(account, "immersion_qa", "Immersion QA").json()
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
        var languageRequests = 0
        fun paragraphs(view: View): List<StableImmersionText> = when (view) {
            is StableImmersionText -> listOf(view)
            is ViewGroup -> (0 until view.childCount).flatMap { paragraphs(view.getChildAt(it)) }
            else -> emptyList()
        }
        fun lastParagraph(): Pair<String, Int>? {
            var result: Pair<String, Int>? = null
            instrumentation.runOnMainSync {
                result = WindowInspector.getGlobalWindowViews().flatMap { paragraphs(it) }
                    .singleOrNull { it.text.toString() == "I like music." &&
                        it.getGlobalVisibleRect(android.graphics.Rect()) }?.let { it.visibleText() to it.height }
            }
            return result
        }
        fun capture(name: String) {
            compose.waitForIdle()
            UiDevice.getInstance(instrumentation).waitForIdle()
            check(UiDevice.getInstance(instrumentation).takeScreenshot(File(output, "$name.png")))
        }
        val originals = if (reversed) listOf("Ninapenda muziki.") else listOf("I am reading a book now.", "I am drinking water now.", "Where is the phone charger?", "I like music.")
        try {
            runBlocking { withContext(Dispatchers.Main) {
                chat = ChatSession(context, transport, "immersion-${UUID.randomUUID()}"); initialized = true
                chat.start(); check(chat.ready); chat.find("alex")
                originals.forEach { chat.send(it, peer) }
            } }
            compose.setContent { if (visible.value) VipiTheme(appearance.value) { FriendConversationScreen(chat, peer, "en", "sw", .5, onLanguages = { languageRequests++ }) {} } }
            compose.waitUntil(20_000) { lastParagraph()?.first == "I like muziki." }
            val height = lastParagraph()!!.second
            capture("android-swahili-conversation-light")
            val metadata = compose.onAllNodes(SemanticsMatcher("message metadata") {
                it.config.getOrElse(androidx.compose.ui.semantics.SemanticsProperties.TestTag) { "" }.startsWith("message-meta-")
            }).fetchSemanticsNodes()
            assertTrue("Message metadata must not be squeezed into a vertical column", metadata.all { it.boundsInRoot.height <= 48 * base.resources.displayMetrics.density })
            compose.waitUntil(10_000) { lastParagraph()?.first == "I like music." }
            assertEquals(height, lastParagraph()!!.second)
            compose.onAllNodesWithContentDescription("Reading options").onLast().performClick()
            compose.onNodeWithText("Swahili").performClick()
            compose.onNodeWithText("Ninapenda muziki.").assertIsDisplayed()
            capture("android-swahili-whole-translation-light")
            compose.onAllNodesWithContentDescription("Reading options").onLast().performClick()
            compose.onNodeWithText("Immersed").performClick()
            compose.waitUntil(10_000) { lastParagraph()?.first == "I like muziki." }
            compose.onAllNodesWithContentDescription("Reading options").onLast().performClick()
            compose.onNodeWithText("Message language").performClick()
            compose.onNodeWithText(if (reversed) "Swahili" else "English").performClick()
            compose.waitUntil(10_000) { lastParagraph()?.first in listOf("I like muziki.", "I like music.") }
            compose.onAllNodesWithContentDescription("Reading options").onLast().performClick()
            compose.onNodeWithText("Copy original message").performClick()
            compose.runOnIdle {
                val clipboard = base.getSystemService(android.content.Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                assertEquals(originals.last(), clipboard.primaryClip?.getItemAt(0)?.text?.toString())
            }
            compose.onNodeWithTag("conversation-options").performClick()
            compose.onNodeWithText("Languages").performClick()
            compose.runOnIdle { assertEquals(1, languageRequests) }
            compose.onNodeWithTag("message-input").performClick().performTextInput("A draft")
            compose.onNodeWithTag("message-input").assertTextContains("A draft")
            compose.runOnIdle { assertEquals("A draft", chat.compose(peer)) }
            compose.waitUntil(5_000) { lastParagraph() != null }
            val held = lastParagraph()!!.first
            capture("android-swahili-composing-light")
            val until = android.os.SystemClock.uptimeMillis()+8_000
            while (android.os.SystemClock.uptimeMillis()<until) {
                assertEquals(held, lastParagraph()?.first); android.os.SystemClock.sleep(100)
            }
            // An emulator keyboard's first-use coachmark is not Vipi UI.
            val device = UiDevice.getInstance(instrumentation)
            device.findObject(By.text("Got it"))?.click()
            compose.runOnIdle { appearance.value = Appearance.DARK }
            compose.waitForIdle(); device.waitForIdle()
            capture("android-swahili-composing-dark")
            runBlocking { withContext(Dispatchers.Main) { assertEquals(originals, chat.messages(peer).sortedBy { it.cursor }.map { it.text }) } }
            File(output, "receipt.json").writeText(JSONObject().put("synthetic_contact_and_transport", true)
                .put("actual_conversation_immersion_path", true).put("continuous_switching", true)
                .put("stable_height", true).put("whole_translation", true).put("composing_paused", true)
                .put("target_language_original", reversed).put("manual_language_selection", true).put("copy_original_verified", true)
                .put("languages_menu_after_preparation", true).put("encrypted_originals_unchanged", true).toString(2))
        } catch (failure: Throwable) {
            capture("android-swahili-failure")
            throw failure
        } finally {
            compose.runOnIdle { visible.value = false }; compose.waitForIdle()
            if (initialized) runBlocking { withContext(Dispatchers.Main) { chat.close() } }
            if (priorClipboard != null) clipboard.setPrimaryClip(priorClipboard) else clipboard.clearPrimaryClip()
            root.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
        }
    }
}
