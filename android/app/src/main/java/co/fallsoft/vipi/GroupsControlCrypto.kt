package co.fallsoft.vipi

import org.json.JSONObject
import org.signal.libsignal.protocol.SessionCipher
import org.signal.libsignal.protocol.SignalProtocolAddress
import org.signal.libsignal.protocol.message.PreKeySignalMessage
import org.signal.libsignal.protocol.message.SignalMessage
import java.util.UUID

internal data class GroupPendingControl(val id: UUID, val group: UUID, val sender: UUID, val pinnedIdentity: ByteArray, val transition: GroupRosterTransition) {
    fun json() = JSONObject().put("id", id).put("group", group).put("sender", sender).put("pinned_identity", android.util.Base64.encodeToString(pinnedIdentity, android.util.Base64.NO_WRAP)).put("transition", transition.json())
    companion object { fun parse(o: JSONObject) = GroupPendingControl(o.uuid("id"), o.uuid("group"), o.uuid("sender"), android.util.Base64.decode(o.getString("pinned_identity"), android.util.Base64.NO_WRAP), GroupRosterTransition.parse(o.getJSONObject("transition"))) }
}
/** Control plaintext is never exposed as a message. A pre-existing pinned
 * Signal identity is checked before decryption, then bound to bootstrap consent. */
internal class GroupsControlCrypto(private val vault: MessageVault, private val core: MessagingCore) {
    private val membership = GroupsMembership(vault)
    fun prepare(id: UUID, roster: GroupSnapshot, change: GroupRosterTransition, now: Long): GroupFanout = vault.transaction {
        val key = "${roster.id}/$id"
        vault.get("group-control-outgoing", key)?.let { return@transaction GroupFanout.parse(GroupsStore.json(it)) }
        val previous = requireNotNull(membership.currentInTransaction(roster.id)) { "Authenticated group membership is missing." }
        require(change.actor == vault.account && (previous.matches(roster) || (change.action == GroupControlAction.ADD && roster.members.map { GroupApprovedPerson(it.id, it.role) }.toSet() == change.members.toSet())))
        change.validated(roster.id, previous, vault.account)
        val envelopes = org.json.JSONArray()
        roster.members.filter { it.id != vault.account }.forEach { member ->
            val device = requireNotNull(member.device)
            if (vault.get("peer-device", member.id.toString())?.toString(Charsets.UTF_8) != device.toString() || vault.get("identity", "${member.id}/1") == null || vault.get("identity-change", member.id.toString()) != null || vault.get("blocked", member.id.toString()) != null) throw PeerIdentityChanged(member.id)
            val envelope = UUID.randomUUID()
            val body = change.json().put("version", 2).put("kind", "group-control").put("id", envelope).put("sender", vault.account).put("recipient", member.id).put("sender_device_id", core.device.id).put("createdAt", now).put("group_id", roster.id).put("group_epoch", roster.epoch).put("group_message_id", id)
            val cipher = SessionCipher(core.store, SignalProtocolAddress(vault.account.toString(), 1), SignalProtocolAddress(member.id.toString(), 1)).encrypt(GroupsStore.bytes(body))
            require(cipher.type in setOf(2, 3) && cipher.serialize().size <= 65536)
            envelopes.put(JSONObject().put("id", envelope).put("recipient_id", member.id).put("recipient_device_id", device).put("cipher_type", cipher.type).put("ciphertext", android.util.Base64.encodeToString(cipher.serialize(), android.util.Base64.NO_WRAP)))
        }
        val body = JSONObject().put("id", id).put("epoch", roster.epoch).put("created_at", java.time.Instant.ofEpochMilli(now)).put("envelopes", envelopes).toString()
        val result = GroupFanout(roster.id, id, roster.epoch, body)
        vault.put("group-control-outgoing", key, GroupsStore.bytes(result.json())); vault.put("group-control-outgoing-change", key, GroupsStore.bytes(change.json())); result
    }
    fun accepted(response: JSONObject, fanout: GroupFanout) {
        require(response.uuid("id") == fanout.message && response.uuid("group_id") == fanout.group && response.strictInt("epoch") == fanout.epoch)
        val deliveries = response.getJSONArray("deliveries").objects()
        require(deliveries.map { it.uuid("id") }.toSet() == JSONObject(fanout.body).getJSONArray("envelopes").objects().map { it.uuid("id") }.toSet() && deliveries.all { it.getString("state") in setOf("accepted", "delivered") })
        vault.transaction {
            val key = "${fanout.group}/${fanout.message}"; val bytes = requireNotNull(vault.get("group-control-outgoing-change", key)); val change = GroupRosterTransition.parse(GroupsStore.json(bytes))
            vault.get("group-control-logical", key)?.let { require(GroupRosterTransition.parse(GroupsStore.json(it)) == change) }
                ?: run { membership.applyInTransaction(change, fanout.group, vault.account); vault.put("group-control-logical", key, bytes) }
        }
    }
    fun reconciled(fanout: GroupFanout) = vault.transaction {
        val key = "${fanout.group}/${fanout.message}"; vault.remove("group-control-outgoing", key); vault.remove("group-control-outgoing-change", key)
    }

    private fun drainInTransaction(group: UUID) {
        repeat(100) {
            val current = membership.currentInTransaction(group) ?: return
            var advanced = false
            for (id in vault.ids("group-control-pending").filter { it.startsWith("$group/") }) {
                val bytes = vault.get("group-control-pending", id) ?: continue; val candidate = GroupPendingControl.parse(GroupsStore.json(bytes))
                if (candidate.transition.fromRevision != current.revision || vault.get("identity", "${candidate.sender}/1")?.contentEquals(candidate.pinnedIdentity) != true || vault.get("identity-change", candidate.sender.toString()) != null) continue
                if (runCatching { candidate.transition.validated(group, current, candidate.sender) }.isFailure) { vault.put("group-control-rejected", id, bytes); vault.remove("group-control-pending", id); continue }
                membership.applyInTransaction(candidate.transition, group, candidate.sender); vault.put("group-control-logical", id, GroupsStore.bytes(candidate.transition.json())); vault.remove("group-control-pending", id); advanced = true; break
            }
            if (!advanced) return
        }
    }
    fun pending() = vault.transaction { vault.ids("group-control-pending").map { GroupPendingControl.parse(GroupsStore.json(requireNotNull(vault.get("group-control-pending", it)))) } }
    fun receive(item: GroupIncoming, now: Long) = vault.transaction {
        val route = item.routed; val e = route.envelope
        require(item.kind == "control" && route.recipientDevice == core.device.id && e.sender != vault.account && item.epoch > 0 && e.type in setOf(2, 3) && e.ciphertext.size in 32..65536)
        val pinned = requireNotNull(vault.get("identity", "${e.sender}/1")) { "Review the inviter’s existing encryption identity before opening this group approval." }
        if (vault.get("identity-change", e.sender.toString()) != null) throw PeerIdentityChanged(e.sender)
        require(vault.get("blocked", e.sender.toString()) == null)
        val fingerprint = e.fingerprint() + "control/${item.group}/${item.epoch}/${item.message}/${route.senderDevice}/${route.recipientDevice}".toByteArray(Charsets.UTF_8)
        vault.get("group-control-envelope", e.id.toString())?.let {
            require(it.contentEquals(fingerprint)); vault.put("group-receipt", e.id.toString(), byteArrayOf(1)); return@transaction
        }
        require(e.createdAt >= 0 && e.createdAt <= Math.addExact(now, 300_000) && now < Math.addExact(e.createdAt, MessageJournal.TTL))
        if (vault.get("peer-device", e.sender.toString())?.toString(Charsets.UTF_8) != route.senderDevice.toString() || vault.get("retired-peer-device", "${e.sender}/${route.senderDevice}") != null) throw PeerIdentityChanged(e.sender)
        val cipher = SessionCipher(core.store, SignalProtocolAddress(vault.account.toString(), 1), SignalProtocolAddress(e.sender.toString(), 1))
        val clear = try { if (e.type == 3) cipher.decrypt(PreKeySignalMessage(e.ciphertext)) else cipher.decrypt(SignalMessage(e.ciphertext)) }
            catch (_: org.signal.libsignal.protocol.UntrustedIdentityException) { throw PeerIdentityChanged(e.sender) }
        require(vault.get("identity", "${e.sender}/1")?.contentEquals(pinned) == true)
        val body = GroupsStore.json(clear)
        require(body.strictInt("version") == 2 && body.getString("kind") == "group-control" && body.uuid("id") == e.id && body.uuid("sender") == e.sender && body.uuid("recipient") == vault.account && body.uuid("sender_device_id") == route.senderDevice && body.strictLong("createdAt") == e.createdAt)
        require(body.uuid("group_id") == item.group && body.strictInt("group_epoch") == item.epoch && body.uuid("group_message_id") == item.message)
        val transition = GroupRosterTransition.parse(body); val key = "${item.group}/${item.message}"
        vault.get("group-control-logical", key)?.let { previous -> require(GroupRosterTransition.parse(GroupsStore.json(previous)) == transition) }
            ?: run {
                vault.get("group-control-pending", key)?.let { require(GroupPendingControl.parse(GroupsStore.json(it)).transition == transition) { "Conflicting pending group control" } }
                val current = membership.currentInTransaction(item.group)
                if (current != null && current.revision == transition.fromRevision) {
                    membership.applyInTransaction(transition, item.group, e.sender); vault.put("group-control-logical", key, GroupsStore.bytes(transition.json()))
                } else {
                    vault.put("group-control-pending", key, GroupsStore.bytes(GroupPendingControl(item.message, item.group, e.sender, pinned, transition).json()))
                }
            }
        drainInTransaction(item.group)
        vault.put("group-control-envelope", e.id.toString(), fingerprint); vault.put("group-receipt", e.id.toString(), byteArrayOf(1))
    }
    fun confirmBootstrap(reviewed: GroupPendingControl) = vault.transaction {
        val key = "${reviewed.group}/${reviewed.id}"
        val saved = GroupPendingControl.parse(GroupsStore.json(requireNotNull(vault.get("group-control-pending", key))))
        require(saved.id == reviewed.id && saved.group == reviewed.group && saved.sender == reviewed.sender && saved.transition == reviewed.transition && saved.pinnedIdentity.contentEquals(reviewed.pinnedIdentity))
        if (vault.get("identity", "${saved.sender}/1")?.contentEquals(saved.pinnedIdentity) != true || vault.get("identity-change", saved.sender.toString()) != null) throw PeerIdentityChanged(saved.sender)
        membership.bootstrapInTransaction(saved.transition, saved.group, saved.sender, saved.sender)
        vault.put("group-control-logical", key, GroupsStore.bytes(saved.transition.json())); vault.remove("group-control-pending", key)
        drainInTransaction(saved.group)
    }
}
