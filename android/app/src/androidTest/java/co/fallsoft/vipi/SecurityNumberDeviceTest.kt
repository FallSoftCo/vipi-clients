package co.fallsoft.vipi

import android.content.ContextWrapper
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.security.KeyStore
import java.util.UUID
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.signal.libsignal.protocol.IdentityKey
import org.signal.libsignal.protocol.IdentityKeyPair
import org.signal.libsignal.protocol.SignalProtocolAddress

@RunWith(AndroidJUnit4::class)
class SecurityNumberDeviceTest {
    // Public Signal v0.105.0 NumericFingerprintGeneratorTest vectors,
    // Signal Messenger, LLC, AGPL-3.0-only; no user keys or phone numbers.
    private fun key(hex: String) =
        IdentityKey(hex.chunked(2).map { it.toInt(16).toByte() }.toByteArray())

    @Test
    fun crossPlatformVectorAndIdentifierBinding() {
        val alice = UUID.fromString("10000000-0000-4000-8000-000000000001")
        val bob = UUID.fromString("10000000-0000-4000-8000-000000000002")
        val a = key("0506863bc66d02b40d27b8d49ca7c09e9239236f9d7d25d6fcca5ce13c7064d868")
        val b = key("05f781b6fb32fed9ba1cf2de978d4d5da28dc34046ae814402b5c0dbd96fda907b")
        val start = System.nanoTime()
        val first = SecurityNumber.make(alice, a, bob, b, null)
        val ms = (System.nanoTime() - start) / 1_000_000.0
        val second = SecurityNumber.make(bob, b, alice, a, null)
        assertEquals(first.digits, second.digits)
        assertEquals(12, first.groups.size)
        assertTrue(first.groups.all { it.length == 5 })
        assertFalse(first.verified)
        assertNotEquals(
            first.digits,
            SecurityNumber.make(alice, a, UUID.randomUUID(), b, null).digits,
        )
        assertNotEquals(first.digits, SecurityNumber.make(alice, a, bob, a, null).digits)
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        File(context.filesDir, "security-number-vector-android.json")
            .writeText(
                JSONObject()
                    .put("purpose", "SYNTHETIC PUBLIC KEY VECTOR")
                    .put("digits", first.digits)
                    .put("binding_hex", first.binding)
                    .put("generation_ms", ms)
                    .put("iterations", 5200)
                    .put("version", 2)
                    .toString()
            )
    }

    @Test
    fun verificationPersistsAndNeverSurvivesDifferentKeys() {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(base.cacheDir, "security-number-${UUID.randomUUID()}").apply { mkdirs() }
        val context =
            object : ContextWrapper(base) {
                override fun getFilesDir() = File(root, "files").apply { mkdirs() }

                override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() }
            }
        val account = UUID.randomUUID()
        val peer = UUID.randomUUID()
        try {
            MessageVault(context, account).use { vault ->
                val core = MessagingCore(vault)
                assertNull(core.securityNumber(peer))
                vault.transaction {
                    core.store.saveIdentity(
                        SignalProtocolAddress(peer.toString(), 1),
                        IdentityKeyPair.generate().publicKey,
                    )
                }
                val original = requireNotNull(core.securityNumber(peer))
                assertFalse(original.verified)
                core.setIdentityVerified(true, peer, original)
                MessageVault(context, account).use { second ->
                    val reopened = MessagingCore(second)
                    assertTrue(requireNotNull(reopened.securityNumber(peer)).verified)
                    core.setIdentityVerified(false, peer, original)
                    assertFalse(requireNotNull(reopened.securityNumber(peer)).verified)
                }
                core.setIdentityVerified(true, peer, original)
                // Explicit replacement simulation, never used by production trust callbacks.
                vault.transaction {
                    vault.put(
                        "identity",
                        "$peer/1",
                        IdentityKeyPair.generate().publicKey.serialize(),
                    )
                }
                val changed = requireNotNull(core.securityNumber(peer))
                assertFalse(changed.verified)
                assertNotEquals(original.digits, changed.digits)
                assertTrue(runCatching { core.setIdentityVerified(true, peer, original) }.isFailure)
                assertTrue(
                    runCatching {
                        core.setIdentityVerified(
                            true,
                            peer,
                            changed.copy(digits = "0".repeat(60)),
                        )
                    }
                        .isFailure
                )
                core.setIdentityVerified(true, peer, changed)
                vault.transaction {
                    vault.put("local", "identity", IdentityKeyPair.generate().serialize())
                }
                assertFalse(requireNotNull(core.securityNumber(peer)).verified)
                assertTrue(runCatching { core.setIdentityVerified(true, peer, changed) }.isFailure)
            }
        } finally {
            root.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply {
                load(null)
                deleteEntry("co.fallsoft.vipi.messages.$account")
            }
        }
    }
}
