import Foundation
import VipiCore

/// App-resource catalog for the 108 additional directions. Presence of files
/// grants no promotion; BundledStarterLookup owns that separate decision.
@MainActor final class BundledSourceFrameCatalog {
    static let indexFile = "all-pair-source-catalog-001.json"
    // Filled only from the compiler's reviewed, frozen index receipt.
    static let pinnedIndexSHA256: String? = "16b2198d52dfd0eb780e56669ce7863ae64d8521c960ed902484144917a98e7a"

    struct Entry: Decodable {
        let pair, source, target, file, sha256, manifest_file, manifest_sha256: String
        let bytes, manifest_bytes: Int
    }
    private struct Index: Decodable { let schema: String; let entries: [Entry] }
    private let root: URL, indexSHA: String
    private let entries: [String: Entry]
    private var loaded: [String: SourceUnitLookup] = [:]
    private var unavailable = Set<String>()

    private static let bundled: BundledSourceFrameCatalog? = {
        guard let sha = pinnedIndexSHA256,
              let root = Bundle.main.resourceURL?.appendingPathComponent("immersion"),
              let bytes = try? boundedRead(root.appendingPathComponent(indexFile), maximum: 131_072) else { return nil }
        return try? BundledSourceFrameCatalog(root: root, indexBytes: bytes, expectedIndexSHA256: sha)
    }()

    static func bundledProviders() -> [String: SourceUnitLookup] {
        bundled?.providers() ?? [:]
    }

    init(root: URL, indexBytes: Data, expectedIndexSHA256: String) throws {
        guard indexBytes.count <= 131_072,
              Self.hashShape(expectedIndexSHA256), JapaneseStarterLookup.digest(indexBytes) == expectedIndexSHA256 else { throw SourceFrameLookup.Invalid.evidence }
        let index = try JSONDecoder().decode(Index.self, from: indexBytes)
        guard index.schema == "vipi-bundled-source-frame-index-1", index.entries.count == 108 else { throw SourceFrameLookup.Invalid.evidence }
        var entries: [String: Entry] = [:]
        for entry in index.entries {
            guard SourceFrameLookup.languages.contains(entry.source), SourceFrameLookup.languages.contains(entry.target), entry.source != entry.target,
                  entry.pair == entry.source + "-" + entry.target, !["en-ja", "en-sw"].contains(entry.pair), entries[entry.pair] == nil,
                  entry.file.range(of: "^source-frames-" + entry.pair + "-[0-9]{3}\\.json$", options: .regularExpression) != nil,
                  entry.manifest_file == "source-frames-" + entry.pair + "-catalog.json",
                  (1...1_048_576).contains(entry.bytes), (1...8_192).contains(entry.manifest_bytes),
                  Self.hashShape(entry.sha256), Self.hashShape(entry.manifest_sha256) else { throw SourceFrameLookup.Invalid.evidence }
            entries[entry.pair] = entry
        }
        self.root = root; self.indexSHA = expectedIndexSHA256; self.entries = entries
    }

    private static func hashShape(_ value: String) -> Bool {
        value.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil
    }
    private static func boundedRead(_ url: URL, maximum: Int, expected: Int? = nil) throws -> Data {
        guard let size = try FileManager.default.attributesOfItem(atPath: url.path)[.size] as? NSNumber,
              size.intValue > 0, size.intValue <= maximum, expected == nil || size.intValue == expected else { throw SourceFrameLookup.Invalid.evidence }
        let bytes = try Data(contentsOf: url)
        guard bytes.count == size.intValue else { throw SourceFrameLookup.Invalid.evidence }
        return bytes
    }
    private func load(_ entry: Entry) throws -> SourceUnitLookup {
        if let provider = loaded[entry.pair] { return provider }
        guard !unavailable.contains(entry.pair) else { throw SourceFrameLookup.Invalid.evidence }
        do {
            let data = try Self.boundedRead(root.appendingPathComponent(entry.file), maximum: 1_048_576, expected: entry.bytes)
            let manifest = try Self.boundedRead(root.appendingPathComponent(entry.manifest_file), maximum: 8_192, expected: entry.manifest_bytes)
            guard JapaneseStarterLookup.digest(data) == entry.sha256,
                  JapaneseStarterLookup.digest(manifest) == entry.manifest_sha256 else { throw SourceFrameLookup.Invalid.evidence }
            let baselineID = "bundled-source-empty-v1:" + indexSHA + ":" + entry.pair
            let baseline = SourceUnitLookup(identity: baselineID) { context in
                SourceLookupEvidence(original: context.original, source: entry.source, target: entry.target,
                    catalogIdentity: baselineID, partial: nil, recognitions: [])
            }
            let owner = try SourceFrameLookup(bytes: data, manifestBytes: manifest, target: entry.target,
                baselineIdentity: baselineID, source: entry.source)
            let provider = owner.provider(baseline: baseline, raw: { [] })
            loaded[entry.pair] = provider
            return provider
        } catch { unavailable.insert(entry.pair); throw error }
    }
    func providers() -> [String: SourceUnitLookup] {
        Dictionary(uniqueKeysWithValues: entries.values.map { entry in
            let identity = "bundled-source-pair-v1:" + indexSHA + ":" + entry.pair
            return (entry.pair, SourceUnitLookup(identity: identity) { context in
                guard context.pair.source == entry.source, context.pair.target == entry.target else { throw SourceFrameLookup.Invalid.evidence }
                let provider = try self.load(entry), evidence = try await provider.resolve(context)
                guard evidence.validated(text: context.original, sourceLanguage: entry.source, targetLanguage: entry.target, identity: provider.identity) != nil else { throw SourceFrameLookup.Invalid.evidence }
                return SourceLookupEvidence(original: evidence.original, source: evidence.source, target: evidence.target,
                    catalogIdentity: identity, partial: evidence.partial, recognitions: evidence.recognitions,
                    eligiblePool: evidence.eligiblePool, nativeSourceTokenCount: evidence.nativeSourceTokenCount)
            })
        })
    }
}
