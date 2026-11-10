import XCTest
import Foundation
import VipiCore
@testable import Vipi

/// Capture actual default-route results; empty and withheld messages remain data.
@MainActor final class PositivePredicatesTests: XCTestCase {
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
    func testCurrentConversationDepth() async throws {
        guard let path = ProcessInfo.processInfo.environment["VIPI_POSITIVE_PREDICATES_QA"] else {
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
            for target in ["sw"] {
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
        XCTAssertEqual(rows, 160)
        try encoded(["rows": rows, "translation_calls": calls,
                     "seconds": ProcessInfo.processInfo.systemUptime - started,
                     "actual_default_factory": true, "semantic_acceptance_asserted": false])
            .write(to: root.appendingPathComponent("apple-status.json"))
    }

    func testPredicateControls() async throws {
        guard let path = ProcessInfo.processInfo.environment["VIPI_POSITIVE_PREDICATES_QA"] else { throw XCTSkip("Explicit candidate only") }
        let root = URL(fileURLWithPath:path)
        let manifest = try XCTUnwrap(JSONSerialization.jsonObject(with:Data(contentsOf:root.appendingPathComponent("manifest.json"))) as? [String:String])
        let bytes = try Data(contentsOf:root.appendingPathComponent("controls.json"))
        XCTAssertEqual(JapaneseStarterLookup.digest(bytes),manifest["controls.json"])
        let document = try XCTUnwrap(JSONSerialization.jsonObject(with:bytes) as? [String:Any])
        let cases = try XCTUnwrap(document["cases"] as? [[String:Any]])
        XCTAssertEqual(cases.count,37)
        let assets = try XCTUnwrap(Bundle.main.resourceURL).appendingPathComponent("immersion")
        let packManifest = try Data(contentsOf:assets.appendingPathComponent("starter-sw-catalog.json"))
        let metadata = try JSONDecoder().decode(SwahiliStarterLookup.Manifest.self,from:packManifest)
        XCTAssertEqual(metadata.file,"starter-en-sw-006.json")
        let packData = try Data(contentsOf:assets.appendingPathComponent(metadata.file))
        let output = root.appendingPathComponent("apple-controls.json")
        XCTAssertFalse(FileManager.default.fileExists(atPath:output.path))
        guard !FileManager.default.fileExists(atPath:output.path) else { return }
        var rows:[[String:Any]] = []
        for item in cases {
            let text = try XCTUnwrap(item["source"] as? String)
            let density = try XCTUnwrap(item["density"] as? Double)
            let known = Set(try XCTUnwrap(item["known_ids"] as? [String]))
            let masks = try XCTUnwrap(item["source_masks"] as? [[Int]]).map { NSRange(location:$0[0],length:$0[1]-$0[0]) }
            let owner = try SwahiliStarterLookup(data:packData,manifest:packManifest,packMultiple:true)
            let evidence = try owner.resolve(.init(original:text,pair:.init(source:"en",target:"sw"),density:density,knownConceptIDs:known),sourceMasks:masks)
            let spans = evidence.partial?.spans ?? []
            let predicates = owner.trace.filter { ($0["entry_id"] as? String)?.hasPrefix("clause-en-sw-") == true }
            let selected = evidence.partial?.references.filter { $0.referenceID.contains(":clause-en-sw-") } ?? []
            let expected = try XCTUnwrap(item["expected_predicate_count"] as? Int)
            let row:[String:Any] = ["id":item["id"]!,"group":item["group"]!,"source":text,"density":density,"known_ids":Array(known).sorted(),
                "expected_predicate_count":expected,"predicate_count":selected.count,
                "mixed_script":mixed(spans,original:text,reading:false),"native_words":LocalImmersion.words(text,language:"en").map(range),
                "spans":spans.map { ["source":$0.original,"target":$0.translated,"reading":$0.romanization as Any? ?? NSNull(),"source_utf16":range($0.range)] },
                "predicate_trace":predicates,"source_trace":owner.trace,
                "recognitions":evidence.recognitions.map { ["context":range($0.context),"mask":$0.mask.map(range) as Any? ?? NSNull(),"mode":mode($0.mode),"approved_outputs":$0.approvedOutputs.map{["id":$0.outputID,"range":range($0.range)]}] },
                "raw_guard_control_not_default_conversation":true,"semantic_acceptance_asserted":false,"translation_calls":0]
            rows.append(row)
            try encoded(["rows":rows,"count":rows.count,"translation_calls":0]).write(to:output,options:.atomic)
            XCTAssertEqual(selected.count,expected,"Predicate selection \(text)")
            for held in predicates where !(held["reason"] is NSNull) {
                let bounds = try XCTUnwrap(held["source_utf16"] as? [Int]);let focus=NSRange(location:bounds[0],length:bounds[1]-bounds[0])
                XCTAssertFalse(spans.contains { NSIntersectionRange($0.range,focus).length>0 },"Withheld predicate must not rescue inner words: \(text)")
            }
        }
    }
}
