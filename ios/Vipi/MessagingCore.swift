import Foundation
import LibSignalClient

struct RoutedMessage {
    let envelope: ChatEnvelope; let senderDevice: UUID; let recipientDevice: UUID
    var attachmentIDs: [String] = []
    func sendData() throws -> Data {
        let date = ISO8601DateFormatter(); date.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        var body: [String: Any] = ["id": envelope.id.uuidString.lowercased(), "recipient_id": envelope.recipient.uuidString.lowercased(),
            "recipient_device_id": recipientDevice.uuidString.lowercased(), "created_at": date.string(from: Date(timeIntervalSince1970: Double(envelope.createdAt) / 1000)),
            "cipher_type": envelope.type, "ciphertext": envelope.ciphertext.base64EncodedString()]
        if !attachmentIDs.isEmpty { body["attachment_ids"] = attachmentIDs }
        return try JSONSerialization.data(withJSONObject: body)
    }
    struct Received: Decodable {
        let id: UUID; let sender_id: UUID; let sender_device_id: UUID; let recipient_device_id: UUID
        let created_at: String; let cipher_type: Int; let ciphertext: Data
        let group_id: UUID?; let group_epoch: Int?; let group_message_id: UUID?; let group_kind: String?
        var hasGroupContext: Bool { group_id != nil || group_epoch != nil || group_message_id != nil || group_kind != nil }
        func routed(account: UUID) throws -> RoutedMessage {
            guard !hasGroupContext else { throw MessageJournal.Failure.invalidMessage }
            let parser = ISO8601DateFormatter(); parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            var date = parser.date(from: created_at)
            if date == nil { parser.formatOptions = [.withInternetDateTime]; date = parser.date(from: created_at) }
            guard let date, date.timeIntervalSince1970 >= 0, date.timeIntervalSince1970 < 10_000_000_000 else { throw MessageJournal.Failure.invalidMessage }
            return RoutedMessage(envelope: ChatEnvelope(id: id, sender: sender_id, recipient: account,
                createdAt: Int64((date.timeIntervalSince1970 * 1000).rounded()), type: cipher_type, ciphertext: ciphertext), senderDevice: sender_device_id, recipientDevice: recipient_device_id)
        }
    }
}

struct OwnDeviceReplacement {
    let previousDevice: UUID
    let previousIdentity: Data
    let device: DeviceCredential
    let identity: Data
    let registration: UInt32

}

final class MessagingCore {
    private let vault: MessageVault
    let store: DurableSignalStore
    let keys: SignalKeys
    let journal: MessageJournal
    let device: DeviceCredential
    private let local: ProtocolAddress
    private let context = NullContext()
    init(vault: MessageVault) throws {
        self.vault = vault; store = try DurableSignalStore(vault: vault)
        keys = SignalKeys(store: store); journal = MessageJournal(vault: vault); device = try DeviceCredential.load(vault: vault)
        local = try ProtocolAddress(name: vault.account.uuidString.lowercased(), deviceId: 1)
    }
    func replacementCandidate() throws -> OwnDeviceReplacement {
        let prior = try vault.transaction { try store.identityKeyPair(context: context).serialize() }
        return OwnDeviceReplacement(previousDevice: device.id, previousIdentity: prior,
            device: try DeviceCredential.generate(), identity: IdentityKeyPair.generate().serialize(),
            registration: UInt32.random(in: 1...16380))
    }
    func confirmDeviceReplacement(_ candidate: OwnDeviceReplacement) throws {
        try vault.transaction {
            guard candidate.previousDevice == device.id, candidate.device.id != device.id, candidate.identity != candidate.previousIdentity,
                  try store.identityKeyPair(context: context).serialize() == candidate.previousIdentity,
                  (1...16380).contains(candidate.registration) else { throw DurableSignalStore.Failure.identityChanged }
            _ = try IdentityKeyPair(bytes: candidate.identity)
            let encoder = JSONEncoder(), decoder = JSONDecoder()
            for id in try vault.ids("pending") {
                if let bytes = try vault.get("outgoing", id) {
                    var saved = try decoder.decode(StoredChat.self, from: bytes)
                    if ["queued", "accepted"].contains(saved.state) {
                        saved.state = "failed"; try vault.put("outgoing", id, encoder.encode(saved))
                    }
                }
                try vault.remove("pending", id)
            }
            for id in try vault.ids("draft") {
                guard let bytes = try vault.get("draft", id) else { continue }
                var draft = try decoder.decode(DraftChat.self, from: bytes)
                if draft.state == "queued" { draft.state = "cancelled"; try vault.put("draft", id, encoder.encode(draft)) }
            }
            // Preserve peer identities/routes, global claim replay receipts and
            // history. Only local protocol state belongs to the replaced device.
            for kind in ["session", "prekey", "signed-prekey", "kyber-prekey", "kyber-last-resort", "kyber-used", "sender-key", "key-directory", "pending-claim", "pending-review-claim", "identity-verification", "receipt"] {
                for id in try vault.ids(kind) { try vault.remove(kind, id) }
            }
            try vault.put("local", "identity", candidate.identity)
            try vault.put("local", "registration", Data(String(candidate.registration).utf8))
            try vault.put("local", "service-device", encoder.encode(candidate.device))
            try vault.remove("local", "registered-device")
            try vault.put("local", "replacement-consent", Data(candidate.device.id.uuidString.lowercased().utf8))
        }
    }
    func hasSession(peer: UUID) throws -> Bool { try vault.transaction { try store.loadSession(for: ProtocolAddress(name: peer.uuidString.lowercased(), deviceId: 1), context: context) != nil } }
    func securityNumber(peer: UUID) throws -> SecurityNumber? {
        try vault.transaction { try securityNumberInTransaction(peer: peer) }
    }
    private func securityNumberInTransaction(peer: UUID) throws -> SecurityNumber? {
            guard peer != vault.account,
                  let remote = try store.identity(for: ProtocolAddress(name: peer.uuidString.lowercased(), deviceId: 1), context: context) else { return nil }
            return try SecurityNumber.make(local: vault.account, localKey: store.identityKeyPair(context: context).identityKey,
                peer: peer, peerKey: remote, receipt: vault.get("identity-verification", peer.uuidString.lowercased()))
    }
    func setIdentityVerified(_ verified: Bool, peer: UUID, compared: SecurityNumber) throws {
        try vault.transaction {
            guard let current = try securityNumberInTransaction(peer: peer), current.binding == compared.binding,
                  current.digits == compared.digits else { throw DurableSignalStore.Failure.identityChanged }
            if verified { try vault.put("identity-verification", peer.uuidString.lowercased(), current.binding) }
            else { try vault.remove("identity-verification", peer.uuidString.lowercased()) }
        }
    }
    func queue(id: UUID, peer: UUID, text: String, createdAt: Int64, now: Int64, attachments: [AttachmentManifest] = []) throws -> RoutedMessage {
        let envelope = try journal.queue(id: id, recipient: peer, text: text, createdAt: createdAt, now: now, attachments: attachments) { clear in
            guard let target = try vault.get("peer-device", peer.uuidString.lowercased()) else { throw SignalKeys.Failure.invalidBundle }
            let encrypted = try signalEncrypt(message: clear, for: ProtocolAddress(name: peer.uuidString.lowercased(), deviceId: 1), localAddress: local, sessionStore: store, identityStore: store, context: context)
            try vault.put("outgoing-route", id.uuidString.lowercased(), target)
            return (Int(encrypted.messageType.rawValue), encrypted.serialize())
        }
        let target = try vault.transaction {
            guard let data = try vault.get("outgoing-route", id.uuidString.lowercased()), let uuid = UUID(uuidString: String(decoding: data, as: UTF8.self)) else { throw MessageJournal.Failure.invalidMessage }
            return uuid
        }
        guard let saved = try journal.outgoing(id) else { throw MessageJournal.Failure.missingMessage }
        return RoutedMessage(envelope: envelope, senderDevice: device.id, recipientDevice: target, attachmentIDs: (saved.attachments ?? []).flatMap(\.blobIDs))
    }
    func receive(_ value: RoutedMessage, now: Int64, validate: () throws -> Void = {}, onNew: () -> Void = {}, commitMetadata: () throws -> Void = {}) throws -> StoredChat {
        guard value.recipientDevice == device.id else { throw MessageJournal.Failure.invalidMessage }
        let peer = value.envelope.sender.uuidString.lowercased(), sender = Data(value.senderDevice.uuidString.lowercased().utf8)
        return try journal.receive(value.envelope, now: now, onNew: onNew, commitMetadata: commitMetadata, validateRoute: {
            try validate()
            if let stored = try vault.get("incoming-route", value.envelope.id.uuidString.lowercased()) {
                guard stored == sender, try vault.get("incoming", value.envelope.id.uuidString.lowercased()) != nil else { throw MessageJournal.Failure.conflict }
                return // Journal still checks the exact committed envelope hash.
            }
            if let stored = try vault.get("peer-device", peer), stored != sender {
                if try vault.get("retired-peer-device", peer + "/" + value.senderDevice.uuidString.lowercased()) != nil { throw DurableSignalStore.Failure.retiredDevice }
                throw DurableSignalStore.Failure.identityChanged
            }
        }) { type, bytes in
            let address = try ProtocolAddress(name: peer, deviceId: 1), clear: Data
            if type == 3 { clear = try signalDecryptPreKey(message: PreKeySignalMessage(bytes: bytes), from: address, localAddress: local, sessionStore: store, identityStore: store, preKeyStore: store, signedPreKeyStore: store, kyberPreKeyStore: store, context: context) }
            else { clear = try signalDecrypt(message: SignalMessage(bytes: bytes), from: address, to: local, sessionStore: store, identityStore: store, context: context) }
            try vault.put("peer-device", peer, sender); try vault.put("incoming-route", value.envelope.id.uuidString.lowercased(), sender)
            return clear
        }
    }
}
