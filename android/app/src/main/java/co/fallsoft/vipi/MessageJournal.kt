package co.fallsoft.vipi

import android.util.Base64
import org.json.JSONObject
import java.security.MessageDigest
import java.util.UUID

internal data class ChatEnvelope(val id: UUID, val sender: UUID, val recipient: UUID, val createdAt: Long, val type: Int, val ciphertext: ByteArray) {
    fun json() = JSONObject().put("id", id.toString()).put("sender", sender.toString()).put("recipient", recipient.toString())
        .put("createdAt", createdAt).put("type", type).put("ciphertext", Base64.encodeToString(ciphertext, Base64.NO_WRAP))
    fun fingerprint(): ByteArray = MessageDigest.getInstance("SHA-256").digest("$id\u0000$sender\u0000$recipient\u0000$createdAt\u0000$type\u0000".toByteArray() + ciphertext)
    companion object { fun parse(value: JSONObject) = ChatEnvelope(UUID.fromString(value.getString("id")), UUID.fromString(value.getString("sender")), UUID.fromString(value.getString("recipient")), value.getLong("createdAt"), value.getInt("type"), Base64.decode(value.getString("ciphertext"), Base64.NO_WRAP)) }
}
internal data class StoredChat(val envelope: ChatEnvelope, val text: String, val state: String, val seen: Boolean = false, val attachments: List<AttachmentManifest> = emptyList(), val features: ChatFeatures = ChatFeatures.EMPTY) {
    fun encode() = JSONObject().put("envelope", envelope.json()).put("text", text).put("state", state).put("seen", seen).also { features.write(it); if (attachments.isNotEmpty()) it.put("attachments", MessageAttachments.json(attachments)) }.toString().toByteArray(Charsets.UTF_8)
    companion object { fun parse(bytes: ByteArray): StoredChat { val value = JSONObject(bytes.toString(Charsets.UTF_8)); return StoredChat(ChatEnvelope.parse(value.getJSONObject("envelope")), value.getString("text"), value.getString("state"), value.optBoolean("seen"), MessageAttachments.parse(value), ChatFeatures.parse(value, value.getString("text"))) } }
}

internal data class DraftChat(val id: UUID, val recipient: UUID, val text: String, val createdAt: Long, val state: String = "queued", val attachments: List<AttachmentManifest> = emptyList(), val features: ChatFeatures = ChatFeatures.EMPTY) {
    fun encode() = JSONObject().put("id", id.toString()).put("recipient", recipient.toString()).put("text", text).put("createdAt", createdAt).put("state", state).also { features.write(it); if (attachments.isNotEmpty()) it.put("attachments", MessageAttachments.json(attachments)) }.toString().toByteArray(Charsets.UTF_8)
    companion object { fun parse(data: ByteArray): DraftChat { val v = JSONObject(data.toString(Charsets.UTF_8)); return DraftChat(UUID.fromString(v.getString("id")), UUID.fromString(v.getString("recipient")), v.getString("text"), v.getLong("createdAt"), v.getString("state"), MessageAttachments.parse(v), ChatFeatures.parse(v, v.getString("text"))) } }
}

/** Transport-independent journal: retry returns the exact saved ciphertext; a
 * receipt is permissible only after receive() has returned from its commit. */
internal class MessageJournal(private val vault: MessageVault) {
    fun saveDraft(id: UUID, recipient: UUID, text: String, createdAt: Long, now: Long, consumeCompose: Boolean = false, attachments: List<AttachmentManifest> = emptyList(), consumeVoiceDraft: Boolean = false, features: ChatFeatures = ChatFeatures.EMPTY) = vault.transaction {
        saveDraftInTransaction(id, recipient, text, createdAt, now, consumeCompose, attachments, consumeVoiceDraft, features)
    }
    fun saveDraftInTransaction(id: UUID, recipient: UUID, text: String, createdAt: Long, now: Long, consumeCompose: Boolean = false, attachments: List<AttachmentManifest> = emptyList(), consumeVoiceDraft: Boolean = false, features: ChatFeatures = ChatFeatures.EMPTY) {
        MessageAttachments.validate(attachments)
        require(now >= 0 && createdAt >= 0 && createdAt <= Math.addExact(now, 300_000) && now < Math.addExact(createdAt, TTL))
        require(text.isNotBlank() && text.toByteArray(Charsets.UTF_8).size <= 32768)
        vault.get("outgoing", id.toString())?.let {
            val saved = StoredChat.parse(it)
            require(saved.text == text && saved.features == features && saved.attachments == attachments && saved.envelope.recipient == recipient && saved.envelope.createdAt == createdAt) { "Message ID conflict" }
            return
        }
        val draft = DraftChat(id, recipient, text, createdAt, attachments = attachments, features = features)
        val existing = vault.get("draft", id.toString())
        if (existing != null) require(DraftChat.parse(existing) == draft) { "Message ID conflict" }
        if (consumeVoiceDraft && existing == null) {
            val expected = attachments.single()
            require(expected.kind == AttachmentKind.VOICE)
            val bytes = requireNotNull(vault.get(VoiceDrafts.RECORD, recipient.toString()))
            check(AttachmentManifest.parse(JSONObject(bytes.toString(Charsets.UTF_8))) == expected)
            vault.remove(VoiceDrafts.RECORD, recipient.toString())
        }
        vault.put("draft", id.toString(), draft.encode())
        if (consumeCompose && features != ChatFeatures.EMPTY) vault.remove("action-compose", ConversationRef.Direct(recipient).storageKey)
        if (features.reaction == null) ConversationHistory.record(vault, "draft", id, recipient, createdAt)
        if (consumeCompose && vault.get("compose", recipient.toString())?.contentEquals(text.toByteArray(Charsets.UTF_8)) == true) vault.remove("compose", recipient.toString())
    }
    fun draft(id: UUID): DraftChat? = vault.transaction { vault.get("draft", id.toString())?.let(DraftChat::parse) }
    fun pendingDrafts(now: Long): List<DraftChat> = vault.transaction {
        require(now >= 0)
        vault.ids("draft").mapNotNull { id ->
            val saved = DraftChat.parse(requireNotNull(vault.get("draft", id)))
            if (now >= Math.addExact(saved.createdAt, TTL)) { vault.put("draft", id, saved.copy(state = "expired").encode()); null }
            else if (saved.state == "queued") saved else null
        }
    }
    fun queue(id: UUID, recipient: UUID, text: String, createdAt: Long, now: Long, attachments: List<AttachmentManifest> = emptyList(), features: ChatFeatures = ChatFeatures.EMPTY, encrypt: (ByteArray) -> Pair<Int, ByteArray>): ChatEnvelope {
        // Save the user's text before attempting session establishment/encryption.
        saveDraft(id, recipient, text, createdAt, now, attachments = attachments, features = features)
        return vault.transaction {
        require(now >= 0)
        vault.get("outgoing", id.toString())?.let { saved ->
            val existing = StoredChat.parse(saved)
            require(existing.text == text && existing.features == features && existing.attachments == attachments && existing.envelope.recipient == recipient && existing.envelope.createdAt == createdAt) { "Message ID conflict" }
            check(existing.state in setOf("queued", "accepted") && now < Math.addExact(createdAt, TTL)) { "Message is terminal" }
            return@transaction existing.envelope
        }
        require(text.isNotBlank() && text.toByteArray(Charsets.UTF_8).size <= 32768)
        require(createdAt >= 0 && createdAt <= Math.addExact(now, 300_000) && now < Math.addExact(createdAt, TTL))
        val payload = JSONObject().put("version", 1).put("id", id.toString()).put("sender", vault.account.toString())
            .put("recipient", recipient.toString()).put("createdAt", createdAt).put("text", text).also { if (attachments.isNotEmpty()) it.put("attachments", MessageAttachments.json(attachments))
                if (features.reaction == null) vault.attachOwnAvatar(it, recipient, id)
                features.writeWire(it)
            }.toString().toByteArray(Charsets.UTF_8)
        val (type, ciphertext) = encrypt(payload)
        require(type in setOf(2, 3) && ciphertext.size in 32..65536)
        val envelope = ChatEnvelope(id, vault.account, recipient, createdAt, type, ciphertext)
        vault.put("outgoing", id.toString(), StoredChat(envelope, text, "queued", attachments = attachments, features = features).encode())
        vault.put("pending", id.toString(), byteArrayOf(1))
        vault.remove("draft", id.toString())
        if (features.reaction == null) ConversationHistory.record(vault, "outgoing", id, recipient, createdAt)
        envelope
        }
    }
    fun receive(envelope: ChatEnvelope, now: Long, decrypt: (Int, ByteArray) -> ByteArray): StoredChat = receive(envelope, now, {}, decrypt)
    fun receive(envelope: ChatEnvelope, now: Long, validateRoute: () -> Unit, decrypt: (Int, ByteArray) -> ByteArray): StoredChat = vault.transaction {
        require(now >= 0)
        require(envelope.recipient == vault.account && envelope.type in setOf(2, 3) && envelope.ciphertext.size in 32..65536)
        validateRoute()
        vault.get("incoming", envelope.id.toString())?.let {
            val saved = StoredChat.parse(it)
            require(saved.envelope.fingerprint().contentEquals(envelope.fingerprint())) { "Message ID conflict" }
            vault.put("receipt", envelope.id.toString(), byteArrayOf(1))
            return@transaction saved
        }
        require(envelope.createdAt >= 0 && envelope.createdAt <= Math.addExact(now, 300_000) && now < Math.addExact(envelope.createdAt, TTL))
        val clear = decrypt(envelope.type, envelope.ciphertext)
        require(clear.size <= 65536)
        val payload = JSONObject(clear.toString(Charsets.UTF_8))
        require(payload.getInt("version") == 1 && payload.getString("id") == envelope.id.toString() && payload.getString("sender") == envelope.sender.toString()
            && payload.getString("recipient") == vault.account.toString() && payload.getLong("createdAt") == envelope.createdAt) { "Authenticated message metadata mismatch" }
        val text = payload.getString("text")
        require(text.isNotBlank() && text.toByteArray(Charsets.UTF_8).size <= 32768)
        StoredChat(envelope, text, "delivered", attachments = MessageAttachments.parse(payload), features = ChatFeatures.parse(payload, text)).also {
            payload.optJSONObject("profile_avatar")?.let(ProfileAvatar::parse)?.let { update ->
                if (update.revision > (vault.avatar(envelope.sender)?.revision ?: 0)) vault.storeAvatar(envelope.sender, update)
            }
            vault.put("incoming", envelope.id.toString(), it.encode())
            val ref = ConversationRef.Direct(envelope.sender)
            val reactions = ConversationReactions(vault)
            val change = it.features.reaction
            if (change == null) {
                ConversationStreaks.direct(vault, envelope.sender, false, envelope.createdAt)
                ConversationHistory.record(vault, "incoming", envelope.id, envelope.sender, envelope.createdAt, unread = true)
                reactions.resolve(ref, envelope.id, envelope.sender)
            } else {
                require(it.attachments.isEmpty())
                val device = requireNotNull(vault.get("incoming-route", envelope.id.toString())).toString(Charsets.UTF_8)
                reactions.record(ref, change, envelope.sender, UUID.fromString(device))
            }
            vault.put("receipt", envelope.id.toString(), byteArrayOf(1))
        }
    }
    fun outgoing(id: UUID): StoredChat? = vault.transaction { vault.get("outgoing", id.toString())?.let(StoredChat::parse) }
    fun pendingReceipts(): List<UUID> = vault.transaction { vault.ids("receipt").map(UUID::fromString) }
    fun receiptAccepted(id: UUID) = vault.transaction { vault.remove("receipt", id.toString()) }
    fun pending(now: Long, limit: Int = 100): List<ChatEnvelope> = vault.transaction {
        require(now >= 0 && limit in 1..100)
        buildList {
            for (id in vault.ids("pending")) {
                val item = StoredChat.parse(requireNotNull(vault.get("outgoing", id)))
                if (now >= Math.addExact(item.envelope.createdAt, TTL)) {
                    vault.put("outgoing", id, item.copy(state = "expired").encode()); vault.remove("pending", id)
                } else if (size < limit) add(item.envelope)
            }
        }
    }
    fun setBlocked(blocked: Boolean, peer: UUID) = vault.transaction {
        if (!blocked) { vault.remove("blocked", peer.toString()); return@transaction }
        vault.put("blocked", peer.toString(), byteArrayOf(1))
        for (id in vault.ids("draft")) {
            val draft = vault.get("draft", id)?.let(DraftChat::parse) ?: continue
            if (draft.recipient == peer && draft.state == "queued")
                vault.put("draft", id, draft.copy(state = "cancelled").encode())
        }
        for (id in vault.ids("pending")) {
            val saved = vault.get("outgoing", id)?.let(StoredChat::parse) ?: continue
            if (saved.envelope.recipient == peer) {
                if (saved.state in setOf("queued", "accepted")) vault.put("outgoing", id, saved.copy(state = "cancelled").encode())
                vault.remove("pending", id)
            }
        }
    }
    fun applyStatus(id: UUID, state: String) = vault.transaction {
        require(state in setOf("accepted", "delivered", "read", "failed", "expired"))
        val saved = StoredChat.parse(requireNotNull(vault.get("outgoing", id.toString())))
        // Late/duplicate network responses cannot regress a committed terminal state.
        if (saved.state == "read" || (saved.state == "delivered" && state != "read") ||
            (state !in setOf("delivered", "read") && saved.state in setOf("failed", "expired", "cancelled"))) return@transaction
        if (saved.features.reaction == null && state in setOf("accepted", "delivered", "read") && saved.envelope.sender == vault.account)
            LaunchFeedback.directAccepted(vault, id.toString(), saved.envelope.createdAt)
        vault.avatarStatus(id, state)
        val updated = saved.copy(state = state)
        ConversationStreaks.outgoing(vault, updated)
        vault.put("outgoing", id.toString(), updated.encode())
        if (state in setOf("accepted", "delivered", "read")) {
            val reactions = ConversationReactions(vault)
            val ref = ConversationRef.Direct(saved.envelope.recipient)
            val change = saved.features.reaction
            if (change == null) reactions.resolve(ref, id, vault.account)
            else {
                val actorDevice = vault.get("action-origin-device", id.toString())?.toString(Charsets.UTF_8)
                val current = vault.get("local", "service-device")?.let(GroupsStore::json)?.getString("id")
                if (actorDevice != null && actorDevice == current) reactions.record(ref, change, vault.account, UUID.fromString(actorDevice))
            }
        }
        if (state != "accepted") vault.remove("pending", id.toString())
    }
    companion object { const val TTL = 72 * 60 * 60 * 1000L }
}
