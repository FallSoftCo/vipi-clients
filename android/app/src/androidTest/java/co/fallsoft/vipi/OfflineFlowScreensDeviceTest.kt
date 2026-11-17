package co.fallsoft.vipi

import android.content.ContextWrapper
import android.content.Intent
import android.os.SystemClock
import androidx.compose.runtime.MutableState
import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.KeyStore
import java.time.Instant
import java.util.UUID

/** Actual screens with a private synthetic account, fake transport and no provider calls. */
class OfflineFlowScreensDeviceTest {
    @Test fun homeInviteComposerRecoveryAndPlanStates() = runBlocking {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val inst = InstrumentationRegistry.getInstrumentation()
        val base = inst.targetContext
        val root = File(base.cacheDir, "offline-flow-${UUID.randomUUID()}").apply { mkdirs() }
        val isolated = object : ContextWrapper(base) { override fun getNoBackupFilesDir() = root }
        val account = UUID.randomUUID(); val peer = UUID.randomUUID(); val requests = mutableListOf<String>()
        val chatApi = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject {
                requests.add("$method $path")
                return when {
                    path == "/v1/me" -> ChatProfile(account, "sample_user", "Sample User").json()
                    path == "/v1/devices" -> JSONObject().put("id", requireNotNull(body).getString("device_id")).put("active", true)
                    path == "/v1/keys" -> JSONObject().put("revision", 1).put("remaining", 20)
                    path == "/v1/messages/pending" -> JSONObject().put("messages", JSONArray()).put("next_cursor", JSONObject.NULL)
                    path == "/v1/people/friend_qa" -> ChatProfile(peer, "friend_qa", "Sample Friend").json()
                    path == "/v1/people/sample_user" -> ChatProfile(account, "sample_user", "Sample User").json()
                    path.startsWith("/v1/blocks/") -> JSONObject().put("blocked", false)
                    else -> error("Unexpected synthetic chat request: $method $path")
                }
            }
        }
        val planApi = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject {
                assertEquals("GET", method); assertEquals("/v1/entitlements", path)
                throw java.io.IOException("Synthetic offline entitlement check")
            }
        }
        val chat = ChatSession(isolated, chatApi, "screen-${UUID.randomUUID()}")
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        val plans = Subscriptions(base, planApi, scope)
        fun setState(instance: Any, name: String, value: Any?) {
            val field = instance.javaClass.getDeclaredField("${name}\$delegate").apply { isAccessible = true }
            @Suppress("UNCHECKED_CAST")
            val state = field.get(instance) as MutableState<Any?>
            state.value = value
        }
        val device = UiDevice.getInstance(inst)
        val suffix = InstrumentationRegistry.getArguments().getString("vipiFlowRun") ?: "light"
        require(suffix.matches(Regex("[a-z0-9-]+")))
        val out = File(base.filesDir, "offline-flow-plan-r08-$suffix").apply { check(!exists()); mkdirs() }
        var scenario: ActivityScenario<MainActivity>? = null
        try {
            withContext(Dispatchers.Main) {
                chat.start(); assertTrue(chat.ready)
                assertEquals(peer, chat.find("  @Friend_qa  ").id)
                val before = requests.size
                for (input in listOf("@@friend_qa", "friend@qa")) {
                    try { chat.find(input); fail("Expected invalid username") }
                    catch (error: ServiceFailure) { assertEquals("invalid_username", error.code) }
                }
                assertEquals(before, requests.size)
                try { chat.find("@sample_user"); fail("Expected own username rejection") }
                catch (error: ServiceFailure) { assertEquals("own_username", error.code) }
            }
            scenario = ActivityScenario.launch(Intent(base, MainActivity::class.java).putExtra("vipi_screen", "home"))
            lateinit var model: VipiModel
            scenario!!.onActivity { activity ->
                model = ViewModelProvider(activity)[VipiModel::class.java]
                assertNull("QA package must remain signed out", model.authentication.userID)
                setState(model, "chat", chat); model.navigate(Screen.HOME)
            }
            assertTrue(device.wait(Until.hasObject(By.text("Start a conversation")), 15_000))
            assertTrue(device.takeScreenshot(File(out, "home-profile.png")))
            scenario!!.onActivity { model.navigate(Screen.NEW_CHAT) }
            assertTrue(device.wait(Until.hasObject(By.text("Invite a friend")), 10_000))
            assertTrue(device.takeScreenshot(File(out, "new-chat-profile.png")))
            device.findObject(By.text("Invite a friend")).click()
            SystemClock.sleep(2_000)
            assertNotEquals("Chooser must be outside the Vipi app", base.packageName, device.currentPackageName)
            device.dumpWindowHierarchy(File(out, "invite-chooser.xml"))
            assertTrue(device.takeScreenshot(File(out, "invite-chooser.png")))
            device.pressBack()
            scenario!!.onActivity {
                chat.send("Hello! こんにちは مرحبا", peer)
                model.openConversation(peer)
            }
            assertTrue(device.wait(Until.hasObject(By.clazz("android.widget.EditText")), 15_000))
            device.findObject(By.clazz("android.widget.EditText")).click()
            SystemClock.sleep(800)
            assertTrue(device.wait(Until.hasObject(By.textContains("Hello!")), 10_000))
            device.dumpWindowHierarchy(File(out, "friend-composer-keyboard.xml"))
            assertTrue(device.takeScreenshot(File(out, "friend-composer-keyboard.png")))
            device.pressBack()
            scenario!!.onActivity { model.navigate(Screen.BACKUP) }
            assertTrue(device.wait(Until.hasObject(By.textContains("backup")), 10_000))
            assertTrue(device.takeScreenshot(File(out, "backup-form.png")))
            device.findObject(By.text("Restore history")).click()
            assertTrue(device.wait(Until.hasObject(By.text("Choose a backup to restore")), 5_000))
            assertFalse(device.hasObject(By.text("Confirm password to save a backup")))
            device.findObject(By.clazz("android.widget.EditText")).text = "synthetic-passphrase"
            SystemClock.sleep(1_000)
            var restore = device.findObject(By.text("Choose a backup to restore"))
            while (restore != null && !restore.isClickable) restore = restore.parent
            assertNotNull("Restore control semantics missing", restore)
            assertTrue(restore!!.isEnabled)
            assertTrue(device.takeScreenshot(File(out, "backup-restore.png")))
            device.click(restore.visibleCenter.x, restore.visibleCenter.y)
            SystemClock.sleep(1_000)
            assertNotEquals("Document picker must open", base.packageName, device.currentPackageName)
            device.pressBack()
            assertTrue(device.wait(Until.hasObject(By.text("Choose a backup to restore")), 5_000))
            scenario!!.onActivity { setState(chat, "needsDeviceRecovery", true); setState(chat, "ready", false); model.navigate(Screen.HOME) }
            assertTrue(device.wait(Until.hasObject(By.textContains("another device")), 10_000))
            SystemClock.sleep(500)
            device.dumpWindowHierarchy(File(out, "device-recovery.xml"))
            assertTrue(device.takeScreenshot(File(out, "device-recovery.png")))
            var node = device.findObject(By.text("Start a conversation"))
            while (node != null && !node.isClickable) node = node.parent
            assertNotNull("Clickable control semantics missing", node)
            assertFalse("New chats require a ready device", node!!.isEnabled)
            device.click(node.visibleCenter.x, node.visibleCenter.y)
            assertTrue(device.hasObject(By.textContains("another device")))
            assertFalse(device.hasObject(By.text("Invite a friend")))
            scenario!!.onActivity {
                setState(chat, "needsDeviceRecovery", false); setState(chat, "ready", true)
                setState(model, "subscriptions", plans)
                setState(model, "screen", Screen.PLANS)
            }
            assertTrue(device.wait(Until.hasObject(By.textContains("couldn’t")), 15_000))
            assertEquals("Unknown status must appear once", 1, device.findObjects(By.textContains("Your plan access couldn’t be checked")).size)
            assertTrue(device.takeScreenshot(File(out, "plan-unknown.png")))
            val end = Instant.now().minusSeconds(3600)
            val expiredTrial = CardlessTrial(end.minusSeconds(30L * 24 * 60 * 60), end, false)
            val expired = SubscriptionAccess(PlanAccess(false, null, null, cardlessTrial = expiredTrial), PlanAccess(false, null, null), false, "a".repeat(64), false, Instant.now(), SystemClock.elapsedRealtime())
            scenario!!.onActivity { setState(plans, "notice", null); setState(plans, "access", expired); setState(plans, "accessCheckState", AccessCheckState.LOADED) }
            SystemClock.sleep(800)
            assertTrue(device.wait(Until.hasObject(By.textContains("Your free Vipi access ended")), 10_000))
            assertFalse(device.hasObject(By.textContains("Your plan access couldn’t be checked")))
            assertTrue(device.takeScreenshot(File(out, "plan-expired-no-store-offer.png")))
            File(out, "receipt.json").writeText(JSONObject().put("synthetic_profile", true).put("fake_transport_only", true).put("share_sent", false).put("message_sent", false).put("store_offer_loaded", false).put("screens", JSONArray(listOf("home-profile", "new-chat-profile", "invite-chooser", "friend-composer-keyboard", "backup-form", "backup-restore", "device-recovery", "plan-unknown", "plan-expired-no-store-offer"))).toString(2))
        } finally {
            scenario?.close()
            withContext(Dispatchers.Main) { plans.close(); chat.close(); scope.cancel() }
            root.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply { load(null) }.deleteEntry("co.fallsoft.vipi.messages.$account")
        }
    }
}
