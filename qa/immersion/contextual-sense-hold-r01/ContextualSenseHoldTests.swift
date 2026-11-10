import XCTest
import Foundation
import VipiCore
@testable import Vipi

/// Capture actual default-route results; empty and withheld messages remain data.
@MainActor final class ContextualSenseHoldTests: XCTestCase {
    private func encoded(_ value: Any) throws -> Data {
        try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    }
    private func range(_ value: NSRange) -> [Int] {
        [value.location, NSMaxRange(value)]
    }
    private func mode(_ value: SourceAtomicMode) -> String {
        switch value {
        case .none: return "NONE"
        case .atomic: return "ATOMIC"
        case .headBackoff: return "HEAD_BACKOFF"
        case .ambiguous: return "AMBIGUOUS"
        }
    }
    private func mixed(_ spans: [ImmersionSpan], original: String, reading: Bool) -> String {
        var text = original
        for span in spans.reversed() {
            text = (text as NSString).replacingCharacters(in: span.range,
                with: reading ? (span.romanization ?? span.translated) : span.translated)
        }
        return text
    }
    private func verifyRetainedMasks() async throws {
        let lookup = try XCTUnwrap(BundledStarterLookup.provider())
        for text in ["hair", "My hair is short.", "He's one of the ones without hair!"] {
            let evidence = try await lookup.resolve(.init(original: text,
                pair: .init(source: "en", target: "sw"), density: 0.75, knownConceptIDs: []))
            let constraints = try XCTUnwrap(evidence.validated(text: text, sourceLanguage: "en",
                targetLanguage: "sw", identity: lookup.identity))
            let focus = (text as NSString).range(of: "hair")
            XCTAssertFalse(constraints.permits(range: focus))
            XCTAssertFalse(evidence.partial?.spans.contains { $0.range == focus } ?? false)
            // Constructed-target negative control only; not a native translation observation.
            let legacy = ImmersionEngine().align(original: text, translation: "nywele",
                entries: [.init(source: "hair", targets: ["nywele"])], density: 1, targetLanguage: "sw")
            XCTAssertEqual(legacy.spans.count, 1)
            XCTAssertTrue(constraints.filterLegacy(legacy).spans.isEmpty)
        }
    }
    func testCurrentConversationDepth() async throws {
        guard let path = ProcessInfo.processInfo.environment["VIPI_CONTEXTUAL_SENSE_HOLD_QA"] else {
            throw XCTSkip("Explicit frozen conversation diagnostic only")
        }
        let root = URL(fileURLWithPath: path)
        let manifest = try XCTUnwrap(JSONSerialization.jsonObject(with:
            Data(contentsOf: root.appendingPathComponent("manifest.json"))) as? [String: String])
        for (name, hash) in manifest {
            XCTAssertFalse(name.contains("/"))
            XCTAssertEqual(JapaneseStarterLookup.digest(try Data(contentsOf:
                root.appendingPathComponent(name))), hash)
        }
        let input = try XCTUnwrap(JSONSerialization.jsonObject(with:
            Data(contentsOf: root.appendingPathComponent("messages.json"))) as? [String: Any])
        let cases = try XCTUnwrap(input["cases"] as? [[String: Any]])
        XCTAssertEqual(cases.count, 80)
        XCTAssertTrue(SourceFrameLookup.promotionEnabled)
        try await verifyRetainedMasks()
        let output = root.appendingPathComponent("apple-output.jsonl")
        XCTAssertFalse(FileManager.default.fileExists(atPath: output.path))
        guard !FileManager.default.fileExists(atPath: output.path) else { return }
        FileManager.default.createFile(atPath: output.path, contents: nil)
        let handle = try FileHandle(forWritingTo: output)
        defer { try? handle.close() }
        let catalog = BundledImmersionCatalog()
        let started = ProcessInfo.processInfo.systemUptime
        var rows = 0, calls = 0
        for item in cases {
            let id = try XCTUnwrap(item["id"] as? String)
            let stratum = try XCTUnwrap(item["stratum"] as? String)
            let source = try XCTUnwrap(item["source"] as? String)
            for target in ["ja", "sw"] {
                for density in [0.25, 0.75] {
                    let setup = ProcessInfo.processInfo.systemUptime
                    // Normal bundled factory. This changes only model availability:
                    // no translated target, provider, or display spans are injected.
                    let owner = ConversationImmersion(modelStatus: { _ in .unsupported })
                    await owner.configure(pair: .init(source: "en", target: target), density: density)
                    owner.selectInputLanguage("en", for: id)
                    let callStart = ProcessInfo.processInfo.systemUptime
                    let presentation = await owner.result(for: source, inputLanguage: "en", messageID: id)
                    let elapsed = (ProcessInfo.processInfo.systemUptime - callStart) * 1000
                    let outcome = owner.lastOutcome
                    let spans = presentation?.spans ?? []
                    let references: [SourceReferenceUnit]
                    if case .partial(let value)? = presentation { references = value.references }
                    else { references = [] }
                    let evidence: [String: Any] = [
                        "identity": outcome?.sourceConstraints?.catalogIdentity as Any? ?? NSNull(),
                        "selected_route_only": true,
                        "references": references.map { unit -> [String: Any] in
                            ["scope": range(unit.range), "reference": unit.referenceID,
                             "pack_sha": unit.catalogSHA256, "native_source_tokens": unit.nativeSourceTokens,
                             "concept_id": unit.conceptID as Any? ?? NSNull(),
                             "output_id": unit.outputID as Any? ?? NSNull()]
                        },
                        "recognitions": (outcome?.sourceConstraints?.recognitions ?? []).map { value -> [String: Any] in
                            ["rule": value.ruleID, "record_sha": value.recordSHA256,
                             "context": range(value.context), "mask": value.mask.map(range) as Any? ?? NSNull(),
                             "mode": mode(value.mode),
                             "approved": value.approvedOutputs.map { ["id": $0.outputID, "scope": range($0.range)] as [String: Any] }]
                        }
                    ]
                    let reference = try await catalog.reference(original: source, pair: .init(source: "en", target: target))
                    let callCount = outcome?.localTranslationCalls ?? -1
                    calls += max(0, callCount)
                    let row: [String: Any] = [
                        "id": id, "stratum": stratum, "pair": "en-" + target,
                        "source": source, "density": density, "known_ids": [],
                        "native_words": LocalImmersion.words(source, language: "en").map(range),
                        "spans": spans.map { ["source": $0.original, "target": $0.translated,
                            "reading": $0.romanization as Any? ?? NSNull(), "source_utf16": range($0.range)] as [String: Any] },
                        "mixed_script": mixed(spans, original: source, reading: false),
                        "mixed_reading": mixed(spans, original: source, reading: true),
                        "origin": outcome?.origin?.rawValue as Any? ?? NSNull(),
                        "status": outcome?.status.rawValue as Any? ?? NSNull(),
                        "translation_calls": callCount, "elapsed_ms": elapsed,
                        "setup_ms": (callStart - setup) * 1000, "reference_hit": reference != nil,
                        "source_evidence": evidence, "actual_default_factory": true,
                        "provider_target_spans_injected": false, "input_language_override": "en"
                    ]
                    try handle.write(contentsOf: encoded(row) + Data([10]))
                    owner.close()
                    rows += 1
                    XCTAssertEqual(callCount, 0)
                    guard try handle.offset() < 16 * 1024 * 1024,
                          ProcessInfo.processInfo.systemUptime - started < 300 else {
                        XCTFail("Capture limit exceeded; preserve partial output"); return
                    }
                }
            }
        }
        try handle.synchronize()
        XCTAssertEqual(rows, 320)
        try encoded(["rows": rows, "translation_calls": calls,
                     "seconds": ProcessInfo.processInfo.systemUptime - started,
                     "actual_default_factory": true, "semantic_acceptance_asserted": false, "constructed_target_mask_controls": 3])
            .write(to: root.appendingPathComponent("apple-status.json"))
    }
}
