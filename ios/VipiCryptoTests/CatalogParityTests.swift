import Foundation
import CryptoKit
import XCTest
@testable import Vipi

/// Authored reference diagnostics only; no private messages or evaluation corpus.
final class CatalogParityTests: XCTestCase {
    func testCaptureActualReferenceSelectionsForNativeComparison() async throws {
        let revision = ProcessInfo.processInfo.environment["VIPI_CATALOG_PARITY_RUN"] ?? ""
        guard revision.count == 3, revision.allSatisfy(\.isNumber) else { throw XCTSkip("Explicit diagnostic receipt required") }
        let root = try XCTUnwrap(Bundle.main.resourceURL?.appendingPathComponent("immersion"))
        let bytes = try Data(contentsOf: root.appendingPathComponent("catalog.json"))
        let index = try XCTUnwrap(JSONSerialization.jsonObject(with: bytes) as? [String:Any])
        let rows = try XCTUnwrap(index["references"] as? [[String:String]])
        let catalog = BundledImmersionCatalog(root: root)
        var cases = [[String:Any]]()
        for (i,row) in rows.enumerated() {
            let pairID = try XCTUnwrap(row["pair"]), codes = pairID.split(separator:"-").map(String.init)
            let original = try XCTUnwrap(row["original"]), translation = try XCTUnwrap(row["translation"])
            let result = try await catalog.result(original: original, translation: translation,
                pair: .init(source:codes[0],target:codes[1]), density:1)
            XCTAssertEqual(result.original,original); XCTAssertEqual(result.translation,translation)
            let spans: [[String:Any]] = result.spans.map { s in
                ["start":s.range.location,"end":NSMaxRange(s.range),"target_start":s.targetRange.location,
                 "target_end":NSMaxRange(s.targetRange),"original":s.original,"translated":s.translated,
                 "reading":s.romanization.map { $0 as Any } ?? NSNull()]
            }
            cases.append(["index":i,"pair":pairID,"original":original,"translation":translation,"spans":spans])
        }
        let output = URL.documentsDirectory.appendingPathComponent("catalog-parity-\(revision).json")
        XCTAssertFalse(FileManager.default.fileExists(atPath:output.path))
        let report: [String:Any] = ["schema":"vipi-native-catalog-parity-1","catalog_sha256":SHA256.hash(data:bytes).map{String(format:"%02x",$0)}.joined(),"cases":cases,"semantic_acceptance":false]
        try JSONSerialization.data(withJSONObject:report,options:[.sortedKeys]).write(to:output,options:.atomic)
    }
}
