package co.fallsoft.vipi

import android.content.ContextWrapper
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import java.io.File
import java.security.KeyStore
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

/**
 * Real native views and encrypted storage; synthetic contact and transport. No authentication, live
 * account, or network delivery is claimed.
 */
class ChatBlockingUIDeviceTest {
    @get:Rule val compose = createComposeRule()

    private class Transport(val owner: UUID, val peer: UUID) : ChatTransport {
        var blocked = false
        var fail = false

        override suspend fun request(
            method: String,
            path: String,
            body: JSONObject?,
            device: DeviceCredential?,
            query: Map<String, String>,
        ): JSONObject {
            return when {
                path == "/v1/me" -> ChatProfile(owner, "block_ui_qa", "UI QA").json()
                path == "/v1/devices" ->
                    JSONObject()
                        .put("id", requireNotNull(body).getString("device_id"))
                        .put("active", true)
                path == "/v1/keys" -> JSONObject().put("revision", 1).put("remaining", 20)
                path == "/v1/people/alex" -> ChatProfile(peer, "alex", "Alex").json()
                path == "/v1/messages/pending" ->
                    JSONObject().put("messages", JSONArray()).put("next_cursor", JSONObject.NULL)
                path.startsWith("/v1/blocks/") -> {
                    if (fail) throw ServiceFailure(0, "offline")
                    if (method == "PUT") blocked = requireNotNull(body).getBoolean("blocked")
                    JSONObject().put("blocked", blocked)
                }
                else -> error("Unexpected synthetic transport path: $path")
            }
        }
    }

    @Test
    fun blockCancelOfflineUnblockAndThemes() {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val run = InstrumentationRegistry.getArguments().getString("vipiBlockRun") ?: "001"
        require(run.matches(Regex("[0-9]{3}")))
        val output = File(base.filesDir, "block-ui-$run")
        check(!output.exists())
        output.mkdirs()
        val root = File(base.cacheDir, "block-ui-${UUID.randomUUID()}").apply { mkdirs() }
        val context =
            object : ContextWrapper(base) {
                override fun getFilesDir() = File(root, "files").apply { mkdirs() }

                override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() }
            }
        val account = UUID.randomUUID()
        val peer = UUID.randomUUID()
        val transport = Transport(account, peer)
        val appearance = mutableStateOf(Appearance.LIGHT)
        val visible = mutableStateOf(true)
        lateinit var chat: ChatSession
        var initialized = false
        fun capture(name: String) {
            compose.waitForIdle()
            val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
            // System bars update outside Compose's idling resource.
            device.waitForIdle(1_000)
            // SystemUI icon tint animates on its own clock after window flags change.
            android.os.SystemClock.sleep(350)
            check(device.takeScreenshot(File(output, name + ".png")))
        }
        try {
            runBlocking {
                withContext(Dispatchers.Main) {
                    chat = ChatSession(context, transport, "block-ui-${UUID.randomUUID()}")
                    initialized = true
                    chat.start()
                    check(chat.ready)
                    chat.find("alex")
                    chat.send("Coffee tomorrow?", peer)
                    chat.setBlocked(true, peer)
                    chat.setBlocked(false, peer)
                }
            }
            compose.setContent {
                if (visible.value)
                    VipiTheme(appearance.value) { FriendConversationScreen(chat, peer) {} }
            }
            compose.onNodeWithContentDescription("Conversation options").performClick()
            compose.onNodeWithText("Block").performClick()
            compose.onNodeWithText("Block Alex?").assertIsDisplayed()
            capture("android-block-confirm-light")
            compose.onNodeWithText("Cancel").performClick()
            compose.runOnIdle { assertFalse(transport.blocked) }
            compose.onNodeWithContentDescription("Conversation options").performClick()
            compose.onNodeWithText("Block").performClick()
            compose.onAllNodesWithText("Block").onLast().performClick()
            compose.onNodeWithText("You blocked this person.").assertIsDisplayed()
            compose.onNodeWithContentDescription("Send message").assertDoesNotExist()
            capture("android-blocked-light")
            compose.runOnIdle { appearance.value = Appearance.DARK }
            capture("android-blocked-dark")
            compose.runOnIdle { transport.fail = true }
            compose.onNodeWithText("Unblock").performClick()
            compose.onNodeWithText("Unblock Alex?").assertIsDisplayed()
            compose.onAllNodesWithText("Unblock").onLast().performClick()
            compose
                .onNodeWithText("Couldn’t confirm the change. Check your connection and try again.")
                .assertIsDisplayed()
            compose.onNodeWithText("You blocked this person.").assertIsDisplayed()
            capture("android-unblock-offline-dark")
            compose.runOnIdle { transport.fail = false }
            compose.onNodeWithText("Unblock").performClick()
            compose.onAllNodesWithText("Unblock").onLast().performClick()
            compose.onNodeWithText("Coffee tomorrow?").assertIsDisplayed()
            compose.onNodeWithTag("message-input").assertIsDisplayed().performTextInput("Thanks")
            compose
                .onNodeWithContentDescription("Send message")
                .assertIsEnabled()
                .assertIsDisplayed()
            UiDevice.getInstance(InstrumentationRegistry.getInstrumentation()).pressBack()
            capture("android-unblocked-dark")
            File(output, "receipt.json")
                .writeText(
                    JSONObject()
                        .put("synthetic_contact_and_transport", true)
                        .put("real_native_ui_interactions", true)
                        .put("cancel_preserved_state", true)
                        .put("offline_unblock_remained_blocked", true)
                        .put("old_message_retained", true)
                        .toString()
                )
        } finally {
            compose.runOnIdle { visible.value = false }
            compose.waitForIdle()
            if (initialized) runBlocking { withContext(Dispatchers.Main) { chat.close() } }
            root.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply {
                load(null)
                deleteEntry("co.fallsoft.vipi.messages.$account")
            }
        }
    }
}
