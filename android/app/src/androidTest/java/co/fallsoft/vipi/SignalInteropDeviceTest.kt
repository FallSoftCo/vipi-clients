package co.fallsoft.vipi

import android.util.Base64
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.signal.libsignal.protocol.*
import org.signal.libsignal.protocol.ecc.ECKeyPair
import org.signal.libsignal.protocol.kem.KEMKeyPair
import org.signal.libsignal.protocol.kem.KEMKeyType
import org.signal.libsignal.protocol.message.*
import org.signal.libsignal.protocol.state.*
import org.signal.libsignal.protocol.state.impl.InMemorySignalProtocolStore
import java.io.File

/** Synthetic test keys only. Never used by the app, an account, or a production service. */
@RunWith(AndroidJUnit4::class)
class SignalInteropDeviceTest {
    private val directory get() = InstrumentationRegistry.getInstrumentation().targetContext.filesDir
    private val alice = SignalProtocolAddress("0fcb6760-c826-4539-811e-c9be982b4f24", 1)
    private val bob = SignalProtocolAddress("7108a872-a0a9-46d5-a994-c2a53692d31f", 1)
    private fun ByteArray.b64() = Base64.encodeToString(this, Base64.NO_WRAP)
    private fun JSONObject.bytes(name: String) = Base64.decode(getString(name), Base64.NO_WRAP)

    @Test fun exportAndroidHandshake() {
        val aliceKeys = IdentityKeyPair.generate()
        val bobKeys = IdentityKeyPair.generate()
        val sender = InMemorySignalProtocolStore(aliceKeys, 101)
        val preKey = ECKeyPair.generate()
        val signed = ECKeyPair.generate()
        val kyber = KEMKeyPair.generate(KEMKeyType.KYBER_1024)
        val signedSignature = bobKeys.privateKey.calculateSignature(signed.publicKey.serialize())
        val kyberSignature = bobKeys.privateKey.calculateSignature(kyber.publicKey.serialize())
        val bundle = PreKeyBundle(202, 1, 1, preKey.publicKey, 2, signed.publicKey, signedSignature, bobKeys.publicKey, 3, kyber.publicKey, kyberSignature)
        SessionBuilder(sender, bob, alice).process(bundle)
        val ciphertext = SessionCipher(sender, alice, bob).encrypt("Coffee by the river? ☕ مرحباً".toByteArray())
        assertEquals(CiphertextMessage.PREKEY_TYPE, ciphertext.type)
        val fixture = JSONObject().put("purpose", "SYNTHETIC TEST KEYS — NEVER USE FOR REAL ACCOUNTS")
            .put("version", "0.105.0").put("aliceAddress", alice.name).put("bobAddress", bob.name)
            .put("aliceIdentity", aliceKeys.serialize().b64()).put("aliceRegistration", 101)
            .put("bobIdentity", bobKeys.serialize().b64()).put("bobRegistration", 202)
            .put("bobPreKey", PreKeyRecord(1, preKey).serialize().b64())
            .put("bobSignedPreKey", SignedPreKeyRecord(2, System.currentTimeMillis(), signed, signedSignature).serialize().b64())
            .put("bobKyberPreKey", KyberPreKeyRecord(3, System.currentTimeMillis(), kyber, kyberSignature).serialize().b64())
            .put("aliceSession", sender.loadSession(bob).serialize().b64())
            .put("ciphertext", ciphertext.serialize().b64())
        File(directory, "android-handshake.json").writeText(fixture.toString(2))
    }

    @Test fun importSwiftReplies() {
        check(InstrumentationRegistry.getArguments().getString("vipiSwiftReplyReady") == "true") { "Run the Swift interoperability test and transfer its reply first." }
        val fixture = JSONObject(File(directory, "android-handshake.json").readText())
        val replies = JSONObject(File(directory, "swift-replies.json").readText()).getJSONArray("messages")
        val sender = InMemorySignalProtocolStore(IdentityKeyPair(fixture.bytes("aliceIdentity")), fixture.getInt("aliceRegistration"))
        sender.storeSession(bob, SessionRecord(fixture.bytes("aliceSession")))
        sender.saveIdentity(bob, IdentityKeyPair(fixture.bytes("bobIdentity")).publicKey)
        val cipher = SessionCipher(sender, alice, bob)
        // Arrival order differs from send order; skipped message keys must still work.
        for (index in listOf(2, 0, 1)) {
            val bytes = Base64.decode(replies.getString(index), Base64.NO_WRAP)
            if (index == 2) {
                val altered = bytes.copyOf(); altered[altered.lastIndex] = (altered.last().toInt() xor 1).toByte()
                assertTrue(runCatching { cipher.decrypt(SignalMessage(altered)) }.isFailure)
            }
            assertEquals("Swift reply $index — río ☕", cipher.decrypt(SignalMessage(bytes)).toString(Charsets.UTF_8))
            assertTrue(runCatching { cipher.decrypt(SignalMessage(bytes)) }.isFailure)
        }
        File(directory, "signal-interop-receipt.json").writeText(JSONObject().put("libsignal", "0.105.0")
            .put("androidToSwift", "passed").put("swiftToAndroid", "passed").put("outOfOrder", "passed")
            .put("tampering", "rejected").put("replay", "rejected").toString(2))
    }
}
