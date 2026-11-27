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
        let header =
            "\(id.uuidString.lowercased())\0\(sender.uuidString.lowercased())\0\(recipient.uuidString.lowercased())\0\(createdAt)\0\(type)\0"
        return Data(SHA256.hash(data: Data(header.utf8) + ciphertext))
    }
}
struct StoredChat: Codable {
    let envelope: ChatEnvelope
    let text: String
    var state: String
    var seen: Bool? = nil
    var includedAvatarRevision: Int64? = nil
    var attachments: [AttachmentManifest]? = nil
    var features: ChatFeatures? = nil
}
struct DraftChat: Codable, Equatable {
    let id: UUID
    let recipient: UUID
    let text: String
    let createdAt: Int64
    var state = "queued"
    var attachments: [AttachmentManifest]? = nil
    var features: ChatFeatures? = nil
}
private struct EncodedProfileAvatar: Codable {
    let value: PrivateProfileAvatar?
    init(_ avatar: PrivateProfileAvatar) { value = avatar }
    init(from decoder: Decoder) throws { value = try? PrivateProfileAvatar(from: decoder) }
    func encode(to encoder: Encoder) throws { try value?.encode(to: encoder) }
}
private struct ChatPayload: Codable {
    let version: Int
    let id: String
    let sender: String
    let recipient: String
    let createdAt: Int64
    let text: String
    var attachments: [AttachmentManifest]? = nil
    // Decode the optional profile field independently. A malformed auxiliary
    // field must never discard an otherwise valid authenticated chat message.
    var profile_avatar: EncodedProfileAvatar? = nil
    var chat_features: WireChatFeatures? = nil
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
        created >= 0 && now >= 0 && created <= Int64.max - Self.ttl && now <= Int64.max - 300_000
            && created <= now + 300_000 && now < created + Self.ttl
    }
    func avatar(_ account: UUID) throws -> PrivateProfileAvatar? {
        try vault.transaction { try avatarInTransaction(account) }
    }
    private func avatarInTransaction(_ account: UUID) throws -> PrivateProfileAvatar? {
        try vault.get("private-avatar", key(account)).map { try decoder.decode(PrivateProfileAvatar.self, from: $0) }
    }
    private func updateAvatar(_ value: PrivateProfileAvatar, for account: UUID) throws {
        guard value.revision > (try avatarInTransaction(account)?.revision ?? 0) else { return }
        try vault.put("private-avatar", key(account), encoder.encode(value))
    }
    func setOwnAvatar(_ jpeg: Data?, now: Int64) throws {
        try vault.transaction {
            let old = try avatarInTransaction(vault.account)?.revision ?? 0
            guard old < Int64.max else { throw Failure.invalidMessage }
            try updateAvatar(PrivateProfileAvatar(revision: max(old + 1, now), jpeg: jpeg), for: vault.account)
        }
    }
    private func featuresToSend(
        id: UUID, recipient: UUID, date: Int64, text: String, attachments: [AttachmentManifest],
        requested: ChatFeatures?
    ) throws -> ChatFeatures? {
        guard requested == requested?.validated(in: text) else { throw Failure.invalidMessage }
        guard requested?.link_preview != nil else { return requested }
        return try ChatFeatures.fit(requested) { candidate in
            try encoder.encode(
                ChatPayload(
                    version: 1, id: key(id), sender: key(vault.account), recipient: key(recipient), createdAt: date,
                    text: text, attachments: attachments.isEmpty ? nil : attachments,
                    chat_features: candidate.map(WireChatFeatures.init)))
        }.0
    }
    func saveDraft(
        id: UUID, recipient: UUID, text: String, createdAt: Int64, now: Int64, consumeCompose: Bool = false,
        consumeVoice: String? = nil, attachments: [AttachmentManifest] = [], features requested: ChatFeatures? = nil
    ) throws {
        let features = try featuresToSend(
            id: id, recipient: recipient, date: createdAt, text: text, attachments: attachments, requested: requested)
        try MessageAttachments.validate(attachments)
        try vault.transaction {
            guard validTime(createdAt, now), !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                text.utf8.count <= 32768
            else { throw Failure.invalidMessage }
            if let bytes = try vault.get("outgoing", key(id)) {
                let saved = try decoder.decode(StoredChat.self, from: bytes)
                guard saved.text == text, saved.features == features, (saved.attachments ?? []) == attachments,
                    saved.envelope.recipient == recipient, saved.envelope.createdAt == createdAt
                else { throw Failure.conflict }
                return
            }
            let draft = DraftChat(
                id: id, recipient: recipient, text: text, createdAt: createdAt,
                attachments: attachments.isEmpty ? nil : attachments, features: features)
            if let bytes = try vault.get("draft", key(id)), try decoder.decode(DraftChat.self, from: bytes) != draft {
                throw Failure.conflict
            }
            try vault.put("draft", key(id), encoder.encode(draft))
            if features?.reaction == nil {
                try ConversationHistory.record(vault, kind: "draft", id: id, peer: recipient, createdAt: createdAt)
            }
            if features?.reaction == nil, consumeCompose, try vault.get("compose", key(recipient)) == Data(text.utf8) {
                try vault.remove("compose", key(recipient))
                try vault.remove("compose-features", "direct:" + key(recipient))
                try vault.remove("compose-preview-muted", "direct:" + key(recipient))
            }
            if let consumeVoice {
                guard let data = try vault.get("voice-compose", key(recipient)),
                    try decoder.decode(AttachmentManifest.self, from: data).id == consumeVoice
                else { throw Failure.conflict }
                try vault.remove("voice-compose", key(recipient))
            }
        }
    }
    func draft(_ id: UUID) throws -> DraftChat? {
        try vault.transaction { try vault.get("draft", key(id)).map { try decoder.decode(DraftChat.self, from: $0) } }
    }
    func pendingDrafts(now: Int64) throws -> [DraftChat] {
        try vault.transaction {
            guard now >= 0 else { throw Failure.invalidMessage }
            var result: [DraftChat] = []
            for id in try vault.ids("draft") {
                guard let data = try vault.get("draft", id) else { throw Failure.missingMessage }
                var saved = try decoder.decode(DraftChat.self, from: data)
                if now >= saved.createdAt + Self.ttl {
                    saved.state = "expired"
                    try vault.put("draft", id, encoder.encode(saved))
                } else if saved.state == "queued" {
                    result.append(saved)
                }
            }
            return result
        }
    }
    func queue(
        id: UUID, recipient: UUID, text: String, createdAt: Int64, now: Int64, attachments: [AttachmentManifest] = [],
        features requested: ChatFeatures? = nil, encrypt: (Data) throws -> (Int, Data)
    ) throws -> ChatEnvelope {
        let features = try featuresToSend(
            id: id, recipient: recipient, date: createdAt, text: text, attachments: attachments, requested: requested)
        try saveDraft(
            id: id, recipient: recipient, text: text, createdAt: createdAt, now: now, attachments: attachments,
            features: features)
        return try vault.transaction {
            if let bytes = try vault.get("outgoing", key(id)) {
                let saved = try decoder.decode(StoredChat.self, from: bytes)
                guard saved.text == text, saved.features == features, (saved.attachments ?? []) == attachments,
                    saved.envelope.recipient == recipient, saved.envelope.createdAt == createdAt
                else { throw Failure.conflict }
                guard ["queued", "accepted"].contains(saved.state), validTime(createdAt, now) else {
                    throw Failure.terminal
                }
                return saved.envelope
            }
            guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, text.utf8.count <= 32768,
                validTime(createdAt, now)
            else { throw Failure.invalidMessage }
            var payload = ChatPayload(
                version: 1, id: key(id), sender: key(vault.account), recipient: key(recipient), createdAt: createdAt,
                text: text, attachments: attachments.isEmpty ? nil : attachments,
                chat_features: features.map(WireChatFeatures.init))
            var clear = try encoder.encode(payload)
            let target = try vault.get("peer-device", key(recipient))
            let lastAvatar = try target.flatMap {
                try vault.get("sent-avatar", key(recipient) + "/" + String(decoding: $0, as: UTF8.self))
            }
            let lastRevision = lastAvatar.flatMap { Int64(String(decoding: $0, as: UTF8.self)) } ?? 0
            var included: Int64?
            if features?.reaction == nil, let own = try avatarInTransaction(vault.account), own.revision > lastRevision
            {
                payload.profile_avatar = EncodedProfileAvatar(own)
                let decorated = try encoder.encode(payload)
                if decorated.count <= 60 * 1024 {
                    clear = decorated
                    included = own.revision
                }
            }
            let (type, ciphertext) = try encrypt(clear)
            guard [2, 3].contains(type), (32...65536).contains(ciphertext.count) else { throw Failure.invalidMessage }
            let envelope = ChatEnvelope(
                id: id, sender: vault.account, recipient: recipient, createdAt: createdAt, type: type,
                ciphertext: ciphertext)
            try vault.put(
                "outgoing", key(id),
                encoder.encode(
                    StoredChat(
                        envelope: envelope, text: text, state: "queued", includedAvatarRevision: included,
                        attachments: attachments.isEmpty ? nil : attachments, features: features)))
            try vault.put("pending", key(id), Data([1]))
            try vault.remove("draft", key(id))
            if features?.reaction == nil {
                try ConversationHistory.record(vault, kind: "outgoing", id: id, peer: recipient, createdAt: createdAt)
            }
            return envelope
        }
    }
    func receive(
        _ envelope: ChatEnvelope, now: Int64, senderDevice: UUID? = nil, onNew: () -> Void = {},
        commitMetadata: () throws -> Void = {}, validateRoute: () throws -> Void = {},
        decrypt: (Int, Data) throws -> Data
    ) throws -> StoredChat {
        var inserted = false
        let stored = try vault.transaction {
            guard envelope.recipient == vault.account, [2, 3].contains(envelope.type),
                (32...65536).contains(envelope.ciphertext.count)
            else { throw Failure.invalidMessage }
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
            guard payload.version == 1, payload.id == key(envelope.id), payload.sender == key(envelope.sender),
                payload.recipient == key(vault.account), payload.createdAt == envelope.createdAt,
                !payload.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, payload.text.utf8.count <= 32768
            else { throw Failure.invalidMessage }
            if let avatar = payload.profile_avatar?.value {
                try updateAvatar(avatar, for: envelope.sender)
            }
            try MessageAttachments.validate(payload.attachments ?? [])
            var features = payload.chat_features?.value?.validated(in: payload.text)
            if let reply = features?.reply, ![vault.account, envelope.sender].contains(reply.sender_id) {
                features?.reply = nil
                features = features?.validated(in: payload.text)
            }
            let saved = StoredChat(
                envelope: envelope, text: payload.text, state: "delivered", attachments: payload.attachments,
                features: features)
            try vault.put("incoming", key(envelope.id), encoder.encode(saved))
            if let reaction = saved.features?.reaction {
                if let senderDevice {
                    try applyReaction(reaction, envelope: envelope, peer: envelope.sender, device: senderDevice)
                }
            } else {
                try MessageReactions.resolve(
                    vault, id: MessageReactions.key(.direct, envelope.sender, envelope.id, envelope.sender))
                try ConversationHistory.record(
                    vault, kind: "incoming", id: envelope.id, peer: envelope.sender, createdAt: envelope.createdAt,
                    unread: true)
            }
            try vault.put("receipt", key(envelope.id), Data([1]))
            try commitMetadata()
            inserted = true
            return saved
        }
        if inserted { onNew() }
        return stored
    }
    private func applyReaction(_ reaction: ChatFeatures.Reaction, envelope: ChatEnvelope, peer: UUID, device: UUID)
        throws
    {
        guard [peer, vault.account].contains(reaction.target_sender_id) else { return }
        let kind = reaction.target_sender_id == vault.account ? "outgoing" : "incoming"
        let target = try vault.get(kind, key(reaction.message_id)).map { try decoder.decode(StoredChat.self, from: $0) }
        let known =
            target?.envelope.sender == reaction.target_sender_id && target?.features?.reaction == nil
            && target?.envelope.recipient == (reaction.target_sender_id == vault.account ? peer : vault.account)
        try MessageReactions.apply(
            vault, scope: .direct, conversation: peer, actor: envelope.sender, device: device,
            event: envelope.id, reaction: reaction, targetKnown: known)
    }
    func outgoing(_ id: UUID) throws -> StoredChat? {
        try vault.transaction {
            try vault.get("outgoing", key(id)).map { try decoder.decode(StoredChat.self, from: $0) }
        }
    }
    func pendingReceipts() throws -> [UUID] {
        try vault.transaction {
            try vault.ids("receipt").map { value in
                guard let id = UUID(uuidString: value) else { throw Failure.invalidMessage }
                return id
            }
        }
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
                    try vault.put("outgoing", id, encoder.encode(saved))
                    try vault.remove("pending", id)
                } else if result.count < limit {
                    result.append(saved.envelope)
                }
            }
            return result
        }
    }
    func setBlocked(_ blocked: Bool, peer: UUID) throws {
        try vault.transaction {
            if !blocked {
                try vault.remove("blocked", key(peer))
                return
            }
            try vault.put("blocked", key(peer), Data([1]))
            for id in try vault.ids("draft") {
                guard let bytes = try vault.get("draft", id) else { continue }
                var draft = try decoder.decode(DraftChat.self, from: bytes)
                if draft.recipient == peer && draft.state == "queued" {
                    draft.state = "cancelled"
                    try vault.put("draft", id, encoder.encode(draft))
                }
            }
            for id in try vault.ids("pending") {
                guard let bytes = try vault.get("outgoing", id) else { continue }
                var saved = try decoder.decode(StoredChat.self, from: bytes)
                if saved.envelope.recipient == peer {
                    if ["queued", "accepted"].contains(saved.state) {
                        saved.state = "cancelled"
                        try vault.put("outgoing", id, encoder.encode(saved))
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
            if saved.state == "read" || saved.state == "delivered"
                || (state != "delivered" && ["failed", "expired", "cancelled"].contains(saved.state))
            {
                return
            }
            #if !VIPI_NOTIFICATION_EXTENSION
            if saved.features?.reaction == nil, !["accepted", "delivered", "read"].contains(saved.state),
                ["accepted", "delivered"].contains(state)
            {
                try? recordSuccessfulChatSend(vault, key: "outgoing/" + key(id), authoredAt: saved.envelope.createdAt)
            }
            #endif
            if ["accepted", "delivered"].contains(state), let revision = saved.includedAvatarRevision,
                let target = try vault.get("outgoing-route", key(id))
            {
                let receipt = key(saved.envelope.recipient) + "/" + String(decoding: target, as: UTF8.self)
                let previous =
                    try vault.get("sent-avatar", receipt).flatMap { Int64(String(decoding: $0, as: UTF8.self)) } ?? 0
                if revision > previous { try vault.put("sent-avatar", receipt, Data(String(revision).utf8)) }
            }
            if ["accepted", "delivered"].contains(state) {
                if let reaction = saved.features?.reaction {
                    if let data = try vault.get("local", "registered-device"),
                        let device = UUID(uuidString: String(decoding: data, as: UTF8.self))
                    {
                        try applyReaction(
                            reaction, envelope: saved.envelope, peer: saved.envelope.recipient, device: device)
                    }
                } else {
                    try MessageReactions.resolve(
                        vault, id: MessageReactions.key(.direct, saved.envelope.recipient, id, vault.account))
                }
            }
            if saved.features?.reaction == nil, state == "delivered" {
                try ConversationStreak.observe(
                    vault, scope: .direct, id: saved.envelope.recipient, sender: vault.account,
                    at: saved.envelope.createdAt)
            }
            saved.state = state
            try vault.put("outgoing", key(id), encoder.encode(saved))
            if state != "accepted" { try vault.remove("pending", key(id)) }
        }
    }
}
