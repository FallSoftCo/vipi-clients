import Foundation
import XCTest
import VipiCore
@testable import Vipi

@MainActor final class LocalPhraseCandidateTests: XCTestCase {
    func testActualLocalRoutes() async throws {
        guard let path = ProcessInfo.processInfo.environment["VIPI_LOCAL_PHRASE_INPUT"] else {
            throw XCTSkip("Explicit private candidate input required")
        }
        let root = URL(fileURLWithPath: path)
        func bytes(_ name: String) throws -> Data { try Data(contentsOf: root.appendingPathComponent(name)) }
        let fixture = try XCTUnwrap(JSONSerialization.jsonObject(with: bytes("fixtures.json")) as? [String: Any])
        let cases = try XCTUnwrap(fixture["cases"] as? [[String: Any]])
        let jaManifest = try bytes("starter-catalog.json")
        let jaFile = try XCTUnwrap((JSONSerialization.jsonObject(with: jaManifest) as? [String: Any])?["file"] as? String)
        let ja = try JapaneseStarterLookup(data: bytes(jaFile), manifest: jaManifest, packMultiple: true)
        let swManifest = try bytes("starter-sw-catalog.json")
        let swFile = try XCTUnwrap((JSONSerialization.jsonObject(with: swManifest) as? [String: Any])?["file"] as? String)
        let sw = try SwahiliStarterLookup(data: bytes(swFile), manifest: swManifest, packMultiple: true)
        let candidate = try XCTUnwrap(BundledStarterLookup.compose(
            japanese: SourceFrameLookup.bundled(target: "ja", baseline: ja.provider(), raw: { ja.rawCandidates }),
            swahili: SourceFrameLookup.bundled(target: "sw", baseline: sw.provider(), raw: { sw.rawCandidates })))
        var rows: [[String: Any]] = []
        for (variant, provider) in [("baseline", try XCTUnwrap(BundledStarterLookup.provider())), ("candidate", candidate)] {
            let owner = ConversationImmersion(modelStatus: { _ in .unsupported }, sourceUnits: provider)
            for c in cases {
                let source = try XCTUnwrap(c["source"] as? String)
                let pair = try XCTUnwrap(c["pair"] as? String)
                let target = String(pair.suffix(2))
                for density in [0.25, 0.75] {
                    await owner.configure(pair: .init(source: "en", target: target), density: density)
                    let result = await owner.result(for: source, inputLanguage: "en")
                    let outcome = try XCTUnwrap(owner.lastOutcome)
                    XCTAssertEqual(outcome.localTranslationCalls, 0)
                    XCTAssertTrue([ImmersionStatus.partial, .noLocalMatch].contains(outcome.status), "Lookup must succeed or explicitly miss: \(source) / \(variant) / \(outcome.status)")
                    let spans = result?.spans ?? []
                    let mixed = NSMutableString(string: source)
                    for span in spans.reversed() { mixed.replaceCharacters(in: span.range, with: span.translated) }
                    rows.append(["id": c["id"]!, "variant": variant, "target": target, "density": density,
                        "source": source, "mixed": String(mixed), "status": outcome.status.rawValue,
                        "translation_calls": outcome.localTranslationCalls,
                        "spans": spans.map { ["start": $0.range.location, "end": NSMaxRange($0.range),
                            "source": $0.original, "target": $0.translated, "reading": $0.romanization ?? ""] as [String: Any] }])
                }
            }
            owner.close()
        }
        XCTAssertEqual(rows.count, cases.count * 4)
        for variant in ["baseline", "candidate"] { for target in ["ja", "sw"] {
            XCTAssertTrue(rows.contains { $0["variant"] as? String == variant && $0["target"] as? String == target && !($0["spans"] as? [[String: Any]] ?? []).isEmpty }, "Fixture must demonstrate actual output for \(variant)/\(target)")
        } }
        try JSONSerialization.data(withJSONObject: rows, options: [.sortedKeys]).write(to: root.appendingPathComponent("apple-results.json"), options: .atomic)
    }
}
