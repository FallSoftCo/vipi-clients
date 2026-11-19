package co.fallsoft.vipi

import org.json.JSONObject
import java.util.Locale
import java.util.UUID

internal data class ChatItem(val id: UUID, val peer: UUID, val text: String, val createdAt: Long,
    val outgoing: Boolean, val state: String, val cursor: String)
internal data class ChatThread(val peer: UUID, val latest: ChatItem, val unread: Int)

/** Keyset-paged opaque message references. All text, input drafts, contacts and
 * unread counts stay encrypted. Journal mutations update this index atomically. */
internal class ConversationHistory(private val vault: MessageVault) {
    init { vault.transaction {
        val version = vault.get("metadata", "history-index")
        if (version == null) {
            for (kind in listOf("draft", "outgoing", "incoming", "imported")) {
                for (id in vault.ids(kind)) {
                    val data = requireNotNull(vault.get(kind, id))
                    if (kind == "imported") {
                        val item = HistoryBackupStore.item(JSONObject(data.toString(Charsets.UTF_8)), "")
                        record(vault, kind, item.id, item.peer, item.createdAt)
                    } else if (kind == "draft") {
                        val item = DraftChat.parse(data); record(vault, kind, item.id, item.recipient, item.createdAt)
                    } else {
                        val item = StoredChat.parse(data).envelope
                        record(vault, kind, item.id, if (kind == "incoming") item.sender else item.recipient, item.createdAt)
                    }
                }
            }
            vault.put("metadata", "history-index", byteArrayOf(1))
        } else check(version.contentEquals(byteArrayOf(1))) { "Unsupported history index" }
    } }
    private fun item(cursor: String): ChatItem {
        val ref = JSONObject(requireNotNull(vault.get("history", cursor)).toString(Charsets.UTF_8))
        val kind = ref.getString("kind"); val bytes = requireNotNull(vault.get(kind, ref.getString("id")))
        if (kind == "imported") return HistoryBackupStore.item(JSONObject(bytes.toString(Charsets.UTF_8)), cursor)
        if (kind == "draft") {
            val value = DraftChat.parse(bytes)
            return ChatItem(value.id, value.recipient, value.text, value.createdAt, true, value.state, cursor)
        }
        val value = StoredChat.parse(bytes); val outgoing = kind == "outgoing"
        return ChatItem(value.envelope.id, if (outgoing) value.envelope.recipient else value.envelope.sender,
            value.text, value.envelope.createdAt, outgoing, value.state, cursor)
    }
    fun messages(peer: UUID, before: String? = null, limit: Int = 50): List<ChatItem> = vault.transaction {
        vault.pageIDs("history", "$peer/", before, limit).map(::item)
    }
    fun threads(): List<ChatThread> = vault.transaction {
        vault.ids("thread").map { key ->
            val value = JSONObject(requireNotNull(vault.get("thread", key)).toString(Charsets.UTF_8))
            ChatThread(UUID.fromString(key), item(value.getString("latest")), value.getInt("unread"))
        }.sortedWith(compareByDescending<ChatThread> { it.latest.createdAt }.thenByDescending { it.latest.id.toString() })
    }
    fun markRead(peer: UUID) = vault.transaction {
        vault.get("thread", peer.toString())?.let { data ->
            val value = JSONObject(data.toString(Charsets.UTF_8)).put("unread", 0)
            vault.put("thread", peer.toString(), value.toString().toByteArray(Charsets.UTF_8))
        }
    }
    fun composeDraft(peer: UUID): String = vault.transaction { vault.get("compose", peer.toString())?.toString(Charsets.UTF_8) ?: "" }
    fun saveComposeDraft(text: String, peer: UUID) {
        require(text.toByteArray(Charsets.UTF_8).size <= MAX_DRAFT_BYTES)
        vault.transaction { vault.put("compose", peer.toString(), text.toByteArray(Charsets.UTF_8)) }
    }
    companion object {
        // Editable drafts may exceed the 32 KiB send limit. Bound them at
        // 128 KiB (well within the vault’s 2 MiB record limit); never truncate.
        const val MAX_DRAFT_BYTES = 128 * 1024
        fun record(vault: MessageVault, kind: String, id: UUID, peer: UUID, createdAt: Long, unread: Boolean = false) {
            val index = "$peer/" + String.format(Locale.ROOT, "%019d", createdAt) + "/$id"
            val exists = vault.get("history", index) != null
            val ref = JSONObject().put("kind", kind).put("id", id.toString())
            vault.put("history", index, ref.toString().toByteArray(Charsets.UTF_8))
            val summary = vault.get("thread", peer.toString())?.let { JSONObject(it.toString(Charsets.UTF_8)) }
                ?: JSONObject().put("peer", peer.toString()).put("latest", index).put("unread", 0)
            if (index > summary.getString("latest")) summary.put("latest", index)
            if (!exists && unread) summary.put("unread", Math.addExact(summary.getInt("unread"), 1))
            vault.put("thread", peer.toString(), summary.toString().toByteArray(Charsets.UTF_8))
        }
    }
}
