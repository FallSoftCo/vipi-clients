package co.fallsoft.vipi

import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import org.json.JSONObject
import java.util.UUID
import java.security.GeneralSecurityException
import org.json.JSONException

/** Account-local index. One encrypted bucket spans 32 UTC days. A day stores its
 * first author until a second distinct author qualifies it, then only a flag.
 * Message text, receipt arrival time, and repeat sends never affect a streak. */
internal object ConversationStreaks {
    const val DAY_MS = 86_400_000L
    private const val QUALIFIED = "+"
    private val sources = listOf("incoming", "outgoing", "imported", "group-message")

    private fun kind(group: Boolean) = if (group) "streak-group" else "streak-direct"
    private fun bucketID(conversation: UUID, day: Long) = "$conversation/${day / 32}"
    private class UnreadableBucket(val kind: String, val id: String, cause: Exception) : Exception(cause)

    private fun bucket(vault: MessageVault, kind: String, id: String): JSONObject? = try {
        vault.get(kind, id)?.let { JSONObject(it.toString(Charsets.UTF_8)) }
    } catch (cause: GeneralSecurityException) {
        throw UnreadableBucket(kind, id, cause)
    } catch (cause: JSONException) {
        throw UnreadableBucket(kind, id, cause)
    } catch (cause: IllegalArgumentException) {
        throw UnreadableBucket(kind, id, cause)
    }

    private fun repair(vault: MessageVault, bad: UnreadableBucket) {
        // The original journal is authoritative. Only an unreadable derived bucket
        // is removed, and migration restarts from its durable sources on next read.
        vault.remove(bad.kind, bad.id)
        vault.put("metadata", "streak-needs-rebuild", byteArrayOf(1))
    }

    private fun record(vault: MessageVault, group: Boolean, conversation: UUID, author: UUID, time: Long) {
        if (time < 0) return
        val day = time / DAY_MS
        val kind = kind(group)
        val id = bucketID(conversation, day)
        val key = (day % 32).toString()
        val days = try { bucket(vault, kind, id) } catch (bad: UnreadableBucket) {
            repair(vault, bad)
            null
        } ?: JSONObject()
        val first = days.optString(key)
        if (first == QUALIFIED || first == author.toString()) return
        days.put(key, if (first.isEmpty()) author.toString() else QUALIFIED)
        vault.put(kind, id, days.toString().toByteArray())
    }

    fun direct(vault: MessageVault, peer: UUID, outgoing: Boolean, time: Long) {
        if (peer != vault.account) record(vault, false, peer, if (outgoing) vault.account else peer, time)
    }

    fun outgoing(vault: MessageVault, chat: StoredChat) {
        if (chat.features.reaction != null) return
        val envelope = chat.envelope
        if (envelope.sender == vault.account && chat.state in setOf("delivered", "read"))
            direct(vault, envelope.recipient, true, envelope.createdAt)
    }

    fun imported(vault: MessageVault, row: JSONObject) {
        // Legacy portable outbound records omit delivery state and include failed sends.
        if (row.getString("direction") == "incoming")
            direct(vault, row.uuid("peer_id"), false, row.getLong("sent_at_ms"))
    }

    fun group(vault: MessageVault, row: GroupMessage) {
        if (row.features.reaction != null) return
        val eligible = if (row.sender == vault.account) row.delivery == GroupDelivery.ACCEPTED
                       else row.delivery == GroupDelivery.RECEIVED
        if (eligible) record(vault, true, row.group, row.sender, row.createdAt)
    }

    /** Resumable keyset pages. Live updates use the very same transaction as the
     * message and can safely interleave with migration, including behind a cursor. */
    suspend fun backfill(vault: MessageVault) {
        vault.transaction {
            if (vault.get("metadata", "streak-needs-rebuild") != null) {
                sources.forEach { vault.remove("metadata", "streak-backfill-$it") }
                vault.remove("metadata", "streak-needs-rebuild")
            }
        }
        for (source in sources) {
            val checkpoint = "streak-backfill-$source"
            do {
                currentCoroutineContext().ensureActive()
                val more = vault.transaction {
                    val before = vault.get("metadata", checkpoint)?.toString(Charsets.UTF_8)
                    if (before == "") return@transaction false
                    val page = vault.pageIDs(source, "", before, 32)
                    for (id in page) {
                        val data = requireNotNull(vault.get(source, id))
                        when (source) {
                            "imported" -> imported(vault, JSONObject(data.toString(Charsets.UTF_8)))
                            "group-message" -> group(vault, GroupMessage.parse(JSONObject(data.toString(Charsets.UTF_8))))
                            "outgoing" -> outgoing(vault, StoredChat.parse(data))
                            "incoming" -> {
                                val chat = StoredChat.parse(data)
                                if (chat.features.reaction != null) continue
                                val e = chat.envelope
                                if (e.recipient == vault.account) direct(vault, e.sender, false, e.createdAt)
                            }
                        }
                    }
                    val cursor = if (page.size == 32) page.last() else ""
                    vault.put("metadata", checkpoint, cursor.toByteArray())
                    cursor.isNotEmpty()
                }
            } while (more)
        }
    }

    suspend fun counts(vault: MessageVault, group: Boolean, ids: List<UUID>, day: Long): Map<UUID, Int> {
        // One bounded repair attempt. An unreadable original row keeps its page
        // checkpoint intact; callers can omit the optional count without hiding chats.
        repeat(2) {
            backfill(vault)
            try {
                val result = vault.transaction {
                    if (vault.get("metadata", "streak-needs-rebuild") != null) null
                    else ids.associateWith { count(vault, group, it, day) }
                }
                if (result != null) return result
            } catch (bad: UnreadableBucket) {
                vault.transaction { repair(vault, bad) }
            }
        }
        return emptyMap()
    }

    /** At most one decryption per 32 streak days, independent of message volume. */
    fun count(vault: MessageVault, group: Boolean, conversation: UUID, today: Long): Int {
        var loaded = -1L
        var days: JSONObject? = null
        fun qualified(day: Long): Boolean {
            if (day < 0) return false
            if (loaded != day / 32) {
                loaded = day / 32
                days = bucket(vault, kind(group), bucketID(conversation, day))
            }
            return days?.optString((day % 32).toString()) == QUALIFIED
        }
        var day = if (qualified(today)) today else today - 1
        var count = 0
        while (qualified(day)) { count++; day-- }
        return count
    }
}
