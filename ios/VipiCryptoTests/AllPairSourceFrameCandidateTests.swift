import Foundation
import XCTest
import VipiCore
@testable import Vipi

@MainActor final class AllPairSourceFrameCandidateTests: XCTestCase {
    private func synthetic(source: String, target: String, variants: [[String: Any]], focus: String, output: String) throws -> SourceFrameLookup {
        let pack: [String: Any] = ["schema": "vipi-source-frame-pack-1", "version": "001", "source": source, "target": target,
            "policy": "reference-first-source-frames-1", "approval_sha256": String(repeating: "a", count: 64),
            "patterns": [["id": "test-rule", "pair": source + "-" + target, "source": focus, "target": output,
                "reading": "", "meaning": "bounded test", "concept_id": "test-concept", "source_only_permission": true, "variants": variants]]]
        let bytes = try JSONSerialization.data(withJSONObject: pack, options: [.sortedKeys])
        let manifest: [String: Any] = ["schema": "vipi-source-frame-manifest-1", "file": "source-frames-" + source + "-" + target + "-001.json",
            "sha256": JapaneseStarterLookup.digest(bytes), "bytes": bytes.count, "patterns": 1, "version": "001",
            "source": source, "target": target, "policy": "reference-first-source-frames-1"]
        return try SourceFrameLookup(bytes: bytes, manifestBytes: JSONSerialization.data(withJSONObject: manifest), target: target, baselineIdentity: "test-baseline", source: source)
    }
    func testExplicitContextScopesAndUnicodeRightBoundaries() throws {
        func resolve(_ owner: SourceFrameLookup, _ text: String, _ source: String, _ target: String) throws -> SourceLookupEvidence {
            try owner.resolve(original: text, density: 0.75, known: [], baseline: .init(original: text, source: source, target: target, catalogIdentity: "test-baseline", partial: nil, recognitions: []), raw: [])
        }
        let clause = try synthetic(source: "zh", target: "en", variants: [["context": "吃面包", "focus_utf16": [1, 3], "right_boundary": "clause_or_end"]], focus: "面包", output: "bread")
        for text in ["吃面包", "吃面包。", "吃面包\t，喝水", "吃面包\r\n喝水", "吃面包\u{00a0}\u{3000}；喝水"] {
            XCTAssertEqual(try resolve(clause, text, "zh", "en").partial?.spans.first?.translated, "bread", text)
        }
        for text in ["吃面包虫", "吃面包\t虫", "吃面包\u{00a0}虫", "吃面包\u{3000}虫", "吃面包\u{000b}，喝水"] {
            let value = try resolve(clause, text, "zh", "en")
            XCTAssertNil(value.partial, text); XCTAssertTrue(value.recognitions.isEmpty, "Rejected guards cannot mask unrelated matches")
        }
        let sentence = try synthetic(source: "en", target: "es", variants: [["context": "Hello.", "focus_utf16": [0, 5], "context_scope": "whole_sentence"]], focus: "Hello", output: "Hola")
        for text in ["Hello.", "  Hello.  ", "We can talk later. Hello."] {
            XCTAssertEqual(try resolve(sentence, text, "en", "es").partial?.spans.first?.translated, "Hola", text)
        }
        let nested = try resolve(sentence, "We said Hello.", "en", "es")
        XCTAssertNil(nested.partial); XCTAssertTrue(nested.recognitions.isEmpty)
        XCTAssertThrowsError(try synthetic(source: "en", target: "es", variants: [["context": "Hello.", "focus_utf16": [0, 5], "context_scope": "arbitrary"]], focus: "Hello", output: "Hola"))
        XCTAssertThrowsError(try synthetic(source: "zh", target: "en", variants: [["context": "吃面包", "focus_utf16": [1, 3], "right_boundary": "arbitrary"]], focus: "面包", output: "bread"))
    }

    func testIsolatedCandidateNativeBoundariesAndAutomaticRouting() async throws {
        let root = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("all-pair-starter-candidate-r02")
        guard FileManager.default.fileExists(atPath: root.path) else { throw XCTSkip("Explicit isolated candidate required") }
        XCTAssertTrue(BundledStarterLookup.allPairPromotionEnabled)
        let fixture = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("native-fixtures.json"))) as? [String: Any])
        let cases = try XCTUnwrap(fixture["cases"] as? [[String: Any]])
        var owners: [String: SourceFrameLookup] = [:], providers: [String: SourceUnitLookup] = [:]
        for source in SourceFrameLookup.languages.sorted() { for target in SourceFrameLookup.languages.sorted() where source != target {
            let pair = source + "-" + target
            let manifestData = try Data(contentsOf: root.appendingPathComponent("packs/source-frames-" + pair + "-catalog.json"))
            let manifest = try JSONDecoder().decode(SourceFrameLookup.Manifest.self, from: manifestData)
            let bytes = try Data(contentsOf: root.appendingPathComponent("packs/" + manifest.file))
            let baseline = SourceUnitLookup(identity: "empty-candidate-baseline-" + pair) { context in
                SourceLookupEvidence(original: context.original, source: source, target: target,
                    catalogIdentity: "empty-candidate-baseline-" + pair, partial: nil, recognitions: [])
            }
            let owner = try SourceFrameLookup(bytes: bytes, manifestBytes: manifestData, target: target, baselineIdentity: baseline.identity, source: source)
            owners[pair] = owner; providers[pair] = owner.provider(baseline: baseline, raw: { [] })
        } }
        XCTAssertEqual(providers.count, 110)
        let composed = try XCTUnwrap(BundledStarterLookup.compose(japanese: JapaneseStarterLookup.bundledIfPromoted(), swahili: SwahiliStarterLookup.bundledIfPromoted(), candidates: providers))
        let production = try XCTUnwrap(BundledStarterLookup.provider())
        let detector = MessageLanguage()
        var records: [[String: Any]] = [], automatic: [[String: Any]] = []
        var conversations: [String: ConversationImmersion] = [:]
        defer { for conversation in conversations.values { conversation.close() } }
        var demonstrated = Set<String>(), automaticPairs = Set<String>(), controlled = Set<String>()
        func spans(_ values: [ImmersionSpan]) -> [[String: Any]] {
            values.map { ["source": $0.original, "target": $0.translated, "reading": $0.romanization ?? "", "range": [$0.range.location, NSMaxRange($0.range)]] }
        }
        for row in cases {
            let pairID = try XCTUnwrap(row["pair"] as? String), source = try XCTUnwrap(row["source_language"] as? String), target = try XCTUnwrap(row["target_language"] as? String)
            let text = try XCTUnwrap(row["original"] as? String), provider = try XCTUnwrap(providers[pairID]), owner = try XCTUnwrap(owners[pairID])
            let pair = TranslationPair(source: source, target: target)
            if pairID == "en-ja" || pairID == "en-sw" {
                let context = SourceUnitLookup.Context(original: text, pair: pair, density: 0.25, knownConceptIDs: [])
                let before = try await production.resolve(context), after = try await composed.resolve(context)
                XCTAssertEqual(before.partial, after.partial, "Preserve shipped pair precedence")
            }
            let boundaries = LocalImmersion.words(text, language: source)
            let evidence = try await provider.resolve(.init(original: text, pair: pair, density: 0.5, knownConceptIDs: []))
            let selected = evidence.partial?.spans ?? []
            let focus = try XCTUnwrap(row["focus_utf16"] as? [Int])
            let focusRange = NSRange(location: focus[0], length: focus[1] - focus[0])
            for span in selected where span.range == focusRange {
                XCTAssertEqual(span.original, row["expected_source"] as? String)
                XCTAssertEqual(span.translated, row["expected_target"] as? String)
                XCTAssertEqual(span.romanization ?? "", row["reading"] as? String)
            }
            let forbidden = Set(row["forbidden_sources"] as? [String] ?? [])
            XCTAssertTrue(selected.allSatisfy { !forbidden.contains($0.original) }, "Rejected context leaked: " + text)
            for span in selected {
                XCTAssertNotNil(NativeSourceTokenBasis(original: text, wordRanges: boundaries)?.exactWordCost(for: span.range))
                XCTAssertTrue(TranslationIntegrity.preservesIdentifiers(original: text, translation: (text as NSString).replacingCharacters(in: span.range, with: span.translated)))
            }
            records.append(["id": row["id"]!, "pair": pairID, "text": text, "density": 0.5, "native_words": boundaries.map { [$0.location, NSMaxRange($0)] }, "spans": spans(selected), "trace": owner.trace, "expected_source": row["expected_source"]!, "expected_target": row["expected_target"]!, "expected_reading": row["reading"]!])
            if !selected.isEmpty && !demonstrated.contains(pairID) {
                demonstrated.insert(pairID)
            }
            do {
                for manual in [false, true] {
                    let density = 0.25
                    let conversation = conversations[pairID] ?? ConversationImmersion(sourceUnits: composed)
                    conversations[pairID] = conversation
                    await conversation.configure(pair: pair, density: density)
                    let value = await conversation.result(for: text, inputLanguage: manual ? source : nil)
                    XCTAssertTrue((value?.spans ?? []).allSatisfy { !forbidden.contains($0.original) }, "Automatic route leaked rejected context: " + text)
                    let guess = try await detector.identify(text)
                    automatic.append(["id": row["id"]!, "pair": pairID, "manual_source": manual, "text": text, "density": density, "detected": guess as Any? ?? NSNull(), "spans": spans(value?.spans ?? []), "status": conversation.lastOutcome?.status.rawValue as Any? ?? NSNull()])
                    if !manual && !(value?.spans.isEmpty ?? true) && automaticPairs.insert(pairID).inserted {
                        await conversation.configure(pair: .init(source: target, target: source), density: density)
                        let reversed = await conversation.result(for: text)
                        automatic.append(["pair": target + "-" + source, "text": text, "density": density,
                            "direction": "already-target-language", "detected": guess as Any? ?? NSNull(),
                            "spans": spans(reversed?.spans ?? []), "status": conversation.lastOutcome?.status.rawValue as Any? ?? NSNull()])
                    }
                    conversation.close()
                }
            }
            if !selected.isEmpty && controlled.insert(pairID).inserted {
                for protected in ["`" + text + "`", "```\n" + text + "\n```"] {
                    let value = try await provider.resolve(.init(original: protected, pair: pair, density: 0.5, knownConceptIDs: []))
                    XCTAssertTrue(value.partial?.spans.isEmpty ?? true)
                }
                let zero = try await provider.resolve(.init(original: text, pair: pair, density: 0, knownConceptIDs: []))
                XCTAssertNil(zero.partial)
                let unknown = try await provider.resolve(.init(original: "zxqvplm rtxqvz", pair: pair, density: 0.5, knownConceptIDs: []))
                XCTAssertNil(unknown.partial)
            }
        }
        var controls: [[String: Any]] = []
        for row in try XCTUnwrap(fixture["controls"] as? [[String: Any]]) {
            let pairID = try XCTUnwrap(row["pair"] as? String), source = try XCTUnwrap(row["source_language"] as? String), target = try XCTUnwrap(row["target_language"] as? String)
            let text = try XCTUnwrap(row["original"] as? String)
            let value = try await XCTUnwrap(providers[pairID]).resolve(.init(original: text, pair: .init(source: source, target: target), density: 0.5, knownConceptIDs: []))
            controls.append(["id": row["id"]!, "pair": pairID, "text": text, "spans": spans(value.partial?.spans ?? [])])
            XCTAssertNil(value.partial, "Unlisted morphology/ambiguous context: " + text)
        }
        var errorRoutes: [[String: Any]] = []
        let errorURL = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "CLD2Fixtures", withExtension: "json"))
        let errorFixture = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: errorURL)) as? [String: Any])
        for pairID in providers.keys.sorted() {
            let parts = pairID.split(separator: "-").map(String.init)
            let conversation = conversations[pairID] ?? ConversationImmersion(sourceUnits: composed)
            conversations[pairID] = conversation
            await conversation.configure(pair: .init(source: parts[0], target: parts[1]), density: 0.25)
            for row in try XCTUnwrap(errorFixture["errors"] as? [[String: Any]]) {
                let text = try XCTUnwrap(row["text"] as? String)
                let value = await conversation.result(for: text)
                errorRoutes.append(["id": row["id"]!, "pair": pairID, "text": text, "spans": spans(value?.spans ?? [])])
            }
            conversation.close()
        }
        let receipt: [String: Any] = ["controls": controls, "known_detector_errors": errorRoutes,"direct": records, "automatic": automatic, "demonstrated_pairs": demonstrated.sorted(), "automatic_pairs": automaticPairs.sorted(), "promotion_enabled": BundledStarterLookup.allPairPromotionEnabled]
        try JSONSerialization.data(withJSONObject: receipt, options: [.sortedKeys]).write(to: root.appendingPathComponent("apple-native-r02.json"))
        XCTAssertEqual(Set(cases.compactMap { $0["pair"] as? String }).count, 110)
        // A boundary rejection is evidence, never permission to split a source unit.
    }
}
