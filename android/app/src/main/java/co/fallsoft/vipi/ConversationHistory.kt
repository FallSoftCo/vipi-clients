package co.fallsoft.vipi

import java.util.Locale
import java.util.UUID
import org.json.JSONObject

internal data class ChatItem(
    val id: UUID,
    val peer: UUID,
    val text: String,
    val createdAt: Long,
    val outgoing: Boolean,
    val state: String,
    val cursor: String,
    val attachments: List<AttachmentManifest> = emptyList(),
    val features: ChatFeatures = ChatFeatures.EMPTY,
)

// Historical wire values inserted by either client when a voice recording had no caption.
private val generatedVoiceTitles =
    setOf(
        "Voice message",
        "Mensaje de voz",
        "Message vocal",
        "Sprachnachricht",
        "Messaggio vocale",
        "Mensagem de voz",
        "音声メッセージ",
        "ボイスメッセージ",
        "음성 메시지",
        "语音消息",
        "語音訊息",
        "رسالة صوتية",
        "Ujumbe wa sauti",
    )
internal val ChatItem.hasVoiceOnlyPlaceholder: Boolean
    get() = attachments.singleOrNull()?.kind == AttachmentKind.VOICE && text in generatedVoiceTitles

internal data class ChatThread(val peer: UUID, val latest: ChatItem, val unread: Int)

/**
 * Keyset-paged opaque message references. All text, input drafts, contacts and unread counts stay
 * encrypted. Journal mutations update this index atomically.
 */
internal class ConversationHistory(private val vault: MessageVault) {
    init {
        vault.transaction {
            val version = vault.get("metadata", "history-index")
            if (version == null) {
                for (kind in listOf("draft", "outgoing", "incoming", "imported")) {
                    for (id in vault.ids(kind)) {
                        val data = requireNotNull(vault.get(kind, id))
                        if (kind == "imported") {
                            val item =
                                HistoryBackupStore.item(
                                    JSONObject(data.toString(Charsets.UTF_8)),
                                    "",
                                )
                            record(vault, kind, item.id, item.peer, item.createdAt)
                        } else if (kind == "draft") {
                            val item = DraftChat.parse(data)
                            if (item.features.reaction != null) continue
                            record(vault, kind, item.id, item.recipient, item.createdAt)
                        } else {
                            val saved = StoredChat.parse(data)
                            if (saved.features.reaction != null) continue
                            val item = saved.envelope
                            record(
                                vault,
                                kind,
                                item.id,
                                if (kind == "incoming") item.sender else item.recipient,
                                item.createdAt,
                            )
                        }
                    }
                }
                vault.put("metadata", "history-index", byteArrayOf(1))
            } else check(version.contentEquals(byteArrayOf(1))) { "Unsupported history index" }
        }
    }

    private fun item(cursor: String): ChatItem {
        val ref = JSONObject(requireNotNull(vault.get("history", cursor)).toString(Charsets.UTF_8))
        val kind = ref.getString("kind")
        val bytes = requireNotNull(vault.get(kind, ref.getString("id")))
        if (kind == "imported")
            return HistoryBackupStore.item(JSONObject(bytes.toString(Charsets.UTF_8)), cursor)
        if (kind == "draft") {
            val value = DraftChat.parse(bytes)
            return ChatItem(
                value.id,
                value.recipient,
                value.text,
                value.createdAt,
                true,
                value.state,
                cursor,
                value.attachments,
                value.features,
            )
        }
        val value = StoredChat.parse(bytes)
        val outgoing = kind == "outgoing"
        return ChatItem(
            value.envelope.id,
            if (outgoing) value.envelope.recipient else value.envelope.sender,
            value.text,
            value.envelope.createdAt,
            outgoing,
            value.state,
            cursor,
            value.attachments,
            value.features,
        )
    }

    fun find(peer: UUID, id: UUID): ChatItem? = vault.transaction {
        val key = id.toString()
        for (kind in listOf("incoming", "outgoing", "imported", "draft")) {
            val bytes = vault.get(kind, key) ?: continue
            val time =
                when (kind) {
                    "imported" -> GroupsStore.json(bytes).getLong("sent_at_ms")
                    "draft" -> DraftChat.parse(bytes).createdAt
                    else -> StoredChat.parse(bytes).envelope.createdAt
                }
            val cursor = "$peer/" + String.format(Locale.ROOT, "%019d", time) + "/$id"
            if (vault.get("history", cursor) != null) return@transaction item(cursor)
        }
        null
    }

    fun messages(peer: UUID, before: String? = null, limit: Int = 50): List<ChatItem> =
        vault.transaction {
            vault.pageIDs("history", "$peer/", before, limit).map(::item)
        }

    fun threads(): List<ChatThread> = vault.transaction {
        vault
            .ids("thread")
            .map { key ->
                val value =
                    JSONObject(requireNotNull(vault.get("thread", key)).toString(Charsets.UTF_8))
                ChatThread(
                    UUID.fromString(key),
                    item(value.getString("latest")),
                    value.getInt("unread"),
                )
            }
            .sortedWith(
                compareByDescending<ChatThread> { it.latest.createdAt }
                    .thenByDescending { it.latest.id.toString() }
            )
    }

    fun markRead(peer: UUID) = vault.transaction {
        vault.get("thread", peer.toString())?.let { data ->
            val value =
                JSONObject(data.toString(Charsets.UTF_8)).put("unread", 0).apply {
                    remove("notificationMessage")
                    remove("notificationConsent")
                }
            vault.put("thread", peer.toString(), value.toString().toByteArray(Charsets.UTF_8))
        }
    }

    fun composeDraft(peer: UUID): String = vault.transaction {
        vault.get("compose", peer.toString())?.toString(Charsets.UTF_8) ?: ""
    }

    fun saveComposeDraft(text: String, peer: UUID) {
        require(text.toByteArray(Charsets.UTF_8).size <= MAX_DRAFT_BYTES)
        vault.transaction {
            vault.put("compose", peer.toString(), text.toByteArray(Charsets.UTF_8))
        }
    }

    fun notificationPosted(deliveries: Map<UUID, String>) = vault.transaction {
        for ((peer, id) in deliveries) vault.put(
            "posted-notification",
            peer.toString(),
            id.toByteArray(),
        )
    }

    companion object {
        // Editable drafts may exceed the 32 KiB send limit. Bound them at
        // 128 KiB (well within the vault’s 2 MiB record limit); never truncate.
        const val MAX_DRAFT_BYTES = 128 * 1024

        fun record(
            vault: MessageVault,
            kind: String,
            id: UUID,
            peer: UUID,
            createdAt: Long,
            unread: Boolean = false,
        ) {
            val index = "$peer/" + String.format(Locale.ROOT, "%019d", createdAt) + "/$id"
            val exists = vault.get("history", index) != null
            val ref = JSONObject().put("kind", kind).put("id", id.toString())
            vault.put("history", index, ref.toString().toByteArray(Charsets.UTF_8))
            val summary =
                vault.get("thread", peer.toString())?.let {
                    JSONObject(it.toString(Charsets.UTF_8))
                } ?: JSONObject().put("peer", peer.toString()).put("latest", index).put("unread", 0)
            if (index > summary.getString("latest")) summary.put("latest", index)
            if (!exists && unread) {
                summary.put("unread", Math.addExact(summary.getInt("unread"), 1))
                if (kind == "incoming") {
                    val consent =
                        vault.get("local", "notification-previews")?.toString(Charsets.UTF_8)
                    summary
                        .put("notificationMessage", id.toString())
                        .put("notificationConsent", consent)
                        .put("notificationDeliveryTracked", true)
                }
            }
            vault.put("thread", peer.toString(), summary.toString().toByteArray(Charsets.UTF_8))
        }
    }
}
