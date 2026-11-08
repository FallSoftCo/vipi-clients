import CryptoKit
import Darwin
import Foundation
import SQLite3
import VipiCore

struct VocabularyManifest: Codable, Sendable {
    let pack_id: String
    let source_language: String
    let target_language: String
    let revision: Int
    let schema_version: Int
    let normalization: String
    let file: String
    let bytes: Int
    let sha256: String
    let key_id: String
    let signature_algorithm: String
    let context_policy: String?
    let native_source_guard_policy: String?
    let native_source_guard_sha256: String?
}

enum VocabularyPackError: Error { case invalid, untrustedKey, signature, rollback, storage, reinstallRequired, cleanupPending }
struct VocabularyPackStatus: Sendable {
    let acceptedRevision: Int?
    let acceptedHash: String?
    let active: Bool
    let reinstallRequired: Bool
    let cleanupPendingFiles: [String]
}
enum VocabularyPackCheckpoint: Sendable, Equatable { case waitingForNamespace, staged, beforeDirectorySync, beforeActivation, cleanup, beforeRemoval }

/// One Keychain namespace may have more than one actor handle. Its short-lived
/// native lock covers synchronous disk/Keychain work without any await inside.
private final class VocabularyPackNamespaces: @unchecked Sendable {
    static let shared = VocabularyPackNamespaces()
    private let guardLock = NSLock()
    private var locks: [String: NSRecursiveLock] = [:]
    func lock(_ namespace: String) -> NSRecursiveLock {
        guardLock.withLock {
            if let existing = locks[namespace] { return existing }
            let value = NSRecursiveLock(); locks[namespace] = value; return value
        }
    }
}
enum VocabularyPackKind: Sendable {
    case vocabulary, reviewedContext, reviewedFrame
    var reviewed: Bool { self != .vocabulary }
    var schemas: [Int] { self == .reviewedFrame ? [6,7,8] : [5] }
    func policy(_ schema:Int) -> String {
        guard self == .reviewedFrame else {return "reviewed-finite-context-1"}
        switch schema {
        case 8:return "reviewed-bidirectional-side-unit-3"
        case 7:return "reviewed-bidirectional-phrase-and-unit-2"
        default:return "reviewed-bidirectional-phrase-1"
        }
    }
    var databaseFile: String { self == .reviewedFrame ? "frames.sqlite" : "contexts.sqlite" }
    func metadataSchema(_ schema:Int) -> String {
        guard self == .reviewedFrame else {return "vipi-reviewed-context-1"}
        switch schema {
        case 8:return "vipi-reviewed-frame-3"
        case 7:return "vipi-reviewed-frame-2"
        default:return "vipi-reviewed-frame-1"
        }
    }
    var indexes: [String] { self == .reviewedFrame ? ["source_inputs", "target_inputs"] : ["context_inputs"] }
}

/// Serializes install/query/removal; files contain only public vocabulary data.
actor VocabularyPackStore {
    private let root: URL
    private let trustedKeys: [String: Data]
    private let receiptPrefix: String
    private let kind: VocabularyPackKind
    private let namespaceLock: NSRecursiveLock
    private struct Accepted: Codable { let revision: Int; let hash: String }
    private struct Activation: Codable { let file: String; let manifestBytes: Data; let signature: Data }
    private struct Record: Codable {
        let schema: String
        let accepted: Accepted
        let active: Activation?
        enum CodingKeys: String, CodingKey { case schema, accepted, active }
        init(schema: String, accepted: Accepted, active: Activation?) {
            self.schema = schema; self.accepted = accepted; self.active = active
        }
        init(from decoder: Decoder) throws {
            let fields = try decoder.container(keyedBy: CodingKeys.self)
            guard fields.contains(.active) else { throw VocabularyPackError.invalid }
            schema = try fields.decode(String.self, forKey: .schema)
            accepted = try fields.decode(Accepted.self, forKey: .accepted)
            active = try fields.decodeIfPresent(Activation.self, forKey: .active)
        }
        func encode(to encoder: Encoder) throws {
            var fields = encoder.container(keyedBy: CodingKeys.self)
            try fields.encode(schema, forKey: .schema); try fields.encode(accepted, forKey: .accepted)
            if let active { try fields.encode(active, forKey: .active) }
            else { try fields.encodeNil(forKey: .active) }
        }
    }
    private enum Saved { case absent, legacy(Accepted), current(Record)
        var accepted: Accepted? {
            switch self { case .absent: nil; case .legacy(let value): value; case .current(let value): value.accepted }
        }
    }
    #if DEBUG
    private var qualificationFailure: (@Sendable (VocabularyPackCheckpoint) throws -> Void)?
    func qualifyFailure(_ hook: @escaping @Sendable (VocabularyPackCheckpoint) throws -> Void) { qualificationFailure = hook }
    #endif

    init(root: URL, trustedKeys: [String: Data], receiptPrefix: String = "pack-", kind: VocabularyPackKind = .vocabulary) throws {
        guard receiptPrefix.range(of: "^[a-z0-9-]{1,64}$", options: .regularExpression) != nil else { throw VocabularyPackError.invalid }
        self.kind = kind
        self.root = kind.reviewed ? root.appendingPathComponent(kind == .reviewedFrame ? "reviewed-frames" : "reviewed-contexts") : root
        self.trustedKeys = trustedKeys; self.receiptPrefix = (kind.reviewed ? (kind == .reviewedFrame ? "frame-" : "context-") : "") + receiptPrefix
        namespaceLock = VocabularyPackNamespaces.shared.lock(self.receiptPrefix)
        try FileManager.default.createDirectory(at: self.root, withIntermediateDirectories: true)
    }
    private func validID(_ id: String) -> Bool { id.range(of: #"^[a-z]{2,3}-[a-z]{2,3}$"#, options: .regularExpression) != nil }
    private func saved(_ id: String) throws -> Saved {
        guard let data = try KeychainStore.read(account: receiptPrefix + id) else { return .absent }
        guard data.count <= 32_768, let fields = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { throw VocabularyPackError.invalid }
        let value: Saved
        if Set(fields.keys) == ["revision", "hash"] { value = .legacy(try JSONDecoder().decode(Accepted.self, from: data)) }
        else {
            let record = try JSONDecoder().decode(Record.self, from: data)
            guard record.schema == "vipi-pack-activation-1" else { throw VocabularyPackError.invalid }
            value = .current(record)
        }
        guard let accepted = value.accepted, accepted.revision > 0,
              accepted.hash.range(of: #"^[a-f0-9]{64}$"#, options: .regularExpression) != nil else { throw VocabularyPackError.invalid }
        return value
    }
    private func commit(_ record: Record, id: String) throws {
        let data = try JSONEncoder().encode(record)
        guard data.count <= 32_768 else { throw VocabularyPackError.invalid }
        try KeychainStore.save(data, account: receiptPrefix + id)
    }
    private func checkpoint(_ point: VocabularyPackCheckpoint) throws {
        #if DEBUG
        try qualificationFailure?(point)
        #endif
    }
    private func active(_ value: Saved, id: String) throws -> (Activation, VocabularyManifest)? {
        if case .legacy = value { throw VocabularyPackError.reinstallRequired }
        guard case .current(let record) = value, let active = record.active else { return nil }
        guard (1...16_384).contains(active.manifestBytes.count), (64...80).contains(active.signature.count) else { throw VocabularyPackError.invalid }
        let manifest = try JSONDecoder().decode(VocabularyManifest.self, from: active.manifestBytes)
        guard let keyData = trustedKeys[manifest.key_id] else { throw VocabularyPackError.untrustedKey }
        let key = try P256.Signing.PublicKey(derRepresentation: keyData)
        guard manifest.signature_algorithm == "ECDSA-P256-SHA256",
              key.isValidSignature(try P256.Signing.ECDSASignature(derRepresentation: active.signature), for: active.manifestBytes) else { throw VocabularyPackError.signature }
        guard manifest.pack_id == id, id == manifest.source_language + "-" + manifest.target_language,
              manifest.revision == record.accepted.revision, manifest.sha256 == record.accepted.hash,
              active.file == "\(id)-\(record.accepted.revision)-\(record.accepted.hash).sqlite" else { throw VocabularyPackError.rollback }
        return (active, manifest)
    }
    private func cleanupFiles(id: String, keeping: String?) throws -> [URL] {
        try FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil).filter {
            $0.lastPathComponent != keeping && ($0.lastPathComponent == id + ".json" ||
                $0.lastPathComponent.range(of: "^" + id + #"-[1-9][0-9]*-[a-f0-9]{64}\.sqlite$"#, options: .regularExpression) != nil)
        }
    }
    private func cleanup(id: String, keeping: String?) throws {
        try checkpoint(.cleanup)
        var failed = false
        for file in try cleanupFiles(id: id, keeping: keeping) {
            do { try FileManager.default.removeItem(at: file) } catch { failed = true }
        }
        if failed { throw VocabularyPackError.cleanupPending }
    }
    func status(id: String) throws -> VocabularyPackStatus {
        try namespaceLock.withLock {
            guard validID(id) else { throw VocabularyPackError.invalid }
            let value = try saved(id)
            if case .legacy(let accepted) = value {
                return .init(acceptedRevision: accepted.revision, acceptedHash: accepted.hash,
                    active: false, reinstallRequired: true, cleanupPendingFiles: [])
            }
            let current = try active(value, id: id)
            if let current { try verifyActiveFile(current.0.file, manifest: current.1) }
            return .init(acceptedRevision: value.accepted?.revision, acceptedHash: value.accepted?.hash,
                active: current != nil, reinstallRequired: false,
                cleanupPendingFiles: try cleanupFiles(id: id, keeping: current?.0.file).map(\.lastPathComponent).sorted())
        }
    }
    func install(manifestBytes: Data, signature: Data, database: Data) throws -> String {
        try checkpoint(.waitingForNamespace)
        return try namespaceLock.withLock { try installLocked(manifestBytes: manifestBytes, signature: signature, database: database) }
    }
    private func installLocked(manifestBytes: Data, signature: Data, database: Data) throws -> String {
        try Task.checkCancellation()
        guard (1...16_384).contains(manifestBytes.count), (64...80).contains(signature.count), (512...67_108_864).contains(database.count) else { throw VocabularyPackError.invalid }
        let manifest = try JSONDecoder().decode(VocabularyManifest.self, from: manifestBytes)
        guard let keyData = trustedKeys[manifest.key_id] else { throw VocabularyPackError.untrustedKey }
        let key = try P256.Signing.PublicKey(derRepresentation: keyData)
        guard manifest.signature_algorithm == "ECDSA-P256-SHA256", key.isValidSignature(try P256.Signing.ECDSASignature(derRepresentation: signature), for: manifestBytes) else { throw VocabularyPackError.signature }
        let id = manifest.pack_id
        let hash = SHA256.hash(data: database).map { String(format: "%02x", $0) }.joined()
        guard validID(id), id == manifest.source_language + "-" + manifest.target_language, manifest.revision > 0,
              (kind.reviewed ? kind.schemas.contains(manifest.schema_version) : [1, 3, 4].contains(manifest.schema_version)),
              (kind.reviewed ? manifest.normalization == "exact-utf16" :
                (manifest.normalization == "unicode-nfc-lower" || (manifest.schema_version >= 3 && manifest.normalization == "unicode-nfc-lower-arabic-harakat-v1"))),
              (kind.reviewed ? manifest.context_policy == kind.policy(manifest.schema_version) :
                (manifest.schema_version == 4 ? ["all-source-senses-veto-3","all-source-senses-native-guards-veto-4"].contains(manifest.context_policy ?? "") : (manifest.context_policy == nil || manifest.context_policy == "cross-sense-label-veto-2"))),
              (manifest.context_policy == "all-source-senses-native-guards-veto-4") == (manifest.native_source_guard_policy != nil),
              manifest.file == (kind.reviewed ? kind.databaseFile : "vocabulary.sqlite"),
              manifest.bytes == database.count, manifest.sha256 == hash,
              database.prefix(16) == Data("SQLite format 3\0".utf8) else { throw VocabularyPackError.invalid }
        let previous = try saved(id)
        if let accepted = previous.accepted {
            guard manifest.revision > accepted.revision || (manifest.revision == accepted.revision && hash == accepted.hash) else { throw VocabularyPackError.rollback }
        }
        let filename = "\(id)-\(manifest.revision)-\(hash).sqlite"
        let destination = root.appendingPathComponent(filename)
        let temporary = root.appendingPathComponent("install-\(UUID()).sqlite")
        defer { try? FileManager.default.removeItem(at: temporary) }
        try database.write(to: temporary, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        let stagedFile = try FileHandle(forWritingTo: temporary)
        do { try stagedFile.synchronize(); try stagedFile.close() }
        catch { try? stagedFile.close(); throw error }
        try withDatabase(temporary) { db in
            guard try scalar(db, "PRAGMA application_id") == "1447645257", try scalar(db, "PRAGMA user_version") == String(manifest.schema_version),
                  try scalar(db, "PRAGMA quick_check") == "ok", try scalar(db, "SELECT value FROM metadata WHERE key='pack_id'") == id else { throw VocabularyPackError.invalid }
            if kind.reviewed {
                guard try scalar(db,"SELECT value FROM metadata WHERE key='schema'") == kind.metadataSchema(manifest.schema_version),
                      try scalar(db,"SELECT value FROM metadata WHERE key='context_policy'") == kind.policy(manifest.schema_version),
                      try scalar(db,"SELECT id FROM mappings LIMIT 1") != nil,
                      try scalar(db,"SELECT count(*) FROM mappings WHERE length(CAST(payload AS BLOB))>32768") == "0",
                      try scalar(db,"PRAGMA foreign_key_check") == nil else { throw VocabularyPackError.invalid }
                for index in kind.indexes {
                    guard try scalar(db,"SELECT count(*) FROM (SELECT input FROM \(index) GROUP BY input HAVING count(*)>256)") == "0",
                          try scalar(db,"SELECT count(*) FROM mappings m WHERE NOT EXISTS (SELECT 1 FROM \(index) i WHERE i.mapping_id=m.id)") == "0" else {throw VocabularyPackError.invalid}
                }
                return
            }
            guard try scalar(db,"SELECT source FROM vocabulary LIMIT 1") != nil else { throw VocabularyPackError.invalid }
            if let policy=manifest.native_source_guard_policy {
                guard manifest.schema_version==4,manifest.source_language=="zh",
                      policy=="attested-native-han-lexeme-and-polysemy-veto-1",
                      let guardHash=manifest.native_source_guard_sha256,
                      try scalar(db,"SELECT value FROM metadata WHERE key='native_source_guard_policy'")==policy,
                      try scalar(db,"SELECT value FROM metadata WHERE key='native_source_guard_sha256'")==guardHash,
                      try scalar(db,"SELECT count(*) FROM source_guards WHERE length(source)<1 OR length(source)>32 OR protect_inner NOT IN (0,1) OR ambiguous NOT IN (0,1)")=="0"
                else {throw VocabularyPackError.invalid}
            }
            if manifest.schema_version >= 3 {
                guard try scalar(db, "SELECT value FROM metadata WHERE key='schema'") == "vipi-bilingual-\(manifest.schema_version)",
                      try scalar(db, "SELECT source_url FROM senses LIMIT 1") != nil,
                      try scalar(db, "SELECT reading FROM vocabulary LIMIT 1") != nil,
                      try scalar(db, "PRAGMA foreign_key_check") == nil else { throw VocabularyPackError.invalid }
                if let policy = manifest.context_policy {
                    guard try scalar(db, "SELECT value FROM metadata WHERE key='context_policy'") == policy,
                          try scalar(db, "SELECT count(*) FROM sense_context WHERE length(hints)>4096") == "0" else { throw VocabularyPackError.invalid }
                }
                if manifest.schema_version == 4 {
                    guard try scalar(db, "SELECT count(*) FROM source_senses") != "0",
                          try scalar(db, "SELECT count(*) FROM vocabulary v WHERE NOT EXISTS (SELECT 1 FROM source_senses s WHERE s.source=v.source AND s.sense_id=v.sense_id)") == "0" else { throw VocabularyPackError.invalid }
                }
            }
        }
        try checkpoint(.staged); try Task.checkCancellation()
        let existed = FileManager.default.fileExists(atPath: destination.path)
        var committed = false
        defer {
            // A newly finalized upgrade is disposable before activation. Never
            // remove a pre-existing immutable file or a repaired active file.
            if !committed && !existed {
                if case .current(let value) = previous, value.active?.file == filename {} else { try? FileManager.default.removeItem(at: destination) }
            }
        }
        if existed {
            _ = try FileManager.default.replaceItemAt(destination, withItemAt: temporary)
        } else { try FileManager.default.moveItem(at: temporary, to: destination) }
        try checkpoint(.beforeDirectorySync)
        let directory = open(root.path, O_RDONLY | O_DIRECTORY)
        guard directory >= 0 else { throw VocabularyPackError.storage }
        let synchronized = fsync(directory)
        let closed = close(directory)
        guard synchronized == 0, closed == 0 else { throw VocabularyPackError.storage }
        try checkpoint(.beforeActivation); try Task.checkCancellation()
        try commit(.init(schema: "vipi-pack-activation-1", accepted: .init(revision: manifest.revision, hash: hash),
            active: .init(file: filename, manifestBytes: manifestBytes, signature: signature)), id: id)
        committed = true
        // Activation has happened. Cleanup or late cancellation cannot turn
        // this into an apparent failed install. status() exposes leftovers.
        try? cleanup(id: id, keeping: filename)
        return id
    }

    func entries(id: String, text: String, translation: String? = nil) throws -> [VocabularyEntry] {
        try namespaceLock.withLock { try entriesLocked(id: id, text: text, translation: translation) }
    }
    private func entriesLocked(id: String, text: String, translation: String?) throws -> [VocabularyEntry] {
        guard validID(id), text.utf16.count <= 16_384 else { throw VocabularyPackError.invalid }
        guard let (activation, manifest) = try active(saved(id), id: id) else { return [] }
        let pointer = (file: activation.file, manifest: manifest)
        try verifyActiveFile(activation.file, manifest: manifest)
        if kind == .reviewedFrame {
            guard kind.schemas.contains(pointer.manifest.schema_version),pointer.manifest.context_policy==kind.policy(pointer.manifest.schema_version) else {throw VocabularyPackError.invalid}
            guard let translation, !translation.isEmpty, translation.utf16.count<=32768 else {return []}
            return try withDatabase(root.appendingPathComponent(pointer.file)) { db in
                try ReviewedFrameLookup.entries(db:db,original:text,translation:translation,
                    source:pointer.manifest.source_language,target:pointer.manifest.target_language)
            }
        }
        if kind == .reviewedContext {
            guard pointer.manifest.schema_version == 5 else { throw VocabularyPackError.invalid }
            return try withDatabase(root.appendingPathComponent(pointer.file)) { db in
                let source=pointer.manifest.source_language,target=pointer.manifest.target_language
                return try ReviewedContextLookup.entries(db: db, original: text, source: source, target: target)
            }
        }
        let rawTerms = try candidateTerms(text, language: pointer.manifest.source_language)
        let terms = pointer.manifest.normalization == "unicode-nfc-lower-arabic-harakat-v1" ? Array(Set(rawTerms.map(ImmersionEngine.lookupKey))).sorted() : rawTerms
        if terms.isEmpty { return [] }
        return try withDatabase(root.appendingPathComponent(pointer.file)) { db in
            struct LookupKey: Hashable { let source: String; let sense: String }
            struct Group { var targets = Set<String>(); var readings: [String: Set<String>] = [:]; var hints = Set<String>() }
            var grouped: [LookupKey: Group] = [:]
            var meanings: [String: Set<String>] = [:]
            var nativeGuards:[VocabularyEntry]=[]
            for offset in stride(from: 0, to: terms.count, by: 200) {
                let batch = Array(terms[offset..<min(offset + 200, terms.count)])
                let placeholders = Array(repeating: "?", count: batch.count).joined(separator: ",")
                let sql: String
                if pointer.manifest.schema_version == 4 {
                    sql = "SELECT s.source,s.sense_id,v.target,v.reading,COALESCE(c.hints,'') FROM source_senses s LEFT JOIN vocabulary v ON v.source=s.source AND v.sense_id=s.sense_id LEFT JOIN sense_context c ON c.sense_id=s.sense_id WHERE s.source IN (\(placeholders)) ORDER BY s.source,s.sense_id,v.target,v.reading"
                } else {
                    var columns = pointer.manifest.schema_version == 3 ? "source,sense_id,target,reading" : "source,'' AS sense_id,target,'' AS reading"
                    columns += pointer.manifest.context_policy == "cross-sense-label-veto-2" ? ",COALESCE((SELECT hints FROM sense_context WHERE sense_context.sense_id=vocabulary.sense_id),'') AS hints" : ",'' AS hints"
                    sql = "SELECT DISTINCT " + columns + " FROM vocabulary WHERE source IN (\(placeholders)) ORDER BY source,sense_id,target,reading"
                }
                var statement: OpaquePointer?
                guard sqlite3_prepare_v2(db, sql, -1, &statement, nil) == SQLITE_OK else { throw VocabularyPackError.storage }
                defer { sqlite3_finalize(statement) }
                for (index, term) in batch.enumerated() {
                    guard sqlite3_bind_text(statement, Int32(index + 1), term, -1, unsafeBitCast(-1, to: sqlite3_destructor_type.self)) == SQLITE_OK else { throw VocabularyPackError.storage }
                }
                var result = sqlite3_step(statement)
                while result == SQLITE_ROW {
                    guard let source = sqlite3_column_text(statement, 0), let sense = sqlite3_column_text(statement, 1) else { throw VocabularyPackError.invalid }
                    let key = LookupKey(source: String(cString: source), sense: String(cString: sense))
                    if grouped[key] == nil { grouped[key] = Group() }
                    if let target = sqlite3_column_text(statement, 2), let reading = sqlite3_column_text(statement, 3) {
                        let surface = String(cString: target)
                        grouped[key, default: Group()].targets.insert(surface)
                        grouped[key, default: Group()].readings[surface, default: []].insert(String(cString: reading))
                    }
                    if let hints = sqlite3_column_text(statement, 4) { grouped[key, default: Group()].hints.formUnion(String(cString: hints).split(separator: "\u{1f}").map(String.init)) }
                    meanings[key.source, default: []].insert(key.sense)
                    result = sqlite3_step(statement)
                }
                guard result == SQLITE_DONE else { throw VocabularyPackError.storage }
                if pointer.manifest.native_source_guard_policy=="attested-native-han-lexeme-and-polysemy-veto-1" {
                    var guardStatement:OpaquePointer?
                    guard sqlite3_prepare_v2(db,"SELECT source,protect_inner,ambiguous FROM source_guards WHERE source IN (\(placeholders))",-1,&guardStatement,nil)==SQLITE_OK else {throw VocabularyPackError.storage}
                    defer {sqlite3_finalize(guardStatement)}
                    for(index,term) in batch.enumerated() {
                        guard sqlite3_bind_text(guardStatement,Int32(index+1),term,-1,unsafeBitCast(-1,to:sqlite3_destructor_type.self))==SQLITE_OK else {throw VocabularyPackError.storage}
                    }
                    var guardResult=sqlite3_step(guardStatement)
                    while guardResult==SQLITE_ROW {
                        guard let source=sqlite3_column_text(guardStatement,0) else {throw VocabularyPackError.invalid}
                        nativeGuards.append(.init(source:String(cString:source),targets:[],protectInner:sqlite3_column_int(guardStatement,1)==1,
                                                  unresolvedNativeSenses:sqlite3_column_int(guardStatement,2)==1))
                        guardResult=sqlite3_step(guardStatement)
                    }
                    guard guardResult==SQLITE_DONE else {throw VocabularyPackError.storage}
                }
            }
            return grouped.keys.sorted { ($0.source, $0.sense) < ($1.source, $1.sense) }.map { key in
                let group = grouped[key]!
                return VocabularyEntry(source: key.source, targets: group.targets.sorted(), romanizations: group.readings.mapValues { $0.sorted() }, contextHints: group.hints.sorted(), requiresContext: meanings[key.source, default: []].count > 1)
            }+nativeGuards
        }
    }

    func remove(id: String) throws {
        try namespaceLock.withLock {
            guard validID(id) else { throw VocabularyPackError.invalid }
            let current = try saved(id)
            // Legacy unsigned metadata cannot be promoted by removal either.
            if case .legacy = current { throw VocabularyPackError.reinstallRequired }
            guard let accepted = current.accepted else { return }
            try checkpoint(.beforeRemoval); try Task.checkCancellation()
            try commit(.init(schema: "vipi-pack-activation-1", accepted: accepted, active: nil), id: id)
            do { try cleanup(id: id, keeping: nil) }
            catch { throw VocabularyPackError.cleanupPending }
        }
    }

    private func verifyActiveFile(_ filename: String, manifest: VocabularyManifest) throws {
        let file = root.appendingPathComponent(filename)
        let values = try file.resourceValues(forKeys: [.fileSizeKey])
        guard values.fileSize == manifest.bytes else { throw VocabularyPackError.invalid }
        let stream = try FileHandle(forReadingFrom: file); defer { try? stream.close() }
        var hash = SHA256()
        while let data = try stream.read(upToCount: 65_536), !data.isEmpty {
            try Task.checkCancellation(); hash.update(data: data)
        }
        guard hash.finalize().map({ String(format: "%02x", $0) }).joined() == manifest.sha256 else { throw VocabularyPackError.invalid }
    }

    private func withDatabase<T>(_ url: URL, _ body: (OpaquePointer) throws -> T) throws -> T {
        var handle: OpaquePointer?
        guard sqlite3_open_v2(url.path, &handle, SQLITE_OPEN_READONLY | SQLITE_OPEN_NOMUTEX, nil) == SQLITE_OK, let db = handle else { if let handle { sqlite3_close(handle) }; throw VocabularyPackError.storage }
        defer { sqlite3_close(db) }
        return try body(db)
    }
    private func scalar(_ db: OpaquePointer, _ sql: String) throws -> String? {
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &statement, nil) == SQLITE_OK else { throw VocabularyPackError.storage }
        defer { sqlite3_finalize(statement) }
        let status = sqlite3_step(statement)
        if status == SQLITE_DONE { return nil }
        guard status == SQLITE_ROW, let value = sqlite3_column_text(statement, 0) else { throw VocabularyPackError.storage }
        return String(cString: value)
    }
    private func candidateTerms(_ text: String, language: String) throws -> [String] {
        let ns = text as NSString
        let regex = try NSRegularExpression(pattern: #"[\p{L}\p{M}]+(?:['’-][\p{L}\p{M}]+)*"#)
        let words = ["zh", "ja"].contains(language) ? LocalImmersion.words(text, language: language) : regex.matches(in: text, range: NSRange(location: 0, length: ns.length)).map(\.range)
        var terms = Set<String>()
        for start in words.indices { for count in 1...min(5, words.count - start) {
            let end = start + count - 1
            if (start..<end).contains(where: { index in
                let gap = ns.substring(with: NSRange(location: NSMaxRange(words[index]), length: words[index + 1].location - NSMaxRange(words[index])))
                return !gap.allSatisfy(\.isWhitespace)
            }) { continue }
            let range = NSRange(location: words[start].location, length: NSMaxRange(words[end]) - words[start].location)
            let surface = ns.substring(with: range).split(whereSeparator: \.isWhitespace).joined(separator: " ")
            terms.insert(surface.precomposedStringWithCanonicalMapping.lowercased())
        } }
        return terms.sorted()
    }
}
