package co.fallsoft.vipi

import android.database.sqlite.SQLiteDatabase
import android.util.Base64
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.security.KeyStore
import java.util.UUID
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.signal.libsignal.protocol.*
import org.signal.libsignal.protocol.ecc.ECKeyPair
import org.signal.libsignal.protocol.kem.*
import org.signal.libsignal.protocol.message.*
import org.signal.libsignal.protocol.state.*

@RunWith(AndroidJUnit4::class)
class DurableMessagingDeviceTest {
    private val context
        get() = InstrumentationRegistry.getInstrumentation().targetContext

    private val folder
        get() = context.filesDir

    private class Interrupted : RuntimeException()

    private fun ByteArray.b64() = Base64.encodeToString(this, Base64.NO_WRAP)

    private fun reject(block: () -> Unit) {
        assertTrue(runCatching(block).isFailure)
    }

    @Test
    fun exportDurableHandshake() {
        val aliceID = UUID.randomUUID()
        val bobID = UUID.randomUUID()
        val alice = SignalProtocolAddress(aliceID.toString(), 1)
        val bob = SignalProtocolAddress(bobID.toString(), 1)
        val keys = IdentityKeyPair.generate()
        val pre = ECKeyPair.generate()
        val signed = ECKeyPair.generate()
        val kyber = KEMKeyPair.generate(KEMKeyType.KYBER_1024)
        val signedSignature = keys.privateKey.calculateSignature(signed.publicKey.serialize())
        val kyberSignature = keys.privateKey.calculateSignature(kyber.publicKey.serialize())
        val id = UUID.randomUUID()
        val created = System.currentTimeMillis()
        val text = "Persistent coffee by the river — café ☕ مرحباً"
        val vault = MessageVault(context, aliceID)
        val store = DurableSignalStore(vault)
        vault.transaction {
            SessionBuilder(store, bob, alice)
                .process(
                    PreKeyBundle(
                        202,
                        1,
                        1,
                        pre.publicKey,
                        2,
                        signed.publicKey,
                        signedSignature,
                        keys.publicKey,
                        3,
                        kyber.publicKey,
                        kyberSignature,
                    )
                )
        }
        val before = vault.transaction { store.loadSession(bob)!!.serialize() }
        val journal = MessageJournal(vault)
        reject {
            journal.queue(id, bobID, text, created, created) { clear ->
                SessionCipher(store, alice, bob).encrypt(clear)
                throw Interrupted()
            }
        }
        assertNull(journal.outgoing(id))
        MessageVault(context, aliceID).use { opened ->
            assertEquals(text, MessageJournal(opened).draft(id)!!.text)
        }
        assertArrayEquals(before, vault.transaction { store.loadSession(bob)!!.serialize() })
        val envelope =
            journal.queue(id, bobID, text, created, created) { clear ->
                SessionCipher(store, alice, bob).encrypt(clear).let { it.type to it.serialize() }
            }
        assertNull(journal.draft(id))
        vault.close()
        MessageVault(context, aliceID).use { reopened ->
            val again =
                MessageJournal(reopened).queue(id, bobID, text, created, created + 1) {
                    error("A retry must not encrypt again")
                }
            assertArrayEquals(envelope.ciphertext, again.ciphertext)
            assertEquals(1, MessageJournal(reopened).pending(created).size)
        }
        val fixture =
            JSONObject()
                .put("purpose", "SYNTHETIC DURABLE MESSAGING QA ONLY")
                .put("version", "0.105.0")
                .put("alice", aliceID.toString())
                .put("bob", bobID.toString())
                .put("bobIdentity", keys.serialize().b64())
                .put("bobPreKey", PreKeyRecord(1, pre).serialize().b64())
                .put(
                    "bobSignedPreKey",
                    SignedPreKeyRecord(2, created, signed, signedSignature).serialize().b64(),
                )
                .put(
                    "bobKyberPreKey",
                    KyberPreKeyRecord(3, created, kyber, kyberSignature).serialize().b64(),
                )
                .put("envelope", envelope.json())
        File(folder, "durable-handshake.json").writeText(fixture.toString(2))
    }

    @Test
    fun importDurableSwiftReplies() {
        check(InstrumentationRegistry.getArguments().getString("vipiDurableReplyReady") == "true")
        val fixture = JSONObject(File(folder, "durable-handshake.json").readText())
        val aliceID = UUID.fromString(fixture.getString("alice"))
        val bobID = UUID.fromString(fixture.getString("bob"))
        val alice = SignalProtocolAddress(aliceID.toString(), 1)
        val bob = SignalProtocolAddress(bobID.toString(), 1)
        val replies =
            JSONObject(File(folder, "durable-swift-replies.json").readText())
                .getJSONArray("messages")
        for (index in listOf(2, 0, 1)) MessageVault(context, aliceID).use { vault ->
            val store = DurableSignalStore(vault)
            val journal = MessageJournal(vault)
            val envelope = ChatEnvelope.parse(replies.getJSONObject(index))
            fun decrypt(type: Int, bytes: ByteArray) =
                if (type == CiphertextMessage.PREKEY_TYPE)
                    SessionCipher(store, alice, bob).decrypt(PreKeySignalMessage(bytes))
                else SessionCipher(store, alice, bob).decrypt(SignalMessage(bytes))
            if (index == 2) {
                val changed = envelope.ciphertext.copyOf()
                changed[changed.lastIndex] = (changed.last().toInt() xor 1).toByte()
                reject {
                    journal.receive(
                        envelope.copy(ciphertext = changed),
                        envelope.createdAt,
                        ::decrypt,
                    )
                }
                reject {
                    journal.receive(
                        envelope.copy(id = UUID.randomUUID()),
                        envelope.createdAt,
                        ::decrypt,
                    )
                }
                reject {
                    journal.receive(envelope, envelope.createdAt) { type, bytes ->
                        decrypt(type, bytes)
                        throw Interrupted()
                    }
                }
            }
            assertEquals(
                "Durable Swift reply $index — río ☕",
                journal.receive(envelope, envelope.createdAt, ::decrypt).text,
            )
            assertEquals(
                "delivered",
                journal
                    .receive(envelope, envelope.createdAt) { _, _ -> error("Duplicate decrypted") }
                    .state,
            )
            vault.transaction {
                val changedIdentity = IdentityKeyPair.generate().publicKey
                assertFalse(
                    store.isTrustedIdentity(
                        bob,
                        changedIdentity,
                        IdentityKeyStore.Direction.SENDING,
                    )
                )
                assertFalse(
                    store.isTrustedIdentity(
                        bob,
                        changedIdentity,
                        IdentityKeyStore.Direction.RECEIVING,
                    )
                )
                reject { store.saveIdentity(bob, changedIdentity) }
            }
        }
        File(folder, "durable-interop-receipt.json")
            .writeText(
                JSONObject()
                    .put("status", "passed")
                    .put("libsignal", "0.105.0")
                    .put("scope", "native durable stores and journal, not live relay or UI")
                    .put(
                        "checks",
                        "restart, atomic rollback, stable retry ciphertext, out-of-order, duplicate, tamper, metadata binding, identity rejection",
                    )
                    .toString(2)
            )
    }

    @Test
    fun concurrentTransactionsDoNotLoseUpdates() {
        val account = UUID.randomUUID()
        MessageVault(context, account).use { first ->
            MessageVault(context, account).use { second ->
                first.transaction { first.put("test", "counter", "0".toByteArray()) }
                val executor = java.util.concurrent.Executors.newFixedThreadPool(2)
                try {
                    val futures =
                        listOf(first, second).map { vault ->
                            executor.submit {
                                repeat(30) {
                                    vault.transaction {
                                        val value =
                                            vault
                                                .get("test", "counter")!!
                                                .toString(Charsets.UTF_8)
                                                .toInt()
                                        vault.put(
                                            "test",
                                            "counter",
                                            (value + 1).toString().toByteArray(),
                                        )
                                    }
                                }
                            }
                        }
                    futures.forEach { it.get(20, java.util.concurrent.TimeUnit.SECONDS) }
                    assertEquals(
                        "60",
                        first.transaction {
                            first.get("test", "counter")!!.toString(Charsets.UTF_8)
                        },
                    )
                } finally {
                    executor.shutdownNow()
                }
            }
        }
    }

    @Test
    fun storageIntegrityAndExpiry() {
        val account = UUID.randomUUID()
        val peer = UUID.randomUUID()
        val id = UUID.randomUUID()
        val now = 1_800_000_000_000L
        val marker = "PRIVATE CHAT TEXT MUST NEVER APPEAR IN SQLITE"
        val vault = MessageVault(context, account)
        val file = vault.file
        val journal = MessageJournal(vault)
        reject { vault.put("test", "outside", byteArrayOf(1)) }
        vault.transaction {
            vault.put("test", "a", marker.toByteArray())
            vault.put("test", "b", byteArrayOf(2))
        }
        val envelope = journal.queue(id, peer, marker, now, now) { 2 to ByteArray(64) { 7 } }
        val draftID = UUID.randomUUID()
        journal.saveDraft(draftID, peer, "Waiting for a connection", now, now)
        assertEquals(1, journal.pendingDrafts(now).size)
        assertTrue(journal.pendingDrafts(now + MessageJournal.TTL).isEmpty())
        assertEquals("expired", journal.draft(draftID)!!.state)
        journal.applyStatus(id, "accepted")
        assertEquals(1, journal.pending(now + MessageJournal.TTL - 1).size)
        assertTrue(journal.pending(now + MessageJournal.TTL).isEmpty())
        assertEquals("expired", journal.outgoing(id)!!.state)
        reject {
            journal.queue(id, peer, marker, now, now + MessageJournal.TTL) {
                error("Expired retry")
            }
        }
        journal.applyStatus(id, "delivered")
        journal.applyStatus(id, "accepted")
        assertEquals("delivered", journal.outgoing(id)!!.state)
        vault.close()
        for (path in file.parentFile!!.listFiles().orEmpty()) if (path.isFile)
            assertFalse(path.readBytes().toString(Charsets.ISO_8859_1).contains(marker))
        SQLiteDatabase.openDatabase(file.path, null, SQLiteDatabase.OPEN_READWRITE).use { db ->
            db.execSQL(
                "UPDATE records SET value=(SELECT value FROM records WHERE kind='test' AND id='a') WHERE kind='test' AND id='b'"
            )
        }
        MessageVault(context, account).use { opened ->
            reject { opened.transaction { opened.get("test", "b") } }
            assertArrayEquals(marker.toByteArray(), opened.transaction { opened.get("test", "a") })
        }
        KeyStore.getInstance("AndroidKeyStore").apply {
            load(null)
            deleteEntry("co.fallsoft.vipi.messages.$account")
        }
        reject { MessageVault(context, account) }
        assertTrue(file.exists())
    }
}
