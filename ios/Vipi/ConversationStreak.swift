import Foundation
import CryptoKit

enum StreakScope: String, Sendable { case direct, group }

/// One encrypted bucket per 32 UTC days. A day needs at most its first author and, after a reply, one bit.
enum ConversationStreak {
    static let millisecondsPerDay: Int64 = 86_400_000
    static func today(_ date: Date = Date()) -> Int64 { Int64(floor(date.timeIntervalSince1970 / 86_400)) }
    private struct Bucket: Codable {
        var complete: UInt32 = 0
        var first: [Int: UUID] = [:]
    }
    private static func key(_ scope: StreakScope, _ id: UUID) -> String {
        scope.rawValue + "/" + id.uuidString.lowercased()
    }
    /// A damaged optional index must not block an authenticated message write.
    /// Restart this conversation's scan only; the message journal remains authoritative.
    private static func derived<T: Decodable>(_ type: T.Type, vault: MessageVault, kind: String, id: String, conversation: String) throws -> T? {
        do {
            return try vault.get(kind, id).map { try JSONDecoder().decode(type, from: $0) }
        } catch let error as MessageVault.Failure {
            guard case .invalidRecord = error else { throw error }
        } catch is DecodingError {
        } catch is CryptoKitError {
        }
        try vault.remove(kind, id)
        if kind == "streak-days" { try vault.put("streak-reset", conversation, Data([1])) }
        return nil
    }
    static func observe(_ vault: MessageVault, scope: StreakScope, id: UUID, sender: UUID, at timestamp: Int64) throws {
        guard timestamp >= 0, scope != .direct || (id != vault.account && (sender == id || sender == vault.account)) else { return }
        let day = timestamp / millisecondsPerDay
        let conversation = key(scope, id), bucketID = conversation + "/" + String(day / 32)
        let index = Int(day % 32), bit = UInt32(1) << index
        var bucket = try derived(Bucket.self, vault: vault, kind: "streak-days", id: bucketID, conversation: conversation) ?? Bucket()
        guard bucket.complete & bit == 0, bucket.first[index] != sender else { return }
        if bucket.first.removeValue(forKey: index) != nil { bucket.complete |= bit }
        else { bucket.first[index] = sender }
        try vault.put("streak-days", bucketID, JSONEncoder().encode(bucket))
    }
    #if !VIPI_NOTIFICATION_EXTENSION
    static func observeGroup(_ vault: MessageVault, _ message: GroupMessage) throws {
        guard message.withheldReason == nil,
              (message.sender == vault.account ? message.delivery == .accepted : message.delivery == .received) else { return }
        try observe(vault, scope: .group, id: message.groupID, sender: message.sender, at: message.createdAt)
    }
    private struct Cursor: Codable { var before: String?; var done = false }
    /// Backfill keyset pages across the entire conversation. Each cursor advances with its indexed days.
    static func backfillPage(_ vault: MessageVault, scope: StreakScope, id: UUID) throws -> Bool {
        try vault.transaction {
            let progressID = key(scope, id), decoder = JSONDecoder()
            if try vault.get("streak-reset", progressID) != nil {
                try vault.remove("streak-cursor", progressID)
                try vault.remove("streak-reset", progressID)
            }
            var cursor = try derived(Cursor.self, vault: vault, kind: "streak-cursor", id: progressID, conversation: progressID) ?? Cursor()
            if cursor.done { return true }
            let kind = scope == .group ? "group-message" : "history"
            let page = try vault.pageIDs(kind, prefix: id.uuidString.lowercased() + "/", before: cursor.before, limit: 64)
            for entry in page {
                guard let bytes = try vault.get(kind, entry) else { throw MessageVault.Failure.invalidRecord }
                if scope == .group {
                    try observeGroup(vault, decoder.decode(GroupMessage.self, from: bytes))
                    continue
                }
                let ref = try decoder.decode(ConversationHistory.Reference.self, from: bytes)
                guard ref.kind != "draft", let raw = try vault.get(ref.kind, ref.id.uuidString.lowercased()) else { continue }
                if ref.kind == "imported" {
                    let message = try decoder.decode(HistoryBackupMessage.self, from: raw)
                    if !message.outgoing { try observe(vault, scope: scope, id: id, sender: id, at: message.createdAt) }
                } else if ref.kind == "incoming" || ref.kind == "outgoing" {
                    let row = try decoder.decode(StoredChat.self, from: raw)
                    if ref.kind == "incoming" || row.state == "delivered" || row.state == "read" {
                        try observe(vault, scope: scope, id: id, sender: row.envelope.sender, at: row.envelope.createdAt)
                    }
                }
            }
            cursor.before = page.last
            cursor.done = page.count < 64
            try vault.put("streak-cursor", progressID, JSONEncoder().encode(cursor))
            return try cursor.done && vault.get("streak-reset", progressID) == nil
        }
    }
    static func count(_ vault: MessageVault, scope: StreakScope, id: UUID, through today: Int64) throws -> Int {
        try vault.transaction {
            var day = today, length = 0, loaded: Int64 = -1, complete: UInt32 = 0
            while day >= 0 {
                if loaded != day / 32 {
                    loaded = day / 32
                    let conversation = key(scope, id), bucketID = conversation + "/" + String(loaded)
                    complete = try derived(Bucket.self, vault: vault, kind: "streak-days", id: bucketID, conversation: conversation)?.complete ?? 0
                }
                if complete & (1 << Int(day % 32)) != 0 { length += 1 }
                else if day != today { break }
                day -= 1
            }
            return length
        }
    }
    static func load(_ vault: MessageVault, scope: StreakScope, id: UUID, through day: Int64) async throws -> Int {
        while true {
            try Task.checkCancellation()
            if try backfillPage(vault, scope: scope, id: id) {
                let length = try count(vault, scope: scope, id: id, through: day)
                if try vault.transaction({ try vault.get("streak-reset", key(scope,id)) == nil }) { return length }
            }
            await Task.yield()
        }
    }
    #endif
}
