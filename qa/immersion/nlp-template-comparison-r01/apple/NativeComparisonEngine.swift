import Foundation
import CryptoKit

enum ProbeError: Error { case invalid(String) }
func rangeJSON(_ range: NSRange) -> [Int] { [range.location, NSMaxRange(range)] }
func jsonBytes(_ value: Any) throws -> Data {
    try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes])
}
func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }

/// All data and orchestration here are diagnostic-only. Native production
/// source selection/presentation validation is called without installing a
/// SourceUnitLookup provider or altering app catalogs.
final class NativeComparisonEngine {
    typealias Matcher = NativePatternMatcher
    struct Face: Decodable {
        let id: String, concept_id: String, source_language: String, source_form: String
        let target_language: String, target: String, primary_ref: String, qualification: String
        let reading: String?
    }
    struct Payload: Decodable {
        let schema: String, production: Bool, contract_sha256: String
        let faces: [Face]
        let form_sets: [String: [Matcher.Form]]
        let patterns: [Matcher.Pattern]
        let fallback_entries: [String]
    }
    struct Recognition {
        let pattern: Matcher.Pattern
        let parse: Matcher.Parse
        let contextCost: Int
        let mask: NSRange?
        let approved: [(Matcher.Output, NSRange)]
        let recordHash: String
        let morphology: [String: Any]
        var trace: [String: Any] {
            ["rule_id": pattern.id, "meaning_id": pattern.meaning_id,
             "context_range_utf16": rangeJSON(parse.context), "context_native_cost": contextCost,
             "part_ranges_utf16": Dictionary(uniqueKeysWithValues: parse.bindings.map { ($0.name, rangeJSON($0.range)) }),
             "bindings_original": Dictionary(uniqueKeysWithValues: parse.bindings.map { ($0.name, $0.original) }),
             "form_ids": Dictionary(uniqueKeysWithValues: parse.bindings.compactMap { b in b.formID.map { (b.name, $0) } }),
             "morphological_analyses": morphology,
             "atomic_range_utf16": mask.map(rangeJSON) as Any? ?? NSNull(),
             "atomicity": pattern.atomicity.mode, "record_sha256": recordHash,
             "allowed_inner_outputs": approved.map { ["output_id": $0.0.id, "range_utf16": rangeJSON($0.1)] },
             "allowed_inner_output_ids": approved.map { $0.0.id },
             "reason": pattern.atomicity.reason, "evidence_ref": pattern.evidence_ref]
        }
    }
    struct Geometry {
        let words: [NSRange]
        let sentences: [NSRange]
        let windows: [NSRange]?
        let literals: [Matcher.LiteralScope]
        let recognitions: [Recognition]
        let parseRejections: [[String: Any]]
        let peakStates: Int
    }
    struct Candidate {
        let id: String
        let outputID: String
        let face: Face
        let unit: SourceReferenceUnit
        let context: NSRange
        let contextCost: Int
        let priority: Int
        let recognition: Int?
        var trace: [String: Any] {
            ["candidate_id": id, "output_id": outputID, "face_id": face.id,
             "source_range_utf16": rangeJSON(unit.range), "original": unit.original,
             "target": unit.translated, "reading": unit.reading as Any? ?? NSNull(),
             "native_cost": unit.nativeSourceTokens, "concept_id": face.concept_id,
             "context_range_utf16": rangeJSON(context), "context_native_cost": contextCost,
             "priority": priority, "recognition_index": recognition as Any? ?? NSNull(),
             "qualification": face.qualification, "primary_ref": face.primary_ref]
        }
    }
    let payload: Payload
    let payloadHash: String
    let semantics: [String: Any]
    let known: [String: [String]]
    let faces: [String: Face]
    let forms: [String: Matcher.Form]
    let formEvidence: [String: [String: Any]]
    let recordHashes: [String: String]
    let protection: [String: Any]
    let inheritance: [String: [String]]
    let arms = ["exact_top_down", "existing_finite_slots", "typed_slots_attested_morphology"]

    init(payloadData: Data, semanticsData: Data) throws {
        payloadHash = digest(payloadData)
        payload = try JSONDecoder().decode(Payload.self, from: payloadData)
        guard !payload.production, payload.schema == "vipi.nlp-template-payload.r01",
              payload.contract_sha256 == "3767a5f794023ff1fef85f5120658ce7881be0c143fd2357dcfcfe705272fdf2",
              let raw = try JSONSerialization.jsonObject(with: payloadData) as? [String: Any],
              let rawPatterns = raw["patterns"] as? [[String: Any]],
              let rawForms = raw["form_sets"] as? [String: [[String: Any]]],
              let value = try JSONSerialization.jsonObject(with: semanticsData) as? [String: Any],
              let known = value["known_snapshots"] as? [String: [String]],
              let protection = value["literal_protection"] as? [String: Any],
              let inheritance = value["arm_inheritance"] as? [String: [String]],
              Set(payload.faces.map(\.id)).count == payload.faces.count,
              Set(payload.patterns.map(\.id)).count == payload.patterns.count else { throw ProbeError.invalid("Payload schema") }
        semantics = value; self.known = known; self.protection = protection; self.inheritance = inheritance
        faces = Dictionary(uniqueKeysWithValues: payload.faces.map { ($0.id, $0) })
        let allForms = payload.form_sets.values.flatMap { $0 }
        guard Set(allForms.map(\.id)).count == allForms.count else { throw ProbeError.invalid("Duplicate form ID") }
        forms = Dictionary(uniqueKeysWithValues: allForms.map { ($0.id, $0) })
        formEvidence = Dictionary(uniqueKeysWithValues: rawForms.values.flatMap { $0 }.compactMap { value in
            (value["id"] as? String).map { ($0, value) }
        })
        recordHashes = try Dictionary(uniqueKeysWithValues: rawPatterns.map { raw in
            guard let id = raw["id"] as? String else { throw ProbeError.invalid("Pattern ID") }
            var canonical = raw
            let declared = canonical.removeValue(forKey: "record_sha256") as? String
            let actual = digest(try jsonBytes(canonical))
            if let declared, declared != actual { throw ProbeError.invalid("Pattern record digest " + id) }
            return (id, actual)
        })
        for pattern in payload.patterns {
            guard (1...12).contains(pattern.parts.count), Set(pattern.parts.map(\.name)).count == pattern.parts.count,
                  ["none", "atomic", "head_backoff", "ambiguous"].contains(pattern.atomicity.mode) else { throw ProbeError.invalid(pattern.id) }
            for part in pattern.parts where part.kind == "focus" || part.kind == "morph" {
                guard let id = part.form_set, let values = payload.form_sets[id], (1...32).contains(values.count) else {
                    throw ProbeError.invalid("Form alternatives " + pattern.id)
                }
            }
        }
    }
    func geometry(text: String, source: String) throws -> Geometry {
        let words = LocalImmersion.words(text, language: source)
        let sentences = LocalImmersion.sentences(text, language: source)
        let literals = try NativeLiteralScopes.collect(text, protection: protection)
        guard text.utf16.count <= 16_384, let native = NativeSourceTokenBasis(original: text, wordRanges: words),
              let windows = ReviewedFrameLookup.windows(text, language: source) else {
            return .init(words: words, sentences: sentences, windows: nil, literals: literals, recognitions: [],
                         parseRejections: [["reason": "native_input_or_window_limit"]], peakStates: 0)
        }
        let ordered = windows.values.flatMap { $0 }.sorted {
            let a = native.cost(for: $0) ?? 0, b = native.cost(for: $1) ?? 0
            if a != b { return a > b }
            if $0.length != $1.length { return $0.length > $1.length }
            return $0.location < $1.location
        }
        // A required exact finite surface absent from the whole source cannot
        // occur in any smaller window. This is a shortlist only; raw UTF16
        // equality and every source guard still run in the matcher below.
        let shortlisted = payload.patterns.filter { pattern in
            pattern.source_language == source && pattern.parts.allSatisfy { part in
                switch part.kind {
                case "literal": return part.value.map(text.contains) ?? false
                case "enum": return (part.values ?? []).contains(where: text.contains)
                case "focus", "morph": return (payload.form_sets[part.form_set ?? ""] ?? []).contains { text.contains($0.surface) }
                case "typed": return true
                default: return false
                }
            }
        }
        var result: [Recognition] = [], rejected: [[String: Any]] = [], peak = 0
        for context in ordered {
            for pattern in shortlisted {
                let parsed = Matcher.match(original: text, context: context, pattern: pattern,
                                           formSets: payload.form_sets, literalScopes: literals)
                peak = max(peak, parsed.peakStates)
                if let rejection = parsed.rejection {
                    rejected.append(["rule_id": pattern.id, "context_range_utf16": rangeJSON(context), "reason": rejection])
                }
                for parse in parsed.parses {
                    // Exercise the unchanged native finite matcher. The custom
                    // parser supplies bindings only; it cannot grant a finite
                    // control match that the production primitive rejects.
                    if pattern.arms.contains("existing_finite_slots") {
                        guard pattern.parts.filter({ $0.kind == "focus" }).count == 1,
                              let binding = parse.bindings.first(where: { $0.kind == "focus" }) else {
                            throw ProbeError.invalid("Finite focus shape " + pattern.id)
                        }
                        let parts: [ContextPart] = try pattern.parts.map { part in
                            switch part.kind {
                            case "literal": return .literal(part.value ?? "")
                            case "enum": return .slot(part.values ?? [])
                            case "focus": return .focus(binding.original)
                            default: throw ProbeError.invalid("Finite part " + part.kind)
                            }
                        }
                        let fragment = (text as NSString).substring(with: context)
                        let expected = NSRange(location: binding.range.location-context.location, length: binding.range.length)
                        guard ContextMappingMatcher.focus(in: fragment, parts: parts) == expected else {
                            rejected.append(["rule_id": pattern.id, "context_range_utf16": rangeJSON(context), "reason": "native_finite_matcher_rejected"])
                            continue
                        }
                    }
                    let approved = pattern.approved_outputs.compactMap { output in parse.range(output.scope).map { (output, $0) } }
                    guard approved.count == pattern.approved_outputs.count else { throw ProbeError.invalid("Output scope " + pattern.id) }
                    let mask = pattern.atomicity.scope.flatMap(parse.range)
                    if pattern.atomicity.mode != "none" && mask == nil { throw ProbeError.invalid("Atomic scope " + pattern.id) }
                    result.append(.init(pattern: pattern, parse: parse, contextCost: native.cost(for: context) ?? 0,
                                        mask: mask, approved: approved, recordHash: recordHashes[pattern.id]!,
                                        morphology: Dictionary(uniqueKeysWithValues: parse.bindings.compactMap { binding in
                                            binding.formID.flatMap { formEvidence[$0] }.map { (binding.name, $0 as Any) }
                                        })))
                }
            }
        }
        return .init(words: words, sentences: sentences, windows: ordered, literals: literals,
                     recognitions: result, parseRejections: rejected, peakStates: peak)
    }

    func candidates(text: String, source: String, target: String, arm: String, geometry: Geometry)
        throws -> (candidates: [Candidate], rejections: [[String: Any]], recognitions: [Int]) {
        guard let native = NativeSourceTokenBasis(original: text, wordRanges: geometry.words) else {
            return ([], [["reason": "invalid_native_geometry"]], [])
        }
        let acceptedArms = Set(inheritance[arm] ?? [])
        let recognitions = geometry.recognitions.enumerated().filter { !acceptedArms.isDisjoint(with: $0.element.pattern.arms) }
        var candidates: [Candidate] = [], rejected: [[String: Any]] = []
        func add(faceID: String, outputID: String, concept: String, range: NSRange,
                 context: NSRange, contextCost: Int, priority: Int, recognition: Int?) {
            let origin = recognition.map { geometry.recognitions[$0].pattern.id + ":" + String($0) } ?? "fallback"
            let id = "\(origin)|\(outputID)|\(faceID)|\(range.location):\(NSMaxRange(range))|\(context.location):\(NSMaxRange(context))"
            func reject(_ reason: String) { rejected.append(["candidate_id": id, "source_range_utf16": rangeJSON(range), "reason": reason]) }
            guard let face = faces[faceID], face.source_language == source, face.target_language == target,
                  face.concept_id == concept else { reject("missing_or_conflicting_face"); return }
            let original = (text as NSString).substring(with: range)
            guard original.utf16.elementsEqual(face.source_form.utf16) else { reject("face_source_scope_mismatch"); return }
            guard let cost = native.exactWordCost(for: range) else { reject("native_complete_word_scope"); return }
            guard !geometry.literals.contains(where: { NSIntersectionRange($0.range, range).length > 0 }) else {
                reject("protected_literal_scope"); return
            }
            for (_, other) in recognitions {
                guard let mask = other.mask, NSIntersectionRange(mask, range).length > 0 else { continue }
                guard other.pattern.atomicity.mode != "ambiguous",
                      other.approved.contains(where: { $0.0.id == outputID && $0.1 == range }) else {
                    reject("atomic_context_blocks_inner_output:" + other.pattern.id); return
                }
            }
            if let recognition {
                let own = geometry.recognitions[recognition]
                for (index, other) in recognitions where index != recognition && other.pattern.meaning_id != own.pattern.meaning_id {
                    if NSIntersectionRange(other.parse.context, own.parse.context).length > 0 &&
                        (other.approved.contains { NSIntersectionRange($0.1, range).length > 0 } ||
                         other.mask.map { NSIntersectionRange($0, range).length > 0 } == true) {
                        reject("conflicting_meaning:" + other.pattern.id); return
                    }
                }
            }
            let unit = SourceReferenceUnit(range: range, original: original, translated: face.target, reading: face.reading,
                referenceID: face.primary_ref, catalogSHA256: payloadHash, nativeSourceTokens: cost, conceptID: concept)
            // The established presentation factory checks non-Roman readings,
            // identifiers and full target/source geometry before selection.
            guard SourceReferencePresentation.create(original: text, target: target, units: [unit], density: 1,
                                                     nativeSourceTokenCount: native.count) != nil else {
                reject("native_presentation_rejected"); return
            }
            candidates.append(.init(id: id, outputID: outputID, face: face, unit: unit, context: context,
                                    contextCost: contextCost, priority: priority, recognition: recognition))
        }
        for (index, recognition) in recognitions {
            for (output, range) in recognition.approved {
                let faceID: String?
                if let part = output.face_from_part,
                   let form = recognition.parse.bindings.first(where: { $0.name == part })?.formID {
                    faceID = forms[form]?.face_ids[target]
                } else { faceID = output.face_ids?[target] }
                guard let faceID else {
                    rejected.append(["rule_id": recognition.pattern.id, "output_id": output.id,
                                     "source_range_utf16": rangeJSON(range), "reason": "no_target_face"]); continue
                }
                add(faceID: faceID, outputID: output.id, concept: output.concept_id, range: range,
                    context: recognition.parse.context, contextCost: recognition.contextCost,
                    priority: recognition.pattern.priority, recognition: index)
            }
        }
        for faceID in payload.fallback_entries {
            guard let face = faces[faceID], face.source_language == source, face.target_language == target else { continue }
            for word in geometry.words where (text as NSString).substring(with: word).utf16.elementsEqual(face.source_form.utf16) {
                add(faceID: faceID, outputID: "diagnostic-fallback:" + face.id, concept: face.concept_id, range: word,
                    context: word, contextCost: 1, priority: -1, recognition: nil)
            }
        }
        candidates.sort { a, b in
            if a.contextCost != b.contextCost { return a.contextCost > b.contextCost }
            if a.context.length != b.context.length { return a.context.length > b.context.length }
            if a.priority != b.priority { return a.priority > b.priority }
            if a.unit.nativeSourceTokens != b.unit.nativeSourceTokens { return a.unit.nativeSourceTokens > b.unit.nativeSourceTokens }
            if a.unit.range.location != b.unit.range.location { return a.unit.range.location < b.unit.range.location }
            if a.outputID != b.outputID { return a.outputID < b.outputID }
            return a.id < b.id
        }
        return (candidates, rejected, recognitions.map(\.offset))
    }
    func select(text: String, target: String, density: Double, knownID: String,
                candidates: [Candidate], words: [NSRange], literals: [Matcher.LiteralScope]) -> [String: Any] {
        let start = DispatchTime.now().uptimeNanoseconds
        // Convert the frozen context order to explicit ranks. This does not
        // reuse the unrelated word-catalog TRAIN frequency policy.
        let values = candidates.enumerated().map { index, candidate in
            SourceUnitSelection.Candidate(unit: candidate.unit, lexiconID: candidate.id, category: .content, rank: index)
        }
        let selected = SourceUnitSelection.select(original: text, target: target, candidates: values,
            nativeWordRanges: words, protectedRanges: literals.map(\.range), density: density,
            knownConceptIDs: Set(known[knownID] ?? []))
        let references = selected?.partial?.references ?? []
        let ids = references.compactMap { unit in candidates.first { $0.unit == unit }?.id }
        return ["density": density, "known_snapshot_id": knownID, "native_source_word_count": words.count,
                "native_budget": selected?.budget ?? max(1, Int(Double(words.count)*density)),
                "selected_candidate_ids": ids, "used_source_tokens": selected?.usedSourceTokens ?? 0,
                "rejections": selected?.rejected ?? [:], "provider_calls": 0,
                "elapsed_ns": DispatchTime.now().uptimeNanoseconds-start]
    }
}
