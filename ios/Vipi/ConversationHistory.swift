import Foundation

struct ChatItem: Identifiable {
    let id: UUID; let peer: UUID; let text: String; let createdAt: Int64
    let outgoing: Bool; let state: String; let cursor: String
}
struct ChatThread: Identifiable {
    var id: UUID { peer }
    let peer: UUID; let latest: ChatItem; let unread: Int
}

/// Only opaque IDs/timestamps are indexed. Text, draft input, contacts and unread
/// counts remain authenticated encrypted values in the native message vault.
final class ConversationHistory {
    private struct Reference: Codable { let kind: String; let id: UUID }
    private struct Summary: Codable { let peer: UUID; var latest: String; var unread: Int }
    private let vault: MessageVault
    init(vault: MessageVault) throws {
        self.vault = vault
        try vault.transaction {
            if try vault.get("metadata", "history-index") == nil {
                // Upgrade existing local journals once; old history is already read.
                for kind in ["draft", "outgoing", "incoming"] {
                    for id in try vault.ids(kind) {
                        guard let bytes = try vault.get(kind, id) else { throw MessageJournal.Failure.missingMessage }
                        if kind == "draft" {
                            let item = try JSONDecoder().decode(DraftChat.self, from: bytes)
                            try Self.record(vault, kind: kind, id: item.id, peer: item.recipient, createdAt: item.createdAt)
                        } else {
                            let item = try JSONDecoder().decode(StoredChat.self, from: bytes), envelope = item.envelope
                            try Self.record(vault, kind: kind, id: envelope.id, peer: kind == "incoming" ? envelope.sender : envelope.recipient, createdAt: envelope.createdAt)
                        }
                    }
                }
                try vault.put("metadata", "history-index", Data([1]))
            } else if try vault.get("metadata", "history-index") != Data([1]) { throw MessageVault.Failure.incompatible }
        }
    }
    private static func index(peer: UUID, createdAt: Int64, id: UUID) -> String {
        peer.uuidString.lowercased() + "/" + String(format: "%019lld", createdAt) + "/" + id.uuidString.lowercased()
    }
    /// Called inside the SAME transaction as draft/ratchet/decryption changes.
    static func record(_ vault: MessageVault, kind: String, id: UUID, peer: UUID, createdAt: Int64, unread: Bool = false) throws {
        let key = index(peer: peer, createdAt: createdAt, id: id), peerKey = peer.uuidString.lowercased()
        let existing = try vault.get("history", key)
        try vault.put("history", key, JSONEncoder().encode(Reference(kind: kind, id: id)))
        var summary = try vault.get("thread", peerKey).map { try JSONDecoder().decode(Summary.self, from: $0) }
            ?? Summary(peer: peer, latest: key, unread: 0)
        if key > summary.latest { summary.latest = key }
        if existing == nil && unread { summary.unread += 1 }
        try vault.put("thread", peerKey, JSONEncoder().encode(summary))
    }
    private func item(_ cursor: String) throws -> ChatItem {
        guard let data = try vault.get("history", cursor) else { throw MessageJournal.Failure.missingMessage }
        let ref = try JSONDecoder().decode(Reference.self, from: data)
        guard let bytes = try vault.get(ref.kind, ref.id.uuidString.lowercased()) else { throw MessageJournal.Failure.missingMessage }
        if ref.kind == "imported" {
            let value = try JSONDecoder().decode(HistoryBackupMessage.self, from: bytes)
            return ChatItem(id: value.id, peer: value.peer, text: value.text, createdAt: value.createdAt, outgoing: value.outgoing, state: "imported", cursor: cursor)
        }
        if ref.kind == "draft" {
            let value = try JSONDecoder().decode(DraftChat.self, from: bytes)
            return ChatItem(id: value.id, peer: value.recipient, text: value.text, createdAt: value.createdAt, outgoing: true, state: value.state, cursor: cursor)
        }
        let value = try JSONDecoder().decode(StoredChat.self, from: bytes), outgoing = ref.kind == "outgoing"
        return ChatItem(id: value.envelope.id, peer: outgoing ? value.envelope.recipient : value.envelope.sender,
            text: value.text, createdAt: value.envelope.createdAt, outgoing: outgoing, state: value.state, cursor: cursor)
    }
    func messages(peer: UUID, before: String? = nil, limit: Int = 50) throws -> [ChatItem] {
        try vault.transaction {
            try vault.pageIDs("history", prefix: peer.uuidString.lowercased() + "/", before: before, limit: limit).map(item)
        }
    }
    /// Pages bound plaintext memory and release the database lock between pages.
    /// Unsent drafts and messages still in delivery are never export candidates.
    func backupPeerIDs() throws -> [UUID] {
        var peers: [UUID] = []
        // UUID keys are partitioned by their first hexadecimal character; each
        // query returns at most 100 opaque IDs, never a latest-message value.
        for prefix in "0123456789abcdef" {
            var cursor: String?
            repeat {
                try Task.checkCancellation()
                let page = try vault.transaction { try vault.pageIDs("thread", prefix: String(prefix), before: cursor, limit: 100) }
                for key in page {
                    guard peers.count + 2 < HistoryBackupCodec.maxRecords,
                          let id = UUID(uuidString: key), id.uuidString.lowercased() == key else { throw HistoryBackupCodec.Failure.damaged }
                    peers.append(id)
                }
                cursor = page.count == 100 ? page.last : nil
            } while cursor != nil
        }
        return peers
    }
    func backupPage(peer: UUID, before: String?) throws -> (messages: [HistoryBackupMessage], next: String?) {
        try vault.transaction {
            let ids = try vault.pageIDs("history", prefix: peer.uuidString.lowercased() + "/", before: before, limit: 100)
            var result: [HistoryBackupMessage] = []
            for id in ids {
                guard let data = try vault.get("history", id) else { throw MessageJournal.Failure.missingMessage }
                let ref = try JSONDecoder().decode(Reference.self, from: data), value = try item(id)
                guard ref.kind == "imported" || (ref.kind == "incoming" && value.state == "delivered") ||
                      (ref.kind == "outgoing" && ["delivered", "failed", "expired", "cancelled"].contains(value.state)) else { continue }
                result.append(HistoryBackupMessage(id: value.id, peer: value.peer, outgoing: value.outgoing, createdAt: value.createdAt, text: value.text))
            }
            return (result, ids.count == 100 ? ids.last : nil)
        }
    }
    func threads() throws -> [ChatThread] {
        try vault.transaction {
            try vault.ids("thread").map { key in
                guard let data = try vault.get("thread", key) else { throw MessageJournal.Failure.missingMessage }
                let value = try JSONDecoder().decode(Summary.self, from: data)
                return try ChatThread(peer: value.peer, latest: item(value.latest), unread: value.unread)
            }.sorted { a, b in
                a.latest.createdAt == b.latest.createdAt ? a.latest.id.uuidString > b.latest.id.uuidString : a.latest.createdAt > b.latest.createdAt
            }
        }
    }
    func markRead(_ peer: UUID) throws {
        try vault.transaction {
            let key = peer.uuidString.lowercased()
            guard let data = try vault.get("thread", key) else { return }
            var value = try JSONDecoder().decode(Summary.self, from: data); value.unread = 0
            try vault.put("thread", key, JSONEncoder().encode(value))
        }
    }
    func composeDraft(_ peer: UUID) throws -> String {
        try vault.transaction { String(decoding: try vault.get("compose", peer.uuidString.lowercased()) ?? Data(), as: UTF8.self) }
    }
    func saveComposeDraft(_ text: String, peer: UUID) throws {
        guard text.utf8.count <= 32768 else { throw MessageJournal.Failure.invalidMessage }
        try vault.transaction { try vault.put("compose", peer.uuidString.lowercased(), Data(text.utf8)) }
    }
}
