package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.util.UUID
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ConversationStreaksDeviceTest {
    private val context
        get() = InstrumentationRegistry.getInstrumentation().targetContext

    private val today = 20_000L
    private val peer = UUID.randomUUID()
    private val account = UUID.randomUUID()

    private fun outgoing(v: MessageVault, day: Long, state: String): UUID {
        val e =
            ChatEnvelope(
                UUID.randomUUID(),
                account,
                peer,
                day * ConversationStreaks.DAY_MS + 42,
                1,
                byteArrayOf(1),
            )
        v.transaction {
            v.put("outgoing", e.id.toString(), StoredChat(e, "See you soon", state).encode())
        }
        return e.id
    }

    private fun count(v: MessageVault, day: Long = today, group: Boolean = false) = v.transaction {
        ConversationStreaks.count(v, group, peer, day)
    }

    @Test
    fun restoredIncomingPairsWithDeliveredButNotAmbiguousOutboundAndSurvivesReopen() {
        val file = File(context.cacheDir, "streak-${UUID.randomUUID()}.vipihistory")
        val password = "Private streak backup fixture"
        try {
            HistoryBackupCodec.write(file, password, account) { emit ->
                emit(
                    JSONObject()
                        .put("type", "peer")
                        .put("id", peer.toString())
                        .put("username", JSONObject.NULL)
                        .put("display_name", JSONObject.NULL)
                )
                for (day in listOf(today, today - 2, today - 1)) {
                    for (dir in listOf("incoming", "outgoing")) emit(
                        JSONObject()
                            .put("type", "message")
                            .put("id", UUID.randomUUID().toString())
                            .put("peer_id", peer.toString())
                            .put("direction", dir)
                            .put("sent_at_ms", day * ConversationStreaks.DAY_MS)
                            .put("text", "Hi there")
                    )
                }
            }
            MessageVault(context, account).use { vault ->
                val backup = HistoryBackupStore(vault)
                val verified = backup.validate(file, password)
                assertEquals(6, backup.merge(file, password, verified).added)
                assertEquals(6, backup.merge(file, password, verified).unchanged)
                assertEquals(0, count(vault))
                val journal = MessageJournal(vault)
                val expired = outgoing(vault, today, "queued")
                journal.applyStatus(expired, "accepted")
                journal.applyStatus(expired, "expired")
                assertEquals(0, count(vault))
                for (day in listOf(today, today - 2, today - 1)) {
                    val id = outgoing(vault, day, "queued")
                    journal.applyStatus(id, "accepted")
                    journal.applyStatus(id, "delivered")
                    journal.applyStatus(id, "read")
                    journal.applyStatus(id, "read")
                }
                assertEquals(3, count(vault))
                assertEquals(3, count(vault, today + 1))
                assertEquals(0, count(vault, today + 2))
            }
            MessageVault(context, account).use { reopened ->
                runBlocking { ConversationStreaks.backfill(reopened) }
                assertEquals(3, count(reopened))
                // A new local device identity invalidates unfinished transport
                // work while keeping the same account's proven conversations.
                val old = MessagingCore(reopened)
                val time = (today + 1) * ConversationStreaks.DAY_MS
                val pending = UUID.randomUUID()
                old.journal.queue(pending, peer, "Waiting for delivery", time, time) {
                    3 to ByteArray(64) { 4 }
                }
                old.journal.applyStatus(pending, "accepted")
                reopened.transaction { ConversationStreaks.direct(reopened, peer, false, time) }
                val fresh = DeviceRecovery.candidate(reopened, old.device)
                DeviceRecovery.commit(reopened, old.device, fresh)
                assertEquals(fresh, MessagingCore(reopened).device)
                assertEquals("failed", old.journal.outgoing(pending)?.state)
                assertEquals(3, count(reopened, today + 1))
            }
            MessageVault(context, UUID.randomUUID()).use { assertEquals(0, count(it)) }
        } finally {
            file.delete()
        }
    }

    @Test
    fun eligibleMediaMessagesCountOnceEvenAcrossReceiptAndOriginalReplay() {
        MessageVault(context, account).use { vault ->
            val journal = MessageJournal(vault)
            for ((i, kind) in
                listOf(AttachmentKind.PHOTO, AttachmentKind.VIDEO, AttachmentKind.VOICE)
                    .withIndex()) {
                val time = (today - 2 + i) * ConversationStreaks.DAY_MS
                val media =
                    AttachmentManifest(
                        UUID.randomUUID(),
                        kind,
                        ByteArray(32),
                        MediaPart(
                            UUID.randomUUID(),
                            "original",
                            100,
                            128,
                            "ab".repeat(32),
                        ),
                        null,
                        "message",
                        "application/octet-stream",
                    )
                val e = ChatEnvelope(UUID.randomUUID(), peer, account, time, 2, ByteArray(32))
                val payload =
                    JSONObject()
                        .put("version", 1)
                        .put("id", e.id)
                        .put("sender", peer)
                        .put("recipient", account)
                        .put("createdAt", time)
                        .put("text", "Media")
                        .put("attachments", MessageAttachments.json(listOf(media)))
                journal.receive(e, time + 200) { _, _ -> payload.toString().toByteArray() }
                journal.receive(e, time + 250) { _, _ -> error("Duplicate decrypted again") }
                val out = ChatEnvelope(UUID.randomUUID(), account, peer, time, 2, ByteArray(32))
                vault.transaction {
                    vault.put(
                        "outgoing",
                        out.id.toString(),
                        StoredChat(out, "Media", "queued", attachments = listOf(media)).encode(),
                    )
                }
                journal.applyStatus(out.id, "delivered")
                assertEquals(i + 1, count(vault, time / ConversationStreaks.DAY_MS))
            }
        }
    }

    @Test
    fun brokenDerivedBucketRebuildsOnceWithoutChangingTheOriginalRecords() {
        MessageVault(context, account).use { vault ->
            val outgoing = outgoing(vault, today, "delivered")
            val e =
                ChatEnvelope(
                    UUID.randomUUID(),
                    peer,
                    account,
                    today * ConversationStreaks.DAY_MS,
                    2,
                    ByteArray(32),
                )
            val incoming = StoredChat(e, "Hello", "delivered").encode()
            vault.transaction { vault.put("incoming", e.id.toString(), incoming) }
            fun read() = runBlocking {
                ConversationStreaks.counts(vault, false, listOf(peer), today)[peer]
            }
            assertEquals(1, read())
            vault.transaction {
                vault.put("streak-direct", "$peer/${today / 32}", "invalid JSON".toByteArray())
            }
            assertEquals(1, read())
            assertArrayEquals(
                incoming,
                vault.transaction { vault.get("incoming", e.id.toString()) },
            )
            assertEquals("delivered", MessageJournal(vault).outgoing(outgoing)?.state)
        }
    }

    @Test
    fun pagedPreupgradeJournalFutureSkewGroupAuthorsAndNamespaces() {
        MessageVault(context, account).use { vault ->
            val other = UUID.randomUUID()
            val store = GroupsStore(vault)
            fun group(day: Long, sender: UUID, state: GroupDelivery) =
                GroupMessage(
                    UUID.randomUUID(),
                    peer,
                    1,
                    1,
                    sender,
                    "Coffee?",
                    day * ConversationStreaks.DAY_MS,
                    state,
                )
            // Pre-upgrade canonical rows, including multiple history pages and an eligible future
            // day.
            vault.transaction {
                for (i in 0..129) {
                    val day = today - 128 + i
                    for (out in listOf(false, true)) {
                        val e =
                            ChatEnvelope(
                                UUID.randomUUID(),
                                if (out) account else peer,
                                if (out) peer else account,
                                day * ConversationStreaks.DAY_MS,
                                1,
                                byteArrayOf(2),
                            )
                        vault.put(
                            if (out) "outgoing" else "incoming",
                            e.id.toString(),
                            StoredChat(e, "Hello", "delivered").encode(),
                        )
                    }
                }
                val old = group(today - 1, peer, GroupDelivery.RECEIVED)
                vault.put("group-message", "$peer/${old.id}", old.json().toString().toByteArray())
            }
            runBlocking { ConversationStreaks.backfill(vault) }
            assertEquals(129, count(vault))
            assertEquals(130, count(vault, today + 1))
            assertEquals(0, count(vault, group = true))
            store.saveMessage(group(today - 1, peer, GroupDelivery.RECEIVED))
            store.saveMessage(group(today - 1, account, GroupDelivery.EXPIRED))
            val held = group(today - 1, other, GroupDelivery.WITHHELD)
            store.saveMessage(held)
            assertEquals(0, count(vault, group = true))
            store.saveMessage(held.copy(delivery = GroupDelivery.RECEIVED))
            assertEquals(1, count(vault, group = true)) // Neither sender was the viewer.
            store.saveMessage(group(today, peer, GroupDelivery.RECEIVED))
            val queued = group(today, account, GroupDelivery.QUEUED)
            store.saveMessage(queued)
            assertEquals(1, count(vault, group = true))
            store.saveMessage(queued.copy(delivery = GroupDelivery.ACCEPTED))
            assertEquals(2, count(vault, group = true))
            assertEquals(129, count(vault))
        }
    }
}
