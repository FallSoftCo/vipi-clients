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
    private var catalogSHA256: String?
    private var references: [String: [String: String]] = [:]
    init(root: URL? = Bundle.main.resourceURL?.appendingPathComponent("immersion")) { self.root = root }
    private func loadIndex() throws -> Index {
        if let index { return index }
        guard let root else { throw VocabularyPackError.invalid }
        let bytes = try Data(contentsOf: root.appendingPathComponent("catalog.json"))
        let value = try JSONDecoder().decode(Index.self, from: bytes)
        guard value.schema == "vipi-bundled-frames-1" else { throw VocabularyPackError.invalid }
        var loaded: [String: [String: String]] = [:]
        for reference in value.references {
            guard loaded[reference.pair]?[reference.original] == nil else { throw VocabularyPackError.invalid }
            loaded[reference.pair, default: [:]][reference.original] = reference.translation
        }
        references = loaded
        catalogSHA256 = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
        index = value; return value
    }
    func reference(original: String, pair: TranslationPair) throws -> String? {
        let id = pair.source + "-" + pair.target
        _ = try loadIndex()
        guard let values = references[id] else { return nil }
        if let value = values[original] { return value }
        return ReferenceComposition.compose(original: original,
            sentences: LocalImmersion.sentences(original, language: pair.source), target: pair.target,
            lookup: { values[$0] })
    }
    func partial(original: String, pair: TranslationPair, density: Double) throws -> PartialImmersionResult? {
        guard pair.valid else { throw VocabularyPackError.invalid }
        guard !original.isEmpty, original.utf16.count <= 16_384 else { return nil }
        _ = try loadIndex()
        guard let values = references[pair.source + "-" + pair.target], let catalogSHA256 else { return nil }
        let text = original as NSString
        guard let nativeBasis = NativeSourceTokenBasis(original: original,
            wordRanges: LocalImmersion.words(original, language: pair.source)) else { return nil }
        let units = LocalImmersion.sentences(original, language: pair.source).compactMap { range -> SourceReferenceUnit? in
            let source = text.substring(with: range)
            guard let translated = values[source], source.utf16.count <= 128, translated.utf16.count <= 128 else { return nil }
            guard let cost = nativeBasis.cost(for: range) else { return nil }
            let identity = pair.source + "\0" + pair.target + "\0" + source + "\0" + translated
            let reference = SHA256.hash(data: Data(identity.utf8)).map { String(format: "%02x", $0) }.joined()
            return .init(range: range, original: source, translated: translated,
                reading: SentenceReadings.reading(translated, language: pair.target),
                referenceID: "catalog-reference-sha256:" + reference, catalogSHA256: catalogSHA256,
                nativeSourceTokens: cost)
        }
        return SourceReferencePresentation.create(original: original, target: pair.target, units: units,
            density: density, nativeSourceTokenCount: nativeBasis.count)
    }
    func result(original: String, translation: String, pair: TranslationPair, density: Double,
                supplementalEntries: [VocabularyEntry] = [], sourceConstraints: SourceLookupConstraints? = nil) throws -> ImmersionResult {
        try autoreleasepool {
            try lookup(original:original,translation:translation,pair:pair,density:density,supplementalEntries:supplementalEntries,sourceConstraints:sourceConstraints)
        }
    }
    private func lookup(original: String, translation: String, pair: TranslationPair, density: Double,
                        supplementalEntries: [VocabularyEntry], sourceConstraints: SourceLookupConstraints?) throws -> ImmersionResult {
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
            density: density, source: pair.source, target: pair.target, supplementalEntries: supplementalEntries, sourceConstraints: sourceConstraints)
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
