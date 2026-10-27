import CryptoKit
import Foundation
import SQLite3
import VipiCore

/// Public, app-signed starter data. No message text or downloaded QA keys are
/// persisted here. Future updates use the separate signed pack installer.
actor BundledImmersionCatalog {
    private struct Index: Decodable {
        struct Pack: Decodable { let id: String; let sha256: String; let bytes: Int }
        struct Reference: Decodable { let pair: String; let original: String; let translation: String }
        let schema: String
        let packs: [Pack]
        let contexts: [Pack]?
        let references: [Reference]
    }
    private let root: URL?
    private var verified = Set<String>()
    private var index: Index?
    private var references: [String: [String: String]] = [:]
    init(root: URL? = Bundle.main.resourceURL?.appendingPathComponent("immersion")) { self.root = root }
    private func loadIndex() throws -> Index {
        if let index { return index }
        guard let root else { throw VocabularyPackError.invalid }
        let value = try JSONDecoder().decode(Index.self, from: Data(contentsOf: root.appendingPathComponent("catalog.json")))
        guard value.schema == "vipi-bundled-frames-1" else { throw VocabularyPackError.invalid }
        for reference in value.references {
            guard references[reference.pair]?[reference.original] == nil else { throw VocabularyPackError.invalid }
            references[reference.pair, default: [:]][reference.original] = reference.translation
        }
        index = value; return value
    }
    func reference(original: String, pair: TranslationPair) throws -> String? {
        let id = pair.source + "-" + pair.target
        _ = try loadIndex()
        guard let values = references[id] else { return nil }
        if let value = values[original] { return value }
        // Compose only independently known complete sentences. Retain every
        // whitespace separator; an unrecognised clause makes this unavailable.
        let sentences = LocalImmersion.sentences(original, language: pair.source)
        guard !sentences.isEmpty else { return nil }
        let text = original as NSString
        var end = 0, output = ""
        for range in sentences {
            let gap = text.substring(with: NSRange(location: end, length: range.location-end))
            guard gap.allSatisfy(\.isWhitespace), let value = values[text.substring(with: range)] else { return nil }
            output += gap + value; end = NSMaxRange(range)
        }
        let tail = text.substring(from: end)
        return tail.allSatisfy(\.isWhitespace) ? output + tail : nil
    }
    func result(original: String, translation: String, pair: TranslationPair, density: Double,
                supplementalEntries: [VocabularyEntry] = []) throws -> ImmersionResult {
        guard let root, pair.valid else { throw VocabularyPackError.invalid }
        let id = pair.source + "-" + pair.target
        let index = try loadIndex()
        guard let pack = index.packs.first(where: { $0.id == id }) else { throw VocabularyPackError.invalid }
        var entries = try withDatabase(root: root, pack: pack, suffix: "") { db in
            try ReviewedFrameLookup.entries(db: db, original: original, translation: translation,
                source: pair.source, target: pair.target)
        }
        if let context = index.contexts?.first(where: { $0.id == id }) {
            entries += try withDatabase(root: root, pack: context, suffix: "-contexts") { db in
                try ReviewedContextLookup.entries(db: db, original: original, source: pair.source, target: pair.target)
            }
        }
        return LocalImmersion.align(original: original, translation: translation, entries: entries,
            density: density, source: pair.source, target: pair.target, supplementalEntries: supplementalEntries)
    }
    private func withDatabase<T>(root: URL, pack: Index.Pack, suffix: String, body: (OpaquePointer) throws -> T) throws -> T {
        let id = pack.id + suffix
        let database = root.appendingPathComponent(id + ".sqlite")
        if !verified.contains(id) {
            let data = try Data(contentsOf: database)
            guard data.count == pack.bytes,
                  SHA256.hash(data: data).map({ String(format: "%02x", $0) }).joined() == pack.sha256 else {
                throw VocabularyPackError.invalid
            }
            verified.insert(id)
        }
        var handle: OpaquePointer?
        guard sqlite3_open_v2(database.path, &handle, SQLITE_OPEN_READONLY | SQLITE_OPEN_NOMUTEX, nil) == SQLITE_OK,
              let db = handle else { if let handle { sqlite3_close(handle) }; throw VocabularyPackError.storage }
        defer { sqlite3_close(db) }
        return try body(db)
    }
}
