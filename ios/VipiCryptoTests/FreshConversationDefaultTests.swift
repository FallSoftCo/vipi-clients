import Foundation
import XCTest
import VipiCore
@testable import Vipi

@MainActor final class FreshConversationDefaultTests: XCTestCase {
    struct Fixture: Decodable { let items: [Item] }
    struct Item: Decodable { let id, source_language, message: String }
    func testFrozenIndependentMessagesThroughActualDefault() async throws {
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let input = documents.appendingPathComponent("frozen-conversations-r01.json")
        guard FileManager.default.fileExists(atPath: input.path) else { throw XCTSkip("Explicit frozen independent messages required") }
        let bytes = try Data(contentsOf: input)
        let fixtureSHA = "ac6332cacdde6594f9083e57f04d100bb0fdf1ce7862bef2a18630324fdbca71"
        XCTAssertEqual(JapaneseStarterLookup.digest(bytes), fixtureSHA)
        let items = try JSONDecoder().decode(Fixture.self, from: bytes).items
        XCTAssertEqual(items.count, 132)
        let output = documents.appendingPathComponent("fresh-conversation-default-r01")
        guard !FileManager.default.fileExists(atPath: output.path) else { return XCTFail("Preserve existing independent capture") }
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        let owner = ConversationImmersion(), detector = MessageLanguage()
        defer { owner.close() }
        var total = 0, pairs: [[String: Any]] = []
        for source in SourceFrameLookup.languages.sorted() {
            let originals = items.filter { $0.source_language == source }
            XCTAssertEqual(originals.count, 12)
            for target in SourceFrameLookup.languages.sorted() where target != source {
                await owner.configure(pair: .init(source: source, target: target), density: 0.25)
                var rows: [[String: Any]] = []
                for item in originals {
                    let detected = try await detector.identify(item.message)
                    let start = ProcessInfo.processInfo.systemUptime
                    let result = await owner.result(for: item.message) // No provider, translation or source-language injection.
                    let elapsed = (ProcessInfo.processInfo.systemUptime - start) * 1000
                    let outcome = try XCTUnwrap(owner.lastOutcome, item.id)
                    XCTAssertEqual(outcome.localTranslationCalls, 0, item.id)
                    let base = result?.original ?? item.message
                    let mixed = NSMutableString(string: base), reading = NSMutableString(string: base)
                    for span in (result?.spans ?? []).reversed() {
                        mixed.replaceCharacters(in: span.range, with: span.translated)
                        reading.replaceCharacters(in: span.range, with: span.romanization ?? span.translated)
                    }
                    let spans = (result?.spans ?? []).map { ["start_utf16": $0.range.location, "end_utf16": NSMaxRange($0.range), "source": $0.original, "target": $0.translated, "reading": $0.romanization as Any? ?? NSNull()] as [String: Any] }
                    rows.append(["id": item.id, "source_language": source, "target_language": target,
                        "original": item.message, "presentation_original": base, "original_preserved": base == item.message,
                        "mixed_script": mixed as String, "mixed_reading": reading as String, "spans": spans,
                        "detected_language": detected as Any? ?? NSNull(), "input_language_override": NSNull(),
                        "status": outcome.status.rawValue, "origin": outcome.origin?.rawValue as Any? ?? NSNull(),
                        "translation_calls": outcome.localTranslationCalls, "model_readiness_calls": outcome.modelReadinessCalls,
                        "alignment_calls": outcome.alignmentCalls, "milliseconds": elapsed])
                }
                let pair = source + "-" + target
                let payload: [String: Any] = ["fixture_sha256": fixtureSHA, "pair": pair, "density": 0.25,
                    "default_provider": true, "injected_provider": false, "rows": rows]
                let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
                try data.write(to: output.appendingPathComponent(pair + ".json"), options: .withoutOverwriting)
                pairs.append(["pair": pair, "file": pair + ".json", "sha256": JapaneseStarterLookup.digest(data), "count": rows.count])
                total += rows.count
                try JSONSerialization.data(withJSONObject: ["fixture_sha256": fixtureSHA, "completed_cases": total, "pairs": pairs], options: [.sortedKeys]).write(to: output.appendingPathComponent("progress.json"), options: .atomic)
            }
        }
        XCTAssertEqual(total, 1320); XCTAssertEqual(pairs.count, 110)
    }
}
