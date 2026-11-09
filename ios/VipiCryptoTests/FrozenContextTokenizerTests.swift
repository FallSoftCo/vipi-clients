import Foundation
import CryptoKit
import XCTest
@testable import Vipi

final class FrozenContextTokenizerTests: XCTestCase {
    func testPinnedPythonScalarTokenAndNormalizationParity() throws {
        let data = try XCTUnwrap(Data(base64Encoded: FrozenContextTokenizerFixture.base64))
        XCTAssertEqual(SHA256.hash(data: data).map { String(format:"%02x",$0) }.joined(), FrozenContextTokenizerFixture.sha256)
        let fixture = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let cases = try XCTUnwrap(fixture["cases"] as? [[String: Any]])
        let tokenizer = try FrozenContextTokenizer()
        for row in cases {
            let source = try XCTUnwrap(row["source"] as? String)
            if row["supported"] as? Bool == false {
                XCTAssertThrowsError(try tokenizer.tokenize(source)) { error in
                    guard case FrozenContextTokenizer.Failure.unsupportedScalar = error else { return XCTFail("Wrong abstention: \(error)") }
                }
                continue
            }
            let expected = try XCTUnwrap(row["tokens"] as? [[String: Any]])
            let actual = try tokenizer.tokenize(source)
            XCTAssertEqual(actual.count, expected.count)
            for (a, e) in zip(actual, expected) {
                XCTAssertEqual(Array(a.original.utf8), Array(try XCTUnwrap(e["text"] as? String).utf8))
                XCTAssertEqual(Array(a.normalized.utf8), Array(try XCTUnwrap(e["normalized"] as? String).utf8))
                XCTAssertEqual([a.range.location, a.range.length], e["range"] as? [Int])
                XCTAssertEqual(a.hasAlphabeticScalar, e["has_alpha"] as? Bool)
            }
            XCTAssertEqual(Array(try tokenizer.normalize(source).utf8), Array(try XCTUnwrap(row["normalized"] as? String).utf8))
        }
        XCTAssertThrowsError(try tokenizer.tokenize(String(repeating: "x", count: 16_385)))
        let receipt: [String: Any] = ["schema":"vipi.context-tokenizer-parity.r01", "cases":cases.count,
            "table_sha256":FrozenContextUnicodeTables.sha256, "fixture_sha256":FrozenContextTokenizerFixture.sha256,
            "os":ProcessInfo.processInfo.operatingSystemVersionString,
            "scope":"Pinned scalar classification/casefold and sampled Foundation NFC parity only, not whole-pack selection or semantics"]
        let attachment = XCTAttachment(data: try JSONSerialization.data(withJSONObject: receipt, options:[.sortedKeys]), uniformTypeIdentifier:"public.json")
        attachment.name = "frozen-context-tokenizer-parity-r01"; attachment.lifetime = .keepAlways; add(attachment)
    }
}
