import Foundation
import CryptoKit

struct ChatEnvelope: Codable {
    let id: UUID
    let sender: UUID
    let recipient: UUID
    let createdAt: Int64
    let type: Int
    let ciphertext: Data
    func fingerprint() -> Data {
        let header = "\(id.uuidString.lowercased())\0\(sender.uuidString.lowercased())\0\(recipient.uuidString.lowercased())\0\(createdAt)\0\(type)\0"
        return Data(SHA256.hash(data: Data(header.utf8) + ciphertext))
    }
}
struct StoredChat: Codable {
    let envelope: ChatEnvelope
    let text: String
    var state: String
    var seen: Bool? = nil
}
struct DraftChat: Codable, Equatable {
    let id: UUID
    let recipient: UUID
    let text: String
    let createdAt: Int64
    var state = "queued"
}
private struct ChatPayload: Codable {
    let version: Int
    let id: String
    let sender: String
    let recipient: String
    let createdAt: Int64
    let text: String
}

/// Transport-independent persistence. Only a returned, committed receive() may
/// lead to a delivery acknowledgement. Retrying reuses saved ciphertext.
final class MessageJournal {
    enum Failure: Error { case invalidMessage, conflict, terminal, missingMessage }
    static let ttl: Int64 = 72 * 60 * 60 * 1000
    private let vault: MessageVault
    private let encoder = JSONEncoder(), decoder = JSONDecoder()
    init(vault: MessageVault) { self.vault = vault }
    private func key(_ id: UUID) -> String { id.uuidString.lowercased() }
    private func validTime(_ created: Int64, _ now: Int64) -> Bool {
        created >= 0 && now >= 0 && created <= Int64.max - Self.ttl && now <= Int64.max - 300_000 && created <= now + 300_000 && now < created + Self.ttl
    }
    func saveDraft(id: UUID, recipient: UUID, text: String, createdAt: Int64, now: Int64, consumeCompose: Bool = false) throws {
        try vault.transaction {
            guard validTime(createdAt, now), !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, text.utf8.count <= 32768 else { throw Failure.invalidMessage }
            if let bytes = try vault.get("outgoing", key(id)) {
                let saved = try decoder.decode(StoredChat.self, from: bytes)
                guard saved.text == text, saved.envelope.recipient == recipient, saved.envelope.createdAt == createdAt else { throw Failure.conflict }
                return
            }
            let draft = DraftChat(id: id, recipient: recipient, text: text, createdAt: createdAt)
            if let bytes = try vault.get("draft", key(id)), try decoder.decode(DraftChat.self, from: bytes) != draft { throw Failure.conflict }
            try vault.put("draft", key(id), encoder.encode(draft))
            try ConversationHistory.record(vault, kind: "draft", id: id, peer: recipient, createdAt: createdAt)
            if consumeCompose, try vault.get("compose", key(recipient)) == Data(text.utf8) { try vault.remove("compose", key(recipient)) }
        }
    }
    func draft(_ id: UUID) throws -> DraftChat? { try vault.transaction { try vault.get("draft", key(id)).map { try decoder.decode(DraftChat.self, from: $0) } } }
    func pendingDrafts(now: Int64) throws -> [DraftChat] {
        try vault.transaction {
            guard now >= 0 else { throw Failure.invalidMessage }
            var result: [DraftChat] = []
            for id in try vault.ids("draft") {
                guard let data = try vault.get("draft", id) else { throw Failure.missingMessage }
                var saved = try decoder.decode(DraftChat.self, from: data)
                if now >= saved.createdAt + Self.ttl { saved.state = "expired"; try vault.put("draft", id, encoder.encode(saved)) }
                else if saved.state == "queued" { result.append(saved) }
            }
            return result
        }
    }
    func queue(id: UUID, recipient: UUID, text: String, createdAt: Int64, now: Int64, encrypt: (Data) throws -> (Int, Data)) throws -> ChatEnvelope {
        try saveDraft(id: id, recipient: recipient, text: text, createdAt: createdAt, now: now)
        return try vault.transaction {
            if let bytes = try vault.get("outgoing", key(id)) {
                let saved = try decoder.decode(StoredChat.self, from: bytes)
                guard saved.text == text, saved.envelope.recipient == recipient, saved.envelope.createdAt == createdAt else { throw Failure.conflict }
                guard ["queued", "accepted"].contains(saved.state), validTime(createdAt, now) else { throw Failure.terminal }
                return saved.envelope
            }
            guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, text.utf8.count <= 32768, validTime(createdAt, now) else { throw Failure.invalidMessage }
            let payload = ChatPayload(version: 1, id: key(id), sender: key(vault.account), recipient: key(recipient), createdAt: createdAt, text: text)
            let (type, ciphertext) = try encrypt(encoder.encode(payload))
            guard [2, 3].contains(type), (32...65536).contains(ciphertext.count) else { throw Failure.invalidMessage }
            let envelope = ChatEnvelope(id: id, sender: vault.account, recipient: recipient, createdAt: createdAt, type: type, ciphertext: ciphertext)
            try vault.put("outgoing", key(id), encoder.encode(StoredChat(envelope: envelope, text: text, state: "queued")))
            try vault.put("pending", key(id), Data([1]))
            try vault.remove("draft", key(id))
            try ConversationHistory.record(vault, kind: "outgoing", id: id, peer: recipient, createdAt: createdAt)
            return envelope
        }
    }
    func receive(_ envelope: ChatEnvelope, now: Int64, validateRoute: () throws -> Void = {}, decrypt: (Int, Data) throws -> Data) throws -> StoredChat {
        try vault.transaction {
            guard envelope.recipient == vault.account, [2, 3].contains(envelope.type), (32...65536).contains(envelope.ciphertext.count) else { throw Failure.invalidMessage }
            try validateRoute()
            if let bytes = try vault.get("incoming", key(envelope.id)) {
                let saved = try decoder.decode(StoredChat.self, from: bytes)
                guard saved.envelope.fingerprint() == envelope.fingerprint() else { throw Failure.conflict }
                try vault.put("receipt", key(envelope.id), Data([1]))
                return saved
            }
            guard validTime(envelope.createdAt, now) else { throw Failure.invalidMessage }
            let clear = try decrypt(envelope.type, envelope.ciphertext)
            guard clear.count <= 65536 else { throw Failure.invalidMessage }
            let payload = try decoder.decode(ChatPayload.self, from: clear)
            guard payload.version == 1, payload.id == key(envelope.id), payload.sender == key(envelope.sender), payload.recipient == key(vault.account), payload.createdAt == envelope.createdAt,
                  !payload.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, payload.text.utf8.count <= 32768 else { throw Failure.invalidMessage }
            let saved = StoredChat(envelope: envelope, text: payload.text, state: "delivered")
            try vault.put("incoming", key(envelope.id), encoder.encode(saved))
            try ConversationHistory.record(vault, kind: "incoming", id: envelope.id, peer: envelope.sender, createdAt: envelope.createdAt, unread: true)
            try vault.put("receipt", key(envelope.id), Data([1]))
            return saved
        }
    }
    func outgoing(_ id: UUID) throws -> StoredChat? {
        try vault.transaction { try vault.get("outgoing", key(id)).map { try decoder.decode(StoredChat.self, from: $0) } }
    }
    func pendingReceipts() throws -> [UUID] {
        try vault.transaction { try vault.ids("receipt").map { value in
            guard let id = UUID(uuidString: value) else { throw Failure.invalidMessage }; return id
        } }
    }
    func receiptAccepted(_ id: UUID) throws { try vault.transaction { try vault.remove("receipt", key(id)) } }
    func pending(now: Int64, limit: Int = 100) throws -> [ChatEnvelope] {
        try vault.transaction {
            guard (1...100).contains(limit) else { throw Failure.invalidMessage }
            var result: [ChatEnvelope] = []
            for id in try vault.ids("pending") {
                guard let bytes = try vault.get("outgoing", id) else { throw Failure.missingMessage }
                var saved = try decoder.decode(StoredChat.self, from: bytes)
                if now >= saved.envelope.createdAt + Self.ttl {
                    saved.state = "expired"
                    try vault.put("outgoing", id, encoder.encode(saved)); try vault.remove("pending", id)
                } else if result.count < limit { result.append(saved.envelope) }
            }
            return result
        }
    }
    func setBlocked(_ blocked: Bool, peer: UUID) throws {
        try vault.transaction {
            if !blocked { try vault.remove("blocked", key(peer)); return }
            try vault.put("blocked", key(peer), Data([1]))
            for id in try vault.ids("draft") {
                guard let bytes = try vault.get("draft", id) else { continue }
                var draft = try decoder.decode(DraftChat.self, from: bytes)
                if draft.recipient == peer && draft.state == "queued" {
                    draft.state = "cancelled"; try vault.put("draft", id, encoder.encode(draft))
                }
            }
            for id in try vault.ids("pending") {
                guard let bytes = try vault.get("outgoing", id) else { continue }
                var saved = try decoder.decode(StoredChat.self, from: bytes)
                if saved.envelope.recipient == peer {
                    if ["queued", "accepted"].contains(saved.state) {
                        saved.state = "cancelled"; try vault.put("outgoing", id, encoder.encode(saved))
                    }
                    try vault.remove("pending", id)
                }
            }
        }
    }
    func applyStatus(_ id: UUID, state: String) throws {
        try vault.transaction {
            guard ["accepted", "delivered", "failed", "expired"].contains(state) else { throw Failure.invalidMessage }
            guard let bytes = try vault.get("outgoing", key(id)) else { throw Failure.missingMessage }
            var saved = try decoder.decode(StoredChat.self, from: bytes)
            if saved.state == "read" || saved.state == "delivered" || (state != "delivered" && ["failed", "expired", "cancelled"].contains(saved.state)) { return }
            saved.state = state
            try vault.put("outgoing", key(id), encoder.encode(saved))
            if state != "accepted" { try vault.remove("pending", key(id)) }
        }
    }
}
