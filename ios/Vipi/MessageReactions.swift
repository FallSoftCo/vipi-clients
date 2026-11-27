import Foundation

/// One last-writer register per authenticated actor on an immutable message.
/// Ciphertext retries share a logical event ID. A clear remains a tombstone.
enum MessageReactions {
    enum Scope: String { case direct, group }
    struct Entry: Codable, Equatable {
        let actor: UUID
        let device: UUID
        let event: UUID
        let sequence: Int64
        let emoji: String?
    }
    static func key(_ scope: Scope, _ conversation: UUID, _ target: UUID, _ author: UUID) -> String {
        [scope.rawValue, conversation.uuidString, target.uuidString, author.uuidString].joined(separator: "/")
            .lowercased()
    }
    static func next(_ vault: MessageVault, scope: Scope, conversation: UUID, target: UUID, author: UUID, device: UUID)
        throws -> Int64
    {
        try vault.transaction {
            let id = key(scope, conversation, target, author) + "/" + device.uuidString.lowercased()
            let value =
                try vault.get("reaction-sequence", id).map { try JSONDecoder().decode(Int64.self, from: $0) } ?? 0
            guard value < Int64(Int32.max) else { throw MessageJournal.Failure.invalidMessage }
            try vault.put("reaction-sequence", id, JSONEncoder().encode(value + 1))
            return value + 1
        }
    }
    static func apply(
        _ vault: MessageVault, scope: Scope, conversation: UUID, actor: UUID, device: UUID, event: UUID,
        reaction: ChatFeatures.Reaction, targetKnown: Bool
    ) throws {
        guard reaction.valid, event != reaction.message_id else { return }
        let id = key(scope, conversation, reaction.message_id, reaction.target_sender_id)
        let kind = targetKnown ? "reaction-state" : "reaction-unresolved"
        if targetKnown { try resolve(vault, id: id) }
        let current = try vault.get(kind, id)
        if !targetKnown, current == nil, try vault.pageIDs(kind, prefix: "", limit: 96).count >= 96 { return }
        var values = try current.map { try JSONDecoder().decode([Entry].self, from: $0) } ?? []
        if let previous = values.first(where: { $0.actor == actor }), previous.device == device {
            guard (reaction.sequence, event.uuidString) > (previous.sequence, previous.event.uuidString) else { return }
        }
        values.removeAll { $0.actor == actor }
        guard targetKnown || values.count < 64 else { return }
        values.append(
            Entry(actor: actor, device: device, event: event, sequence: reaction.sequence, emoji: reaction.emoji))
        try vault.put(kind, id, JSONEncoder().encode(values))
    }
    static func resolve(_ vault: MessageVault, id: String) throws {
        if let bytes = try vault.get("reaction-unresolved", id) {
            if try vault.get("reaction-state", id) == nil { try vault.put("reaction-state", id, bytes) }
            try vault.remove("reaction-unresolved", id)
        }
    }
    static func entries(_ vault: MessageVault, scope: Scope, conversation: UUID, target: UUID, author: UUID) throws
        -> [Entry]
    {
        try vault.transaction {
            let id = key(scope, conversation, target, author)
            return try vault.get("reaction-state", id).map { try JSONDecoder().decode([Entry].self, from: $0) } ?? []
        }
    }
}
