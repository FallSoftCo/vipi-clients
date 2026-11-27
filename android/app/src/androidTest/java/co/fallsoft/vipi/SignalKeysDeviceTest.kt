package co.fallsoft.vipi

import android.util.Base64
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.util.UUID
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.signal.libsignal.protocol.*
import org.signal.libsignal.protocol.message.PreKeySignalMessage

@RunWith(AndroidJUnit4::class)
class SignalKeysDeviceTest {
    private val context
        get() = InstrumentationRegistry.getInstrumentation().targetContext

    private fun reject(action: () -> Unit) {
        assertTrue(runCatching(action).isFailure)
    }

    @Test
    fun durablePublicationAndValidatedSession() {
        val now = System.currentTimeMillis()
        val alice = UUID.randomUUID()
        val bob = UUID.randomUUID()
        val bobDevice = UUID.randomUUID()
        val request = UUID.randomUUID()
        val published =
            MessageVault(context, bob).use { vault ->
                SignalKeys(DurableSignalStore(vault)).publication(now, 3)
            }
        MessageVault(context, bob).use { vault ->
            val keys = SignalKeys(DurableSignalStore(vault))
            assertEquals(published.toString(), keys.publication(now + 1).toString())
            reject { keys.published(2) }
            keys.published(1)
            keys.published(1)
            val next = keys.publication(now + 1, 2)
            assertEquals(2, next.getInt("revision"))
            assertEquals(4, next.getJSONArray("one_time").getJSONObject(0).getInt("id"))
            assertEquals(
                published.getJSONObject("signed").toString(),
                next.getJSONObject("signed").toString(),
            )
        }
        val response =
            JSONObject()
                .put("request_id", request)
                .put("user_id", bob)
                .put("device_id", bobDevice)
                .put("signal_device_id", 1)
                .put("registration_id", published.getInt("registration_id"))
                .put("identity_key", published.getString("identity_key"))
                .put("signed", published.getJSONObject("signed"))
                .put("one_time", published.getJSONArray("one_time").getJSONObject(0))
        val aliceAddress = SignalProtocolAddress(alice.toString(), 1)
        val bobAddress = SignalProtocolAddress(bob.toString(), 1)
        val envelope =
            MessageVault(context, alice).use { vault ->
                val store = DurableSignalStore(vault)
                val keys = SignalKeys(store)
                for (field in listOf("signed", "one_time")) {
                    val broken = JSONObject(response.toString())
                    broken
                        .getJSONObject(field)
                        .put("signature", Base64.encodeToString(ByteArray(64), Base64.NO_WRAP))
                    reject { keys.establish(bob, request, broken) }
                    assertFalse(vault.transaction { store.containsSession(bobAddress) })
                }
                assertEquals(bobDevice, keys.establish(bob, request, response))
                val message =
                    MessageJournal(vault).queue(
                        UUID.randomUUID(),
                        bob,
                        "Real keys, local voices — café ☕",
                        now,
                        now,
                    ) {
                        SessionCipher(store, aliceAddress, bobAddress).encrypt(it).let { cipher ->
                            cipher.type to cipher.serialize()
                        }
                    }
                val ratchet = vault.transaction { store.loadSession(bobAddress)!!.serialize() }
                assertEquals(bobDevice, keys.establish(bob, request, response))
                assertArrayEquals(
                    ratchet,
                    vault.transaction { store.loadSession(bobAddress)!!.serialize() },
                )
                reject { keys.establish(bob, UUID.randomUUID(), response) }
                message
            }
        MessageVault(context, bob).use { vault ->
            val store = DurableSignalStore(vault)
            val received =
                MessageJournal(vault).receive(envelope, now) { type, bytes ->
                    assertEquals(3, type)
                    SessionCipher(store, bobAddress, aliceAddress)
                        .decrypt(PreKeySignalMessage(bytes))
                }
            assertEquals("Real keys, local voices — café ☕", received.text)
            vault.transaction {
                assertFalse(store.containsPreKey(1))
                assertFalse(store.containsKyberPreKey(1))
            }
        }
        File(context.filesDir, "public-key-publication.json").writeText(published.toString(2))
    }
}
