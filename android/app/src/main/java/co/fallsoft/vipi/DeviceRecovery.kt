package co.fallsoft.vipi

import android.util.Base64
import org.json.JSONObject
import org.signal.libsignal.protocol.IdentityKeyPair
import java.security.SecureRandom
import java.util.UUID

/** A takeover intent survives an uncertain HTTP response; it is never an automatic takeover. */
internal object DeviceRecovery {
    fun candidate(vault: MessageVault, previous: DeviceCredential): DeviceCredential = vault.transaction {
        vault.get("local", "replacement-device")?.let {
            val row = JSONObject(it.toString(Charsets.UTF_8)); require(row.getString("from") == previous.id.toString())
            return@transaction DeviceCredential(UUID.fromString(row.getString("id")), row.getString("secret"))
        }
        val secret = Base64.encodeToString(ByteArray(32).also(SecureRandom()::nextBytes), Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
        val next = DeviceCredential(UUID.randomUUID(), secret)
        vault.put("local", "replacement-device", JSONObject().put("from", previous.id).put("id", next.id).put("secret", next.secret).toString().toByteArray())
        next
    }

    fun commit(vault: MessageVault, previous: DeviceCredential, next: DeviceCredential) = vault.transaction {
        val pending = JSONObject(requireNotNull(vault.get("local", "replacement-device")).toString(Charsets.UTF_8))
        require(pending.getString("from") == previous.id.toString() && pending.getString("id") == next.id.toString() && pending.getString("secret") == next.secret)
        val installed = JSONObject(requireNotNull(vault.get("local", "service-device")).toString(Charsets.UTF_8))
        require(installed.getString("id") == previous.id.toString())
        val identity = IdentityKeyPair.generate().serialize()
        val registration = (SecureRandom().nextInt(16380) + 1).toString().toByteArray()
        for (id in vault.ids("pending")) {
            val item = StoredChat.parse(requireNotNull(vault.get("outgoing", id)))
            if (item.state in setOf("queued", "accepted")) vault.put("outgoing", id, item.copy(state = "failed").encode())
            vault.remove("pending", id)
        }
        for (id in vault.ids("draft")) {
            val item = DraftChat.parse(requireNotNull(vault.get("draft", id)))
            if (item.state == "queued") vault.put("draft", id, item.copy(state = "cancelled").encode())
        }
        // Remote identity pins/device bindings also survive; our new keys do not reset peer trust.
        for (kind in listOf("local", "session", "identity-verification", "prekey", "signed-prekey",
            "kyber-prekey", "kyber-last-resort", "kyber-used", "sender-key", "key-directory",
            "pending-claim", "pending-recovery", "receipt")) vault.ids(kind).forEach { vault.remove(kind, it) }
        vault.put("local", "service-device", JSONObject().put("id", next.id).put("secret", next.secret).toString().toByteArray())
        vault.put("local", "registered-device", next.id.toString().toByteArray())
        vault.put("local", "identity", identity); vault.put("local", "registration", registration)
        vault.put("local", "initialized", byteArrayOf(1))
    }
}
