import Foundation
import CryptoKit
import SQLite3

/// Native, synchronous transactions encompass the ratchet and its message records.
/// Values are encrypted; record kinds and opaque IDs remain private SQLite metadata.
final class MessageVault: @unchecked Sendable {
    enum Failure: Error { case database(Int32), missingKey, incompatible, transactionRequired, nestedTransaction, invalidRecord }
    let account: UUID
    let url: URL
    private var database: OpaquePointer?
    private let key: SymmetricKey
    private let lock = NSRecursiveLock()
    private var transactionThread: Thread?
    private static let keyLock = NSLock()
    private let transient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

    init(account: UUID, directory: URL? = nil) throws {
        self.account = account
        let root = directory ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("Messages")
        var folder = root.appendingPathComponent(account.uuidString.lowercased(), isDirectory: true)
        url = folder.appendingPathComponent("messages.sqlite")
        Self.keyLock.lock()
        defer { Self.keyLock.unlock() }
        let keyName = "messages-\(account.uuidString.lowercased())"
        if let data = try KeychainStore.read(account: keyName) {
            guard data.count == 32 else { throw Failure.missingKey }
            key = SymmetricKey(data: data)
        } else {
            guard !FileManager.default.fileExists(atPath: url.path) else { throw Failure.missingKey }
            let created = SymmetricKey(size: .bits256)
            try KeychainStore.save(created.withUnsafeBytes { Data($0) }, account: keyName)
            key = created
        }
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true, attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication])
        var values = URLResourceValues(); values.isExcludedFromBackup = true
        try folder.setResourceValues(values)
        let code = sqlite3_open_v2(url.path, &database, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX, nil)
        guard code == SQLITE_OK else { if let database { sqlite3_close(database) }; database = nil; throw Failure.database(code) }
        do {
            sqlite3_busy_timeout(database, 5000)
            try execute("PRAGMA journal_mode=WAL")
            try execute("PRAGMA synchronous=FULL")
            try execute("CREATE TABLE IF NOT EXISTS records (kind TEXT NOT NULL, id TEXT NOT NULL, value BLOB NOT NULL, PRIMARY KEY(kind,id))")
            try transaction {
                if let version = try get("metadata", "schema") {
                    guard version == Data([1]) else { throw Failure.incompatible }
                } else { try put("metadata", "schema", Data([1])) }
            }
        } catch { sqlite3_close(database); database = nil; throw error }
    }
    deinit { if let database { sqlite3_close(database) } }
    func transaction<T>(_ operation: () throws -> T) throws -> T {
        lock.lock(); defer { lock.unlock() }
        guard transactionThread == nil else { throw Failure.nestedTransaction }
        try execute("BEGIN IMMEDIATE")
        transactionThread = Thread.current
        defer { transactionThread = nil }
        do {
            let value = try operation()
            try execute("COMMIT")
            return value
        } catch { try? execute("ROLLBACK"); throw error }
    }
    private func execute(_ sql: String) throws {
        let code = sqlite3_exec(database, sql, nil, nil, nil)
        guard code == SQLITE_OK else { throw Failure.database(code) }
    }
    private func aad(_ kind: String, _ id: String) throws -> Data {
        guard transactionThread === Thread.current else { throw Failure.transactionRequired }
        guard kind.range(of: "^[a-z-]{1,48}$", options: .regularExpression) != nil, (1...512).contains(id.utf16.count), !id.contains("\0") else { throw Failure.invalidRecord }
        return Data("vipi.messages.v1\0\(account.uuidString.lowercased())\0\(kind)\0\(id)".utf8)
    }
    private func statement<T>(_ sql: String, _ kind: String, _ id: String? = nil, body: (OpaquePointer) throws -> T) throws -> T {
        var raw: OpaquePointer?
        let code = sqlite3_prepare_v2(database, sql, -1, &raw, nil)
        guard code == SQLITE_OK, let raw else { throw Failure.database(code) }
        defer { sqlite3_finalize(raw) }
        guard sqlite3_bind_text(raw, 1, kind, -1, transient) == SQLITE_OK else { throw Failure.invalidRecord }
        if let id { guard sqlite3_bind_text(raw, 2, id, -1, transient) == SQLITE_OK else { throw Failure.invalidRecord } }
        return try body(raw)
    }
    func get(_ kind: String, _ id: String) throws -> Data? {
        lock.lock(); defer { lock.unlock() }
        let associated = try aad(kind, id)
        return try statement("SELECT value FROM records WHERE kind=? AND id=?", kind, id) { raw in
            let code = sqlite3_step(raw)
            if code == SQLITE_DONE { return nil }
            guard code == SQLITE_ROW else { throw Failure.database(code) }
            let length = Int(sqlite3_column_bytes(raw, 0))
            guard (29...2_097_181).contains(length), let pointer = sqlite3_column_blob(raw, 0) else { throw Failure.invalidRecord }
            let bytes = Data(bytes: pointer, count: length)
            guard bytes.first == 1 else { throw Failure.invalidRecord }
            return try AES.GCM.open(AES.GCM.SealedBox(combined: bytes.dropFirst()), using: key, authenticating: associated)
        }
    }
    func put(_ kind: String, _ id: String, _ value: Data) throws {
        lock.lock(); defer { lock.unlock() }
        let associated = try aad(kind, id)
        guard value.count <= 2_097_152 else { throw Failure.invalidRecord }
        let encrypted = try AES.GCM.seal(value, using: key, authenticating: associated)
        guard let combined = encrypted.combined else { throw Failure.invalidRecord }
        let bytes = Data([1]) + combined
        try statement("INSERT OR REPLACE INTO records(kind,id,value) VALUES(?,?,?)", kind, id) { raw in
            let bound = bytes.withUnsafeBytes { sqlite3_bind_blob(raw, 3, $0.baseAddress, Int32($0.count), transient) }
            guard bound == SQLITE_OK else { throw Failure.database(bound) }
            let code = sqlite3_step(raw)
            guard code == SQLITE_DONE else { throw Failure.database(code) }
        }
    }
    func remove(_ kind: String, _ id: String) throws {
        lock.lock(); defer { lock.unlock() }
        _ = try aad(kind, id)
        try statement("DELETE FROM records WHERE kind=? AND id=?", kind, id) { raw in
            let code = sqlite3_step(raw); guard code == SQLITE_DONE else { throw Failure.database(code) }
        }
    }
    func ids(_ kind: String) throws -> [String] {
        lock.lock(); defer { lock.unlock() }
        _ = try aad(kind, "enumerate")
        return try statement("SELECT id FROM records WHERE kind=? ORDER BY id", kind) { raw in
            var result: [String] = []
            while true {
                let code = sqlite3_step(raw)
                if code == SQLITE_DONE { return result }
                guard code == SQLITE_ROW, let text = sqlite3_column_text(raw, 0) else { throw Failure.database(code) }
                result.append(String(cString: text))
            }
        }
    }
}
