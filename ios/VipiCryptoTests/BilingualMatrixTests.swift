import Foundation
import CryptoKit
import XCTest
@testable import Vipi

/// Native iOS alignment on provider captures with explicit provenance.
/// This test never executes a translation model itself.
final class BilingualMatrixTests: XCTestCase {
    private struct TranslationReport: Decodable {
        struct Pair: Decodable {
            struct Sample: Decodable { let id: String; let original: String; let translation: String; let status: String; let reference: String? }
            let source: String; let target: String; let samples: [Sample]
        }
        let provider: String; let platform: String; let evidence: String; let results: [Pair]
    }
    func testAllNativePairsUsingCapturedTranslations() async throws {
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let input = documents.appendingPathComponent("bilingual-qa")
        let config = input.appendingPathComponent("run-id.txt")
        let runID = FileManager.default.fileExists(atPath: config.path) ? try String(contentsOf: config, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines) : "001"
        guard runID.range(of: "^[0-9]{3}$", options: .regularExpression) != nil else { throw VocabularyPackError.invalid }
        let packs = input.appendingPathComponent(runID == "001" ? "packs" : "packs-" + runID)
        func filename(_ config: String, fallback: String) throws -> String {
            let url = input.appendingPathComponent(config)
            let value = FileManager.default.fileExists(atPath: url.path) ? try String(contentsOf: url, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines) : fallback
            guard value.range(of: "^[a-z0-9-]+\\.json$", options: .regularExpression) != nil else { throw VocabularyPackError.invalid }
            return value
        }
        let sourceName = try filename("translation-report.txt", fallback: "android-translations.json")
        let outputName = try filename("report-name.txt", fallback: "bilingual-ios-matrix-" + runID + ".json")
        guard !FileManager.default.fileExists(atPath: documents.appendingPathComponent(outputName).path) else {
            XCTFail("Preserve qualification receipts"); throw VocabularyPackError.invalid
        }
        let captureData = try Data(contentsOf: input.appendingPathComponent(sourceName))
        let captured = try JSONDecoder().decode(TranslationReport.self, from: captureData)
        let attribution = (try JSONSerialization.jsonObject(with: captureData) as? [String: Any])?["attribution"] as? [String: String]
        XCTAssertEqual(captured.results.count, 90)
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("bilingual-matrix-\(UUID())")
        let prefix = "bilingual-qa-" + UUID().uuidString.lowercased() + "-"
        defer {
            try? FileManager.default.removeItem(at: root)
            for pair in captured.results { KeychainStore.delete(account: prefix + pair.source + "-" + pair.target) }
        }
        let store = try VocabularyPackStore(root: root, trustedKeys: ["bilingual-qualification-" + runID: Data(contentsOf: packs.appendingPathComponent("signing-public-key.der"))], receiptPrefix: prefix)
        var rows: [[String: Any]] = []
        func milliseconds(_ from: ContinuousClock.Instant) -> Double {
            let duration = from.duration(to: .now).components
            return Double(duration.seconds) * 1000 + Double(duration.attoseconds) / 1e15
        }
        for pair in captured.results {
            let id = pair.source + "-" + pair.target, folder = packs.appendingPathComponent(pair.source + "-" + pair.target)
            let start = ContinuousClock.now
            let installed = try await store.install(manifestBytes: Data(contentsOf: folder.appendingPathComponent("manifest.json")), signature: Data(contentsOf: folder.appendingPathComponent("manifest.sig")), database: Data(contentsOf: folder.appendingPathComponent("vocabulary.sqlite")))
            XCTAssertEqual(installed, id)
            let installMS = milliseconds(start)
            var samples: [[String: Any]] = []
            for sample in pair.samples {
                XCTAssertEqual(sample.status, "executed")
                let start = ContinuousClock.now
                let entries = try await store.entries(id: id, text: sample.original)
                let result = LocalImmersion.align(original: sample.original, translation: sample.translation, entries: entries, density: 0.3, source: pair.source, target: pair.target)
                func words(_ text: String, _ language: String) -> [[String: Any]] {
                    LocalImmersion.words(text, language: language).map { ["text": (text as NSString).substring(with: $0), "start": $0.location, "end": NSMaxRange($0)] }
                }
                samples.append(["id": sample.id, "original": sample.original, "translation": sample.translation,
                    "reference": sample.reference.map { $0 as Any } ?? NSNull(),
                    "status": "executed", "candidate_senses": entries.count, "lookup_alignment_ms": milliseconds(start),
                    "source_words": words(sample.original, pair.source), "target_words": words(sample.translation, pair.target),
                    "spans": result.spans.map { span -> [String: Any] in ["start": span.range.location, "end": NSMaxRange(span.range),
                        "original": span.original, "translated": span.translated, "reading": span.romanization.map { $0 as Any } ?? NSNull(),
                        "targetStart": span.targetRange.location, "targetEnd": NSMaxRange(span.targetRange)] },
                    "speech": result.speech(source: pair.source, target: pair.target).map { ["text": $0.text, "language": $0.language] }])
            }
            rows.append(["source": pair.source, "target": pair.target, "status": "executed", "install_ms": installMS, "samples": samples])
            try await store.remove(id: id)
            var report: [String: Any] = ["schema": 1, "platform": "iOS Simulator", "native_alignment_policy": "sentence-cue-for-polysemy-1", "translation_provider": captured.provider,
                "evidence": "native_ios_alignment_on_captured_translations_not_translation_execution",
                "translation_capture_platform": captured.platform, "translation_capture_evidence": captured.evidence,
                "translation_capture_sha256": SHA256.hash(data: captureData).map { String(format: "%02x", $0) }.joined(),
                "linguistic_acceptance": false, "results": rows]
            if let attribution { report["attribution"] = attribution }
            try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: documents.appendingPathComponent(outputName), options: .atomic)
        }
    }
}
