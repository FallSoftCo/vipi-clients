import CryptoKit
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
}

enum VocabularyPackError: Error { case invalid, untrustedKey, signature, rollback, storage }

/// Serializes install/query/removal; files contain only public vocabulary data.
actor VocabularyPackStore {
    private let root: URL
    private let trustedKeys: [String: Data]
    private struct Accepted: Codable { let revision: Int; let hash: String }
    private struct Pointer: Codable { let file: String; let manifest: VocabularyManifest }

    init(root: URL, trustedKeys: [String: Data]) throws {
        self.root = root; self.trustedKeys = trustedKeys
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }
    private func validID(_ id: String) -> Bool { id.range(of: #"^[a-z]{2,3}-[a-z]{2,3}$"#, options: .regularExpression) != nil }
    private func accepted(_ id: String) throws -> Accepted? {
        guard let data = try KeychainStore.read(account: "pack-" + id) else { return nil }
        return try JSONDecoder().decode(Accepted.self, from: data)
    }
    func install(manifestBytes: Data, signature: Data, database: Data) throws -> String {
        guard (1...16_384).contains(manifestBytes.count), (64...80).contains(signature.count), (512...67_108_864).contains(database.count) else { throw VocabularyPackError.invalid }
        let manifest = try JSONDecoder().decode(VocabularyManifest.self, from: manifestBytes)
        guard let keyData = trustedKeys[manifest.key_id] else { throw VocabularyPackError.untrustedKey }
        let key = try P256.Signing.PublicKey(derRepresentation: keyData)
        guard manifest.signature_algorithm == "ECDSA-P256-SHA256", key.isValidSignature(try P256.Signing.ECDSASignature(derRepresentation: signature), for: manifestBytes) else { throw VocabularyPackError.signature }
        let id = manifest.pack_id
        let hash = SHA256.hash(data: database).map { String(format: "%02x", $0) }.joined()
        guard validID(id), id == manifest.source_language + "-" + manifest.target_language, manifest.revision > 0,
              manifest.schema_version == 1, manifest.normalization == "unicode-nfc-lower", manifest.file == "vocabulary.sqlite",
              manifest.bytes == database.count, manifest.sha256 == hash,
              database.prefix(16) == Data("SQLite format 3\0".utf8) else { throw VocabularyPackError.invalid }
        if let previous = try accepted(id) {
            guard manifest.revision > previous.revision || (manifest.revision == previous.revision && hash == previous.hash) else { throw VocabularyPackError.rollback }
        }
        let filename = "\(id)-\(manifest.revision)-\(hash).sqlite"
        let destination = root.appendingPathComponent(filename)
        let temporary = root.appendingPathComponent("install-\(UUID()).sqlite")
        defer { try? FileManager.default.removeItem(at: temporary) }
        try database.write(to: temporary, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        try withDatabase(temporary) { db in
            guard try scalar(db, "PRAGMA application_id") == "1447645257", try scalar(db, "PRAGMA user_version") == "1",
                  try scalar(db, "PRAGMA quick_check") == "ok", try scalar(db, "SELECT value FROM metadata WHERE key='pack_id'") == id,
                  try scalar(db, "SELECT source FROM vocabulary LIMIT 1") != nil else { throw VocabularyPackError.invalid }
        }
        if FileManager.default.fileExists(atPath: destination.path) {
            _ = try FileManager.default.replaceItemAt(destination, withItemAt: temporary)
        } else { try FileManager.default.moveItem(at: temporary, to: destination) }
        try KeychainStore.save(JSONEncoder().encode(Accepted(revision: manifest.revision, hash: hash)), account: "pack-" + id)
        try JSONEncoder().encode(Pointer(file: filename, manifest: manifest)).write(to: root.appendingPathComponent(id + ".json"), options: .atomic)
        for old in try FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil) where old.lastPathComponent.hasPrefix(id + "-") && old.pathExtension == "sqlite" && old != destination { try? FileManager.default.removeItem(at: old) }
        return id
    }

    func entries(id: String, text: String) throws -> [VocabularyEntry] {
        guard validID(id), text.utf16.count <= 16_384 else { throw VocabularyPackError.invalid }
        let pointerURL = root.appendingPathComponent(id + ".json")
        guard FileManager.default.fileExists(atPath: pointerURL.path) else { return [] }
        let pointer = try JSONDecoder().decode(Pointer.self, from: Data(contentsOf: pointerURL))
        guard let approved = try accepted(id), pointer.manifest.revision == approved.revision, pointer.manifest.sha256 == approved.hash,
              pointer.file == "\(id)-\(approved.revision)-\(approved.hash).sqlite" else { throw VocabularyPackError.rollback }
        let terms = try candidateTerms(text, language: pointer.manifest.source_language)
        if terms.isEmpty { return [] }
        return try withDatabase(root.appendingPathComponent(pointer.file)) { db in
            var grouped: [String: Set<String>] = [:]
            for offset in stride(from: 0, to: terms.count, by: 200) {
                let batch = Array(terms[offset..<min(offset + 200, terms.count)])
                let sql = "SELECT DISTINCT source,target FROM vocabulary WHERE source IN (" + Array(repeating: "?", count: batch.count).joined(separator: ",") + ") ORDER BY source,target"
                var statement: OpaquePointer?
                guard sqlite3_prepare_v2(db, sql, -1, &statement, nil) == SQLITE_OK else { throw VocabularyPackError.storage }
                defer { sqlite3_finalize(statement) }
                for (index, term) in batch.enumerated() {
                    guard sqlite3_bind_text(statement, Int32(index + 1), term, -1, unsafeBitCast(-1, to: sqlite3_destructor_type.self)) == SQLITE_OK else { throw VocabularyPackError.storage }
                }
                var result = sqlite3_step(statement)
                while result == SQLITE_ROW {
                    guard let source = sqlite3_column_text(statement, 0), let target = sqlite3_column_text(statement, 1) else { throw VocabularyPackError.invalid }
                    grouped[String(cString: source), default: []].insert(String(cString: target))
                    result = sqlite3_step(statement)
                }
                guard result == SQLITE_DONE else { throw VocabularyPackError.storage }
            }
            return grouped.keys.sorted().map { VocabularyEntry(source: $0, targets: grouped[$0]!.sorted()) }
        }
    }

    func remove(id: String) throws {
        guard validID(id) else { throw VocabularyPackError.invalid }
        for file in try FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil) where file.lastPathComponent == id + ".json" || (file.lastPathComponent.hasPrefix(id + "-") && file.pathExtension == "sqlite") { try FileManager.default.removeItem(at: file) }
        // Keep accepted revision in Keychain to prevent rollback after deletion.
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
