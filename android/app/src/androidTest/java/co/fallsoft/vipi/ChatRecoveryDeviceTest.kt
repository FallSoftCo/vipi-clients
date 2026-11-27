package co.fallsoft.vipi

import android.content.ContextWrapper
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.security.KeyStore
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ChatRecoveryDeviceTest {
    private class Transport(
        val profile: ChatProfile,
        val stale: UUID,
        val failedPeer: UUID,
        val valid: JSONObject,
        val poison: JSONObject,
    ) : ChatTransport {
        val pages = mutableListOf<String?>()
        val acknowledged = mutableListOf<String>()
        var blocked = false
        var failBlock = false

        override suspend fun request(
            method: String,
            path: String,
            body: JSONObject?,
            device: DeviceCredential?,
            query: Map<String, String>,
        ): JSONObject {
            if (path.startsWith("/v1/blocks/")) {
                if (failBlock) throw ServiceFailure(0, "offline")
                if (method == "PUT") blocked = requireNotNull(body).getBoolean("blocked")
                return JSONObject().put("blocked", blocked)
            }
            return when (path) {
                "/v1/me" -> profile.json()
                "/v1/devices" ->
                    JSONObject()
                        .put("id", requireNotNull(body).getString("device_id"))
                        .put("active", true)
                "/v1/keys" -> JSONObject().put("revision", 1).put("remaining", 20)
                "/v1/messages/pending" -> {
                    pages.add(query["after"])
                    if (query["after"] == null)
                        JSONObject()
                            .put("messages", JSONArray().put(poison))
                            .put("next_cursor", "controlled-next-page")
                    else {
                        assertEquals("controlled-next-page", query["after"])
                        JSONObject()
                            .put("messages", JSONArray().put(valid))
                            .put("next_cursor", JSONObject.NULL)
                    }
                }
                "/v1/messages" -> {
                    if (requireNotNull(body).getString("recipient_id") == failedPeer.toString())
                        throw ServiceFailure(404, "recipient_unavailable")
                    JSONObject().put("state", "accepted")
                }
                else -> {
                    check(path.endsWith("/receipt"))
                    acknowledged.add(path)
                    if (path.contains(stale.toString()))
                        throw ServiceFailure(404, "message_not_found")
                    JSONObject().put("state", "delivered")
                }
            }
        }
    }

    @Test
    fun poisonPageExpiredReceiptAndUnavailablePeerDoNotBlockOtherMessages() = runBlocking {
        withContext(Dispatchers.Main) {
            val base = InstrumentationRegistry.getInstrumentation().targetContext
            val root = File(base.cacheDir, "chat-recovery-${UUID.randomUUID()}").apply { mkdirs() }
            val context =
                object : ContextWrapper(base) {
                    override fun getFilesDir() = File(root, "files").apply { mkdirs() }

                    override fun getNoBackupFilesDir() = File(root, "no-backup").apply { mkdirs() }
                }
            val accounts = List(3) { UUID.randomUUID() }
            val now = System.currentTimeMillis()
            val vaults = mutableListOf<MessageVault>()
            try {
                accounts.forEach { vaults.add(MessageVault(context, it)) }
                val cores = vaults.map { MessagingCore(it) }
                val publications = cores.map { it.keys.publication(now, 2) }
                cores.forEach { it.keys.published(1) }
                fun establish(from: Int, to: Int, key: Int = 0) {
                    val p = publications[to]
                    val request = UUID.randomUUID()
                    cores[from]
                        .keys
                        .establish(
                            accounts[to],
                            request,
                            JSONObject()
                                .put("request_id", request)
                                .put("user_id", accounts[to])
                                .put("device_id", cores[to].device.id)
                                .put("signal_device_id", 1)
                                .put("registration_id", p.getInt("registration_id"))
                                .put("identity_key", p.getString("identity_key"))
                                .put("signed", p.getJSONObject("signed"))
                                .put("one_time", p.getJSONArray("one_time").getJSONObject(key)),
                        )
                }
                establish(1, 0)
                val old =
                    cores[1].queue(
                        UUID.randomUUID(),
                        accounts[0],
                        "Already stored before a long disconnection",
                        now,
                        now,
                    )
                cores[0].receive(old, now)
                val fresh =
                    cores[1].queue(
                        UUID.randomUUID(),
                        accounts[0],
                        "A good message after an unreadable page",
                        now,
                        now,
                    )
                establish(0, 2)
                val first = UUID.fromString("00000000-0000-4000-8000-000000000001")
                val second = UUID.fromString("00000000-0000-4000-8000-000000000002")
                cores[0].queue(first, accounts[1], "This recipient became unavailable", now, now)
                cores[0].queue(second, accounts[2], "This conversation should still send", now, now)
                val valid =
                    fresh
                        .sendJSON()
                        .put("sender_id", accounts[1])
                        .put("sender_device_id", cores[1].device.id)
                val poisonID = UUID.randomUUID()
                val poison = JSONObject(valid.toString()).put("id", poisonID)
                val transport =
                    Transport(
                        ChatProfile(accounts[0], "recovery_qa", "Recovery QA"),
                        old.envelope.id,
                        accounts[1],
                        valid,
                        poison,
                    )
                ChatSession(context, transport, "recovery-qa-${UUID.randomUUID()}").use { chat ->
                    chat.start()
                    assertTrue(chat.ready)
                    assertEquals(listOf(null, "controlled-next-page"), transport.pages)
                    assertTrue(
                        chat.messages(accounts[1]).any {
                            it.text == "A good message after an unreadable page"
                        }
                    )
                    assertEquals("failed", cores[0].journal.outgoing(first)?.state)
                    assertEquals("accepted", cores[0].journal.outgoing(second)?.state)
                    assertTrue(cores[0].journal.pendingReceipts().isEmpty())
                    assertEquals(2, transport.acknowledged.size)
                    assertFalse(transport.acknowledged.any { it.contains(poisonID.toString()) })
                    chat.send("Queued before blocking", accounts[2])
                    val draftID = cores[0].journal.pendingDrafts(now).single().id
                    chat.saveCompose("Keep my unsent writing", accounts[2])
                    chat.setBlocked(true, accounts[2])
                    assertTrue(accounts[2] in chat.blockedPeers)
                    assertTrue(runCatching { chat.send("Must not queue", accounts[2]) }.isFailure)
                    assertEquals("cancelled", cores[0].journal.draft(draftID)?.state)
                    assertEquals("cancelled", cores[0].journal.outgoing(second)?.state)
                    cores[0].journal.applyStatus(second, "accepted")
                    assertEquals("cancelled", cores[0].journal.outgoing(second)?.state)
                    assertEquals("Keep my unsent writing", chat.compose(accounts[2]))
                    ChatSession(context, transport, chat.userID).use { reopened ->
                        assertTrue(accounts[2] in reopened.blockedPeers)
                        transport.failBlock = true
                        assertTrue(
                            runCatching { reopened.setBlocked(false, accounts[2]) }.isFailure
                        )
                        assertTrue(accounts[2] in reopened.blockedPeers)
                        transport.failBlock = false
                        reopened.setBlocked(false, accounts[2])
                        assertFalse(accounts[2] in reopened.blockedPeers)
                    }
                    assertTrue(cores[0].journal.pending(now).isEmpty())
                    assertTrue(cores[0].journal.pendingDrafts(now).isEmpty())
                    chat.refreshBlock(accounts[2])
                    assertFalse(accounts[2] in chat.blockedPeers)
                    chat.send("A new message after unblocking", accounts[2])
                    assertEquals(1, cores[0].journal.pendingDrafts(now).size)
                }
            } finally {
                vaults.forEach { it.close() }
                root.deleteRecursively()
                val keys = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
                accounts.forEach { keys.deleteEntry("co.fallsoft.vipi.messages.$it") }
            }
        }
    }
}
