package co.fallsoft.vipi

import java.io.File
import java.util.UUID
import org.json.JSONObject

/** All imported rows live outside the transport journal and confer no peer trust. */
internal class HistoryBackupStore(private val vault: MessageVault) {
    data class Imported(val added: Int, val unchanged: Int)

    private fun portable(kind: String, bytes: ByteArray): JSONObject? {
        if (kind == "imported") return JSONObject(bytes.toString(Charsets.UTF_8))
        val saved = StoredChat.parse(bytes)
        if (saved.features.reaction != null) return null
        if (
            kind == "outgoing" &&
                saved.state !in setOf("delivered", "failed", "expired", "cancelled")
        )
            return null
        if (kind == "incoming" && saved.state != "delivered") return null
        val envelope = saved.envelope
        return JSONObject()
            .put("type", "message")
            .put("id", envelope.id.toString())
            .put(
                "peer_id",
                (if (kind == "outgoing") envelope.recipient else envelope.sender).toString(),
            )
            .put("direction", if (kind == "outgoing") "outgoing" else "incoming")
            .put("sent_at_ms", envelope.createdAt)
            .put("text", saved.text)
    }

    fun export(file: File, password: String, check: () -> Unit = {}): HistoryBackupCodec.Summary =
        HistoryBackupCodec.write(file, password, vault.account, check) { emit ->
            vault.transaction {
                val peers = linkedSetOf<UUID>()
                val ids = mutableSetOf<String>()
                val kinds = listOf("incoming", "outgoing", "imported")
                for (kind in kinds) for (id in vault.ids(kind)) {
                    check()
                    val row = portable(kind, requireNotNull(vault.get(kind, id))) ?: continue
                    require(ids.add(row.getString("id"))) { "Conflicting history IDs" }
                    peers.add(UUID.fromString(row.getString("peer_id")))
                    require(ids.size + peers.size + 2 <= 200_000)
                }
                for (peer in peers) {
                    val contact =
                        vault.get("contact", peer.toString())?.let {
                            JSONObject(it.toString(Charsets.UTF_8))
                        }
                            ?: vault.get("imported-peer", peer.toString())?.let {
                                JSONObject(it.toString(Charsets.UTF_8))
                            }
                    emit(
                        JSONObject()
                            .put("type", "peer")
                            .put("id", peer.toString())
                            .put("username", contact?.opt("username") ?: JSONObject.NULL)
                            .put("display_name", contact?.opt("display_name") ?: JSONObject.NULL)
                    )
                }
                for (kind in kinds) for (id in vault.ids(kind)) {
                    check()
                    portable(kind, requireNotNull(vault.get(kind, id)))?.let(emit)
                }
            }
        }

    fun validate(file: File, password: String, check: () -> Unit = {}) =
        HistoryBackupCodec.inspect(file, password, vault.account, check)

    fun merge(
        file: File,
        password: String,
        confirmed: HistoryBackupCodec.Inspection,
        check: () -> Unit = {},
    ): Imported = vault.transaction {
        var added = 0
        var unchanged = 0
        // Reauthenticate the same owned encrypted staging file inside the atomic transaction.
        val actual =
            HistoryBackupCodec.inspect(file, password, vault.account, check) { row ->
                when (row.getString("type")) {
                    "peer" -> {
                        val id = row.getString("id")
                        if (
                            vault.get("contact", id) == null &&
                                vault.get("imported-peer", id) == null
                        )
                            vault.put(
                                "imported-peer",
                                id,
                                row.toString().toByteArray(Charsets.UTF_8),
                            )
                    }
                    "message" -> {
                        val id = row.getString("id")
                        val existing =
                            listOf("incoming", "outgoing", "imported").mapNotNull { kind ->
                                vault.get(kind, id)?.let { bytes ->
                                    if (kind == "imported")
                                        JSONObject(bytes.toString(Charsets.UTF_8))
                                    else
                                        StoredChat.parse(bytes).let { saved ->
                                            JSONObject()
                                                .put(
                                                    "peer_id",
                                                    (if (kind == "outgoing")
                                                            saved.envelope.recipient
                                                        else saved.envelope.sender)
                                                        .toString(),
                                                )
                                                .put(
                                                    "direction",
                                                    if (kind == "outgoing") "outgoing"
                                                    else "incoming",
                                                )
                                                .put("sent_at_ms", saved.envelope.createdAt)
                                                .put("text", saved.text)
                                        }
                                }
                            }
                        require(vault.get("draft", id) == null) { "Conflicting history ID" }
                        require(existing.size <= 1)
                        if (existing.isNotEmpty()) {
                            val previous = existing.single()
                            require(
                                listOf("peer_id", "direction", "text").all {
                                    previous.getString(it) == row.getString(it)
                                } && previous.getLong("sent_at_ms") == row.getLong("sent_at_ms")
                            ) {
                                "Conflicting history ID"
                            }
                            unchanged++
                        } else {
                            vault.put("imported", id, row.toString().toByteArray(Charsets.UTF_8))
                            ConversationHistory.record(
                                vault,
                                "imported",
                                UUID.fromString(id),
                                UUID.fromString(row.getString("peer_id")),
                                row.getLong("sent_at_ms"),
                            )
                            added++
                        }
                        ConversationStreaks.imported(vault, row)
                    }
                }
            }
        require(actual == confirmed) { "Backup changed after confirmation" }
        Imported(added, unchanged)
    }

    companion object {
        fun item(row: JSONObject, cursor: String) =
            ChatItem(
                UUID.fromString(row.getString("id")),
                UUID.fromString(row.getString("peer_id")),
                row.getString("text"),
                row.getLong("sent_at_ms"),
                row.getString("direction") == "outgoing",
                "imported",
                cursor,
            )
    }
}
