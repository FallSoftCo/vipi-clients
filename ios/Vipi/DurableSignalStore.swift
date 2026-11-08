import Foundation
import CryptoKit
import LibSignalClient

/// Caller must enclose protocol operations and message persistence in one vault
/// transaction. Deserialize on every read so rollback cannot leave a mutated cache.
final class DurableSignalStore: IdentityKeyStore, PreKeyStore, SignedPreKeyStore, KyberPreKeyStore, SessionStore, SenderKeyStore {
    enum Failure: Error { case identityChanged, retiredDevice, invalidAddress }
    let vault: MessageVault
    init(vault: MessageVault) throws {
        self.vault = vault
        try vault.transaction {
            if try vault.get("local", "initialized") == nil {
                guard try vault.get("local", "identity") == nil, try vault.get("local", "registration") == nil else { throw MessageVault.Failure.invalidRecord }
                try vault.put("local", "identity", IdentityKeyPair.generate().serialize())
                try vault.put("local", "registration", Data(String(UInt32.random(in: 1...16380)).utf8))
                try vault.put("local", "initialized", Data([1]))
            }
            _ = try identityKeyPair(context: NullContext()); _ = try localRegistrationId(context: NullContext())
        }
    }
    private func address(_ value: ProtocolAddress) throws -> String {
        guard let uuid = UUID(uuidString: value.name) else { throw Failure.invalidAddress }
        return "\(uuid.uuidString.lowercased())/\(value.deviceId)"
    }
    private func required(_ kind: String, _ id: String) throws -> Data {
        guard let data = try vault.get(kind, id) else { throw SignalError.invalidKeyIdentifier("Missing local key record") }
        return data
    }
    func identityKeyPair(context: StoreContext) throws -> IdentityKeyPair { try IdentityKeyPair(bytes: required("local", "identity")) }
    func localRegistrationId(context: StoreContext) throws -> UInt32 {
        guard let value = UInt32(String(decoding: try required("local", "registration"), as: UTF8.self)), (1...16380).contains(value) else { throw MessageVault.Failure.invalidRecord }
        return value
    }
    func identity(for value: ProtocolAddress, context: StoreContext) throws -> IdentityKey? { try vault.get("identity", address(value)).map { try IdentityKey(bytes: $0) } }
    func isTrustedIdentity(_ key: IdentityKey, for value: ProtocolAddress, direction: Direction, context: StoreContext) throws -> Bool {
        try identity(for: value, context: context).map { $0 == key } ?? true
    }
    func saveIdentity(_ key: IdentityKey, for value: ProtocolAddress, context: StoreContext) throws -> IdentityChange {
        guard try isTrustedIdentity(key, for: value, direction: .sending, context: context) else { throw Failure.identityChanged }
        try vault.put("identity", address(value), key.serialize())
        return .newOrUnchanged
    }
    func loadSession(for value: ProtocolAddress, context: StoreContext) throws -> SessionRecord? { try vault.get("session", address(value)).map { try SessionRecord(bytes: $0) } }
    func loadExistingSessions(for values: [ProtocolAddress], context: StoreContext) throws -> [SessionRecord] {
        try values.map { value in
            guard let record = try loadSession(for: value, context: context) else { throw SignalError.sessionNotFound("Missing session") }
            return record
        }
    }
    func storeSession(_ record: SessionRecord, for value: ProtocolAddress, context: StoreContext) throws { try vault.put("session", address(value), record.serialize()) }
    func loadPreKey(id: UInt32, context: StoreContext) throws -> PreKeyRecord { try PreKeyRecord(bytes: required("prekey", String(id))) }
    func storePreKey(_ record: PreKeyRecord, id: UInt32, context: StoreContext) throws { try vault.put("prekey", String(id), record.serialize()) }
    func removePreKey(id: UInt32, context: StoreContext) throws { try vault.remove("prekey", String(id)) }
    func loadSignedPreKey(id: UInt32, context: StoreContext) throws -> SignedPreKeyRecord { try SignedPreKeyRecord(bytes: required("signed-prekey", String(id))) }
    func storeSignedPreKey(_ record: SignedPreKeyRecord, id: UInt32, context: StoreContext) throws { try vault.put("signed-prekey", String(id), record.serialize()) }
    func loadKyberPreKey(id: UInt32, context: StoreContext) throws -> KyberPreKeyRecord { try KyberPreKeyRecord(bytes: required("kyber-prekey", String(id))) }
    func storeKyberPreKey(_ record: KyberPreKeyRecord, id: UInt32, context: StoreContext) throws { try vault.put("kyber-prekey", String(id), record.serialize()) }
    func storeLastResortKyberPreKey(_ record: KyberPreKeyRecord, id: UInt32, context: StoreContext) throws {
        try storeKyberPreKey(record, id: id, context: context)
        try vault.put("kyber-last-resort", String(id), Data([1]))
    }
    func markKyberPreKeyUsed(id: UInt32, signedPreKeyId: UInt32, baseKey: PublicKey, context: StoreContext) throws {
        if try vault.get("kyber-last-resort", String(id)) == nil { try vault.remove("kyber-prekey", String(id)); return }
        let digest = SHA256.hash(data: baseKey.serialize()).map { String(format: "%02x", $0) }.joined()
        let usage = "\(id)/\(signedPreKeyId)/\(digest)"
        guard try vault.get("kyber-used", usage) == nil else { throw SignalError.invalidMessage("Previously used base key") }
        try vault.put("kyber-used", usage, Data([1]))
    }
    func storeSenderKey(from sender: ProtocolAddress, distributionId: UUID, record: SenderKeyRecord, context: StoreContext) throws {
        try vault.put("sender-key", "\(address(sender))/\(distributionId.uuidString.lowercased())", record.serialize())
    }
    func loadSenderKey(from sender: ProtocolAddress, distributionId: UUID, context: StoreContext) throws -> SenderKeyRecord? {
        try vault.get("sender-key", "\(address(sender))/\(distributionId.uuidString.lowercased())").map { try SenderKeyRecord(bytes: $0) }
    }
}
