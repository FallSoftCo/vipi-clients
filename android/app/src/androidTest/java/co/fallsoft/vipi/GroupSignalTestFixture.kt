package co.fallsoft.vipi

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import java.util.UUID

/** Real native vaults, pairwise Signal sessions and exact recipient routing in an isolated test. */
internal object GroupSignalTestFixture {
    class Party(val vault: MessageVault) : AutoCloseable {
        val core = MessagingCore(vault)
        val membership = GroupsMembership(vault)
        val store = GroupsStore(vault)
        val controls = GroupsControlCrypto(vault, core)
        val crypto = GroupsCrypto(vault, core, store)
        override fun close() = vault.close()
    }
    fun person(p: Party, owner: Boolean = false) = GroupMember(p.vault.account, "Local friend", "local_friend", if (owner) GroupRole.OWNER else GroupRole.MEMBER, 1, p.core.device.id)
    fun incoming(fanout: GroupFanout, sender: Party, recipient: Party, kind: String): GroupIncoming {
        val body = JSONObject(fanout.body)
        val envelope = body.getJSONArray("envelopes").objects().single { it.uuid("recipient_id") == recipient.vault.account }
        val wire = JSONObject(envelope.toString()).put("sender_id", sender.vault.account).put("sender_device_id", sender.core.device.id)
            .put("created_at", body.getString("created_at")).put("group_id", fanout.group).put("group_epoch", fanout.epoch)
            .put("group_message_id", fanout.message).put("group_kind", kind)
        return GroupIncoming.parse(wire, recipient.vault.account)
    }
    fun admitted(f: GroupFanout): JSONObject = JSONObject().put("id", f.message).put("group_id", f.group).put("epoch", f.epoch).put("admitted", true)
        .put("deliveries", JSONArray(JSONObject(f.body).getJSONArray("envelopes").objects().map { JSONObject().put("id", it.uuid("id")).put("state", "accepted") }))
    fun establish(a: Party, b: Party, now: Long) {
        val publication = b.core.keys.publication(now, 1)
        b.core.keys.published(publication.getInt("revision"))
        val request = UUID.randomUUID()
        val claim = JSONObject(publication.toString()).put("request_id", request).put("user_id", b.vault.account).put("device_id", b.core.device.id).put("signal_device_id", 1)
            .put("one_time", publication.getJSONArray("one_time").getJSONObject(0))
        a.core.keys.establish(b.vault.account, request, claim)
        val hello = a.core.queue(UUID.randomUUID(), b.vault.account, "An existing direct conversation", now, now)
        assertEquals("An existing direct conversation", b.core.receive(hello, now).text)
        val reply = b.core.queue(UUID.randomUUID(), a.vault.account, "Identity confirmed by direct reply", now, now)
        assertEquals("Identity confirmed by direct reply", a.core.receive(reply, now).text)
    }
}
