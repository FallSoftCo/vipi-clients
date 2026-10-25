package co.fallsoft.vipi

import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import org.signal.libsignal.protocol.*
import org.signal.libsignal.protocol.ecc.ECKeyPair
import org.signal.libsignal.protocol.ecc.ECPublicKey
import org.signal.libsignal.protocol.kem.KEMKeyPair
import org.signal.libsignal.protocol.kem.KEMKeyType
import org.signal.libsignal.protocol.kem.KEMPublicKey
import org.signal.libsignal.protocol.state.*
import java.security.MessageDigest
import java.util.UUID

/** Private keys and an exact upload retry are committed before any HTTP request.
 * No networking occurs inside the vault transaction. */
internal class SignalKeys(private val store: DurableSignalStore) {
    private val vault get() = store.vault
    private fun ByteArray.b64() = Base64.encodeToString(this, Base64.NO_WRAP)
    private fun bytes(value: JSONObject, name: String, size: Int): ByteArray {
        val text = value.getString(name)
        val data = Base64.decode(text, Base64.NO_WRAP)
        require(data.size == size && data.b64() == text)
        return data
    }
    private fun integer(name: String) = vault.get("key-directory", name)?.toString(Charsets.UTF_8)?.toInt() ?: 0
    private fun setInteger(name: String, value: Int) = vault.put("key-directory", name, value.toString().toByteArray())

    fun publication(now: Long, count: Int = 20): JSONObject = vault.transaction {
        require(now >= 0 && count in 1..20)
        vault.get("key-directory", "pending")?.let { return@transaction JSONObject(it.toString(Charsets.UTF_8)) }
        val identity = store.identityKeyPair
        val previousSigned = integer("signed")
        val old = if (previousSigned == 0) null else store.loadSignedPreKey(previousSigned)
        val signed = if (old == null || now - old.timestamp >= 7 * 86_400_000L) {
            val pair = ECKeyPair.generate(); val id = Math.addExact(previousSigned, 1)
            SignedPreKeyRecord(id, now, pair, identity.privateKey.calculateSignature(pair.publicKey.serialize())).also {
                store.storeSignedPreKey(id, it); setInteger("signed", id)
            }
        } else old
        val first = Math.addExact(integer("high"), 1)
        val last = Math.addExact(first, count - 1)
        val keys = JSONArray()
        for (id in first..last) {
            val ec = ECKeyPair.generate(); val kem = KEMKeyPair.generate(KEMKeyType.KYBER_1024)
            val signature = identity.privateKey.calculateSignature(kem.publicKey.serialize())
            store.storePreKey(id, PreKeyRecord(id, ec))
            store.storeKyberPreKey(id, KyberPreKeyRecord(id, now, kem, signature))
            keys.put(JSONObject().put("id", id).put("ec_key", ec.publicKey.serialize().b64())
                .put("key", kem.publicKey.serialize().b64()).put("signature", signature.b64()))
        }
        val body = JSONObject().put("revision", Math.addExact(integer("revision"), 1))
            .put("registration_id", store.localRegistrationId).put("identity_key", identity.publicKey.serialize().b64())
            .put("signed", JSONObject().put("id", signed.id).put("key", signed.keyPair.publicKey.serialize().b64()).put("signature", signed.signature.b64()))
            .put("one_time", keys)
        setInteger("high", last)
        vault.put("key-directory", "pending", body.toString().toByteArray(Charsets.UTF_8))
        body
    }

    fun published(revision: Int) = vault.transaction {
        if (integer("revision") == revision) return@transaction
        val body = JSONObject(requireNotNull(vault.get("key-directory", "pending")).toString(Charsets.UTF_8))
        require(body.getInt("revision") == revision)
        setInteger("revision", revision); vault.remove("key-directory", "pending")
    }

    fun establish(peer: UUID, requestID: UUID, response: JSONObject): UUID = vault.transaction {
        require(UUID.fromString(response.getString("user_id")) == peer && peer != vault.account)
        require(UUID.fromString(response.getString("request_id")) == requestID && response.getInt("signal_device_id") == 1)
        val device = UUID.fromString(response.getString("device_id"))
        val registration = response.getInt("registration_id"); require(registration in 1..16380)
        val signed = response.getJSONObject("signed"); val one = response.getJSONObject("one_time")
        val sid = signed.getInt("id"); val kid = one.getInt("id"); require(sid > 0 && kid > 0)
        val bundle = PreKeyBundle(registration, 1, kid, ECPublicKey(bytes(one, "ec_key", 33)), sid,
            ECPublicKey(bytes(signed, "key", 33)), bytes(signed, "signature", 64), IdentityKey(bytes(response, "identity_key", 33)),
            kid, KEMPublicKey(bytes(one, "key", 1569)), bytes(one, "signature", 64))
        // Digest semantic fields, not JSON property order. Persist alongside the
        // resulting ratchet so a delayed HTTP retry cannot reset its session.
        val digest = MessageDigest.getInstance("SHA-256")
        digest.update("$peer/$device/$registration/$sid/$kid/".toByteArray())
        listOf(bytes(response, "identity_key", 33), bytes(signed, "key", 33), bytes(signed, "signature", 64),
            bytes(one, "ec_key", 33), bytes(one, "key", 1569), bytes(one, "signature", 64)).forEach(digest::update)
        val fingerprint = digest.digest()
        vault.get("key-claim", requestID.toString())?.let { require(it.contentEquals(fingerprint)); return@transaction device }
        val address = SignalProtocolAddress(peer.toString(), 1)
        check(!store.containsSession(address)) { "A session already exists; do not reset it from the directory" }
        SessionBuilder(store, address, SignalProtocolAddress(vault.account.toString(), 1)).process(bundle)
        vault.put("peer-device", peer.toString(), device.toString().toByteArray())
        vault.put("key-claim", requestID.toString(), fingerprint)
        device
    }
}
