import Foundation
import CryptoKit
import VipiCore
import XCTest
@testable import Vipi

final class SwahiliConversationCoverageTests: XCTestCase {
    @MainActor func testFrozenTurnsThroughActualLocalTranslationAndAppCatalog() async throws {
        let root = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let bytes = try Data(contentsOf: root.appendingPathComponent("afriwoz-probe-001.json"))
        let corpus = try XCTUnwrap(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        XCTAssertEqual(corpus["schema"] as? String, "vipi-afriwoz-probe-1")
        let cases = try XCTUnwrap(corpus["cases"] as? [[String: Any]])
        let targets = try XCTUnwrap(corpus["targets"] as? [String])
        let catalog = BundledImmersionCatalog()
        let catalogBytes = try Data(contentsOf: XCTUnwrap(Bundle.main.resourceURL?.appendingPathComponent("immersion/catalog.json")))
        let output = root.appendingPathComponent("swahili-coverage-001.json")
        XCTAssertFalse(FileManager.default.fileExists(atPath: output.path))
        var rows: [[String: Any]] = []
        for target in targets {
            let pair = TranslationPair(source: "sw", target: target)
            XCTAssertTrue(SwahiliTranslation.installed(pair), "Evaluation never initiates downloads")
            let translator = try SwahiliTranslation(pair: pair)
            for item in cases {
                let original = try XCTUnwrap((item["text"] as? [String: String])?["sw"])
                let begin = ContinuousClock.now
                let exact = try await catalog.reference(original: original, pair: pair)
                let translation: String
                if let exact { translation = exact } else { translation = try await translator.translate(original) }
                let preserves = TranslationIntegrity.preservesIdentifiers(original: original, translation: translation)
                let result = preserves ? try await catalog.result(original: original, translation: translation, pair: pair, density: 1) : nil
                if let result {
                    XCTAssertEqual(result.speech(source: "sw", target: target, revealed: Set(result.spans.map(\.id))).map(\.text).joined(), original)
                }
                let spans: [[String: Any]] = (result?.spans ?? []).map { span in
                    ["start":span.range.location, "end":NSMaxRange(span.range), "original":span.original,
                     "translated":span.translated, "targetStart":span.targetRange.location, "targetEnd":NSMaxRange(span.targetRange),
                     "reading":span.romanization as Any? ?? NSNull()]
                }
                let duration = begin.duration(to: .now).components
                rows.append(["id":try XCTUnwrap(item["id"] as? String), "source":"sw", "target":target,
                    "original":original, "translation":translation, "exact_reference":exact != nil,
                    "identifier_integrity":preserves, "spans":spans,
                    "elapsed_ms":Double(duration.seconds)*1000 + Double(duration.attoseconds)/1e15])
            }
            let report: [String: Any] = ["schema":"vipi-swahili-live-catalog-coverage-1", "platform":"ios",
                "corpus_sha256":SHA256.hash(data: bytes).map { String(format:"%02x", $0) }.joined(),
                "catalog_sha256":SHA256.hash(data: catalogBytes).map { String(format:"%02x", $0) }.joined(),
                "semantic_acceptance":false, "rows":rows]
            try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: output, options: .atomic)
        }
        XCTAssertEqual(rows.count, cases.count*targets.count)
    }
}
