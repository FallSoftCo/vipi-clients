package co.fallsoft.vipi

import android.app.Application
import android.content.ContextWrapper
import androidx.compose.runtime.MutableState
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.security.KeyStore
import java.util.UUID
import java.util.concurrent.atomic.AtomicInteger

class ProfileCardlessFlowDeviceTest {
    @get:Rule val compose = createComposeRule()

    @Test fun newProfileGoesHomeAndRefreshesAccessWithoutCheckout() {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(base.cacheDir, "profile-${UUID.randomUUID()}").apply { mkdirs() }
        val isolated = object : ContextWrapper(base) { override fun getNoBackupFilesDir() = root }
        val account = UUID.randomUUID()
        val accessChecks = AtomicInteger()
        val chatApi = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject = when (path) {
                "/v1/me" -> if (method == "GET") throw ServiceFailure(404, "profile_required") else ChatProfile(account, "sample_user", "Sample User").json()
                "/v1/devices" -> JSONObject().put("id", requireNotNull(body).getString("device_id")).put("active", true)
                "/v1/keys" -> JSONObject().put("revision", 1).put("remaining", 20)
                "/v1/messages/pending" -> JSONObject().put("messages", JSONArray()).put("next_cursor", JSONObject.NULL)
                else -> error("Unexpected fake chat request: $path")
            }
        }
        val entitlementApi = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject {
                assertEquals("GET", method); assertEquals("/v1/entitlements", path); accessChecks.incrementAndGet()
                throw java.io.IOException("Synthetic unavailable response; no store call")
            }
        }
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        val chat = ChatSession(isolated, chatApi, "profile-${UUID.randomUUID()}")
        val plans = Subscriptions(base, entitlementApi, scope)
        val model = VipiModel(base.applicationContext as Application)
        fun setState(name: String, value: Any?) {
            val field = VipiModel::class.java.getDeclaredField("${name}\$delegate").apply { isAccessible = true }
            @Suppress("UNCHECKED_CAST") (field.get(model) as MutableState<Any?>).value = value
        }
        try {
            runBlocking { withContext(Dispatchers.Main) { chat.start() } }
            assertTrue(chat.needsProfile)
            compose.runOnIdle { setState("chat", chat); setState("subscriptions", plans); model.navigate(Screen.PROFILE) }
            compose.setContent { VipiTheme(Appearance.LIGHT) { ProfileSetupScreen(model) } }
            compose.onNodeWithTag("profile-name").performTextInput("Sample User")
            compose.onNodeWithTag("profile-username").performTextInput("sample_user")
            compose.onNodeWithTag("profile-submit").performClick()
            compose.waitUntil(30_000) { model.screen == Screen.HOME && accessChecks.get() > 0 }
            assertTrue(chat.ready)
            assertEquals(Screen.HOME, model.screen)
        } finally {
            compose.runOnIdle { plans.close(); chat.close(); scope.cancel() }
            root.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply { load(null) }.deleteEntry("co.fallsoft.vipi.messages.$account")
        }
    }
}
