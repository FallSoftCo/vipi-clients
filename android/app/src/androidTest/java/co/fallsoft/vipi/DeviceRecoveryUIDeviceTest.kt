package co.fallsoft.vipi

import android.content.ContextWrapper
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import kotlinx.coroutines.*
import org.json.JSONObject
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.signal.libsignal.protocol.IdentityKeyPair
import java.io.File
import java.security.KeyStore
import java.util.UUID

class DeviceRecoveryUIDeviceTest {
    @get:Rule val compose = createComposeRule()
    @Test fun darkLargeTypeRecoveryNamesConsequencesAndNeverAutoVerifies() {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val run = InstrumentationRegistry.getArguments().getString("vipiRecoveryUIRun") ?: "001"
        require(run.matches(Regex("[0-9]{3}")))
        val output = File(base.filesDir, "device-recovery-ui-$run"); check(!output.exists()); output.mkdirs()
        val root = File(base.cacheDir, "recovery-ui-${UUID.randomUUID()}")
        val context = object : ContextWrapper(base) {
            override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() }
            override fun getCacheDir() = File(root, "cache").apply { mkdirs() }
        }
        val account = UUID.randomUUID(); val peer = UUID.randomUUID(); val peerDevice = UUID.randomUUID()
        val claims = mutableListOf<String>(); var takeovers = 0
        val publication = MessageVault(context, peer).use { MessagingCore(it).keys.publication(System.currentTimeMillis(), 1) }
        val transport = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject = when {
                path == "/v1/me" -> ChatProfile(account, "recovery_ui", "UI QA").json()
                path == "/v1/devices" -> {
                    if (body!!.optBoolean("replace_active")) takeovers++
                    JSONObject().put("id", body.getString("device_id")).put("active", true)
                }
                path == "/v1/keys" -> if (method == "GET") JSONObject().put("remaining", if (takeovers == 0) 20 else 0) else JSONObject().put("revision", body!!.getInt("revision"))
                path == "/v1/people/alex" -> ChatProfile(peer, "alex", "Alex").json()
                path == "/v1/messages/pending" -> JSONObject().put("messages", JSONArray())
                path == "/v1/people/$peer/keys" -> {
                    val request = body!!.getString("request_id"); claims += request
                    JSONObject().put("user_id", peer).put("device_id", peerDevice).put("request_id", request).put("signal_device_id", 1)
                        .put("registration_id", publication.getInt("registration_id")).put("identity_key", publication.getString("identity_key"))
                        .put("signed", publication.getJSONObject("signed")).put("one_time", publication.getJSONArray("one_time").getJSONObject(0))
                }
                else -> error("Unexpected controlled path")
            }
        }
        lateinit var chat: ChatSession; var initialized = false; val mode = mutableIntStateOf(0)
        fun capture(name: String) {
            compose.waitForIdle(); UiDevice.getInstance(InstrumentationRegistry.getInstrumentation()).waitForIdle(500)
            check(UiDevice.getInstance(InstrumentationRegistry.getInstrumentation()).takeScreenshot(File(output, "$name.png")))
        }
        try {
            runBlocking { withContext(Dispatchers.Main) {
                chat = ChatSession(context, transport, "user_recovery_ui"); initialized = true; chat.start(); chat.find("alex")
                MessageVault(context, account).use { vault -> vault.transaction {
                    vault.put("identity", "$peer/1", IdentityKeyPair.generate().publicKey.serialize())
                    vault.put("peer-device", peer.toString(), UUID.randomUUID().toString().toByteArray())
                } }
                chat.setIdentityVerified(true, peer, requireNotNull(chat.securityNumber(peer)))
            } }
            compose.setContent { CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density, 1.8f)) {
                VipiTheme(Appearance.DARK) { when (mode.intValue) {
                    0 -> SecurityNumberSheet(chat, peer) { mode.intValue = 1 }
                    1 -> Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                        if (chat.needsDeviceRecovery) DeviceRecoveryCard(chat) {} else Text("This device is connected")
                    }
                    else -> Unit
                } }
            } }
            compose.onNodeWithText("Friend changed their phone?").performScrollTo().performClick()
            compose.waitUntil(5000) { compose.onAllNodesWithText("Use these keys").fetchSemanticsNodes().isNotEmpty() }
            capture("peer-confirm-dark-large")
            compose.onNodeWithText("Continuing uses these keys but does not mark them verified. Compare all 12 groups with your friend in person or over a trusted call before marking them verified.").performScrollTo().assertIsDisplayed()
            capture("peer-confirm-scrolled-dark-large")
            assertEquals(1, claims.size); assertTrue(chat.securityNumber(peer)!!.verified)
            compose.onNodeWithText("Use these keys").performClick()
            compose.waitUntil(5000) { compose.onAllNodesWithText("Not yet compared").fetchSemanticsNodes().isNotEmpty() }
            assertEquals(2, claims.size); assertEquals(1, claims.distinct().size); assertFalse(chat.securityNumber(peer)!!.verified)
            compose.onNodeWithTag("identity-verify").performScrollTo().assertIsDisplayed()
            capture("peer-unverified-dark-large")
            compose.runOnIdle { chat.noteDeviceRevoked(); mode.intValue = 1 }
            compose.onNodeWithText("Use this device").performClick()
            compose.onNodeWithText("Use Vipi on this device?").assertIsDisplayed(); capture("own-confirm-dark-large")
            compose.onNodeWithText("Cancel").performClick(); assertEquals(0, takeovers)
            compose.onNodeWithText("Use this device").performClick()
            compose.onAllNodesWithText("Use this device").onLast().performClick()
            compose.waitUntil(5000) { chat.ready }
            assertEquals(1, takeovers); compose.onNodeWithText("This device is connected").assertIsDisplayed()
            capture("own-connected-dark-large")
            File(output, "receipt.json").writeText(JSONObject().put("synthetic_account_and_transport", true).put("native_ui", true)
                .put("font_scale", 1.8).put("appearance", "dark").put("same_claim_revalidated", true)
                .put("peer_remains_unverified", true).put("cancel_did_not_take_over", true).put("explicit_takeover_calls", takeovers).toString(2))
        } finally {
            compose.runOnIdle { mode.intValue = 2 }; compose.waitForIdle()
            if (initialized) runBlocking { withContext(Dispatchers.Main) { chat.close() } }
            root.deleteRecursively()
            for (id in listOf(account, peer)) KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$id") }
        }
    }
}
