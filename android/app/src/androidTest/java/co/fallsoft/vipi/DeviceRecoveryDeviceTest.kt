package co.fallsoft.vipi

import android.content.ContextWrapper
import android.util.Base64
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.json.JSONArray
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.Dispatchers
import org.junit.Assert.*
import org.junit.Test
import org.signal.libsignal.protocol.SignalProtocolAddress
import java.io.File
import java.security.KeyStore
import java.util.UUID

class DeviceRecoveryDeviceTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private fun claim(account: UUID, device: UUID, request: UUID, publication: JSONObject) = JSONObject()
        .put("user_id", account).put("device_id", device).put("request_id", request).put("signal_device_id", 1)
        .put("registration_id", publication.getInt("registration_id")).put("identity_key", publication.getString("identity_key"))
        .put("signed", publication.getJSONObject("signed")).put("one_time", publication.getJSONArray("one_time").getJSONObject(0))
    private fun reject(block: () -> Unit) { assertTrue(runCatching(block).isFailure) }

    @Test fun peerChangeRequiresExactConfirmationAndPreservesHistoryRoutesAndReplayReceipts() {
        val alice = UUID.randomUUID(); val bob = UUID.randomUUID(); val now = System.currentTimeMillis()
        val nextRoot = File(context.cacheDir, "peer-recovery-${UUID.randomUUID()}")
        val nextContext = object : ContextWrapper(context) { override fun getNoBackupFilesDir() = nextRoot }
        try { MessageVault(context, alice).use { av -> MessageVault(context, bob).use { oldVault -> MessageVault(nextContext, bob).use { newVault ->
            val a = MessagingCore(av); val oldBob = MessagingCore(oldVault); val newBob = MessagingCore(newVault)
            val oldRequest = UUID.randomUUID(); val request = UUID.randomUUID()
            val oldResponse = claim(bob, oldBob.device.id, oldRequest, oldBob.keys.publication(now, 1))
            a.keys.establish(bob, oldRequest, oldResponse)
            val oldNumber = requireNotNull(a.securityNumber(bob)); a.setIdentityVerified(true, bob, oldNumber)
            val waiting = a.queue(UUID.randomUUID(), bob, "A waiting message must keep its original route.", now, now)
            oldBob.receive(waiting, now)
            val savedIncoming = oldBob.queue(UUID.randomUUID(), alice, "Already saved old-device reply", now, now)
            a.receive(savedIncoming, now)
            val unreadOld = oldBob.queue(UUID.randomUUID(), alice, "Unread old-device reply", now, now)
            val response = claim(bob, newBob.device.id, request, newBob.keys.publication(now, 1))
            val address = SignalProtocolAddress(bob.toString(), 1)
            val ratchet = av.transaction { a.store.loadSession(address)!!.serialize() }
            for (field in listOf("signed", "one_time")) {
                val broken = JSONObject(response.toString()).apply { getJSONObject(field).put("signature", Base64.encodeToString(ByteArray(64), Base64.NO_WRAP)) }
                reject { a.keys.previewRecovery(bob, request, broken) }
            }
            val candidate = a.keys.previewRecovery(bob, request, response)
            assertFalse(candidate.number.verified); assertNotEquals(oldNumber.digits, candidate.number.digits)
            assertArrayEquals(ratchet, av.transaction { a.store.loadSession(address)!!.serialize() })
            assertTrue(a.securityNumber(bob)!!.verified)
            reject { a.keys.confirmRecovery(candidate.copy(number = candidate.number.copy(digits = "0".repeat(60))), response) }
            reject { a.keys.confirmRecovery(candidate, JSONObject(response.toString()).put("device_id", UUID.randomUUID())) }
            assertArrayEquals(ratchet, av.transaction { a.store.loadSession(address)!!.serialize() })
            assertEquals(newBob.device.id, a.keys.confirmRecovery(candidate, response))
            assertFalse(a.securityNumber(bob)!!.verified)
            assertEquals("Already saved old-device reply", a.receive(savedIncoming, now + 1).text)
            val stale = runCatching { a.receive(unreadOld, now + 1) }.exceptionOrNull()
            assertTrue(stale is RetiredPeerMessage)
            assertFalse(unreadOld.envelope.id in a.journal.pendingReceipts())
            assertEquals("failed", a.journal.outgoing(waiting.envelope.id)!!.state)
            assertEquals(waiting.recipientDevice.toString(), av.transaction { av.get("outgoing-route", waiting.envelope.id.toString())!!.toString(Charsets.UTF_8) })
            assertArrayEquals(waiting.envelope.ciphertext, a.journal.outgoing(waiting.envelope.id)!!.envelope.ciphertext)
            val current = av.transaction { a.store.loadSession(address)!!.serialize() }
            // A delayed successful old claim cannot resurrect its ratchet after recovery.
            assertEquals(oldBob.device.id, a.keys.establish(bob, oldRequest, oldResponse))
            assertArrayEquals(current, av.transaction { a.store.loadSession(address)!!.serialize() })
            reject { a.keys.confirmRecovery(candidate, response) }
            val fresh = a.queue(UUID.randomUUID(), bob, "A new message uses the approved new connection.", now + 1, now + 1)
            assertEquals(newBob.device.id, fresh.recipientDevice)
            assertEquals("A new message uses the approved new connection.", newBob.receive(fresh, now + 1).text)
            assertEquals(3, ConversationHistory(av).messages(bob).size)
        } } } } finally {
            nextRoot.deleteRecursively()
            for (id in listOf(alice, bob)) {
                File(context.noBackupFilesDir, "messages/$id").deleteRecursively()
                KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$id") }
            }
        }
    }

    @Test fun ownDeviceCandidateRetriesExactlyThenRotatesOnlyTransportAndIdentity() {
        val account = UUID.randomUUID(); val peer = UUID.randomUUID(); val now = System.currentTimeMillis()
        try { MessageVault(context, account).use { vault ->
            val old = MessagingCore(vault)
            val identity = vault.transaction { old.store.identityKeyPair.serialize() }
            val candidate = DeviceRecovery.candidate(vault, old.device)
            assertEquals(candidate, DeviceRecovery.candidate(vault, old.device))
            val id = UUID.randomUUID()
            val envelope = old.journal.queue(id, peer, "Preserved old outgoing history", now, now) { 3 to ByteArray(64) { 1 } }
            vault.transaction {
                vault.put("outgoing-route", id.toString(), peer.toString().toByteArray())
                vault.put("key-claim", "retained-replay", byteArrayOf(4, 5))
                vault.put("identity-verification", peer.toString(), "old-verification".toByteArray())
                vault.put("contact", peer.toString(), "preserved-contact".toByteArray())
            }
            reject { DeviceRecovery.commit(vault, old.device, candidate.copy(id = UUID.randomUUID())) }
            assertArrayEquals(identity, vault.transaction { old.store.identityKeyPair.serialize() })
            DeviceRecovery.commit(vault, old.device, candidate)
            val fresh = MessagingCore(vault)
            assertEquals(candidate, fresh.device)
            assertFalse(identity.contentEquals(vault.transaction { fresh.store.identityKeyPair.serialize() }))
            assertEquals("failed", fresh.journal.outgoing(id)!!.state)
            assertArrayEquals(envelope.ciphertext, fresh.journal.outgoing(id)!!.envelope.ciphertext)
            assertTrue(fresh.journal.pending(now).isEmpty())
            vault.transaction {
                assertNull(vault.get("identity-verification", peer.toString()))
                assertArrayEquals(byteArrayOf(4, 5), vault.get("key-claim", "retained-replay"))
                assertEquals("preserved-contact", vault.get("contact", peer.toString())!!.toString(Charsets.UTF_8))
                assertEquals(peer.toString(), vault.get("outgoing-route", id.toString())!!.toString(Charsets.UTF_8))
                assertNull(vault.get("local", "replacement-device"))
            }
        } } finally {
            File(context.noBackupFilesDir, "messages/$account").deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
        }
    }

    @Test fun coordinatorRequiresRecentSignInRetriesOneCandidateAndNeverAutomaticallyRetakes(): Unit = runBlocking { withContext(Dispatchers.Main) {
        val account = UUID.randomUUID(); val root = File(context.cacheDir, "takeover-qa-${UUID.randomUUID()}")
        val isolated = object : ContextWrapper(context) {
            override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() }
            override fun getCacheDir() = File(root, "cache").apply { mkdirs() }
        }
        val registrations = mutableListOf<String>(); var recent = false; var loseNextReply = true
        val transport = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject = when (path) {
                "/v1/me" -> ChatProfile(account, "takeover_qa", "Takeover QA").json()
                "/v1/devices" -> {
                    if (!requireNotNull(body).optBoolean("replace_active")) throw ServiceFailure(409, "device_replacement_confirmation_required")
                    registrations += body.getString("device_id")
                    if (!recent) throw ServiceFailure(401, "recent_sign_in_required")
                    if (loseNextReply) { loseNextReply = false; throw java.io.IOException("Controlled lost response") }
                    JSONObject().put("id", body.getString("device_id")).put("active", true)
                }
                "/v1/keys" -> if (method == "GET") JSONObject().put("remaining", 0) else JSONObject().put("revision", body!!.getInt("revision"))
                "/v1/messages/pending" -> JSONObject().put("messages", JSONArray())
                else -> error("Unexpected controlled request")
            }
        }
        try { ChatSession(isolated, transport, "user_takeover_qa").use { chat ->
            chat.start(); assertTrue(chat.needsDeviceRecovery); assertFalse(chat.ready); assertTrue(registrations.isEmpty())
            chat.confirmDeviceReplacement(); assertTrue(chat.recoveryNeedsSignIn); assertFalse(chat.ready)
            recent = true
            chat.confirmDeviceReplacement(); assertFalse(chat.ready)
            chat.confirmDeviceReplacement(); assertTrue(chat.ready); assertFalse(chat.needsDeviceRecovery)
            assertEquals(3, registrations.size); assertEquals(1, registrations.distinct().size)
            chat.noteDeviceRevoked(); assertFalse(chat.ready); assertTrue(chat.needsDeviceRecovery)
            chat.start(); assertEquals(3, registrations.size); assertFalse(chat.ready)
            chat.confirmDeviceReplacement(); assertTrue(chat.ready); assertNotEquals(registrations.first(), registrations.last())
        } } finally {
            root.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
        }
    } }

    @Test fun ownTakeoverPreservesRemoteTrustWhileAllowingExpectedFreshSession() {
        val local = UUID.randomUUID(); val peer = UUID.randomUUID(); val impostor = UUID.randomUUID()
        val now = System.currentTimeMillis()
        try { MessageVault(context, local).use { lv -> MessageVault(context, peer).use { pv -> MessageVault(context, impostor).use { iv ->
            val old = MessagingCore(lv); val remote = MessagingCore(pv); val changed = MessagingCore(iv)
            val publication = remote.keys.publication(now, 1)
            val originalClaim = UUID.randomUUID(); old.keys.establish(peer, originalClaim, claim(peer, remote.device.id, originalClaim, publication))
            val prior = requireNotNull(old.securityNumber(peer)); old.setIdentityVerified(true, peer, prior)
            DeviceRecovery.commit(lv, old.device, DeviceRecovery.candidate(lv, old.device))
            val next = MessagingCore(lv)
            assertFalse(next.hasSession(peer)); assertFalse(next.securityNumber(peer)!!.verified)
            assertNotEquals(prior.digits, next.securityNumber(peer)!!.digits)
            val changedRequest = UUID.randomUUID()
            reject { next.keys.establish(peer, changedRequest, claim(peer, remote.device.id, changedRequest, changed.keys.publication(now, 1))) }
            assertFalse(next.hasSession(peer))
            val changedDevice = UUID.randomUUID()
            reject { next.keys.establish(peer, changedDevice, claim(peer, UUID.randomUUID(), changedDevice, publication)) }
            assertFalse(next.hasSession(peer))
            val expected = UUID.randomUUID()
            assertEquals(remote.device.id, next.keys.establish(peer, expected, claim(peer, remote.device.id, expected, publication)))
            assertTrue(next.hasSession(peer)); assertFalse(next.securityNumber(peer)!!.verified)
        } } } } finally {
            for (id in listOf(local, peer, impostor)) {
                File(context.noBackupFilesDir, "messages/$id").deleteRecursively()
                KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$id") }
            }
        }
    }

    @Test fun changedIncomingDevicePersistsReviewRequirementAndKeepsOldPin(): Unit = runBlocking { withContext(Dispatchers.Main) {
        val account = UUID.randomUUID(); val peer = UUID.randomUUID(); val root = File(context.cacheDir, "peer-warning-${UUID.randomUUID()}")
        val isolated = object : ContextWrapper(context) { override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() } }
        val pinned = org.signal.libsignal.protocol.IdentityKeyPair.generate().publicKey.serialize()
        var localDevice: UUID? = null
        MessageVault(isolated, account).use { vault ->
            localDevice = MessagingCore(vault).device.id
            vault.transaction {
                vault.put("identity", "$peer/1", pinned)
                vault.put("peer-device", peer.toString(), UUID.randomUUID().toString().toByteArray())
            }
        }
        val transport = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject = when(path) {
                "/v1/me" -> ChatProfile(account, "peer_warning", "Warning QA").json()
                "/v1/devices" -> JSONObject().put("id", body!!.getString("device_id")).put("active", true)
                "/v1/keys" -> JSONObject().put("remaining", 20)
                "/v1/messages/pending" -> JSONObject().put("messages", JSONArray().put(JSONObject()
                    .put("id", UUID.randomUUID()).put("sender_id", peer).put("sender_device_id", UUID.randomUUID())
                    .put("recipient_device_id", localDevice).put("created_at", java.time.Instant.now().toString())
                    .put("cipher_type", 3).put("ciphertext", Base64.encodeToString(ByteArray(64), Base64.NO_WRAP))))
                else -> error("Unexpected controlled request")
            }
        }
        try { ChatSession(isolated, transport, "user_peer_warning").use { chat ->
            chat.start(); assertTrue(peer in chat.peersNeedingRecovery)
            reject { chat.send("Must wait for explicit key review", peer) }
            ChatSession(isolated, transport, chat.userID).use { reopened -> assertTrue(peer in reopened.peersNeedingRecovery) }
            MessageVault(isolated, account).use { vault -> vault.transaction { assertArrayEquals(pinned, vault.get("identity", "$peer/1")) } }
        } } finally {
            root.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
        }
    } }
}
