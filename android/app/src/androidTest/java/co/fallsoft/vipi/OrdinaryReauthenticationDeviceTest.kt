package co.fallsoft.vipi

import android.content.ContextWrapper
import android.net.Uri
import androidx.compose.foundation.layout.Column
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.security.KeyStore
import java.util.UUID

class OrdinaryReauthenticationDeviceTest {
    @get:Rule val compose = createComposeRule()
    @Test fun expiredSessionShowsBoundActionAndRejectsAccountSwitchWithoutChangingHistory() {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(base.cacheDir, "reauth-${UUID.randomUUID()}")
        val context = object : ContextWrapper(base) {
            override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() }
            override fun getCacheDir() = File(root, "cache").apply { mkdirs() }
        }
        val subject = "user_reauthentication_fixture"; val account = UUID.randomUUID()
        val records = PrivateRecords(context)
        records.write("session", JSONObject().put("userID", subject).put("accessToken", "synthetic-old-access").put("refreshToken", "synthetic-old-refresh"))
        val auth = Authentication(context); var failure: Exception? = null; var registrations = 0; var requests = 0
        val transport = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject {
                requests++; failure?.let { throw it }
                return when(path) {
                    "/v1/me" -> ChatProfile(account, "reauth_fixture", "Synthetic fixture").json()
                    "/v1/devices" -> { registrations++; JSONObject().put("id", body!!.getString("device_id")).put("active", true) }
                    "/v1/keys" -> JSONObject().put("remaining", 20)
                    "/v1/messages/pending" -> JSONObject().put("messages", JSONArray())
                    else -> error("Unexpected synthetic request")
                }
            }
        }
        lateinit var chat: ChatSession; var initialized = false; var expected: String? = null
        fun main(block: suspend () -> Unit) = runBlocking { withContext(Dispatchers.Main) { block() } }
        try {
            main { chat = ChatSession(context, transport, subject); initialized = true; chat.start() }
            assertTrue(chat.ready); assertEquals(1, registrations)
            val deviceBefore = MessageVault(context, account).use { v -> v.transaction {
                v.put("qualification", "retained-history", "saved conversation".toByteArray())
                requireNotNull(v.get("local", "registered-device"))
            } }
            compose.setContent { VipiTheme(Appearance.LIGHT) { Column {
                if (chat.needsReauthentication && !chat.needsDeviceRecovery) ReauthenticationCard(chat, auth.busy, auth.error) { expected = it }
            } } }
            for (error in listOf(ServiceFailure(401, "sign_in_required"), ServiceFailure(401, "recent_sign_in_required"), Authentication.SignInRequired())) {
                failure = error; main { chat.start() }; compose.waitForIdle()
                assertTrue(chat.needsReauthentication); assertFalse(chat.needsDeviceRecovery); assertTrue(chat.ready); assertNull(chat.eventDevice())
                val beforeRequests = requests; main { chat.synchronize() }; assertEquals(beforeRequests, requests)
                compose.onNodeWithText("Sign in again").assertIsDisplayed().performClick(); assertEquals(subject, expected)
                fun pending() { records.write("pending-sign-in", JSONObject().put("state", "synthetic-state").put("verifier", "synthetic-verifier").put("createdAt", System.currentTimeMillis()).put("expectedUser", expected)) }
                val oldSession = File(context.noBackupFilesDir, "private-records/session").readBytes()
                auth.qualificationExchange = { fields ->
                    assertEquals("synthetic-verifier", fields.getString("code_verifier"))
                    JSONObject().put("user", JSONObject().put("id", "user_other_fixture")).put("access_token", "synthetic-new-access").put("refresh_token", "synthetic-new-refresh")
                }
                pending(); main { auth.complete(Uri.parse("co.fallsoft.vipi://auth/callback?state=synthetic-state&code=synthetic-code")) }
                assertEquals(subject, auth.userID); assertEquals("Sign in to the same account to continue.", auth.error)
                assertArrayEquals(oldSession, File(context.noBackupFilesDir, "private-records/session").readBytes())
                auth.qualificationExchange = { JSONObject().put("user", JSONObject().put("id", subject)).put("access_token", "synthetic-new-access").put("refresh_token", "synthetic-new-refresh") }
                pending(); main { auth.complete(Uri.parse("co.fallsoft.vipi://auth/callback?state=synthetic-state&code=synthetic-code")) }
                assertNull(auth.error); assertEquals(subject, auth.userID)
                failure = null; main { chat.start() }; compose.waitForIdle(); assertFalse(chat.needsReauthentication); assertNotNull(chat.eventDevice())
                compose.onNodeWithText("Sign in again").assertDoesNotExist(); assertEquals(1, registrations)
                MessageVault(context, account).use { v -> v.transaction {
                    assertArrayEquals(deviceBefore, v.get("local", "registered-device"))
                    assertEquals("saved conversation", v.get("qualification", "retained-history")!!.toString(Charsets.UTF_8))
                } }
            }
            failure = ServiceFailure(401, "device_revoked"); main { chat.start() }; compose.waitForIdle()
            assertTrue(chat.needsDeviceRecovery); assertFalse(chat.needsReauthentication); assertFalse(chat.ready)
            compose.onNodeWithText("Sign in again").assertDoesNotExist(); assertEquals(1, registrations)
        } finally {
            if (initialized) main { chat.close() }
            root.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
        }
    }
}
