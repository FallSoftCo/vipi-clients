import Foundation
import XCTest
import VipiCore
@testable import Vipi

@MainActor final class PromotedSourceFrameTests: XCTestCase {
    func testActualBundledDefaultMatchesReviewedCaptureAndRejectsControls() async throws {
        XCTAssertTrue(BundledStarterLookup.allPairPromotionEnabled)
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let root = documents.appendingPathComponent("all-pair-starter-candidate-r02")
        guard FileManager.default.fileExists(atPath: root.appendingPathComponent("native-fixtures.json").path), FileManager.default.fileExists(atPath: root.appendingPathComponent("apple-native-r02.json").path) else { throw XCTSkip("Explicit reviewed qualification inputs required") }
        let fixture = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("native-fixtures.json"))) as? [String: Any])
        let cases = try XCTUnwrap(fixture["cases"] as? [[String: Any]])
        let reviewed = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("apple-native-r02.json"))) as? [String: Any])
        let rows = try XCTUnwrap(reviewed["automatic"] as? [[String: Any]])
        let expected = Dictionary(uniqueKeysWithValues: rows.filter { $0["manual_source"] as? Bool == false }.map { ($0["id"] as! String, $0["spans"] as! [[String: Any]]) })
        let owner = ConversationImmersion() // Actual default; no injected provider or detector.
        defer { owner.close() }
        func spans(_ value: ImmersionPresentation?) -> [[String: Any]] {
            (value?.spans ?? []).map { ["source": $0.original, "target": $0.translated, "reading": $0.romanization ?? "", "range": [$0.range.location, NSMaxRange($0.range)]] }
        }
        var timings: [Double] = [], records: [[String: Any]] = [], controls: [[String: Any]] = []
        for row in cases {
            let id = try XCTUnwrap(row["id"] as? String), source = try XCTUnwrap(row["source_language"] as? String), target = try XCTUnwrap(row["target_language"] as? String), text = try XCTUnwrap(row["original"] as? String)
            await owner.configure(pair: .init(source: source, target: target), density: 0.25)
            let start = ProcessInfo.processInfo.systemUptime
            let value = await owner.result(for: text)
            let milliseconds = (ProcessInfo.processInfo.systemUptime - start) * 1000
            timings.append(milliseconds)
            let actual = spans(value)
            XCTAssertEqual(try JSONSerialization.data(withJSONObject: actual, options: [.sortedKeys]), try JSONSerialization.data(withJSONObject: XCTUnwrap(expected[id]), options: [.sortedKeys]), id)
            XCTAssertEqual(owner.lastOutcome?.localTranslationCalls ?? 0, 0)
            records.append(["id": id, "pair": source + "-" + target, "text": text, "spans": actual, "milliseconds": milliseconds])
        }
        for row in try XCTUnwrap(fixture["controls"] as? [[String: Any]]) {
            let source = try XCTUnwrap(row["source_language"] as? String), target = try XCTUnwrap(row["target_language"] as? String), text = try XCTUnwrap(row["original"] as? String)
            await owner.configure(pair: .init(source: source, target: target), density: 0.25)
            let actual = spans(await owner.result(for: text)); XCTAssertTrue(actual.isEmpty, text)
            controls.append(["id": row["id"]!, "pair": source + "-" + target, "spans": actual])
        }
        let errorsURL = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "CLD2Fixtures", withExtension: "json"))
        let errors = try XCTUnwrap((JSONSerialization.jsonObject(with: Data(contentsOf: errorsURL)) as? [String: Any])?["errors"] as? [[String: Any]])
        for source in SourceFrameLookup.languages.sorted() { for target in SourceFrameLookup.languages.sorted() where source != target {
            await owner.configure(pair: .init(source: source, target: target), density: 0.25)
            for row in errors {
                let text = try XCTUnwrap(row["text"] as? String), actual = spans(await owner.result(for: text))
                XCTAssertTrue(actual.isEmpty, source + "-" + target + ":" + text)
                controls.append(["id": "detector-error:" + (row["id"] as! String), "pair": source + "-" + target, "spans": actual])
            }
            let sample = try XCTUnwrap(cases.first { $0["source_language"] as? String == source && $0["target_language"] as? String == target })
            let text = "```\n" + (sample["original"] as! String) + "\n```", actual = spans(await owner.result(for: text))
            XCTAssertTrue(actual.isEmpty, "Protected text " + source + "-" + target)
            controls.append(["id": "protected-code", "pair": source + "-" + target, "spans": actual])
        } }
        let sorted = timings.sorted()
        let output: [String: Any] = ["default_provider": true, "injected_provider": false, "promotion_enabled": true,
            "rows": records, "controls": controls, "count": records.count,
            "latency_ms": ["p50": sorted[sorted.count / 2], "p95": sorted[Int(Double(sorted.count - 1) * 0.95)], "max": sorted.last!],
            "scope": "finite authored qualification; not conversation-wide accuracy"]
        try JSONSerialization.data(withJSONObject: output, options: [.sortedKeys]).write(to: documents.appendingPathComponent("promoted-source-default-r01.json"))
        XCTAssertEqual(records.count, 5512); XCTAssertEqual(controls.count, 1273)
    }
}
