import XCTest
@testable import Vipi
import VipiCore
import VipiLanguageDetector

@MainActor final class MessageLanguageCLD2Tests: XCTestCase {
    private func fixtures() throws -> [String: Any] {
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "CLD2Fixtures", withExtension: "json"))
        return try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
    }
    func testNativeMaskedParityAndBounds() async throws {
        let rows = try XCTUnwrap(try fixtures()["parity"] as? [[String: Any]])
        XCTAssertEqual(rows.count, 87)
        let detector = MessageLanguage()
        for row in rows {
            let actual = try await detector.identify(try XCTUnwrap(row["text"] as? String))
            XCTAssertEqual(actual, row["expected"] as? String, row["id"] as? String ?? "")
        }
        for text in ["ok", "123", "🙂", "https://example.com/englishwords", String(repeating: "a", count: 16_385)] {
            let actual = try await detector.identify(text); XCTAssertNil(actual)
        }
        var invalid: [CChar] = [CChar(bitPattern: 0xff), 0]
        invalid.withUnsafeMutableBufferPointer { XCTAssertNil(vipi_detect_language($0.baseAddress, 1)) }
        let cancelled = Task { try Task.checkCancellation(); return try await detector.identify("This is an ordinary English sentence about reading a book.") }
        cancelled.cancel()
        do { _ = try await cancelled.value; XCTFail("Cancellation must propagate") } catch is CancellationError {} 
    }
    func testActualDefaultImmersionRouting() async throws {
        let rows = try XCTUnwrap(try fixtures()["errors"] as? [[String: Any]])
        var records: [[String: Any]] = []
        func check(_ text: String, _ source: String, _ target: String, _ id: String, manual: String? = nil) async {
            let owner = ConversationImmersion()
            await owner.configure(pair: .init(source: source, target: target), density: 0.25)
            let value = await owner.result(for: text, inputLanguage: manual)
            if id.hasPrefix("ordinary-en-") {
                XCTAssertEqual(value?.original, text)
                XCTAssertEqual(value?.spans.map(\.original), ["water"])
                XCTAssertEqual(value?.spans.map(\.translated), [target == "ja" ? "水" : "maji"])
            } else {
                XCTAssertNil(value, "Unqualified input must keep its original text: " + id)
            }
            records.append(["id": id, "text": text, "source": source, "target": target,
                            "manual": manual as Any? ?? NSNull(), "original": value?.original as Any? ?? NSNull(),
                            "translation": value?.translation as Any? ?? NSNull(),
                            "spans": value?.spans.map { ["original": $0.original, "translated": $0.translated] } ?? []])
            owner.close()
        }
        for row in rows {
            let text = try XCTUnwrap(row["text"] as? String), id = try XCTUnwrap(row["id"] as? String)
            let expected = try XCTUnwrap(row["expected"] as? String)
            await check(text, "en", expected == "en" ? "ja" : expected, id)
            await check(text, expected, expected == "en" ? "ja" : "en", id)
            await check(text, "en", expected == "en" ? "ja" : expected, id, manual: expected)
        }
        for target in ["ja", "sw"] {
            await check("The dog drinks water near the house.", "en", target, "ordinary-en-" + target)
        }
        await check("Tunakunywa maji sasa.", "en", "sw", "ordinary-sw")
        let url = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("cld2-actual-routing-r01.json")
        try JSONSerialization.data(withJSONObject: records, options: [.prettyPrinted, .sortedKeys]).write(to: url)
    }
}
