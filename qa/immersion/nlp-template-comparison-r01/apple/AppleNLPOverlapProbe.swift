import Foundation
import CryptoKit

/// Synthetic eligibility checks only. Overlays are appended after actual
/// source matching and never enter the linguistic matcher or TRAIN corpus.
@main struct AppleNLPOverlapProbe {
    static func range(_ raw: Any?) throws -> NSRange {
        guard let pair = raw as? [Int], pair.count == 2, pair[0] >= 0, pair[1] > pair[0] else {
            throw ProbeError.invalid("Fixture range")
        }
        return .init(location: pair[0], length: pair[1]-pair[0])
    }
    static func main() throws {
        let a = CommandLine.arguments
        guard a.count == 5 else { throw ProbeError.invalid("payload semantics fixture NEW_OUTPUT") }
        let payload = try Data(contentsOf: URL(fileURLWithPath: a[1]))
        let semantics = try Data(contentsOf: URL(fileURLWithPath: a[2]))
        let fixture = try Data(contentsOf: URL(fileURLWithPath: a[3]))
        guard digest(payload) == "5c6a1c513a68f861ca28fd8c45b99b347e130940a29e6898bcc811fcfb47e5bc",
              digest(semantics) == "ac0df4d3ef183b9628fd6d29b868e50b7c02556a270de355d13dd6ff595cf3d7",
              digest(fixture) == "4f5f9b4e0b6823ed0aaa7807ac962003c09b96f99f728b23df7ae690d8d88c8c",
              !FileManager.default.fileExists(atPath: a[4]),
              let root = try JSONSerialization.jsonObject(with: fixture) as? [String: Any],
              let cases = root["cases"] as? [[String: Any]] else { throw ProbeError.invalid("Frozen fixture") }
        let engine = try NativeComparisonEngine(payloadData: payload, semanticsData: semantics)
        var rows: [[String: Any]] = []
        for sample in cases {
            guard let id = sample["id"] as? String, let text = sample["text"] as? String,
                  let synthetics = sample["synthetic_recognitions"] as? [[String: Any]],
                  let expected = sample["expected"] as? [String: [String]] else { throw ProbeError.invalid("Fixture shape") }
            let original = try engine.geometry(text: text, source: "en")
            guard original.words.map(rangeJSON) == sample["native_source_word_ranges_utf16"] as? [[Int]],
                  let basis = NativeSourceTokenBasis(original: text, wordRanges: original.words) else {
                throw ProbeError.invalid("Native fixture geometry")
            }
            var recognitions = original.recognitions
            var syntheticTraces: [[String: Any]] = []
            for raw in synthetics {
                guard let rule = raw["rule_id"] as? String, rule.hasPrefix("structural-only:"),
                      let meaning = raw["meaning_id"] as? String, let mode = raw["atomic_mode"] as? String,
                      let values = raw["outputs"] as? [[String: Any]], let reason = raw["reason"] as? String,
                      let priority = raw["priority"] as? Int else { throw ProbeError.invalid("Synthetic fixture shape") }
                let context = try range(raw["context_range_utf16"])
                let mask = raw["atomic_range_utf16"] is NSNull ? nil : try range(raw["atomic_range_utf16"])
                let approved: [(NativePatternMatcher.Output, NSRange)] = try values.map { value in
                    guard let outputID = value["id"] as? String, let concept = value["concept_id"] as? String,
                          let faces = value["resolved_face_ids"] as? [String: String] else { throw ProbeError.invalid("Synthetic output") }
                    let output = NativePatternMatcher.Output(id: outputID,
                        scope: .init(kind: "context", part: nil, from: nil, through: nil),
                        face_from_part: nil, face_ids: faces, concept_id: concept)
                    return (output, try range(value["source_range_utf16"]))
                }
                let pattern = NativePatternMatcher.Pattern(id: rule, family: "structural_test_only", source_language: "en",
                    arms: ["exact_top_down"], parts: [],
                    atomicity: .init(mode: mode, scope: nil, reason: reason), approved_outputs: approved.map { $0.0 },
                    meaning_id: meaning, priority: priority, evidence_ref: "synthetic-fixture:" + digest(fixture))
                let actualCost = basis.cost(for: context) ?? 0
                let recognition = NativeComparisonEngine.Recognition(pattern: pattern,
                    parse: .init(context: context, bindings: []), contextCost: actualCost, mask: mask, approved: approved,
                    recordHash: digest(fixture), morphology: [:])
                recognitions.append(recognition)
                syntheticTraces.append(["recognition": recognition.trace,
                    "supplied_synthetic_priority_cost": raw["context_native_words"] as Any? ?? NSNull(),
                    "actual_native_context_cost": actualCost, "linguistic_authority": false])
            }
            let geometry = NativeComparisonEngine.Geometry(words: original.words, sentences: original.sentences,
                windows: original.windows, literals: original.literals, recognitions: recognitions,
                parseRejections: original.parseRejections, peakStates: original.peakStates)
            for target in ["sw", "ja", "es"] {
                let result = try engine.candidates(text: text, source: "en", target: target,
                    arm: "typed_slots_attested_morphology", geometry: geometry)
                let present = Set(result.candidates.map(\.outputID))
                let reject = expected["reject_output_ids"] ?? [], keep = expected["keep_output_ids"] ?? []
                // Diagnostic fallback IDs carry exact face identity in this
                // native implementation; compare their declared concepts too.
                let aliases = Set(result.candidates.filter { $0.recognition == nil }.map { "diagnostic:" + $0.face.concept_id })
                let success = reject.allSatisfy { !present.contains($0) && !aliases.contains($0) } && keep.allSatisfy(present.contains)
                rows.append(["id": id, "text": text, "target": target, "passed": success,
                    "original_native_recognitions": original.recognitions.map(\.trace), "synthetic_overlays": syntheticTraces,
                    "eligible_outputs": result.candidates.map(\.trace), "rejections": result.rejections,
                    "expected": expected, "provider_calls": 0])
            }
        }
        let report: [String: Any] = ["schema": "vipi.apple-nlp-structural-overlap.1", "cases": rows,
            "passed": rows.allSatisfy { $0["passed"] as? Bool == true }, "checks": rows.count,
            "fixture_sha256": digest(fixture), "payload_sha256": digest(payload), "provider_calls": 0,
            "limitations": "Synthetic eligibility-stage conflicts; not language coverage, source recognition or production authority"]
        try jsonBytes(report).write(to: URL(fileURLWithPath: a[4]), options: .withoutOverwriting)
        print("structural_checks=\(rows.count) passed=\(report["passed"]!)")
    }
}
