package co.fallsoft.vipi

import android.util.Base64
import java.time.Instant
import java.util.UUID
import org.json.JSONObject
import org.signal.libsignal.protocol.SessionCipher
import org.signal.libsignal.protocol.SignalProtocolAddress
import org.signal.libsignal.protocol.message.PreKeySignalMessage
import org.signal.libsignal.protocol.message.SignalMessage

internal class PeerIdentityChanged(val peer: UUID) : Exception("Peer encryption identity changed")

internal class RetiredPeerMessage : Exception("Message belongs to a retired peer device")

internal data class RoutedMessage(
    val envelope: ChatEnvelope,
    val senderDevice: UUID,
    val recipientDevice: UUID,
    val attachmentIds: List<UUID> = emptyList(),
    val featureEvent: Boolean = false,
) {
    fun sendJSON() =
        JSONObject()
            .put("id", envelope.id)
            .put("recipient_id", envelope.recipient)
            .put("recipient_device_id", recipientDevice)
            .put("created_at", Instant.ofEpochMilli(envelope.createdAt).toString())
            .put("cipher_type", envelope.type)
            .put("ciphertext", Base64.encodeToString(envelope.ciphertext, Base64.NO_WRAP))
            .also { body ->
                if (featureEvent) body.put("required_chat_features_version", 1)
                if (attachmentIds.isNotEmpty())
                    body.put(
                        "attachment_ids",
                        org.json.JSONArray(attachmentIds.map(UUID::toString)),
                    )
            }

    companion object {
        fun received(value: JSONObject, account: UUID) =
            RoutedMessage(
                ChatEnvelope(
                    UUID.fromString(value.getString("id")),
                    UUID.fromString(value.getString("sender_id")),
                    account,
                    Instant.parse(value.getString("created_at")).toEpochMilli(),
                    value.getInt("cipher_type"),
                    Base64.decode(value.getString("ciphertext"), Base64.NO_WRAP),
                ),
                UUID.fromString(value.getString("sender_device_id")),
                UUID.fromString(value.getString("recipient_device_id")),
            )
    }
}

internal class MessagingCore(private val vault: MessageVault) {
    val store = DurableSignalStore(vault)
    val keys = SignalKeys(store)
    val journal = MessageJournal(vault)
    val device = DeviceCredential.load(vault)
    private val local = SignalProtocolAddress(vault.account.toString(), 1)

    fun hasSession(peer: UUID) = vault.transaction {
        store.containsSession(SignalProtocolAddress(peer.toString(), 1))
    }

    fun securityNumber(peer: UUID): SecurityNumber? = vault.transaction {
        securityNumberInTransaction(peer)
    }

    private fun securityNumberInTransaction(peer: UUID): SecurityNumber? {
        if (peer == vault.account) return null
        val remote = store.getIdentity(SignalProtocolAddress(peer.toString(), 1)) ?: return null
        return SecurityNumber.make(
            vault.account,
            store.identityKeyPair.publicKey,
            peer,
            remote,
            vault.get("identity-verification", peer.toString())?.toString(Charsets.UTF_8),
        )
    }

    fun setIdentityVerified(verified: Boolean, peer: UUID, compared: SecurityNumber) =
        vault.transaction {
            val current = securityNumberInTransaction(peer)
            check(
                current != null &&
                    current.binding == compared.binding &&
                    current.digits == compared.digits
            ) {
                "Encryption identity changed; compare again"
            }
            if (verified)
                vault.put(
                    "identity-verification",
                    peer.toString(),
                    current.binding.toByteArray(Charsets.UTF_8),
                )
            else vault.remove("identity-verification", peer.toString())
        }

    fun queue(
        id: UUID,
        peer: UUID,
        text: String,
        createdAt: Long,
        now: Long,
        attachments: List<AttachmentManifest> = emptyList(),
        features: ChatFeatures = ChatFeatures.EMPTY,
    ): RoutedMessage {
        val envelope =
            journal.queue(id, peer, text, createdAt, now, attachments, features) { clear ->
                val target =
                    requireNotNull(vault.get("peer-device", peer.toString())) {
                        "Recipient keys required"
                    }
                val cipher =
                    SessionCipher(store, local, SignalProtocolAddress(peer.toString(), 1))
                        .encrypt(clear)
                vault.put("outgoing-route", id.toString(), target)
                cipher.type to cipher.serialize()
            }
        val target = vault.transaction {
            UUID.fromString(
                requireNotNull(vault.get("outgoing-route", id.toString())).toString(Charsets.UTF_8)
            )
        }
        val saved = requireNotNull(journal.outgoing(id))
        return RoutedMessage(
            envelope,
            device.id,
            target,
            saved.attachments.flatMap { it.blobIds },
            saved.features.reaction != null,
        )
    }

    fun receive(value: RoutedMessage, now: Long): StoredChat {
        require(value.recipientDevice == device.id)
        val peer = value.envelope.sender.toString()
        val sender = value.senderDevice.toString().toByteArray()
        return journal.receive(
            value.envelope,
            now,
            validateRoute = {
                vault.get("incoming-route", value.envelope.id.toString())?.let {
                    require(it.contentEquals(sender)) { "Message route changed" }
                }
                // Durable duplicates remain governed by their original route and authenticated
                // envelope fingerprint.
                if (vault.get("incoming", value.envelope.id.toString()) == null) {
                    if (vault.get("retired-peer-device", "$peer/${value.senderDevice}") != null)
                        throw RetiredPeerMessage()
                    vault.get("peer-device", peer)?.let {
                        if (!it.contentEquals(sender))
                            throw PeerIdentityChanged(value.envelope.sender)
                    }
                }
            },
        ) { type, bytes ->
            val cipher = SessionCipher(store, local, SignalProtocolAddress(peer, 1))
            val clear =
                try {
                    if (type == 3) cipher.decrypt(PreKeySignalMessage(bytes))
                    else cipher.decrypt(SignalMessage(bytes))
                } catch (_: org.signal.libsignal.protocol.UntrustedIdentityException) {
                    throw PeerIdentityChanged(value.envelope.sender)
                }
            vault.put("peer-device", peer, sender)
            vault.put("incoming-route", value.envelope.id.toString(), sender)
            clear
        }
    }
}
