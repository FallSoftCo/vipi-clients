import Foundation
import XCTest
import VipiCore
@testable import Vipi

/// Explicit private injection. No bundled file, pin, promotion flag or matcher changes.
@MainActor final class EditorialExtensionCandidateTests: XCTestCase {
    struct Fixture: Decodable { let items: [Item] }
    struct Item: Decodable { let id, source_language, message: String }
    private func provider(root: URL, source: String, target: String) throws -> SourceUnitLookup {
        let pair = source + "-" + target
        let metadata = try Data(contentsOf: root.appendingPathComponent("packs/source-frames-" + pair + "-catalog.json"))
        let manifest = try JSONDecoder().decode(SourceFrameLookup.Manifest.self, from: metadata)
        let bytes = try Data(contentsOf: root.appendingPathComponent("packs/" + manifest.file))
        let baseline: SourceUnitLookup
        let raw: () -> [SourceFrameStarterCandidate]
        let bundle = try XCTUnwrap(Bundle.main.resourceURL?.appendingPathComponent("immersion"))
        if source == "en" && target == "ja" {
            let data = try Data(contentsOf: bundle.appendingPathComponent("starter-catalog.json"))
            let descriptor = try JSONDecoder().decode(JapaneseStarterLookup.Manifest.self, from: data)
            let owner = try JapaneseStarterLookup(data: Data(contentsOf: bundle.appendingPathComponent(descriptor.file)), manifest: data, packMultiple: JapaneseStarterLookup.packingEnabled)
            baseline = owner.provider(); raw = { owner.rawCandidates }
        } else if source == "en" && target == "sw" {
            let data = try Data(contentsOf: bundle.appendingPathComponent("starter-sw-catalog.json"))
            let descriptor = try JSONDecoder().decode(SwahiliStarterLookup.Manifest.self, from: data)
            let owner = try SwahiliStarterLookup(data: Data(contentsOf: bundle.appendingPathComponent(descriptor.file)), manifest: data, packMultiple: SwahiliStarterLookup.packingEnabled)
            baseline = owner.provider(); raw = { owner.rawCandidates }
        } else {
            let identity = "editorial-empty-baseline:" + pair
            baseline = SourceUnitLookup(identity: identity) { context in
                .init(original: context.original, source: source, target: target, catalogIdentity: identity, partial: nil, recognitions: [])
            }
            raw = { [] }
        }
        let frame = try SourceFrameLookup(bytes: bytes, manifestBytes: metadata, target: target, baselineIdentity: baseline.identity, source: source)
        let extended = frame.provider(baseline: baseline, raw: raw)
        return try XCTUnwrap(BundledStarterLookup.compose(
            japanese: pair == "en-ja" ? extended : nil,
            swahili: pair == "en-sw" ? extended : nil,
            candidates: ["en-ja", "en-sw"].contains(pair) ? [:] : [pair: extended]))
    }
    private func render(_ result: ImmersionPresentation?, original: String) -> [String: Any] {
        let base = result?.original ?? original
        let mixed = NSMutableString(string: base), reading = NSMutableString(string: base)
        for span in (result?.spans ?? []).reversed() {
            mixed.replaceCharacters(in: span.range, with: span.translated)
            reading.replaceCharacters(in: span.range, with: span.romanization ?? span.translated)
        }
        let refs: [SourceReferenceUnit]
        if case .partial(let partial) = result { refs = partial.references } else { refs = [] }
        return ["presentation_original": base, "original_preserved": base == original,
            "mixed_script": mixed as String, "mixed_reading": reading as String,
            "spans": (result?.spans ?? []).map { span -> [String: Any] in
                let proof = refs.first { $0.range == span.range }
                return ["start_utf16": span.range.location, "end_utf16": NSMaxRange(span.range), "source": span.original,
                    "target": span.translated, "reading": span.romanization as Any? ?? NSNull(),
                    "output_id": proof?.outputID as Any? ?? NSNull(), "concept_id": proof?.conceptID as Any? ?? NSNull()]
            }]
    }
    private func automatic(_ owner: ConversationImmersion, _ detector: MessageLanguage, text: String, id: String) async throws -> [String: Any] {
        let detected = try await detector.identify(text)
        let begin = ProcessInfo.processInfo.systemUptime
        let result = await owner.result(for: text)
        let outcome = try XCTUnwrap(owner.lastOutcome, id)
        XCTAssertEqual(outcome.localTranslationCalls, 0, id)
        var row = render(result, original: text)
        row.merge(["id": id, "original": text, "detected_language": detected as Any? ?? NSNull(), "input_language_override": NSNull(),
            "status": outcome.status.rawValue, "origin": outcome.origin?.rawValue as Any? ?? NSNull(),
            "translation_calls": outcome.localTranslationCalls, "model_readiness_calls": outcome.modelReadinessCalls,
            "alignment_calls": outcome.alignmentCalls, "milliseconds": (ProcessInfo.processInfo.systemUptime - begin) * 1000]) { _, new in new }
        return row
    }
    private func write(_ value: Any, to url: URL) throws {
        try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]).write(to: url, options: .withoutOverwriting)
    }
    func testPrivateCandidateBenchmarkThenControlsAndSample() async throws {
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let root = documents.appendingPathComponent("editorial-extension-private-r01")
        guard FileManager.default.fileExists(atPath: root.path) else { throw XCTSkip("Explicit private candidate required") }
        let frozen = try Data(contentsOf: documents.appendingPathComponent("frozen-conversations-r01.json"))
        XCTAssertEqual(JapaneseStarterLookup.digest(frozen), "ac6332cacdde6594f9083e57f04d100bb0fdf1ce7862bef2a18630324fdbca71")
        let items = try JSONDecoder().decode(Fixture.self, from: frozen).items
        let output = documents.appendingPathComponent("editorial-extension-native-r01")
        guard !FileManager.default.fileExists(atPath: output.path) else { return XCTFail("Do not overwrite retained capture") }
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        let detector = MessageLanguage()
        var completed = 0, emitted = 0, spansCount = 0
        // FIRST: unchanged friend messages, now a development benchmark, not unseen evidence.
        for source in SourceFrameLookup.languages.sorted() { for target in SourceFrameLookup.languages.sorted() where source != target {
            let pair = source + "-" + target
            let injected = try provider(root: root, source: source, target: target)
            let owner = ConversationImmersion(sourceUnits: injected)
            await owner.configure(pair: .init(source: source, target: target), density: 0.25)
            var rows: [[String: Any]] = []
            for item in items where item.source_language == source {
                var row = try await automatic(owner, detector, text: item.message, id: item.id)
                row["source_language"] = source; row["target_language"] = target
                let spans = row["spans"] as! [[String: Any]]
                if !spans.isEmpty { emitted += 1 }; spansCount += spans.count
                rows.append(row)
            }
            owner.close()
            completed += rows.count
            try write(["pair": pair, "density": 0.25, "injected_candidate": true, "default_provider": false, "rows": rows], to: output.appendingPathComponent("benchmark-" + pair + ".json"))
            try JSONSerialization.data(withJSONObject: ["phase": "benchmark", "completed": completed, "emitted_cases": emitted, "spans": spansCount], options: [.sortedKeys]).write(to: output.appendingPathComponent("progress.json"), options: .atomic)
        } }
        XCTAssertEqual(completed, 1320)
        try write(["cases": completed, "emitted_cases": emitted, "spans": spansCount], to: output.appendingPathComponent("benchmark-summary.json"))
        let fixture = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("native-fixtures.json"))) as? [String: Any])
        let controls = try XCTUnwrap(fixture["controls"] as? [[String: Any]])
        let sample = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("positive-sample.json"))) as? [String: Any])
        let positives = try XCTUnwrap(sample["cases"] as? [[String: Any]])
        var failures: [[String: Any]] = [], controlsDone = 0, positivesDone = 0
        for source in SourceFrameLookup.languages.sorted() { for target in SourceFrameLookup.languages.sorted() where source != target {
            let pair = source + "-" + target
            let selectedControls = controls.filter { $0["pair"] as? String == pair }
            let selectedPositive = positives.filter { $0["pair"] as? String == pair }
            if selectedControls.isEmpty && selectedPositive.isEmpty { continue }
            let injected = try provider(root: root, source: source, target: target)
            let owner = ConversationImmersion(sourceUnits: injected)
            await owner.configure(pair: .init(source: source, target: target), density: 0.25)
            var rows: [[String: Any]] = []
            for input in selectedControls + selectedPositive {
                let text = input["original"] as! String, id = input["id"] as! String
                let direct = try await injected.resolve(.init(original: text, pair: .init(source: source, target: target), density: 0.5, knownConceptIDs: []))
                let directRow = render(direct.partial.map { .partial($0) }, original: text)
                let auto = try await automatic(owner, detector, text: text, id: id)
                var row: [String: Any] = ["fixture": input, "direct_density": 0.5, "composed_density": 0.25, "direct": directRow, "automatic": auto]
                if let prefix = input["forbidden_pattern_prefix"] as? String, let focus = input["forbidden_focus"] as? String {
                    let forbidden = [directRow, auto].flatMap { $0["spans"] as! [[String: Any]] }.filter {
                        ($0["output_id"] as? String)?.hasPrefix(prefix) == true && $0["source"] as? String == focus
                    }
                    row["forbidden_outputs"] = forbidden
                    if !forbidden.isEmpty { failures.append(["id": id, "pair": pair, "forbidden": forbidden]) }
                    controlsDone += 1
                } else { positivesDone += 1 }
                rows.append(row)
            }
            owner.close()
            try write(["pair": pair, "injected_candidate": true, "rows": rows], to: output.appendingPathComponent("review-" + pair + ".json"))
        } }
        try write(["controls": controlsDone, "positive_sample": positivesDone, "forbidden_failures": failures], to: output.appendingPathComponent("review-summary.json"))
        XCTAssertEqual(controlsDone, 250); XCTAssertEqual(positivesDone, 44)
        XCTAssertTrue(failures.isEmpty, "Concept-specific negative failures retained in review-summary.json")
    }
}
