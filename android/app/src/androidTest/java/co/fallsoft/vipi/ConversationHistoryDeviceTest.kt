package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.UUID

@RunWith(AndroidJUnit4::class)
class ConversationHistoryDeviceTest {
    @Test fun oversizedEditableDraftReopensExactlyButCannotBecomeAnOutgoingMessage() {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val root = java.io.File(base.cacheDir, "draft-limit-${UUID.randomUUID()}").apply { check(mkdirs()) }
        val context = object : android.content.ContextWrapper(base) { override fun getNoBackupFilesDir() = root }
        val account = UUID.randomUUID(); val peer = UUID.randomUUID()
        val pasted = "界".repeat(10_923) // 32,769 UTF-8 bytes, not UTF-16 count.
        try {
            MessageVault(context, account).use { vault ->
                val history = ConversationHistory(vault)
                history.saveComposeDraft(pasted, peer)
                assertEquals(pasted, history.composeDraft(peer))
                assertTrue(runCatching { MessageJournal(vault).saveDraft(UUID.randomUUID(), peer, pasted, 1_800_000_000_000L, 1_800_000_000_000L) }.isFailure)
                assertTrue(history.messages(peer).isEmpty())
            }
            MessageVault(context, account).use { vault ->
                val history = ConversationHistory(vault)
                assertEquals(pasted, history.composeDraft(peer))
                val atEditingLimit = "a".repeat(ConversationHistory.MAX_DRAFT_BYTES)
                history.saveComposeDraft(atEditingLimit, peer)
                assertTrue(runCatching { history.saveComposeDraft(atEditingLimit + "a", peer) }.isFailure)
                assertEquals(atEditingLimit, history.composeDraft(peer))
                history.saveComposeDraft("Shortened café ☕", peer)
            }
            MessageVault(context, account).use { vault ->
                assertEquals("Shortened café ☕", ConversationHistory(vault).composeDraft(peer))
            }
        } finally {
            root.deleteRecursively()
            java.security.KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
        }
    }
    @Test fun historyPaginationDraftsUnreadAndReceiptRecovery() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val account = UUID.randomUUID(); val peer = UUID.randomUUID(); val other = UUID.randomUUID(); val now = 1_800_000_000_000L
        MessageVault(context, account).use { vault ->
            val journal = MessageJournal(vault); val history = ConversationHistory(vault)
            history.saveComposeDraft("Unsent café ☕", peer)
            val identifiers = mutableSetOf<UUID>()
            repeat(27) { offset ->
                val id = UUID.randomUUID(); identifiers.add(id)
                journal.saveDraft(id, peer, "History $offset", now + offset / 3, now)
            }
            journal.saveDraft(UUID.randomUUID(), other, "Other conversation", now, now)
            val first = history.messages(peer, limit = 10); assertEquals(10, first.size)
            val fresh = UUID.randomUUID()
            journal.saveDraft(fresh, peer, "Arrived while paging", now + 100, now)
            val second = history.messages(peer, before = first.last().cursor, limit = 10)
            val third = history.messages(peer, before = second.last().cursor, limit = 10)
            assertEquals(identifiers, (first + second + third).map { it.id }.toSet())
            assertEquals(27, first.size + second.size + third.size)
            assertEquals(fresh, history.messages(peer).first().id)
            assertEquals(1, history.messages(other).size)
            assertTrue(runCatching { history.messages(peer, limit = 101) }.isFailure)
            MessageVault(context, account).use { reopened -> assertEquals("Unsent café ☕", ConversationHistory(reopened).composeDraft(peer)) }
            assertTrue(runCatching { journal.queue(fresh, peer, "Arrived while paging", now + 100, now) { error("Interrupted") } }.isFailure)
            assertEquals("queued", history.messages(peer).first().state)
            journal.queue(fresh, peer, "Arrived while paging", now + 100, now) { 2 to ByteArray(64) { 7 } }
            journal.applyStatus(fresh, "delivered")
            assertEquals("delivered", history.messages(peer).first().state)
            assertEquals(28, history.messages(peer).size)
            val id = UUID.randomUUID(); val incoming = ChatEnvelope(id, peer, account, now - 1, 2, ByteArray(64) { 9 })
            val clear = JSONObject().put("version", 1).put("id", id).put("sender", peer).put("recipient", account)
                .put("createdAt", now - 1).put("text", "An older reply").toString().toByteArray(Charsets.UTF_8)
            assertTrue(runCatching { journal.receive(incoming, now) { _, _ -> error("Interrupted") } }.isFailure)
            assertTrue(journal.pendingReceipts().isEmpty())
            journal.receive(incoming, now) { _, _ -> clear }
            journal.receive(incoming, now) { _, _ -> error("Duplicate decryption") }
            assertEquals(fresh, history.threads().first().latest.id)
            assertEquals(1, history.threads().first().unread)
            MessageVault(context, account).use { reopened ->
                val reopenedJournal = MessageJournal(reopened)
                assertEquals(listOf(id), reopenedJournal.pendingReceipts())
                ConversationHistory(reopened).markRead(peer)
                assertEquals(0, history.threads().first().unread)
                reopenedJournal.receiptAccepted(id)
            }
            assertTrue(journal.pendingReceipts().isEmpty())
            journal.receive(incoming, now) { _, _ -> error("Duplicate decryption") }
            assertEquals(0, history.threads().first().unread)
            assertEquals(listOf(id), journal.pendingReceipts())
            vault.transaction {
                for (kind in listOf("history", "thread")) for (key in vault.ids(kind)) vault.remove(kind, key)
                vault.remove("metadata", "history-index")
            }
            val upgraded = ConversationHistory(vault)
            assertEquals(29, upgraded.messages(peer).size)
            assertEquals(0, upgraded.threads().first().unread)
            assertEquals("delivered", upgraded.messages(peer).first().state)
            journal.pendingDrafts(now + MessageJournal.TTL + 100)
            assertEquals(27, upgraded.messages(peer).count { it.state == "expired" })
        }
    }
}
