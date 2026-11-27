package co.fallsoft.vipi

import android.content.ContextWrapper
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.util.UUID
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class HumanReportDeviceTest {
    @Test
    fun reportRequiresExactIncomingOriginalAndReusesDurableRequest() = runBlocking {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(base.cacheDir, "report-${UUID.randomUUID()}").apply { mkdirs() }
        val context =
            object : ContextWrapper(base) {
                override fun getNoBackupFilesDir() = root
            }
        val account = UUID.randomUUID()
        val peer = UUID.randomUUID()
        val id = UUID.randomUUID()
        val user = "report-${UUID.randomUUID()}"
        val text = "Selected original message ☕"
        val now = System.currentTimeMillis()
        val calls = mutableListOf<JSONObject>()
        var fail = true
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
                        "/v1/me" -> ChatProfile(account, "report_qa", "Report QA").json()
                        "/v1/devices" ->
                            JSONObject()
                                .put("id", requireNotNull(body).getString("device_id"))
                                .put("active", true)
                        "/v1/keys" -> JSONObject().put("revision", 1).put("remaining", 20)
                        "/v1/messages/pending" ->
                            JSONObject()
                                .put("messages", JSONArray())
                                .put("next_cursor", JSONObject.NULL)
                        "/v1/reports" -> {
                            assertNotNull(device)
                            val request = requireNotNull(body)
                            calls.add(JSONObject(request.toString()))
                            if (fail) throw java.io.IOException("Unconfirmed result")
                            JSONObject()
                                .put("reported", true)
                                .put("report_id", request.getString("report_id"))
                        }
                        else -> error("Unexpected route")
                    }
            }
        val item = ChatItem(id, peer, text, now, false, "delivered", "")
        try {
            MessageVault(context, account).use { vault ->
                vault.transaction {
                    vault.put(
                        "incoming",
                        id.toString(),
                        StoredChat(
                                ChatEnvelope(id, peer, account, now, 2, ByteArray(32)),
                                text,
                                "delivered",
                            )
                            .encode(),
                    )
                    val other = UUID.randomUUID()
                    vault.put(
                        "incoming",
                        other.toString(),
                        StoredChat(
                                ChatEnvelope(other, peer, account, now, 2, ByteArray(32)),
                                "Unselected private text",
                                "delivered",
                            )
                            .encode(),
                    )
                }
            }
            withContext(Dispatchers.Main) {
                ChatSession(context, api, user).use { chat ->
                    chat.start()
                    assertTrue(
                        runCatching { chat.report(item.copy(outgoing = true), "spam") }.isFailure
                    )
                    assertTrue(
                        runCatching { chat.report(item.copy(text = "Changed text"), "spam") }
                            .isFailure
                    )
                    assertTrue(
                        runCatching { chat.report(item.copy(state = "imported"), "spam") }.isFailure
                    )
                    assertTrue(calls.isEmpty())
                    assertTrue(runCatching { chat.report(item, "spam") }.isFailure)
                    assertEquals(1, calls.size)
                }
                ChatSession(context, api, user).use { chat ->
                    chat.start()
                    assertEquals("spam", chat.reportReason(item))
                    assertTrue(runCatching { chat.report(item, "other") }.isFailure)
                    assertEquals(1, calls.size)
                    fail = false
                    chat.report(item, "spam")
                    chat.report(item, "spam")
                }
            }
            assertEquals(2, calls.size)
            assertEquals(calls[0].getString("report_id"), calls[1].getString("report_id"))
            assertEquals(text, calls[1].getString("selected_text"))
            assertEquals(
                setOf(
                    "report_id",
                    "reported_user_id",
                    "message_id",
                    "reason",
                    "selected_text",
                    "consent_version",
                ),
                calls[1].keys().asSequence().toSet(),
            )
            assertFalse(calls[1].toString().contains("Unselected private text"))
        } finally {
            root.deleteRecursively()
            java.security.KeyStore.getInstance("AndroidKeyStore").apply {
                load(null)
                deleteEntry("co.fallsoft.vipi.messages.$account")
            }
        }
    }
}
