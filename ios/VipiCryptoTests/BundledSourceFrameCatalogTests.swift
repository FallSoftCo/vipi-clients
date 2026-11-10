import Foundation
import XCTest
import VipiCore
@testable import Vipi

@MainActor final class BundledSourceFrameCatalogTests: XCTestCase {
    func testPinnedLazyCatalogAndFailClosedResources() async throws {
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let root = documents.appendingPathComponent("all-pair-starter-candidate-r02")
        let indexURL = documents.appendingPathComponent("all-pair-bundle-index-r01.json")
        guard FileManager.default.fileExists(atPath: indexURL.path) else { throw XCTSkip("Explicit pinned compiler index required") }
        let index = try Data(contentsOf: indexURL), pin = try XCTUnwrap(BundledSourceFrameCatalog.pinnedIndexSHA256)
        let catalog = try BundledSourceFrameCatalog(root: root.appendingPathComponent("packs"), indexBytes: index, expectedIndexSHA256: pin)
        let providers = catalog.providers()
        XCTAssertEqual(providers.count, 108); XCTAssertNil(providers["en-ja"]); XCTAssertNil(providers["en-sw"])
        XCTAssertTrue(BundledStarterLookup.allPairPromotionEnabled)
        let fixture = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("native-fixtures.json"))) as? [String: Any])
        let cases = try XCTUnwrap(fixture["cases"] as? [[String: Any]])
        for pairID in providers.keys.sorted() {
            let row = try XCTUnwrap(cases.first { $0["pair"] as? String == pairID && ($0["concept_id"] as? String)?.contains("phone_charger") == true })
            let source = try XCTUnwrap(row["source_language"] as? String), target = try XCTUnwrap(row["target_language"] as? String), original = try XCTUnwrap(row["original"] as? String)
            let context = SourceUnitLookup.Context(original: original, pair: .init(source: source, target: target), density: 0.5, knownConceptIDs: [])
            let provider = try XCTUnwrap(providers[pairID]), evidence = try await provider.resolve(context)
            XCTAssertNotNil(evidence.validated(text: original, sourceLanguage: source, targetLanguage: target, identity: provider.identity))
            // All 108 selected resources must load, preserving exact frozen target/readings.
            let focused = try XCTUnwrap(evidence.partial?.spans.first { $0.original == row["expected_source"] as? String }, pairID)
            do {
                XCTAssertEqual(focused.translated, row["expected_target"] as? String)
                XCTAssertEqual(focused.romanization ?? "", row["reading"] as? String)
            }
            let known = try XCTUnwrap(row["concept_id"] as? String)
            let suppressed = try await provider.resolve(.init(original: original, pair: context.pair, density: 0.5, knownConceptIDs: [known]))
            XCTAssertFalse(suppressed.partial?.references.contains { $0.conceptID == known } ?? false)
        }
        XCTAssertThrowsError(try BundledSourceFrameCatalog(root: root, indexBytes: index, expectedIndexSHA256: String(repeating: "0", count: 64)))
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: index) as? [String: Any])
        let entries = try XCTUnwrap(object["entries"] as? [[String: Any]])
        for mutation in ["duplicate", "traversal", "oversize", "reserved"] {
            var changed = object, rows = entries
            switch mutation {
            case "duplicate": rows[1] = rows[0]
            case "traversal": rows[0]["file"] = "../other.json"
            case "oversize": rows[0]["bytes"] = 1_048_577
            default: rows[0]["pair"] = "en-ja"; rows[0]["source"] = "en"; rows[0]["target"] = "ja"
            }
            changed["entries"] = rows
            let bytes = try JSONSerialization.data(withJSONObject: changed)
            XCTAssertThrowsError(try BundledSourceFrameCatalog(root: root, indexBytes: bytes, expectedIndexSHA256: JapaneseStarterLookup.digest(bytes)), mutation)
        }
        let isolated = documents.appendingPathComponent("corrupt-source-frame-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: isolated, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: isolated) }
        let first = try XCTUnwrap(entries.first), pairID = try XCTUnwrap(first["pair"] as? String)
        for field in ["file", "manifest_file"] {
            let name = try XCTUnwrap(first[field] as? String)
            try FileManager.default.copyItem(at: root.appendingPathComponent("packs/" + name), to: isolated.appendingPathComponent(name))
        }
        let file = isolated.appendingPathComponent(try XCTUnwrap(first["file"] as? String))
        var corrupt = try Data(contentsOf: file); corrupt[corrupt.startIndex] ^= 1; try corrupt.write(to: file)
        let invalid = try BundledSourceFrameCatalog(root: isolated, indexBytes: index, expectedIndexSHA256: pin)
        let row = try XCTUnwrap(cases.first { $0["pair"] as? String == pairID })
        do {
            _ = try await XCTUnwrap(invalid.providers()[pairID]).resolve(.init(original: try XCTUnwrap(row["original"] as? String), pair: .init(source: first["source"] as! String, target: first["target"] as! String), density: 0.5, knownConceptIDs: []))
            XCTFail("Corrupt bundled pack must never provide output")
        } catch {}
    }
}
