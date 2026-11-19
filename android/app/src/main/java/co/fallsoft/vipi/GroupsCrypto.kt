package co.fallsoft.vipi

import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import org.signal.libsignal.protocol.SessionCipher
import org.signal.libsignal.protocol.SignalProtocolAddress
import org.signal.libsignal.protocol.message.PreKeySignalMessage
import org.signal.libsignal.protocol.message.SignalMessage
import java.time.Instant
import java.util.UUID

internal data class GroupFanout(val group: UUID, val message: UUID, val epoch: Int, val body: String) {
    fun json() = JSONObject().put("group", group).put("message", message).put("epoch", epoch).put("body", body)
    companion object { fun parse(o: JSONObject) = GroupFanout(o.uuid("group"), o.uuid("message"), o.getInt("epoch"), o.getString("body")) }
}
internal data class GroupIncoming(val routed: RoutedMessage, val group: UUID, val epoch: Int, val message: UUID, val kind: String) {
    companion object { fun parse(o: JSONObject, account: UUID) = GroupIncoming(RoutedMessage.received(o, account), o.uuid("group_id"), o.strictInt("group_epoch"), o.uuid("group_message_id"), o.getString("group_kind")) }
}
/** All pairwise encryption + immutable fanout commit atomically. HTTP retries
 * use saved bytes; no new encryption after an uncertain result. */
internal class GroupsCrypto(private val vault: MessageVault, private val core: MessagingCore, private val storage: GroupsStore) {
    val messagingCore get() = core
    private val membership = GroupsMembership(vault)
    private val local = SignalProtocolAddress(vault.account.toString(), 1)
    fun prepare(message: GroupMessage, roster: GroupSnapshot, now: Long): GroupFanout {
        roster.validate()
        return vault.transaction {
            val key = "${message.group}/${message.id}"
            vault.get("group-fanout", key)?.let { return@transaction GroupFanout.parse(GroupsStore.json(it)).also { saved -> require(saved.group == message.group && saved.message == message.id && saved.epoch == message.epoch) } }
            require(message.group == roster.id && message.epoch == roster.epoch && message.sender == vault.account && roster.role(vault.account) != null)
            require(message.text.isNotBlank() && message.text.toByteArray(Charsets.UTF_8).size <= 32768 && message.createdAt >= 0 && message.createdAt <= Math.addExact(now, 300_000) && now < Math.addExact(message.createdAt, MessageJournal.TTL))
            require(vault.ids("group-control-outgoing").none { it.startsWith("${roster.id}/") }) { "A group change is waiting to be confirmed. Retry it before sending." }
            val approved = requireNotNull(membership.currentInTransaction(roster.id)) { "Authenticated group membership is missing. Ask an existing admin to approve the people." }
            require(approved.matches(roster) && message.membershipRevision == approved.revision) { "The people in this group haven’t been confirmed securely. Ask an existing admin to approve the change before sending." }
            val recipients = roster.members.filter { it.id != vault.account }; require(recipients.isNotEmpty()) { "Invite someone to join before sending." }
            val envelopes = JSONArray()
            recipients.forEach { member ->
                require(vault.get("blocked", member.id.toString()) == null) { "Review the people in this group before sending." }
                val device = requireNotNull(member.device) { "Someone needs to reconnect their device before this message can be sent to everyone." }
                if (vault.get("peer-device", member.id.toString())?.toString(Charsets.UTF_8) != device.toString() || vault.get("identity-change", member.id.toString()) != null) throw PeerIdentityChanged(member.id)
                val id = UUID.randomUUID()
                val payload = JSONObject().put("version", 2).put("kind", "group").put("id", id).put("sender", vault.account).put("recipient", member.id)
                    .put("sender_device_id", core.device.id).put("createdAt", message.createdAt).put("text", message.text)
                    .put("group_id", roster.id).put("group_epoch", roster.epoch).put("group_message_id", message.id).put("group_revision", approved.revision)
                val cipher = SessionCipher(core.store, local, SignalProtocolAddress(member.id.toString(), 1)).encrypt(GroupsStore.bytes(payload))
                require(cipher.type in setOf(2, 3) && cipher.serialize().size <= 65536)
                envelopes.put(JSONObject().put("id", id).put("recipient_id", member.id).put("recipient_device_id", device).put("cipher_type", cipher.type).put("ciphertext", Base64.encodeToString(cipher.serialize(), Base64.NO_WRAP)))
            }
            val body = JSONObject().put("id", message.id).put("epoch", roster.epoch).put("created_at", Instant.ofEpochMilli(message.createdAt)).put("envelopes", envelopes).toString()
            require(body.toByteArray(Charsets.UTF_8).size <= 1_400_000)
            val result = GroupFanout(roster.id, message.id, roster.epoch, body)
            storage.saveMessageInTransaction(message); vault.put("group-fanout", key, GroupsStore.bytes(result.json())); result
        }
    }
    fun pending(group: UUID, message: UUID) = vault.transaction { vault.get("group-fanout", "$group/$message")?.let { GroupFanout.parse(GroupsStore.json(it)) } }
    fun accepted(response: JSONObject, fanout: GroupFanout) {
        require(response.uuid("id") == fanout.message && response.uuid("group_id") == fanout.group && response.getInt("epoch") == fanout.epoch)
        val deliveries = response.getJSONArray("deliveries").objects()
        require(deliveries.map { it.uuid("id") }.toSet() == JSONObject(fanout.body).getJSONArray("envelopes").objects().map { it.uuid("id") }.toSet())
        require(deliveries.all { it.getString("state") in setOf("accepted", "delivered", "expired", "failed") })
        vault.transaction {
            val message = storage.messagesInTransaction(fanout.group).single { it.id == fanout.message }
            storage.saveMessageInTransaction(message.copy(delivery = if (deliveries.all { it.getString("state") in setOf("accepted", "delivered") }) GroupDelivery.ACCEPTED else GroupDelivery.FAILED))
            if (deliveries.all { it.getString("state") in setOf("accepted", "delivered") }) vault.remove("group-fanout", "${fanout.group}/${fanout.message}")
        }
    }
    fun receive(item: GroupIncoming, now: Long): GroupMessage = vault.transaction {
        val route = item.routed; val envelope = route.envelope
        require(item.kind == "message" && route.recipientDevice == core.device.id && envelope.recipient == vault.account && item.epoch > 0 && envelope.sender != vault.account && envelope.type in setOf(2, 3) && envelope.ciphertext.size in 32..65536)
        val fingerprint = envelope.fingerprint() + "${item.group}/${item.epoch}/${item.message}/${route.senderDevice}/${route.recipientDevice}".toByteArray(Charsets.UTF_8)
        vault.get("group-envelope", envelope.id.toString())?.let { saved ->
            require(saved.contentEquals(fingerprint)) { "Group envelope context changed" }
            val message = storage.messagesInTransaction(item.group).single { it.id == item.message && it.sender == envelope.sender }
            vault.put("group-receipt", envelope.id.toString(), byteArrayOf(1)); return@transaction message
        }
        require(envelope.createdAt >= 0 && envelope.createdAt <= Math.addExact(now, 300_000) && now < Math.addExact(envelope.createdAt, MessageJournal.TTL))
        require(vault.get("blocked", envelope.sender.toString()) == null && vault.get("retired-peer-device", "${envelope.sender}/${route.senderDevice}") == null)
        vault.get("peer-device", envelope.sender.toString())?.let { if (it.toString(Charsets.UTF_8) != route.senderDevice.toString()) throw PeerIdentityChanged(envelope.sender) }
        val cipher = SessionCipher(core.store, local, SignalProtocolAddress(envelope.sender.toString(), 1))
        val clear = try { if (envelope.type == 3) cipher.decrypt(PreKeySignalMessage(envelope.ciphertext)) else cipher.decrypt(SignalMessage(envelope.ciphertext)) }
            catch (_: org.signal.libsignal.protocol.UntrustedIdentityException) { throw PeerIdentityChanged(envelope.sender) }
        val payload = GroupsStore.json(clear)
        require(payload.strictInt("version") == 2 && payload.getString("kind") == "group" && payload.uuid("id") == envelope.id && payload.uuid("sender") == envelope.sender && payload.uuid("recipient") == vault.account && payload.uuid("sender_device_id") == route.senderDevice)
        require(payload.uuid("group_id") == item.group && payload.strictInt("group_epoch") == item.epoch && payload.uuid("group_message_id") == item.message && payload.strictLong("createdAt") == envelope.createdAt)
        val text = payload.getString("text"); require(text.isNotBlank() && text.toByteArray(Charsets.UTF_8).size <= 32768)
        val approved = requireNotNull(membership.currentInTransaction(item.group)) { "Authenticated group membership is missing." }
        require(approved.revision == payload.strictInt("group_revision") && approved.contains(envelope.sender) && approved.contains(vault.account)) { "This message doesn’t match the authenticated people in this group." }
        val message = GroupMessage(item.message, item.group, item.epoch, approved.revision, envelope.sender, text, envelope.createdAt, GroupDelivery.RECEIVED)
        storage.saveMessageInTransaction(message)
        vault.put("peer-device", envelope.sender.toString(), route.senderDevice.toString().toByteArray(Charsets.UTF_8))
        vault.put("group-envelope", envelope.id.toString(), fingerprint); vault.put("group-receipt", envelope.id.toString(), byteArrayOf(1)); message
    }
    fun receipts() = vault.transaction { vault.ids("group-receipt").map(UUID::fromString) }
    fun receiptAccepted(id: UUID) = vault.transaction { vault.remove("group-receipt", id.toString()) }
}
