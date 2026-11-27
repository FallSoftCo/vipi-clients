package co.fallsoft.vipi

import java.security.MessageDigest
import java.security.SecureRandom
import java.util.UUID
import org.signal.libsignal.protocol.*
import org.signal.libsignal.protocol.ecc.ECPublicKey
import org.signal.libsignal.protocol.groups.state.SenderKeyRecord
import org.signal.libsignal.protocol.state.*

/**
 * Every callback requires the caller's MessageVault transaction. No mutable cache survives
 * rollback. Identity changes fail closed in both directions.
 */
internal class DurableSignalStore(val vault: MessageVault) : SignalProtocolStore {
    init {
        vault.transaction {
            if (vault.get("local", "initialized") == null) {
                check(
                    vault.get("local", "identity") == null &&
                        vault.get("local", "registration") == null
                )
                vault.put("local", "identity", IdentityKeyPair.generate().serialize())
                vault.put(
                    "local",
                    "registration",
                    (SecureRandom().nextInt(16380) + 1).toString().toByteArray(),
                )
                vault.put("local", "initialized", byteArrayOf(1))
            }
            getIdentityKeyPair()
            getLocalRegistrationId()
        }
    }

    private fun address(value: SignalProtocolAddress): String =
        "${UUID.fromString(value.name)}/${value.deviceId}"

    private fun required(kind: String, id: String): ByteArray =
        vault.get(kind, id) ?: throw InvalidKeyIdException("Missing local key record")

    override fun getIdentityKeyPair() = IdentityKeyPair(required("local", "identity"))

    override fun getLocalRegistrationId() =
        required("local", "registration").toString(Charsets.UTF_8).toInt().also {
            check(it in 1..16380)
        }

    override fun getIdentity(value: SignalProtocolAddress): IdentityKey? =
        vault.get("identity", address(value))?.let { IdentityKey(it) }

    override fun isTrustedIdentity(
        value: SignalProtocolAddress,
        key: IdentityKey,
        direction: IdentityKeyStore.Direction,
    ): Boolean = getIdentity(value)?.let { it == key } ?: true

    override fun saveIdentity(
        value: SignalProtocolAddress,
        key: IdentityKey,
    ): IdentityKeyStore.IdentityChange {
        check(getIdentity(value)?.let { it == key } ?: true) {
            "Identity change requires explicit verification"
        }
        vault.put("identity", address(value), key.serialize())
        return IdentityKeyStore.IdentityChange.NEW_OR_UNCHANGED
    }

    override fun loadSession(value: SignalProtocolAddress): SessionRecord? =
        vault.get("session", address(value))?.let(::SessionRecord)

    override fun loadExistingSessions(values: List<SignalProtocolAddress>): List<SessionRecord> =
        values.map {
            loadSession(it) ?: throw NoSessionException(it, "Missing session")
        }

    override fun storeSession(value: SignalProtocolAddress, record: SessionRecord) =
        vault.put("session", address(value), record.serialize())

    override fun containsSession(value: SignalProtocolAddress) =
        vault.get("session", address(value)) != null

    override fun deleteSession(value: SignalProtocolAddress) =
        vault.remove("session", address(value))

    override fun getSubDeviceSessions(name: String): List<Int> =
        vault
            .ids("session")
            .filter { it.startsWith("${UUID.fromString(name)}/") }
            .map { it.substringAfter('/').toInt() }
            .filter { it != 1 }

    override fun deleteAllSessions(name: String) {
        vault
            .ids("session")
            .filter { it.startsWith("${UUID.fromString(name)}/") }
            .forEach { vault.remove("session", it) }
    }

    override fun loadPreKey(id: Int) = PreKeyRecord(required("prekey", id.toString()))

    override fun containsPreKey(id: Int) = vault.get("prekey", id.toString()) != null

    override fun storePreKey(id: Int, record: PreKeyRecord) =
        vault.put("prekey", id.toString(), record.serialize())

    override fun removePreKey(id: Int) = vault.remove("prekey", id.toString())

    override fun loadSignedPreKey(id: Int) =
        SignedPreKeyRecord(required("signed-prekey", id.toString()))

    override fun loadSignedPreKeys() =
        vault.ids("signed-prekey").map { loadSignedPreKey(it.toInt()) }

    override fun containsSignedPreKey(id: Int) = vault.get("signed-prekey", id.toString()) != null

    override fun storeSignedPreKey(id: Int, record: SignedPreKeyRecord) =
        vault.put("signed-prekey", id.toString(), record.serialize())

    override fun removeSignedPreKey(id: Int) = vault.remove("signed-prekey", id.toString())

    override fun loadKyberPreKey(id: Int) =
        KyberPreKeyRecord(required("kyber-prekey", id.toString()))

    override fun loadKyberPreKeys() = vault.ids("kyber-prekey").map { loadKyberPreKey(it.toInt()) }

    override fun containsKyberPreKey(id: Int) = vault.get("kyber-prekey", id.toString()) != null

    override fun storeKyberPreKey(id: Int, record: KyberPreKeyRecord) =
        vault.put("kyber-prekey", id.toString(), record.serialize())

    fun storeLastResortKyberPreKey(id: Int, record: KyberPreKeyRecord) {
        storeKyberPreKey(id, record)
        vault.put("kyber-last-resort", id.toString(), byteArrayOf(1))
    }

    override fun markKyberPreKeyUsed(id: Int, signedPreKeyId: Int, baseKey: ECPublicKey) {
        if (vault.get("kyber-last-resort", id.toString()) == null) {
            vault.remove("kyber-prekey", id.toString())
            return
        }
        val digest =
            MessageDigest.getInstance("SHA-256").digest(baseKey.serialize()).joinToString("") {
                "%02x".format(it)
            }
        val usage = "$id/$signedPreKeyId/$digest"
        if (vault.get("kyber-used", usage) != null)
            throw ReusedBaseKeyException("Previously used base key")
        vault.put("kyber-used", usage, byteArrayOf(1))
    }

    override fun storeSenderKey(
        sender: SignalProtocolAddress,
        distributionId: UUID,
        record: SenderKeyRecord,
    ) = vault.put("sender-key", "${address(sender)}/$distributionId", record.serialize())

    override fun loadSenderKey(
        sender: SignalProtocolAddress,
        distributionId: UUID,
    ): SenderKeyRecord? =
        vault.get("sender-key", "${address(sender)}/$distributionId")?.let(::SenderKeyRecord)
}
