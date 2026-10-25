package co.fallsoft.vipi

import android.content.ContextWrapper
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.Density
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
import org.signal.libsignal.protocol.IdentityKeyPair
import java.io.File
import java.security.KeyStore
import java.util.UUID

class SecurityNumberUIDeviceTest {
    @get:Rule val compose = createComposeRule()
    private class Transport(val owner: UUID, val peer: UUID) : ChatTransport {
        override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject = when {
            path == "/v1/me" -> ChatProfile(owner, "security_ui_qa", "UI QA").json()
            path == "/v1/devices" -> JSONObject().put("id", requireNotNull(body).getString("device_id")).put("active", true)
            path == "/v1/keys" -> JSONObject().put("revision", 1).put("remaining", 20)
            path == "/v1/people/alex" -> ChatProfile(peer, "alex", "Alex").json()
            path == "/v1/messages/pending" -> JSONObject().put("messages", JSONArray()).put("next_cursor", JSONObject.NULL)
            path.startsWith("/v1/blocks/") -> JSONObject().put("blocked", false)
            else -> error("Unexpected synthetic transport path: $path")
        }
    }
    @Test fun comparePersistClearAndRejectStaleNumbers() {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val run = InstrumentationRegistry.getArguments().getString("vipiSecurityRun") ?: "001"
        require(run.matches(Regex("[0-9]{3}")))
        val output = File(base.filesDir, "security-ui-$run"); check(!output.exists()); output.mkdirs()
        val root = File(base.cacheDir, "security-ui-${UUID.randomUUID()}").apply { mkdirs() }
        val context = object : ContextWrapper(base) {
            override fun getFilesDir() = File(root, "files").apply { mkdirs() }
            override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() }
        }
        val account = UUID.randomUUID(); val peer = UUID.randomUUID()
        val appearance = mutableStateOf(Appearance.LIGHT); val visible = mutableStateOf(true)
        val fontScale = mutableStateOf(1f)
        lateinit var chat: ChatSession
        var initialized = false
        fun capture(name: String) {
            compose.waitForIdle()
            val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
            device.waitForIdle(1_000); android.os.SystemClock.sleep(350)
            check(device.takeScreenshot(File(output, "$name.png")))
        }
        fun open() {
            compose.onNodeWithContentDescription("Conversation options").performClick()
            compose.onNodeWithText("Verify encryption").performClick()
        }
        fun replaceSyntheticPeerKey() {
            MessageVault(context, account).use { vault -> vault.transaction {
                vault.put("identity", "$peer/1", IdentityKeyPair.generate().publicKey.serialize())
            } }
        }
        try {
            runBlocking { withContext(Dispatchers.Main) {
                chat = ChatSession(context, Transport(account, peer), "security-ui-${UUID.randomUUID()}")
                initialized = true; chat.start(); check(chat.ready); chat.find("alex")
            } }
            compose.setContent { if (visible.value) {
                CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density, fontScale.value)) {
                    VipiTheme(appearance.value) { FriendConversationScreen(chat, peer) {} }
                }
            } }
            open(); compose.onNodeWithTag("identity-not-established").assertIsDisplayed()
            capture("android-security-not-established-light")
            compose.onNodeWithText("Done").performClick()
            compose.runOnIdle { replaceSyntheticPeerKey() }
            open(); compose.onNodeWithTag("security-number").assertIsDisplayed()
            compose.runOnIdle { assertFalse(requireNotNull(chat.securityNumber(peer)).verified) }
            capture("android-security-unverified-light")
            compose.onNodeWithTag("identity-verify").performScrollTo().performClick()
            compose.onNodeWithTag("identity-verified").assertIsDisplayed()
            compose.onNodeWithText("Done").performScrollTo().performClick()
            open(); compose.onNodeWithTag("identity-verified").assertIsDisplayed()
            compose.runOnIdle { appearance.value = Appearance.DARK }
            capture("android-security-verified-dark")
            compose.onNodeWithTag("identity-clear").performScrollTo().performClick()
            compose.onNodeWithTag("identity-verify").assertIsDisplayed()
            compose.runOnIdle { replaceSyntheticPeerKey() }
            compose.onNodeWithTag("identity-verify").performClick()
            compose.onNodeWithText("The keys may have changed, or your choice couldn’t be saved. Compare the current numbers again.").performScrollTo().assertIsDisplayed()
            compose.runOnIdle { assertFalse(requireNotNull(chat.securityNumber(peer)).verified) }
            capture("android-security-changed-dark")
            compose.onNodeWithText("Done").performScrollTo().performClick()
            compose.runOnIdle { appearance.value = Appearance.LIGHT; fontScale.value = 1.8f }
            open(); compose.onNodeWithTag("security-number").performScrollTo().assertIsDisplayed()
            capture("android-security-large-type")
            compose.onNodeWithTag("identity-verify").performScrollTo().assertIsDisplayed()
            File(output, "receipt.json").writeText(JSONObject().put("synthetic_contact_and_transport", true)
                .put("real_native_ui_interactions", true).put("verification_reopened", true)
                .put("stale_number_rejected", true).put("font_scale", 1.8).toString())
        } finally {
            compose.runOnIdle { visible.value = false }; compose.waitForIdle()
            if (initialized) runBlocking { withContext(Dispatchers.Main) { chat.close() } }
            root.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
        }
    }
}
