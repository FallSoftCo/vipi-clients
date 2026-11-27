package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.GroupSignalTestFixture.Party
import co.fallsoft.vipi.GroupSignalTestFixture.admitted
import co.fallsoft.vipi.GroupSignalTestFixture.establish
import co.fallsoft.vipi.GroupSignalTestFixture.incoming
import co.fallsoft.vipi.GroupSignalTestFixture.person
import java.security.KeyStore
import java.util.UUID
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Native crypto/storage qualification only. The HTTP/three-platform stages have their own opt-in
 * harness; this test makes no relay or UI claim.
 */
@RunWith(AndroidJUnit4::class)
class GroupsThreeNativeDeviceTest {
    private val context
        get() = InstrumentationRegistry.getInstrumentation().targetContext

    @Test
    fun threeNativeMembersBootstrapOfflineReopenAndRemovalFence() {
        require(BuildConfig.APPLICATION_ID == "co.fallsoft.vipi.groupsqa")
        val ids = List(3) { UUID.randomUUID() }
        val parties = mutableListOf<Party>()
        val now = System.currentTimeMillis()
        try {
            ids.forEach { parties.add(Party(MessageVault(context, it))) }
            val alice = parties[0]
            var bob = parties[1]
            val carol = parties[2]
            establish(alice, bob, now)
            establish(alice, carol, now)
            establish(bob, carol, now)
            val group = UUID.randomUUID()
            fun roster(count: Int, epoch: Int) =
                GroupSnapshot(
                    group,
                    "Coffee friends",
                    epoch,
                    "active",
                    parties.take(count).mapIndexed { index, p -> person(p, index == 0) },
                    emptyList(),
                )
            alice.membership.createdLocally(roster(1, 1), group)
            for (index in 1..2) {
                val previous =
                    parties.take(index).mapIndexed { i, p ->
                        GroupApprovedPerson(
                            p.vault.account,
                            if (i == 0) GroupRole.OWNER else GroupRole.MEMBER,
                        )
                    }
                val change =
                    GroupRosterTransition(
                        alice.vault.account,
                        GroupControlAction.ADD,
                        ids[index],
                        index,
                        index + 1,
                        index * 2 + 1,
                        previous,
                        previous + GroupApprovedPerson(ids[index], GroupRole.MEMBER),
                    )
                val control =
                    alice.controls.prepare(
                        UUID.randomUUID(),
                        roster(index + 1, index * 2 + 1),
                        change,
                        now,
                    )
                for (recipient in parties.subList(1, index + 1)) {
                    recipient.controls.receive(incoming(control, alice, recipient, "control"), now)
                    if (recipient.membership.current(group) == null) {
                        val pending = recipient.controls.pending().single()
                        recipient.controls.confirmBootstrap(pending)
                    }
                    assertEquals(index + 1, recipient.membership.current(group)?.revision)
                }
                alice.controls.accepted(admitted(control), control)
                alice.controls.reconciled(control)
            }
            val current = roster(3, 5)
            val original =
                GroupMessage(
                    UUID.randomUUID(),
                    group,
                    5,
                    3,
                    ids[0],
                    "Coffee at six? ☕ مرحباً",
                    now,
                    GroupDelivery.QUEUED,
                )
            val fanout = alice.crypto.prepare(original, current, now)
            assertEquals(fanout.body, alice.crypto.prepare(original, current, now + 10).body)
            val bobPacket = incoming(fanout, alice, bob, "message")
            bob.close() // No receiver/vault is available while sender and Carol exchange.
            assertEquals(
                original.text,
                carol.crypto.receive(incoming(fanout, alice, carol, "message"), now)?.text,
            )
            val response =
                GroupMessage(
                    UUID.randomUUID(),
                    group,
                    5,
                    3,
                    ids[2],
                    "Yes, six works. Nos vemos.",
                    now + 1,
                    GroupDelivery.QUEUED,
                )
            val reply = carol.crypto.prepare(response, current, now + 1)
            assertEquals(
                response.text,
                alice.crypto.receive(incoming(reply, carol, alice, "message"), now + 1)?.text,
            )
            // Recreate only Bob's vault and native libsignal objects from disk.
            bob = Party(MessageVault(context, ids[1]))
            parties[1] = bob
            val received = requireNotNull(bob.crypto.receive(bobPacket, now + 2))
            assertEquals(original.id, received.id)
            assertEquals(original.text, received.text)
            assertEquals(received, bob.crypto.receive(bobPacket, now + 2))
            assertEquals(
                response.id,
                bob.crypto.receive(incoming(reply, carol, bob, "message"), now + 2)?.id,
            )
            assertEquals(2, bob.store.messages(group).size)
            assertEquals(2, bob.store.unread(group, ids[1]))
            bob.store.preferences(group) { it.copy(read = setOf(original.id, response.id)) }
            assertEquals(0, bob.store.unread(group, ids[1]))
            val old = requireNotNull(alice.membership.current(group))
            val remove =
                GroupRosterTransition(
                    ids[0],
                    GroupControlAction.REMOVE,
                    ids[1],
                    3,
                    4,
                    6,
                    old.members,
                    old.members.filter { it.id != ids[1] },
                )
            val removal = alice.controls.prepare(UUID.randomUUID(), current, remove, now + 3)
            bob.controls.receive(incoming(removal, alice, bob, "control"), now + 3)
            carol.controls.receive(incoming(removal, alice, carol, "control"), now + 3)
            alice.controls.accepted(admitted(removal), removal)
            alice.controls.reconciled(removal)
            assertFalse(requireNotNull(bob.membership.current(group)).contains(ids[1]))
            val after =
                current.copy(epoch = 6, members = current.members.filter { it.id != ids[1] })
            val fresh =
                GroupMessage(
                    UUID.randomUUID(),
                    group,
                    6,
                    4,
                    ids[0],
                    "The new roster is private.",
                    now + 4,
                    GroupDelivery.QUEUED,
                )
            val rekeyed = alice.crypto.prepare(fresh, after, now + 4)
            assertEquals(
                listOf(ids[2]),
                JSONObject(rekeyed.body).getJSONArray("envelopes").objects().map {
                    it.uuid("recipient_id")
                },
            )
            assertEquals(
                fresh.text,
                carol.crypto.receive(incoming(rekeyed, alice, carol, "message"), now + 4)?.text,
            )
            assertThrows(IllegalArgumentException::class.java) {
                bob.crypto.prepare(fresh.copy(sender = ids[1]), current, now + 4)
            }
            assertEquals(
                2,
                bob.store.messages(group).size,
            ) // Exact old durable history survives removal.
            val changed = bobPacket.copy(message = UUID.randomUUID())
            assertThrows(IllegalArgumentException::class.java) {
                bob.crypto.receive(changed, now + 4)
            }
        } finally {
            parties.forEach { runCatching { it.close() } }
            val keystore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
            ids.forEach { id ->
                java.io.File(context.noBackupFilesDir, "messages/$id").deleteRecursively()
                keystore.deleteEntry("co.fallsoft.vipi.messages.$id")
            }
        }
    }

    @Test
    fun sixteenPeopleAuthorizeTheSameRosterAndOpenAllFifteenCopies() {
        require(BuildConfig.APPLICATION_ID == "co.fallsoft.vipi.groupsqa")
        val ids = List(GroupsUpgrade.maximumPeople) { UUID.randomUUID() }
        val parties = mutableListOf<Party>()
        val now = System.currentTimeMillis()
        val group = UUID.randomUUID()
        try {
            ids.forEach { parties += Party(MessageVault(context, it)) }
            val owner = parties.first()
            fun roster(count: Int) =
                GroupSnapshot(
                    group,
                    "Language practice",
                    count * 2 - 1,
                    "active",
                    parties.take(count).mapIndexed { index, party -> person(party, index == 0) },
                    emptyList(),
                )
            owner.membership.createdLocally(roster(1), group)
            for (index in 1 until ids.size) {
                establish(owner, parties[index], now)
                val before = requireNotNull(owner.membership.current(group))
                val proposal = roster(index + 1)
                val add =
                    GroupRosterTransition(
                        ids.first(),
                        GroupControlAction.ADD,
                        ids[index],
                        before.revision,
                        before.revision + 1,
                        proposal.epoch,
                        before.members,
                        before.members + GroupApprovedPerson(ids[index], GroupRole.MEMBER),
                    )
                val control = owner.controls.prepare(UUID.randomUUID(), proposal, add, now)
                for (recipient in parties.subList(1, index + 1)) {
                    recipient.controls.receive(incoming(control, owner, recipient, "control"), now)
                    if (recipient === parties[index])
                        recipient.controls.confirmBootstrap(recipient.controls.pending().single())
                    assertEquals(
                        add.members.toSet(),
                        recipient.membership.current(group)?.members?.toSet(),
                    )
                }
                owner.controls.accepted(admitted(control), control)
                owner.controls.reconciled(control)
            }
            val full = roster(ids.size)
            val message =
                GroupMessage(
                    UUID.randomUUID(),
                    group,
                    full.epoch,
                    ids.size,
                    ids.first(),
                    "Are we still meeting at six?",
                    now,
                    GroupDelivery.QUEUED,
                )
            val batch = owner.crypto.prepare(message, full, now)
            val packets = JSONObject(batch.body).getJSONArray("envelopes").objects()
            assertEquals(ids.drop(1).toSet(), packets.map { it.uuid("recipient_id") }.toSet())
            assertEquals(15, packets.map { it.getString("ciphertext") }.distinct().size)
            for (receiver in parties.drop(1)) {
                val delivered =
                    requireNotNull(
                        receiver.crypto.receive(incoming(batch, owner, receiver, "message"), now)
                    )
                assertEquals(message.id, delivered.id)
                assertEquals(message.text, delivered.text)
                assertEquals(1, receiver.store.messages(group).size)
            }
        } finally {
            parties.forEach { runCatching { it.close() } }
            val keys = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
            ids.forEach { id ->
                java.io.File(context.noBackupFilesDir, "messages/$id").deleteRecursively()
                keys.deleteEntry("co.fallsoft.vipi.messages.$id")
            }
        }
    }

    @Test
    fun inactiveDeviceRemovalPreservesStrictDataAndReachableBootstrap() {
        require(BuildConfig.APPLICATION_ID == "co.fallsoft.vipi.groupsqa")
        val ids = List(3) { UUID.randomUUID() }
        val parties = mutableListOf<Party>()
        val now = System.currentTimeMillis()
        try {
            ids.forEach { parties.add(Party(MessageVault(context, it))) }
            val alice = parties[0]
            val bob = parties[1]
            val carol = parties[2]
            establish(alice, bob, now)
            establish(alice, carol, now)
            establish(bob, carol, now)
            val group = UUID.randomUUID()
            fun roster(count: Int, epoch: Int) =
                GroupSnapshot(
                    group,
                    "Friends",
                    epoch,
                    "active",
                    parties.take(count).mapIndexed { index, p -> person(p, index == 0) },
                    emptyList(),
                )
            alice.membership.createdLocally(roster(1, 1), group)
            for (index in 1..2) {
                val previous =
                    parties.take(index).mapIndexed { j, p ->
                        GroupApprovedPerson(
                            p.vault.account,
                            if (j == 0) GroupRole.OWNER else GroupRole.MEMBER,
                        )
                    }
                val change =
                    GroupRosterTransition(
                        ids[0],
                        GroupControlAction.ADD,
                        ids[index],
                        index,
                        index + 1,
                        index * 2 + 1,
                        previous,
                        previous + GroupApprovedPerson(ids[index], GroupRole.MEMBER),
                    )
                val proposal = roster(index + 1, index * 2 + 1)
                if (index == 2) {
                    val unreachable =
                        proposal.copy(
                            members =
                                proposal.members.map {
                                    if (it.id == ids[2]) it.copy(device = null) else it
                                }
                        )
                    assertThrows(IllegalArgumentException::class.java) {
                        alice.controls.prepare(UUID.randomUUID(), unreachable, change, now)
                    }
                    assertTrue(
                        alice.vault.transaction {
                            alice.vault.ids("group-control-outgoing").isEmpty()
                        }
                    )
                }
                val control = alice.controls.prepare(UUID.randomUUID(), proposal, change, now)
                parties.subList(1, index + 1).forEach { recipient ->
                    recipient.controls.receive(incoming(control, alice, recipient, "control"), now)
                    if (recipient.membership.current(group) == null)
                        recipient.controls.confirmBootstrap(recipient.controls.pending().single())
                }
                alice.controls.accepted(admitted(control), control)
                alice.controls.reconciled(control)
            }
            val current = roster(3, 5)
            val unavailable =
                current.copy(
                    members =
                        current.members.map { if (it.id == ids[1]) it.copy(device = null) else it }
                )
            val data =
                GroupMessage(
                    UUID.randomUUID(),
                    group,
                    5,
                    3,
                    ids[0],
                    "Ordinary data needs every member",
                    now,
                    GroupDelivery.QUEUED,
                )
            assertThrows(IllegalArgumentException::class.java) {
                alice.crypto.prepare(data, unavailable, now)
            }
            assertNull(alice.crypto.pending(group, data.id))
            val old = requireNotNull(alice.membership.current(group))
            val remove =
                GroupRosterTransition(
                    ids[0],
                    GroupControlAction.REMOVE,
                    ids[1],
                    3,
                    4,
                    6,
                    old.members,
                    old.members.filter { it.id != ids[1] },
                )
            val control = alice.controls.prepare(UUID.randomUUID(), unavailable, remove, now)
            assertEquals(
                listOf(ids[2]),
                JSONObject(control.body).getJSONArray("envelopes").objects().map {
                    it.uuid("recipient_id")
                },
            )
            carol.controls.receive(incoming(control, alice, carol, "control"), now)
            alice.controls.accepted(admitted(control), control)
            alice.controls.reconciled(control)
            assertFalse(requireNotNull(carol.membership.current(group)).contains(ids[1]))
            // Bob did not receive a control; its old history is preserved. The
            // real relay/Session, not invented local receipt, fences its sends.
            assertEquals(3, bob.membership.current(group)?.revision)
            val after =
                current.copy(epoch = 6, members = current.members.filter { it.id != ids[1] })
            val fresh =
                GroupMessage(
                    UUID.randomUUID(),
                    group,
                    6,
                    4,
                    ids[0],
                    "Only approved remaining people",
                    now,
                    GroupDelivery.QUEUED,
                )
            val ciphertext = alice.crypto.prepare(fresh, after, now)
            assertEquals(
                fresh.text,
                carol.crypto.receive(incoming(ciphertext, alice, carol, "message"), now)?.text,
            )
        } finally {
            parties.forEach { runCatching { it.close() } }
            val keys = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
            ids.forEach { id ->
                java.io.File(context.noBackupFilesDir, "messages/$id").deleteRecursively()
                keys.deleteEntry("co.fallsoft.vipi.messages.$id")
            }
        }
    }
}
