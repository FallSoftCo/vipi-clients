package co.fallsoft.vipi

import java.security.MessageDigest
import java.util.UUID
import org.signal.libsignal.protocol.IdentityKey
import org.signal.libsignal.protocol.fingerprint.NumericFingerprintGenerator

internal data class SecurityNumber(val digits: String, val binding: String, val verified: Boolean) {
    val groups
        get() = digits.chunked(5)

    companion object {
        fun make(
            local: UUID,
            localKey: IdentityKey,
            peer: UUID,
            peerKey: IdentityKey,
            receipt: String?,
        ): SecurityNumber {
            val digits =
                NumericFingerprintGenerator(5200)
                    .createFor(
                        2,
                        local.toString().toByteArray(Charsets.UTF_8),
                        localKey,
                        peer.toString().toByteArray(Charsets.UTF_8),
                        peerKey,
                    )
                    .displayableFingerprint
                    .displayText
            check(digits.length == 60 && digits.all { it in '0'..'9' })
            val digest = MessageDigest.getInstance("SHA-256")
            digest.update(
                "vipi-identity-verification-v1\u0000$local\u0000$peer\u0000"
                    .toByteArray(Charsets.UTF_8)
            )
            digest.update(localKey.serialize())
            digest.update(peerKey.serialize())
            val binding = digest.digest().joinToString("") { "%02x".format(it) }
            return SecurityNumber(digits, binding, receipt == binding)
        }
    }
}
