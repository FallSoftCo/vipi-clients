import Foundation
import CryptoKit
import Darwin

@main struct AppleNLPComparison {
    static func rss() -> Int64 {
        var value = rusage()
        getrusage(RUSAGE_SELF, &value)
        return Int64(value.ru_maxrss) // Darwin reports bytes, not Linux KiB.
    }
    static func ranges(_ values: [NSRange]) -> [[Int]] { values.map(rangeJSON) }
    static func basic(_ text: String, _ source: String) -> ([NSRange], [NSRange], [NSRange]?) {
        let words = LocalImmersion.words(text, language: source)
        let sentences = LocalImmersion.sentences(text, language: source)
        let windows = text.utf16.count <= 16_384 ? ReviewedFrameLookup.windows(text, language: source)?.values.flatMap { $0 }.sorted {
            $0.location != $1.location ? $0.location < $1.location : $0.length < $1.length
        } : nil
        return (words, sentences, windows)
    }
    static func spans(_ partial: PartialImmersionResult?) -> [[String: Any]] {
        (partial?.spans ?? []).map { span in
            ["source_range_utf16": rangeJSON(span.range), "original": span.original,
             "target": span.translated, "reading": span.romanization as Any? ?? NSNull(),
             "target_range_utf16": rangeJSON(span.targetRange)]
        }
    }
    static func compact(_ decisions: [[String: Any]], candidates: [NativeComparisonEngine.Candidate],
                        knownOrder: [String]) throws -> [String: Any] {
        let candidateIndices = Dictionary(uniqueKeysWithValues: candidates.enumerated().map { ($0.element.id, $0.offset) })
        var definitions: [[String: Any]] = [], index: [Data: Int] = [:], matrix: [[Any]] = []
        for decision in decisions {
            guard let known = decision["known_snapshot_id"] as? String, let knownIndex = knownOrder.firstIndex(of: known),
                  let ids = decision["selected_candidate_ids"] as? [String] else { throw ProbeError.invalid("Decision shape") }
            let selected = try ids.map { id -> Int in
                guard let value = candidateIndices[id] else { throw ProbeError.invalid("Selected candidate reference") }
                return value
            }
            let definition: [String: Any] = ["selected_candidate_indices": selected,
                "native_budget": decision["native_budget"]!, "used_source_tokens": decision["used_source_tokens"]!,
                "rejections": decision["rejections"]!]
            let key = try jsonBytes(definition), id: Int
            if let found = index[key] { id = found }
            else { id = definitions.count; index[key] = id; definitions.append(definition) }
            matrix.append([decision["density"]!, knownIndex, id, decision["elapsed_ns"]!])
        }
        return ["decision_table": definitions, "decision_matrix": matrix,
                "decision_matrix_columns": ["density", "known_snapshot_index", "decision_index", "elapsed_ns"]]
    }
    static func main() async throws {
        guard CommandLine.arguments.count == 3 else { throw ProbeError.invalid("freeze.json NEW_OUTPUT_DIRECTORY") }
        let freezeURL = URL(fileURLWithPath: CommandLine.arguments[1])
        let freezeData = try Data(contentsOf: freezeURL)
        guard let freeze = try JSONSerialization.jsonObject(with: freezeData) as? [String: Any],
              let inputFiles = freeze["inputs"] as? [String: [String: String]],
              let mode = freeze["mode"] as? String, ["geometry", "comparison"].contains(mode) else {
            throw ProbeError.invalid("Freeze shape")
        }
        func input(_ key: String) throws -> Data {
            guard let file = inputFiles[key], let path = file["path"], let expected = file["sha256"] else {
                throw ProbeError.invalid("Frozen input " + key)
            }
            let url = URL(fileURLWithPath: path, relativeTo: freezeURL.deletingLastPathComponent())
            let data = try Data(contentsOf: url)
            guard digest(data) == expected else { throw ProbeError.invalid("Frozen input changed " + key) }
            return data
        }
        let casesData = try input("cases")
        guard let wrapper = try JSONSerialization.jsonObject(with: casesData) as? [String: Any],
              let cases = wrapper["cases"] as? [[String: Any]], (1...10_000).contains(cases.count),
              cases.count == freeze["expected_case_count"] as? Int else { throw ProbeError.invalid("Cases") }
        let engine = mode == "comparison" ? try NativeComparisonEngine(payloadData: input("payload"), semanticsData: input("semantics")) : nil
        let directory = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
        guard !FileManager.default.fileExists(atPath: directory.path) else { throw ProbeError.invalid("Output already exists") }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
        let rowsURL = directory.appendingPathComponent("rows.jsonl")
        FileManager.default.createFile(atPath: rowsURL.path, contents: nil)
        let writer = try FileHandle(forWritingTo: rowsURL)
        defer { try? writer.close() }
        let catalog = BundledImmersionCatalog()
        let started = DispatchTime.now().uptimeNanoseconds
        var bytes = 0, count = 0, equalWarm = 0, complete = true, stopReason: String?
        var timings: [Double] = [], matched = 0
        for row in cases {
            if DispatchTime.now().uptimeNanoseconds - started > 600_000_000_000 {
                complete = false; stopReason = "600_second_process_budget"; break
            }
            guard let id = row["id"] as? String, let text = row["text"] as? String,
                  let source = row["source_language"] as? String,
                  let targets = row["target_languages"] as? [String] else { throw ProbeError.invalid("Case fields") }
            let firstStart = DispatchTime.now().uptimeNanoseconds
            let first = autoreleasepool { basic(text, source) }
            let firstNS = DispatchTime.now().uptimeNanoseconds - firstStart
            let warmStart = DispatchTime.now().uptimeNanoseconds
            let warm = autoreleasepool { basic(text, source) }
            let warmNS = DispatchTime.now().uptimeNanoseconds - warmStart
            let equal = first.0 == warm.0 && first.1 == warm.1 && first.2 == warm.2
            if equal { equalWarm += 1 }
            timings.append(Double(firstNS) / 1e6)
            var output: [String: Any] = [
                "id": id, "text": text, "source_language": source,
                "text_utf8_sha256": digest(Data(text.utf8)),
                "native_source_word_ranges_utf16": ranges(first.0),
                "native_sentence_ranges_utf16": ranges(first.1),
                "native_window_ranges_utf16": first.2.map(ranges) as Any? ?? NSNull(),
                "window_status": first.2 == nil ? "input_or_window_limit" : "available",
                "first_ms": Double(firstNS)/1e6, "warm_ms": Double(warmNS)/1e6,
                "warm_geometry_equal": equal, "provider_calls": 0]
            if let engine {
                let parseStart = DispatchTime.now().uptimeNanoseconds
                let geometry = try autoreleasepool { try engine.geometry(text: text, source: source) }
                let parseNS = DispatchTime.now().uptimeNanoseconds-parseStart
                let secondStart = DispatchTime.now().uptimeNanoseconds
                let second = try autoreleasepool { try engine.geometry(text: text, source: source) }
                let secondNS = DispatchTime.now().uptimeNanoseconds-secondStart
                let recognitionTrace = geometry.recognitions.map(\.trace)
                output["recognitions"] = recognitionTrace
                output["recognition_warm_equal"] = try jsonBytes(recognitionTrace) == jsonBytes(second.recognitions.map(\.trace))
                output["parse_first_ns"] = parseNS; output["parse_warm_ns"] = secondNS
                output["parse_rejections"] = geometry.parseRejections
                output["peak_match_states"] = geometry.peakStates
                output["protected_ranges"] = geometry.literals.map { ["kind": $0.kind, "range_utf16": rangeJSON($0.range)] }
                // Windows can be reconstructed exactly from the frozen source
                // and word/sentence ranges; retain a digest in the larger
                // comparison output rather than repeating all window arrays.
                output["native_window_ranges_sha256"] = try first.2.map { digest(try jsonBytes(ranges($0))) } as Any? ?? NSNull()
                output["native_window_count"] = first.2?.count ?? 0
                output.removeValue(forKey: "native_window_ranges_utf16")
                let knownOrder = engine.known.keys.sorted()
                output["known_snapshot_order"] = knownOrder
                var targetResults: [[String: Any]] = []
                var any = !geometry.recognitions.isEmpty
                for target in targets {
                    let pair = TranslationPair(source: source, target: target)
                    let whole = try await catalog.reference(original: text, pair: pair)
                    var baseline: [String: Any] = ["arm": "existing_reference_route", "source_mode": "explicit",
                        "automatic_language_detection": "not_executed_macOS_CLI",
                        "whole_reference": whole as Any? ?? NSNull(), "provider_calls": 0,
                        "target_dependent_alignment": "not_executed"]
                    if whole == nil {
                        var partials: [[String: Any]] = []
                        for density in [0.10, 0.25, 0.50] {
                            let partial = try await catalog.partial(original: text, pair: pair, density: density)
                            partials.append(["density": density, "selected_spans": spans(partial)])
                            any = any || partial != nil
                        }
                        baseline["partial_source_references"] = partials
                    } else { any = true }
                    var armResults: [[String: Any]] = []
                    for arm in engine.arms {
                        let candidate = try engine.candidates(text: text, source: source, target: target, arm: arm, geometry: geometry)
                        var decisions: [[String: Any]] = []
                        for density in [0.10, 0.25, 0.50] {
                            for known in knownOrder {
                                decisions.append(engine.select(text: text, target: target, density: density, knownID: known,
                                    candidates: candidate.candidates, words: geometry.words, literals: geometry.literals))
                            }
                        }
                        var armResult: [String: Any] = ["arm": arm, "recognition_indices": candidate.recognitions,
                            "output_candidates": candidate.candidates.map(\.trace), "rejections": candidate.rejections,
                            "provider_calls": 0]
                        if freeze["compact_decisions"] as? Bool == true {
                            armResult.merge(try compact(decisions, candidates: candidate.candidates, knownOrder: knownOrder)) { _, new in new }
                        } else { armResult["decisions"] = decisions }
                        armResults.append(armResult)
                        any = any || !candidate.candidates.isEmpty || !candidate.rejections.isEmpty
                    }
                    targetResults.append(["target": target, "baseline": baseline, "arms": armResults])
                }
                if any { matched += 1; output["target_results"] = targetResults }
                else {
                    output["target_results"] = ["status": "no_recognized_or_output_scope", "targets": targets,
                        "arms": engine.arms, "all_density_known_combinations_have_zero_output": true, "provider_calls": 0]
                }
            }
            var line = try jsonBytes(output); line.append(0x0a)
            if bytes + line.count > 20*1024*1024-16_384 {
                complete = false; stopReason = "20_MiB_output_budget"; break
            }
            try writer.write(contentsOf: line); bytes += line.count; count += 1
        }
        try writer.synchronize()
        let sorted = timings.sorted()
        let report: [String: Any] = ["schema": "vipi.apple-nlp-comparison.capture.1", "mode": mode,
            "complete": complete && count == cases.count, "expected_cases": cases.count, "processed_cases": count,
            "stop_reason": stopReason as Any? ?? NSNull(), "geometry_warm_equal_cases": equalWarm,
            "matched_or_rejected_scope_cases": matched,
            "first_ms_median": sorted.isEmpty ? 0 : sorted[sorted.count/2], "first_ms_max": sorted.last ?? 0,
            "elapsed_seconds": Double(DispatchTime.now().uptimeNanoseconds-started)/1e9,
            "peak_rss_bytes": rss(), "output_bytes": bytes, "output_sha256": digest(try Data(contentsOf: rowsURL)),
            "freeze_sha256": digest(freezeData), "input_sha256": digest(casesData),
            "provider_calls": 0, "source_language": "explicit", "production_provider": "nil",
            "limits": ["macOS native mechanism evidence, not iOS/physical/UI or translation quality proof",
                       "No model/preparation/network inference", "No uncommitted app source used",
                       "Atomic masks retained in comparison only; existing MT fallback integration remains unqualified"]]
        try jsonBytes(report).write(to: directory.appendingPathComponent("summary.json"), options: .atomic)
        print(String(data: try jsonBytes(report), encoding: .utf8)!)
    }
}
