package co.fallsoft.vipi

import android.content.ContextWrapper
import android.os.SystemClock
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.security.KeyStore
import java.util.UUID
import java.util.concurrent.CopyOnWriteArrayList
import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ChatActivityEventsDeviceTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    @Test
    fun readProofSurvivesReconnectAndOnlyAdvancesSeenPeerMessages(): Unit = runBlocking {
        val account = UUID.randomUUID()
        val root = File(context.cacheDir, "activity-receipts-$account").apply { mkdirs() }
        val scoped =
            object : ContextWrapper(context) {
                override fun getNoBackupFilesDir() = root
            }
        val vault = MessageVault(scoped, account)
        val journal = MessageJournal(vault)
        val peer = UUID.randomUUID()
        val other = UUID.randomUUID()
        val incoming = UUID.randomUUID()
        val outgoing = UUID.randomUUID()
        val unseen = UUID.randomUUID()
        fun save(id: UUID, author: UUID, recipient: UUID, kind: String, state: String) {
            val row =
                StoredChat(
                    ChatEnvelope(id, author, recipient, 0, 2, ByteArray(32)),
                    "Native QA",
                    state,
                )
            vault.transaction { vault.put(kind, id.toString(), row.encode()) }
        }
        save(incoming, peer, account, "incoming", "delivered")
        save(unseen, other, account, "incoming", "delivered")
        save(outgoing, account, peer, "outgoing", "delivered")
        val calls = CopyOnWriteArrayList<JSONObject>()
        val online = java.util.concurrent.atomic.AtomicBoolean(false)
        var redraws = 0
        fun owner() =
            ChatActivityEvents(
                vault,
                journal,
                { true },
                { recipient, action, payload ->
                    assertEquals(peer, recipient)
                    assertEquals("receipts", action)
                    calls += payload
                    if (!online.get()) throw java.io.IOException("Disconnected")
                    JSONObject()
                        .put("acknowledged", payload.getJSONArray("seen"))
                        .put("read", payload.getJSONArray("check"))
                },
                { redraws++ },
            )
        var activity = owner()
        try {
            withContext(Dispatchers.Main) {
                activity.visible(peer, listOf(incoming, unseen), listOf(outgoing))
            }
            withTimeout(5_000) { while (calls.isEmpty()) delay(15) }
            assertEquals(incoming.toString(), calls[0].getJSONArray("seen").getString(0))
            assertEquals(1, calls[0].getJSONArray("seen").length())
            assertEquals("delivered", journal.outgoing(outgoing)!!.state)
            withContext(Dispatchers.Main) {
                activity.close()
                activity = owner()
                online.set(true)
                activity.visible(peer, listOf(incoming), listOf(outgoing))
                activity.reconnected()
            }
            withTimeout(6_000) { while (journal.outgoing(outgoing)?.state != "read") delay(15) }
            journal.applyStatus(outgoing, "accepted")
            journal.applyStatus(outgoing, "delivered")
            assertEquals("read", journal.outgoing(outgoing)!!.state)
            assertTrue(vault.transaction { vault.ids("read-pending").isEmpty() })
            assertFalse(
                vault.transaction {
                    StoredChat.parse(vault.get("incoming", unseen.toString())!!).seen
                }
            )
            assertTrue(redraws > 0)
        } finally {
            withContext(Dispatchers.Main) { activity.close() }
            vault.close()
            root.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply {
                load(null)
                deleteEntry("co.fallsoft.vipi.messages.$account")
            }
        }
    }

    @Test
    fun typingIsCoalescedContentlessAndExpiresWithoutAnotherEvent(): Unit = runBlocking {
        val account = UUID.randomUUID()
        val peer = UUID.randomUUID()
        val root = File(context.cacheDir, "activity-typing-$account").apply { mkdirs() }
        val scoped =
            object : ContextWrapper(context) {
                override fun getNoBackupFilesDir() = root
            }
        val vault = MessageVault(scoped, account)
        val calls = CopyOnWriteArrayList<Boolean>()
        val activity =
            ChatActivityEvents(
                vault,
                MessageJournal(vault),
                { true },
                { p, action, payload ->
                    assertEquals(peer, p)
                    assertEquals("typing", action)
                    assertEquals(1, payload.length())
                    calls += payload.getBoolean("active")
                    JSONObject().put("accepted", true)
                },
                {},
            )
        try {
            withContext(Dispatchers.Main) {
                activity.visible(peer, emptyList(), emptyList())
                repeat(30) { activity.composer(peer, true) }
            }
            withTimeout(4_000) { while (calls.size < 2) delay(15) }
            assertEquals(listOf(true, false), calls.toList())
            withContext(Dispatchers.Main) {
                activity.remoteTyping(peer, true)
                assertTrue(activity.isTyping(peer))
            }
            val start = SystemClock.elapsedRealtime()
            withTimeout(8_500) {
                while (withContext(Dispatchers.Main) { activity.isTyping(peer) }) delay(25)
            }
            assertTrue(SystemClock.elapsedRealtime() - start >= 6_800)
        } finally {
            withContext(Dispatchers.Main) { activity.close() }
            vault.close()
            root.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply {
                load(null)
                deleteEntry("co.fallsoft.vipi.messages.$account")
            }
        }
    }
}
