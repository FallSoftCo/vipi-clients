import Foundation
import CryptoKit
import LibSignalClient

struct SignedPublicKey: Codable { let id: UInt32; let key: Data; let signature: Data }
struct OneTimePublicKey: Codable { let id: UInt32; let ec_key: Data; let key: Data; let signature: Data }
struct KeyPublication: Codable {
    let revision: UInt32; let registration_id: UInt32; let identity_key: Data
    let signed: SignedPublicKey; let one_time: [OneTimePublicKey]
}
struct ClaimedKeys: Codable {
    let request_id: UUID; let user_id: UUID; let device_id: UUID; let signal_device_id: UInt32
    let registration_id: UInt32; let identity_key: Data; let signed: SignedPublicKey; let one_time: OneTimePublicKey
}

/// Private keys and the exact pending publication are persisted before network
/// activity. All libsignal mutations share the message vault transaction.
final class SignalKeys {
    enum Failure: Error { case invalidBundle, revisionConflict, existingSession }
    private let store: DurableSignalStore
    private var vault: MessageVault { store.vault }
    private let context = NullContext()
    init(store: DurableSignalStore) { self.store = store }
    private func integer(_ name: String) throws -> UInt32 {
        guard let value = try vault.get("key-directory", name) else { return 0 }
        guard let result = UInt32(String(decoding: value, as: UTF8.self)) else { throw Failure.revisionConflict }
        return result
    }
    private func setInteger(_ name: String, _ value: UInt32) throws { try vault.put("key-directory", name, Data(String(value).utf8)) }
    func publication(now: Int64, count: Int = 20) throws -> KeyPublication {
        try vault.transaction {
            guard now >= 0, (1...20).contains(count) else { throw Failure.invalidBundle }
            if let data = try vault.get("key-directory", "pending") { return try JSONDecoder().decode(KeyPublication.self, from: data) }
            let identity = try store.identityKeyPair(context: context)
            let previousSigned = try integer("signed")
            let old = previousSigned == 0 ? nil : try store.loadSignedPreKey(id: previousSigned, context: context)
            let signed: SignedPreKeyRecord
            if let old, UInt64(now) < old.timestamp + 7 * 86_400_000 { signed = old }
            else {
                guard previousSigned < Int32.max else { throw Failure.revisionConflict }
                let key = PrivateKey.generate(), id = previousSigned + 1
                signed = try SignedPreKeyRecord(id: id, timestamp: UInt64(now), privateKey: key, signature: identity.privateKey.generateSignature(message: key.publicKey.serialize()))
                try store.storeSignedPreKey(signed, id: id, context: context); try setInteger("signed", id)
            }
            let high = try integer("high"), revision = try integer("revision")
            guard high <= UInt32(Int32.max) - UInt32(count), revision < Int32.max else { throw Failure.revisionConflict }
            var keys: [OneTimePublicKey] = []
            for id in (high + 1)...(high + UInt32(count)) {
                let ec = PrivateKey.generate(), kem = KEMKeyPair.generate()
                let signature = identity.privateKey.generateSignature(message: kem.publicKey.serialize())
                try store.storePreKey(PreKeyRecord(id: id, privateKey: ec), id: id, context: context)
                try store.storeKyberPreKey(KyberPreKeyRecord(id: id, timestamp: UInt64(now), keyPair: kem, signature: signature), id: id, context: context)
                keys.append(OneTimePublicKey(id: id, ec_key: ec.publicKey.serialize(), key: kem.publicKey.serialize(), signature: signature))
            }
            let body = KeyPublication(revision: revision + 1, registration_id: try store.localRegistrationId(context: context), identity_key: identity.identityKey.serialize(),
                signed: SignedPublicKey(id: signed.id, key: try signed.publicKey().serialize(), signature: signed.signature), one_time: keys)
            try setInteger("high", high + UInt32(count))
            try vault.put("key-directory", "pending", JSONEncoder().encode(body))
            return body
        }
    }
    func published(revision: UInt32) throws {
        try vault.transaction {
            if try integer("revision") == revision { return }
            guard let data = try vault.get("key-directory", "pending"), try JSONDecoder().decode(KeyPublication.self, from: data).revision == revision else { throw Failure.revisionConflict }
            try setInteger("revision", revision); try vault.remove("key-directory", "pending")
        }
    }
    func establish(peer: UUID, requestID: UUID, response r: ClaimedKeys) throws -> UUID {
        try vault.transaction {
            guard peer != vault.account, r.user_id == peer, r.request_id == requestID, r.signal_device_id == 1,
                (1...16380).contains(r.registration_id), (1...UInt32(Int32.max)).contains(r.signed.id), (1...UInt32(Int32.max)).contains(r.one_time.id),
                r.identity_key.count == 33, r.signed.key.count == 33, r.signed.signature.count == 64,
                r.one_time.ec_key.count == 33, r.one_time.key.count == 1569, r.one_time.signature.count == 64 else { throw Failure.invalidBundle }
            let bundle = try PreKeyBundle(registrationId: r.registration_id, deviceId: 1, prekeyId: r.one_time.id, prekey: PublicKey(r.one_time.ec_key),
                signedPrekeyId: r.signed.id, signedPrekey: PublicKey(r.signed.key), signedPrekeySignature: r.signed.signature, identity: IdentityKey(bytes: r.identity_key),
                kyberPrekeyId: r.one_time.id, kyberPrekey: KEMPublicKey(r.one_time.key), kyberPrekeySignature: r.one_time.signature)
            var digest = SHA256()
            digest.update(data: Data("\(peer.uuidString.lowercased())/\(r.device_id.uuidString.lowercased())/\(r.registration_id)/\(r.signed.id)/\(r.one_time.id)/".utf8))
            for data in [r.identity_key, r.signed.key, r.signed.signature, r.one_time.ec_key, r.one_time.key, r.one_time.signature] { digest.update(data: data) }
            let fingerprint = Data(digest.finalize()), request = requestID.uuidString.lowercased()
            if let saved = try vault.get("key-claim", request) {
                guard saved == fingerprint else { throw Failure.invalidBundle }
                return r.device_id
            }
            let address = try ProtocolAddress(name: peer.uuidString.lowercased(), deviceId: 1)
            guard try store.loadSession(for: address, context: context) == nil else { throw Failure.existingSession }
            try processPreKeyBundle(bundle, for: address, ourAddress: ProtocolAddress(name: vault.account.uuidString.lowercased(), deviceId: 1), sessionStore: store, identityStore: store, context: context)
            try vault.put("peer-device", peer.uuidString.lowercased(), Data(r.device_id.uuidString.lowercased().utf8))
            try vault.put("key-claim", request, fingerprint)
            return r.device_id
        }
    }
}
