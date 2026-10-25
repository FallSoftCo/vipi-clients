import Foundation
import XCTest
@testable import Vipi

/// Apple tokenization/dictionary/alignment on captured *Android* translations.
/// This deliberately does not claim execution of Apple's translation model.
final class BilingualMatrixTests: XCTestCase {
    private struct TranslationReport: Decodable {
        struct Pair: Decodable {
            struct Sample: Decodable { let id: String; let original: String; let translation: String; let status: String }
            let source: String; let target: String; let samples: [Sample]
        }
        let provider: String; let results: [Pair]
    }
    func testAllNativePairsUsingCapturedMLKitTranslations() async throws {
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let input = documents.appendingPathComponent("bilingual-qa")
        let packs = input.appendingPathComponent("packs")
        let captured = try JSONDecoder().decode(TranslationReport.self, from: Data(contentsOf: input.appendingPathComponent("android-translations.json")))
        XCTAssertEqual(captured.results.count, 90)
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("bilingual-matrix-\(UUID())")
        let prefix = "bilingual-qa-" + UUID().uuidString.lowercased() + "-"
        defer {
            try? FileManager.default.removeItem(at: root)
            for pair in captured.results { KeychainStore.delete(account: prefix + pair.source + "-" + pair.target) }
        }
        let store = try VocabularyPackStore(root: root, trustedKeys: ["bilingual-qualification-001": Data(contentsOf: packs.appendingPathComponent("signing-public-key.der"))], receiptPrefix: prefix)
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
                samples.append(["id": sample.id, "original": sample.original, "translation": sample.translation,
                    "status": "executed", "candidate_senses": entries.count, "lookup_alignment_ms": milliseconds(start),
                    "spans": result.spans.map { span -> [String: Any] in ["start": span.range.location, "end": NSMaxRange(span.range),
                        "original": span.original, "translated": span.translated, "reading": span.romanization.map { $0 as Any } ?? NSNull(),
                        "targetStart": span.targetRange.location, "targetEnd": NSMaxRange(span.targetRange)] },
                    "speech": result.speech(source: pair.source, target: pair.target).map { ["text": $0.text, "language": $0.language] }])
            }
            rows.append(["source": pair.source, "target": pair.target, "status": "executed", "install_ms": installMS, "samples": samples])
            try await store.remove(id: id)
            let report: [String: Any] = ["schema": 1, "platform": "iOS Simulator", "translation_provider": captured.provider,
                "evidence": "native_apple_tokenization_dictionary_alignment_on_captured_android_translations_not_apple_translation_execution",
                "linguistic_acceptance": false, "results": rows]
            try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: documents.appendingPathComponent("bilingual-ios-matrix-001.json"), options: .atomic)
        }
    }
}
