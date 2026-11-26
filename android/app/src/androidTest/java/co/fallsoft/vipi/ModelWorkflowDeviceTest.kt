package co.fallsoft.vipi

import android.app.Application
import android.content.Context
import android.content.SharedPreferences
import androidx.lifecycle.ViewModelStore
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.KeyStore
import java.time.Duration
import java.util.UUID

/** Preserved invitation ownership/routing assertions. Controlled transport; commerce is forbidden. */
class ModelWorkflowDeviceTest {
    @Test fun invitationSurvivesSetupAndRelaunchWithoutSendingOrBuying(): Unit = runBlocking(Dispatchers.Main) {
        Fixture().use { f ->
            val model = f.model()
            assertTrue(model.acceptInvitation("https://api.mambovipi.app/invite/Alice_123"))
            assertEquals(Screen.HOME, model.screen)
            assertEquals("alice_123", model.invitationUsername)
            assertFalse(model.acceptInvitation("co.fallsoft.vipi://auth/callback?code=unchanged"))
            f.clearModels()
            val reopened = f.model()
            assertEquals("alice_123", reopened.invitationUsername)
            reopened.activateChats()
            assertEquals(Screen.PROFILE, reopened.screen)
            reopened.chat!!.createProfile("first_user", "First User")
            reopened.navigate(Screen.HOME)
            assertEquals(Screen.NEW_CHAT, reopened.screen)
            assertEquals("alice_123", reopened.invitationUsername)
            assertEquals(0, f.botPosts)
            assertTrue(reopened.chat!!.threads.isEmpty())
            reopened.back()
            assertEquals(Screen.HOME, reopened.screen)
            assertNull(reopened.invitationUsername)
            f.clearModels()
            assertNull(f.model().invitationUsername)
        }
    }

    @Test fun newInvitationOnReadyAccountPrefillsSearchAndInvalidLinkDoesNotReplaceIt(): Unit = runBlocking(Dispatchers.Main) {
        Fixture(profileExists = true).use { f ->
            val model = f.model(); model.activateChats()
            assertTrue(model.acceptInvitation("co.fallsoft.vipi://invite/friend_one"))
            assertEquals(Screen.NEW_CHAT, model.screen)
            assertFalse(model.acceptInvitation("https://evil.example/invite/friend_two"))
            assertEquals("friend_one", model.invitationUsername)
            assertTrue(model.acceptInvitation("https://api.mambovipi.app/invite/friend_two"))
            assertEquals("friend_two", model.invitationUsername)
            assertEquals(0, f.botPosts)
            assertTrue(model.chat!!.threads.isEmpty())
            model.openConversation(UUID.randomUUID())
            assertNull(model.invitationUsername)
        }
    }

    private class Fixture(var profileExists: Boolean = false) : AutoCloseable {
        private val base = InstrumentationRegistry.getInstrumentation().targetContext
        private val prefix = "model-workflow-${UUID.randomUUID()}-"
        private val root = File(base.cacheDir, prefix).apply { check(mkdirs()) }
        private val preferences = mutableSetOf<String>()
        val application = object : Application() {
            init { attachBaseContext(base) }
            override fun getApplicationContext(): Context = this
            override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() }
            override fun getFilesDir() = File(root, "files").apply { mkdirs() }
            override fun getCacheDir() = File(root, "cache").apply { mkdirs() }
            override fun getSharedPreferences(name: String, mode: Int): SharedPreferences {
                preferences += prefix + name
                return base.getSharedPreferences(prefix + name, mode)
            }
        }
        val account = UUID.randomUUID()
        private val subject = "user_workflow_${UUID.randomUUID()}"
        var profileWrites = 0; var registrations = 0; var botPosts = 0
        private var profile = ChatProfile(account, "first_user", "First User")
        private var registered: DeviceCredential? = null
        private val models = mutableListOf<ViewModelStore>()
        init {
            PrivateRecords(application).write("session", IdentityAuthority.FALLSOFT_VIPI_PRODUCTION.tag(JSONObject()
                .put("userID", subject).put("accessToken", "synthetic-access-never-transmitted").put("refreshToken", "synthetic-refresh-never-transmitted")))
        }
        private val api = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject = when (path) {
                "/v1/me" -> if (method == "GET") {
                    if (!profileExists) throw ServiceFailure(404, "profile_required")
                    profile.json()
                } else {
                    assertEquals("PUT", method); profileWrites++; profileExists = true
                    profile = ChatProfile(account, body!!.getString("username"), body.getString("display_name")); profile.json()
                }
                "/v1/devices" -> {
                    assertEquals("POST", method); registrations++
                    registered = DeviceCredential(UUID.fromString(body!!.getString("device_id")), body.getString("secret"))
                    JSONObject().put("id", registered!!.id).put("active", true)
                }
                "/v1/keys" -> { assertEquals("GET", method); assertTrue(device == registered); JSONObject().put("remaining", 20).put("revision", 1) }
                "/v1/messages/pending" -> {
                    assertEquals("GET", method); assertTrue(device == registered)
                    JSONObject().put("messages", JSONArray()).put("next_cursor", JSONObject.NULL)
                }
                "/v1/entitlements", "/v1/bot/allowance", "/v1/bot/messages" -> {
                    botPosts++; error("Free invitation setup cannot request commerce or Bot")
                }
                else -> error("Unexpected endpoint: $method $path")
            }
        }
        private val workflow = object : VipiWorkflowBoundary {
            override fun transport(authentication: Authentication, userID: String): ChatTransport { assertEquals(subject, userID); return api }
            override fun requestPush(context: Context, registration: Boolean) { assertTrue(registration) }
            override fun cancelPush(context: Context) = error("No deletion in workflow")
            override fun foregroundEvents(scope: CoroutineScope, authentication: Authentication, chat: ChatSession): ForegroundInboxEvents = error("No activity event loop in domain workflow")
        }
        fun model(): VipiModel = VipiModel(application, object : LanguageTranslation {
            override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = error("No language download in workflow")
            override suspend fun translate(text: String, source: String, target: String): String = error("No translation in workflow")
            override fun close() = Unit
        }, workflow).also { model -> ViewModelStore().also { it.put("workflow", model); models += it } }
        fun clearModels() { models.forEach { it.clear() }; models.clear() }
        override fun close() {
            clearModels(); root.deleteRecursively(); preferences.forEach(base::deleteSharedPreferences)
            KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
        }
    }
}
