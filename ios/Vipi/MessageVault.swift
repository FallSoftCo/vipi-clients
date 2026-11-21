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

    /// Low-entropy vocabulary is never exposed as a plain hash in SQLite keys.
    func opaqueID(scope:String,value:String) -> String {
        HMAC<SHA256>.authenticationCode(for:Data((scope+"\0"+value).utf8),using:key)
            .map{String(format:"%02x",$0)}.joined()
    }

    init(account: UUID, directory: URL? = nil, previewKey: Data? = nil) throws {
        self.account = account
        Self.keyLock.lock()
        defer { Self.keyLock.unlock() }
        let root: URL
        #if VIPI_NOTIFICATION_EXTENSION
        guard let directory, previewKey != nil else { throw Failure.missingKey }
        root = directory
        #else
        root = try directory ?? NotificationAccess.storageRoot(for: account)
        #endif
        var folder = root.appendingPathComponent(account.uuidString.lowercased(), isDirectory: true)
        url = folder.appendingPathComponent("messages.sqlite")
        var newAccount = false
        if let previewKey {
            guard previewKey.count == 32, FileManager.default.fileExists(atPath: url.path) else { throw Failure.missingKey }
            key = SymmetricKey(data: previewKey)
        } else {
            #if VIPI_NOTIFICATION_EXTENSION
            throw Failure.missingKey
            #else
            let keyName = "messages-\(account.uuidString.lowercased())"
            if let data = try KeychainStore.read(account: keyName) {
                guard data.count == 32, directory != nil || FileManager.default.fileExists(atPath: url.path) else { throw Failure.missingKey }
                key = SymmetricKey(data: data)
            } else {
                guard !FileManager.default.fileExists(atPath: url.path) else { throw Failure.missingKey }
                let created = SymmetricKey(size: .bits256)
                try KeychainStore.save(created.withUnsafeBytes { Data($0) }, account: keyName)
                key = created
                newAccount = true
            }
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true, attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication])
            var values = URLResourceValues(); values.isExcludedFromBackup = true
            try folder.setResourceValues(values)
            #endif
        }
        let flags = SQLITE_OPEN_READWRITE | SQLITE_OPEN_FULLMUTEX | (previewKey == nil ? SQLITE_OPEN_CREATE : 0)
        let code = sqlite3_open_v2(url.path, &database, flags, nil)
        guard code == SQLITE_OK else { if let database { sqlite3_close(database) }; database = nil; throw Failure.database(code) }
        do {
            sqlite3_busy_timeout(database, 5000)
            try execute("PRAGMA journal_mode=WAL")
            try execute("PRAGMA synchronous=FULL")
            if previewKey == nil { try execute("CREATE TABLE IF NOT EXISTS records (kind TEXT NOT NULL, id TEXT NOT NULL, value BLOB NOT NULL, PRIMARY KEY(kind,id))") }
            try transaction {
                if let version = try get("metadata", "schema") {
                    guard version == Data([1]) else { throw Failure.incompatible }
                } else {
                    guard previewKey == nil else { throw Failure.incompatible }
                    try put("metadata", "schema", Data([1]))
                    if newAccount {
                        try put("local", "outside-previews", JSONEncoder().encode(NotificationConsent()))
                    }
                }
            }
        } catch { sqlite3_close(database); database = nil; throw error }
    }
    func notificationConsent() throws -> NotificationConsent? {
        guard let data = try get("local", "outside-previews"), data != Data([0]) else { return nil }
        return try JSONDecoder().decode(NotificationConsent.self, from: data)
    }
    #if !VIPI_NOTIFICATION_EXTENSION
    func authorizeNotifications(_ consent: NotificationConsent) throws {
        guard url.deletingLastPathComponent().deletingLastPathComponent().standardizedFileURL == NotificationAccess.root?.standardizedFileURL else { return }
        try NotificationAccess.authorize(.init(account: account, epoch: consent.epoch, key: key.withUnsafeBytes { Data($0) }))
    }
    #endif
    deinit { if let database { sqlite3_close(database) } }
    func close() throws {
        lock.lock(); defer { lock.unlock() }
        guard transactionThread == nil else { throw Failure.nestedTransaction }
        guard let database else { return }
        let code = sqlite3_close(database)
        guard code == SQLITE_OK else { throw Failure.database(code) }
        self.database = nil
    }
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
        guard database != nil else { throw Failure.database(SQLITE_MISUSE) }
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
    /// Indexed keyset pagination. Prefixes contain only opaque conversation IDs.
    func pageIDs(_ kind: String, prefix: String, before: String? = nil, limit: Int = 50) throws -> [String] {
        lock.lock(); defer { lock.unlock() }
        _ = try aad(kind, prefix)
        guard (1...100).contains(limit) else { throw Failure.invalidRecord }
        let upper = prefix + "\u{FFFF}"
        return try statement("SELECT id FROM records WHERE kind=? AND id>=? AND id<? AND id<? ORDER BY id DESC LIMIT ?", kind, prefix) { raw in
            guard sqlite3_bind_text(raw, 3, upper, -1, transient) == SQLITE_OK,
                  sqlite3_bind_text(raw, 4, before ?? upper, -1, transient) == SQLITE_OK,
                  sqlite3_bind_int(raw, 5, Int32(limit)) == SQLITE_OK else { throw Failure.invalidRecord }
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
