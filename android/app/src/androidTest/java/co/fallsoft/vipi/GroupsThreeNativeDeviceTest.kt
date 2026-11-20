package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.security.KeyStore
import java.util.UUID

/** Native crypto/storage qualification only. The HTTP/three-platform stages
 * have their own opt-in harness; this test makes no relay or UI claim. */
@RunWith(AndroidJUnit4::class)
class GroupsThreeNativeDeviceTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private class Party(val vault: MessageVault) : AutoCloseable {
        val core = MessagingCore(vault)
        val membership = GroupsMembership(vault)
        val store = GroupsStore(vault)
        val controls = GroupsControlCrypto(vault, core)
        val crypto = GroupsCrypto(vault, core, store)
        override fun close() = vault.close()
    }
    private fun person(p: Party, owner: Boolean = false) = GroupMember(p.vault.account, "Local friend", "local_friend", if (owner) GroupRole.OWNER else GroupRole.MEMBER, 1, p.core.device.id)
    private fun incoming(fanout: GroupFanout, sender: Party, recipient: Party, kind: String): GroupIncoming {
        val body = JSONObject(fanout.body)
        val envelope = body.getJSONArray("envelopes").objects().single { it.uuid("recipient_id") == recipient.vault.account }
        val wire = JSONObject(envelope.toString()).put("sender_id", sender.vault.account).put("sender_device_id", sender.core.device.id)
            .put("created_at", body.getString("created_at")).put("group_id", fanout.group).put("group_epoch", fanout.epoch)
            .put("group_message_id", fanout.message).put("group_kind", kind)
        return GroupIncoming.parse(wire, recipient.vault.account)
    }
    private fun admitted(f: GroupFanout): JSONObject = JSONObject().put("id", f.message).put("group_id", f.group).put("epoch", f.epoch).put("admitted", true)
        .put("deliveries", JSONArray(JSONObject(f.body).getJSONArray("envelopes").objects().map { JSONObject().put("id", it.uuid("id")).put("state", "accepted") }))
    private fun establish(a: Party, b: Party, now: Long) {
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
    @Test fun threeNativeMembersBootstrapOfflineReopenAndRemovalFence() {
        require(BuildConfig.APPLICATION_ID == "co.fallsoft.vipi.groupsqa")
        assertFalse(GroupsUpgrade.enabled)
        val ids = List(3) { UUID.randomUUID() }
        val parties = mutableListOf<Party>()
        val now = System.currentTimeMillis()
        try {
            ids.forEach { parties.add(Party(MessageVault(context, it))) }
            val alice = parties[0]; var bob = parties[1]; val carol = parties[2]
            establish(alice, bob, now); establish(alice, carol, now); establish(bob, carol, now)
            val group = UUID.randomUUID()
            fun roster(count: Int, epoch: Int) = GroupSnapshot(group, "Coffee friends", epoch, "active", parties.take(count).mapIndexed { index, p -> person(p, index == 0) }, emptyList())
            alice.membership.createdLocally(roster(1, 1), group)
            for (index in 1..2) {
                val previous = parties.take(index).mapIndexed { i, p -> GroupApprovedPerson(p.vault.account, if (i == 0) GroupRole.OWNER else GroupRole.MEMBER) }
                val change = GroupRosterTransition(alice.vault.account, GroupControlAction.ADD, ids[index], index, index + 1, index * 2 + 1,
                    previous, previous + GroupApprovedPerson(ids[index], GroupRole.MEMBER))
                val control = alice.controls.prepare(UUID.randomUUID(), roster(index + 1, index * 2 + 1), change, now)
                for (recipient in parties.subList(1, index + 1)) {
                    recipient.controls.receive(incoming(control, alice, recipient, "control"), now)
                    if (recipient.membership.current(group) == null) {
                        val pending = recipient.controls.pending().single()
                        recipient.controls.confirmBootstrap(pending)
                    }
                    assertEquals(index + 1, recipient.membership.current(group)?.revision)
                }
                alice.controls.accepted(admitted(control), control); alice.controls.reconciled(control)
            }
            val current = roster(3, 5)
            val original = GroupMessage(UUID.randomUUID(), group, 5, 3, ids[0], "Coffee at six? ☕ مرحباً", now, GroupDelivery.QUEUED)
            val fanout = alice.crypto.prepare(original, current, now)
            assertEquals(fanout.body, alice.crypto.prepare(original, current, now + 10).body)
            val bobPacket = incoming(fanout, alice, bob, "message")
            bob.close() // No receiver/vault is available while sender and Carol exchange.
            assertEquals(original.text, carol.crypto.receive(incoming(fanout, alice, carol, "message"), now)?.text)
            val response = GroupMessage(UUID.randomUUID(), group, 5, 3, ids[2], "Yes, six works. Nos vemos.", now + 1, GroupDelivery.QUEUED)
            val reply = carol.crypto.prepare(response, current, now + 1)
            assertEquals(response.text, alice.crypto.receive(incoming(reply, carol, alice, "message"), now + 1)?.text)
            // Recreate only Bob's vault and native libsignal objects from disk.
            bob = Party(MessageVault(context, ids[1])); parties[1] = bob
            val received = requireNotNull(bob.crypto.receive(bobPacket, now + 2))
            assertEquals(original.id, received.id); assertEquals(original.text, received.text)
            assertEquals(received, bob.crypto.receive(bobPacket, now + 2))
            assertEquals(response.id, bob.crypto.receive(incoming(reply, carol, bob, "message"), now + 2)?.id)
            assertEquals(2, bob.store.messages(group).size); assertEquals(2, bob.store.unread(group, ids[1]))
            bob.store.preferences(group) { it.copy(read = setOf(original.id, response.id)) }
            assertEquals(0, bob.store.unread(group, ids[1]))
            val old = requireNotNull(alice.membership.current(group))
            val remove = GroupRosterTransition(ids[0], GroupControlAction.REMOVE, ids[1], 3, 4, 6, old.members, old.members.filter { it.id != ids[1] })
            val removal = alice.controls.prepare(UUID.randomUUID(), current, remove, now + 3)
            bob.controls.receive(incoming(removal, alice, bob, "control"), now + 3)
            carol.controls.receive(incoming(removal, alice, carol, "control"), now + 3)
            alice.controls.accepted(admitted(removal), removal); alice.controls.reconciled(removal)
            assertFalse(requireNotNull(bob.membership.current(group)).contains(ids[1]))
            val after = current.copy(epoch = 6, members = current.members.filter { it.id != ids[1] })
            val fresh = GroupMessage(UUID.randomUUID(), group, 6, 4, ids[0], "The new roster is private.", now + 4, GroupDelivery.QUEUED)
            val rekeyed = alice.crypto.prepare(fresh, after, now + 4)
            assertEquals(listOf(ids[2]), JSONObject(rekeyed.body).getJSONArray("envelopes").objects().map { it.uuid("recipient_id") })
            assertEquals(fresh.text, carol.crypto.receive(incoming(rekeyed, alice, carol, "message"), now + 4)?.text)
            assertThrows(IllegalArgumentException::class.java) { bob.crypto.prepare(fresh.copy(sender = ids[1]), current, now + 4) }
            assertEquals(2, bob.store.messages(group).size) // Exact old durable history survives removal.
            val changed = bobPacket.copy(message = UUID.randomUUID())
            assertThrows(IllegalArgumentException::class.java) { bob.crypto.receive(changed, now + 4) }
        } finally {
            parties.forEach { runCatching { it.close() } }
            val keystore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
            ids.forEach { id ->
                java.io.File(context.noBackupFilesDir, "messages/$id").deleteRecursively()
                keystore.deleteEntry("co.fallsoft.vipi.messages.$id")
            }
        }
    }
    @Test fun inactiveDeviceRemovalPreservesStrictDataAndReachableBootstrap() {
        require(BuildConfig.APPLICATION_ID == "co.fallsoft.vipi.groupsqa")
        val ids = List(3) { UUID.randomUUID() }; val parties = mutableListOf<Party>(); val now = System.currentTimeMillis()
        try {
            ids.forEach { parties.add(Party(MessageVault(context, it))) }
            val alice = parties[0]; val bob = parties[1]; val carol = parties[2]
            establish(alice, bob, now); establish(alice, carol, now); establish(bob, carol, now)
            val group = UUID.randomUUID()
            fun roster(count: Int, epoch: Int) = GroupSnapshot(group, "Friends", epoch, "active", parties.take(count).mapIndexed { index, p -> person(p, index == 0) }, emptyList())
            alice.membership.createdLocally(roster(1, 1), group)
            for (index in 1..2) {
                val previous = parties.take(index).mapIndexed { j, p -> GroupApprovedPerson(p.vault.account, if (j == 0) GroupRole.OWNER else GroupRole.MEMBER) }
                val change = GroupRosterTransition(ids[0], GroupControlAction.ADD, ids[index], index, index + 1, index * 2 + 1, previous, previous + GroupApprovedPerson(ids[index], GroupRole.MEMBER))
                val proposal = roster(index + 1, index * 2 + 1)
                if (index == 2) {
                    val unreachable = proposal.copy(members = proposal.members.map { if (it.id == ids[2]) it.copy(device = null) else it })
                    assertThrows(IllegalArgumentException::class.java) { alice.controls.prepare(UUID.randomUUID(), unreachable, change, now) }
                    assertTrue(alice.vault.transaction { alice.vault.ids("group-control-outgoing").isEmpty() })
                }
                val control = alice.controls.prepare(UUID.randomUUID(), proposal, change, now)
                parties.subList(1, index + 1).forEach { recipient ->
                    recipient.controls.receive(incoming(control, alice, recipient, "control"), now)
                    if (recipient.membership.current(group) == null) recipient.controls.confirmBootstrap(recipient.controls.pending().single())
                }
                alice.controls.accepted(admitted(control), control); alice.controls.reconciled(control)
            }
            val current = roster(3, 5)
            val unavailable = current.copy(members = current.members.map { if (it.id == ids[1]) it.copy(device = null) else it })
            val data = GroupMessage(UUID.randomUUID(), group, 5, 3, ids[0], "Ordinary data needs every member", now, GroupDelivery.QUEUED)
            assertThrows(IllegalArgumentException::class.java) { alice.crypto.prepare(data, unavailable, now) }
            assertNull(alice.crypto.pending(group, data.id))
            val old = requireNotNull(alice.membership.current(group))
            val remove = GroupRosterTransition(ids[0], GroupControlAction.REMOVE, ids[1], 3, 4, 6, old.members, old.members.filter { it.id != ids[1] })
            val control = alice.controls.prepare(UUID.randomUUID(), unavailable, remove, now)
            assertEquals(listOf(ids[2]), JSONObject(control.body).getJSONArray("envelopes").objects().map { it.uuid("recipient_id") })
            carol.controls.receive(incoming(control, alice, carol, "control"), now)
            alice.controls.accepted(admitted(control), control); alice.controls.reconciled(control)
            assertFalse(requireNotNull(carol.membership.current(group)).contains(ids[1]))
            // Bob did not receive a control; its old history is preserved. The
            // real relay/Session, not invented local receipt, fences its sends.
            assertEquals(3, bob.membership.current(group)?.revision)
            val after = current.copy(epoch = 6, members = current.members.filter { it.id != ids[1] })
            val fresh = GroupMessage(UUID.randomUUID(), group, 6, 4, ids[0], "Only approved remaining people", now, GroupDelivery.QUEUED)
            val ciphertext = alice.crypto.prepare(fresh, after, now)
            assertEquals(fresh.text, carol.crypto.receive(incoming(ciphertext, alice, carol, "message"), now)?.text)
        } finally {
            parties.forEach { runCatching { it.close() } }
            val keys = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
            ids.forEach { id -> java.io.File(context.noBackupFilesDir, "messages/$id").deleteRecursively(); keys.deleteEntry("co.fallsoft.vipi.messages.$id") }
        }
    }

}
