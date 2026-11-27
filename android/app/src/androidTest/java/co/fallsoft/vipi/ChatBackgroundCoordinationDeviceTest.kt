package co.fallsoft.vipi

import android.content.ContextWrapper
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.security.KeyStore
import java.util.UUID
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ChatBackgroundCoordinationDeviceTest {
    @Test
    fun overlappingForegroundAndBackgroundSyncWaitForDurableCompletion() = runBlocking {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(base.cacheDir, "delivery-${UUID.randomUUID()}").apply { mkdirs() }
        val context =
            object : ContextWrapper(base) {
                override fun getNoBackupFilesDir() = root
            }
        val account = UUID.randomUUID()
        val firstInbox = CompletableDeferred<Unit>()
        val releaseInbox = CompletableDeferred<Unit>()
        var calls = 0
        var failInbox = false
        val api =
            object : ChatTransport {
                override suspend fun request(
                    method: String,
                    path: String,
                    body: JSONObject?,
                    device: DeviceCredential?,
                    query: Map<String, String>,
                ): JSONObject =
                    when (path) {
                        "/v1/me" -> ChatProfile(account, "delivery_qa", "Delivery QA").json()
                        "/v1/devices" ->
                            JSONObject()
                                .put("id", requireNotNull(body).getString("device_id"))
                                .put("active", true)
                        "/v1/keys" -> JSONObject().put("revision", 1).put("remaining", 20)
                        "/v1/messages/pending" -> {
                            calls++
                            if (calls == 1) {
                                firstInbox.complete(Unit)
                                releaseInbox.await()
                            }
                            if (failInbox) throw java.io.IOException("Offline")
                            JSONObject()
                                .put("messages", JSONArray())
                                .put("next_cursor", JSONObject.NULL)
                        }
                        else -> error("Unexpected path")
                    }
            }
        try {
            withContext(Dispatchers.Main) {
                ChatSession(context, api, "delivery-${UUID.randomUUID()}").use { chat ->
                    val foreground = async { chat.start() }
                    withTimeout(3000) { firstInbox.await() }
                    val background = async { chat.synchronize() }
                    yield()
                    assertFalse(background.isCompleted)
                    val backup = File(root, "foreground-picker.vipihistory")
                    val export = async { chat.exportHistory(backup, "correct horse vipi 2026") }
                    yield()
                    assertFalse(export.isCompleted)
                    releaseInbox.complete(Unit)
                    withTimeout(15000) {
                        foreground.await()
                        background.await()
                        export.await()
                    }
                    assertEquals(2, calls)
                    assertFalse(chat.syncing)
                    assertTrue(chat.ready)
                    assertTrue(chat.lastSyncComplete)
                    assertEquals(
                        0,
                        chat.inspectHistory(backup, "correct horse vipi 2026").summary.messages,
                    )
                    failInbox = true
                    chat.synchronize()
                    assertFalse(chat.lastSyncComplete)
                    assertNotNull(chat.notice)
                    failInbox = false
                    chat.synchronize()
                    assertTrue(chat.lastSyncComplete)
                }
            }
        } finally {
            releaseInbox.complete(Unit)
            root.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply {
                load(null)
                deleteEntry("co.fallsoft.vipi.messages.$account")
            }
        }
    }
}
