import Foundation
import Translation
import CryptoKit
import Darwin
import VipiCore

/// Public-corpus QA only. Executes the current native catalog/alignment code.
/// This is not a production service or an alternative translation provider.
@main struct MacLiveImmersionProbe {
    struct Input: Decodable {
        struct Case: Decodable {
            let id, source, target, text: String
            let captured_translation: String?
        }
        let name: String
        let cases: [Case]
        let replay_capture_sha256: String?
    }
    static func sha(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
    static func elapsed(_ start: ContinuousClock.Instant) -> Double {
        let d = start.duration(to: .now).components
        return Double(d.seconds) * 1_000 + Double(d.attoseconds) / 1e15
    }
    static func preview(_ text: String, _ spans: [ImmersionSpan], reading: Bool) -> String {
        let output = NSMutableString(string: text)
        for span in spans.reversed() {
            output.replaceCharacters(in: span.range, with: reading ? span.displayedTarget : span.translated)
        }
        return output as String
    }
    static func observed(_ spans: [ImmersionSpan]) -> [[String: Any]] {
        spans.map { ["original": $0.original, "translated": $0.translated,
            "sourceStartUTF16": $0.range.location, "sourceEndUTF16": NSMaxRange($0.range),
            "targetStartUTF16": $0.targetRange.location, "targetEndUTF16": NSMaxRange($0.targetRange),
            "reading": $0.romanization as Any? ?? NSNull()] }
    }
    @MainActor static func main() async throws {
        let a = CommandLine.arguments
        guard a.count == 6 || a.count == 7 else { fatalError("protocol.json immersion-dir lexical-dir new-cache-dir new-report.json [clone-only-seed-cache]") }
        let inputData = try Data(contentsOf: URL(fileURLWithPath: a[1]))
        let input = try JSONDecoder().decode(Input.self, from: inputData)
        let replay = input.replay_capture_sha256 != nil
        guard (1...600).contains(input.cases.count),
              Set(input.cases.map { $0.id + "|" + $0.source + "|" + $0.target }).count == input.cases.count,
              input.cases.allSatisfy({ !$0.text.isEmpty && $0.text.utf16.count <= 16_384 }) else {
            throw VocabularyPackError.invalid
        }
        if replay {
            guard input.replay_capture_sha256?.range(of: "^[0-9a-f]{64}$", options: .regularExpression) != nil,
                  input.cases.allSatisfy({ $0.captured_translation?.isEmpty == false }) else {
                throw VocabularyPackError.invalid
            }
        } else if input.cases.contains(where: { $0.captured_translation != nil }) {
            throw VocabularyPackError.invalid
        }
        let output = URL(fileURLWithPath: a[5]), cache = URL(fileURLWithPath: a[4])
        guard !FileManager.default.fileExists(atPath: output.path),
              !FileManager.default.fileExists(atPath: cache.path) else { throw VocabularyPackError.invalid }
        let catalogRoot = URL(fileURLWithPath: a[2]), lexicalRoot = URL(fileURLWithPath: a[3])
        let catalog = BundledImmersionCatalog(root: catalogRoot)
        // Optional capacity-bounded replay mode: clone existing immutable public
        // SQLite files, then refuse expansion of any absent shard. Never mutate
        // the simulator cache used as the source of these APFS clones.
        if a.count == 7 {
            try FileManager.default.createDirectory(at: cache, withIntermediateDirectories: true)
            let seed = URL(fileURLWithPath: a[6])
            for file in try FileManager.default.contentsOfDirectory(at: seed, includingPropertiesForKeys: nil)
                where file.pathExtension == "sqlite" {
                guard clonefile(file.path, cache.appendingPathComponent(file.lastPathComponent).path, 0) == 0 else {
                    throw VocabularyPackError.storage
                }
            }
        }
        let lexical = BundledLexicalCatalog(resources: lexicalRoot, root: cache)
        var rows: [[String: Any]] = []
        let start = Date()
        func save(complete: Bool) throws {
            let report: [String: Any] = ["schema": "vipi-mac-live-immersion-probe-1",
                "protocol": input.name, "input_sha256": sha(inputData), "complete": complete,
                "started_utc": ISO8601DateFormatter().string(from: start),
                "system": ProcessInfo.processInfo.operatingSystemVersionString,
                "platform": "macOS native; not iOS or Android",
                "provider": replay ? "Retained provider text; no new inference" : "Apple Translation lowLatency; installed models only",
                "translation_reused": replay,
                "replay_capture_sha256": input.replay_capture_sha256 as Any? ?? NSNull(),
                "network_disabled": false, "classification_exercised": false,
                "independent_semantic_acceptance": false, "release_ready": false,
                "catalog_sha256": try sha(Data(contentsOf: catalogRoot.appendingPathComponent("catalog.json"))),
                "lexical_catalog_sha256": try sha(Data(contentsOf: lexicalRoot.appendingPathComponent("catalog.json"))),
                "results": rows]
            try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
                .write(to: output, options: .atomic)
        }
        try save(complete: false)
        let availability = LanguageAvailability(preferredStrategy: .lowLatency)
        var session: TranslationSession?, sessionPair = ""
        defer { session?.cancel() }
        for row in input.cases {
            let pair = TranslationPair(source: row.source, target: row.target)
            guard pair.valid else { throw VocabularyPackError.invalid }
            var result: [String: Any] = ["id": row.id, "source": row.source, "target": row.target,
                "original": row.text, "local_translation_calls": 0]
            do {
                let basis = LocalImmersion.words(row.text, language: row.source)
                result["source_word_ranges"] = basis.map { [$0.location, NSMaxRange($0)] }
                let lookupStart = ContinuousClock.now
                if let partial = try await catalog.partial(original: row.text, pair: pair, density: 1), !partial.spans.isEmpty {
                    result["path"] = "source_reference"
                    result["spans"] = observed(partial.spans)
                    result["mixed"] = preview(row.text, partial.spans, reading: false)
                    result["visible"] = preview(row.text, partial.spans, reading: true)
                    result["target_offsets"] = "per-unit reference, not whole translation"
                    result["lookup_ms"] = elapsed(lookupStart)
                } else {
                    result["source_lookup_ms"] = elapsed(lookupStart)
                    let from = Locale.Language(identifier: row.source), to = Locale.Language(identifier: row.target)
                    var installed = replay
                    if !replay {
                        let state = await availability.status(from: from, to: to)
                        result["availability"] = String(describing: state)
                        installed = state == .installed
                    } else { result["availability"] = "not consulted for captured-text replay" }
                    if !installed {
                        result["path"] = "translation_unavailable"
                        result["spans"] = [[String: Any]]()
                    } else {
                        let key = row.source + "|" + row.target
                        if !replay && sessionPair != key {
                            session?.cancel()
                            session = TranslationSession(installedSource: from, target: to, preferredStrategy: .lowLatency)
                            sessionPair = key
                        }
                        let translationStart = ContinuousClock.now
                        let full: String
                        if replay {
                            full = row.captured_translation!
                            result["translation_ms"] = NSNull()
                        } else {
                            result["local_translation_calls"] = 1
                            full = try await session!.translate(row.text).targetText
                            result["translation_ms"] = elapsed(translationStart)
                        }
                        result["translation"] = full
                        let identifiersIntact = TranslationIntegrity.preservesIdentifiers(original: row.text, translation: full)
                        result["identifier_guard"] = identifiersIntact
                        if !identifiersIntact {
                            result["path"] = "identifier_withheld"
                            result["spans"] = [[String: Any]]()
                            result["status"] = "executed"
                            rows.append(result)
                            try save(complete: false)
                            continue
                        }
                        if a.count == 7 {
                            let metadata = try JSONSerialization.jsonObject(with: Data(contentsOf: lexicalRoot.appendingPathComponent("catalog.json"))) as! [String: Any]
                            let required = Set(["d-" + row.source, "d-" + row.target, "w-" + [row.source, row.target].sorted().joined(separator: "-")])
                            let files = (metadata["files"] as! [[String: Any]]).filter { required.contains($0["id"] as! String) }
                            guard files.count == 3, files.allSatisfy({ file in
                                FileManager.default.fileExists(atPath: cache.appendingPathComponent((file["id"] as! String) + "-" + (file["sha256"] as! String) + ".sqlite").path)
                            }) else {
                                result["path"] = "translation_captured_lexical_cache_missing"
                                result["status"] = "incomplete"
                                rows.append(result)
                                try save(complete: false)
                                continue
                            }
                        }
                        let alignStart = ContinuousClock.now
                        let entries = try await lexical.diagnosedEntries(original: row.text, translation: full, pair: pair)
                        result["diagnostics"] = entries.diagnostics
                        result["lexical_entries"] = entries.entries.count
                        var densities: [[String: Any]] = []
                        for density in [0.25, 1.0] {
                            let actual = try await catalog.result(original: row.text, translation: full, pair: pair,
                                density: density, supplementalEntries: entries.entries)
                            densities.append(["density": density, "spans": observed(actual.spans),
                                "mixed": preview(row.text, actual.spans, reading: false),
                                "visible": preview(row.text, actual.spans, reading: true)])
                        }
                        result["densities"] = densities
                        result["lookup_alignment_ms"] = elapsed(alignStart)
                        result["path"] = replay ? "captured_translation_then_native_alignment" : "one_local_full_translation_then_native_alignment"
                    }
                }
                result["status"] = "executed"
            } catch {
                result["status"] = "failed"
                result["error"] = String(describing: error)
            }
            rows.append(result)
            try save(complete: false)
            print("\(rows.count)/\(input.cases.count) \(row.source)-\(row.target) \(row.id) \(result["path"] ?? result["status"]!)")
        }
        try save(complete: true)
    }
}
