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

class ChatClosureDeviceTest {
    private class Transport(val account: UUID, val peer: UUID) : ChatTransport {
        val started = CompletableDeferred<Unit>()
        val result = CompletableDeferred<JSONObject>()
        var calls = 0

        override suspend fun request(
            method: String,
            path: String,
            body: JSONObject?,
            device: DeviceCredential?,
            query: Map<String, String>,
        ): JSONObject {
            calls++
            return when (path) {
                "/v1/me" -> ChatProfile(account, "close_qa", "Closure QA").json()
                "/v1/devices" ->
                    JSONObject()
                        .put("id", requireNotNull(body).getString("device_id"))
                        .put("active", true)
                "/v1/keys" -> JSONObject().put("revision", 1).put("remaining", 20)
                "/v1/messages/pending" ->
                    JSONObject().put("messages", JSONArray()).put("next_cursor", JSONObject.NULL)
                "/v1/people/alex" -> {
                    started.complete(Unit)
                    result.await()
                }
                else -> error("Unexpected fixture path")
            }
        }
    }

    @Test
    fun closedSessionRejectsLateResponseAndNeverReopensStorage() = runBlocking {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(base.cacheDir, "closure-${UUID.randomUUID()}").apply { mkdirs() }
        val context =
            object : ContextWrapper(base) {
                override fun getFilesDir() = File(root, "files").apply { mkdirs() }

                override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() }
            }
        val account = UUID.randomUUID()
        val peer = UUID.randomUUID()
        val api = Transport(account, peer)
        try {
            withContext(Dispatchers.Main) {
                val chat = ChatSession(context, api, "closure-${UUID.randomUUID()}")
                try {
                    chat.start()
                    assertTrue(chat.ready)
                    val lookup = async { chat.find("alex") }
                    withTimeout(3000) { api.started.await() }
                    chat.close()
                    chat.close()
                    api.result.complete(ChatProfile(peer, "alex", "Alex").json())
                    assertTrue(
                        runCatching { lookup.await() }.exceptionOrNull() is CancellationException
                    )
                    assertFalse(chat.ready)
                    assertNull(chat.profile)
                    assertTrue(chat.contacts.isEmpty())
                    val count = api.calls
                    chat.start()
                    chat.synchronize()
                    assertEquals(count, api.calls)
                    MessageVault(context, account).use { vault ->
                        vault.transaction {
                            assertNull(vault.get("contact", peer.toString()))
                            assertNotNull(vault.get("local", "identity"))
                        }
                    }
                } finally {
                    api.result.cancel()
                    chat.close()
                }
            }
        } finally {
            root.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply {
                load(null)
                deleteEntry("co.fallsoft.vipi.messages.$account")
            }
        }
    }
}
