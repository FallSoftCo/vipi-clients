import Foundation

/// QA-only source parser. Captures never construct a target string and no
/// pattern in this file is installed in the application.
enum NativePatternMatcher {
    struct Form: Decodable {
        let id: String
        let surface: String
        let pos: String
        let features: [String]
        let face_ids: [String: String]
        let primary_ref: String
    }
    struct Part: Decodable {
        let kind: String
        let name: String
        let value: String?
        let values: [String]?
        let type: String?
        let max_words: Int?
        let max_utf16: Int?
        let form_set: String?
    }
    struct RangeSpec: Decodable {
        let kind: String
        let part: String?
        let from: String?
        let through: String?
    }
    struct Atomicity: Decodable {
        let mode: String
        let scope: RangeSpec?
        let reason: String
    }
    struct Output: Decodable {
        let id: String
        let scope: RangeSpec
        let face_from_part: String?
        let face_ids: [String: String]?
        let concept_id: String
    }
    struct Pattern: Decodable {
        let id: String
        let family: String
        let source_language: String
        let arms: [String]
        let parts: [Part]
        let atomicity: Atomicity
        let approved_outputs: [Output]
        let meaning_id: String
        let priority: Int
        let evidence_ref: String
    }
    struct LiteralScope {
        let kind: String
        let range: NSRange
    }
    struct Binding: Equatable {
        let name: String
        let kind: String
        let range: NSRange
        let original: String
        let formID: String?
    }
    struct Parse {
        let context: NSRange
        let bindings: [Binding]
        func range(_ spec: RangeSpec) -> NSRange? {
            switch spec.kind {
            case "context": return context
            case "part": return bindings.first { $0.name == spec.part }?.range
            case "parts":
                guard let first = bindings.firstIndex(where: { $0.name == spec.from }),
                      let last = bindings.firstIndex(where: { $0.name == spec.through }), first <= last else { return nil }
                let start = bindings[first].range.location
                return NSRange(location: start, length: NSMaxRange(bindings[last].range) - start)
            default: return nil
            }
        }
    }
    struct Result {
        let parses: [Parse]
        let rejection: String?
        let peakStates: Int
    }
    private struct State {
        let offset: Int
        let bindings: [Binding]
    }
    private static let nameToken = try! NSRegularExpression(pattern: #"^[\p{L}\p{M}]+(?:[-'’][\p{L}\p{M}]+)*$"#)
    private static let number = try! NSRegularExpression(pattern: #"^\+?[0-9](?:[0-9 .()/\-]*[0-9)])?$"#)
    private static let possessives = Set(["my", "your", "his", "her", "its", "our", "their"])

    private static func exact(_ expression: NSRegularExpression, _ value: String) -> Bool {
        let range = NSRange(location: 0, length: value.utf16.count)
        return expression.firstMatch(in: value, range: range)?.range == range
    }
    private static func possessor(_ value: String, maxWords: Int) -> Bool {
        guard (1...3).contains(maxWords), !value.contains("\n"), !value.contains("\r") else { return false }
        if possessives.contains(value) { return true }
        let base: String
        if value.hasSuffix("'s") || value.hasSuffix("’s") { base = String(value.dropLast(2)) }
        else if value.hasSuffix("s'") || value.hasSuffix("s’") { base = String(value.dropLast()) }
        else { return false }
        // Spaces between name-shaped tokens are part of the original binding.
        let tokens = base.split(separator: " ", omittingEmptySubsequences: false).map(String.init)
        guard !tokens.isEmpty, tokens.count <= maxWords,
              tokens.allSatisfy({ exact(nameToken, $0) && $0.unicodeScalars.contains(where: CharacterSet.letters.contains) }) else { return false }
        return tokens.dropLast().allSatisfy { token in
            !(token.hasSuffix("'s") || token.hasSuffix("’s") || token.hasSuffix("s'") || token.hasSuffix("s’"))
        }
    }

    /// `context` must be one of the unchanged ReviewedFrameLookup windows.
    /// Every binding range is in the original source UTF16 coordinate space.
    static func match(original: String, context: NSRange, pattern: Pattern,
                      formSets: [String: [Form]], literalScopes: [LiteralScope]) -> Result {
        let ns = original as NSString
        guard original.utf16.count <= 16_384, context.length > 0, context.length <= 256,
              context.location >= 0, NSMaxRange(context) <= ns.length,
              Range(context, in: original) != nil, (1...12).contains(pattern.parts.count),
              Set(pattern.parts.map(\.name)).count == pattern.parts.count else {
            return .init(parses: [], rejection: "invalid_context_or_pattern_bounds", peakStates: 0)
        }
        let contextEnd = NSMaxRange(context)
        var states = [State(offset: context.location, bindings: [])], peak = 1
        for part in pattern.parts {
            var next: [State] = []
            for state in states {
                var choices: [(String, String?)] = []
                switch part.kind {
                case "literal":
                    if let value = part.value { choices = [(value, nil)] }
                case "enum": choices = (part.values ?? []).map { ($0, nil) }
                case "morph", "focus":
                    choices = (formSets[part.form_set ?? ""] ?? []).map { ($0.surface, $0.id) }
                case "typed":
                    guard let maximum = part.max_utf16, (1...128).contains(maximum) else {
                        return .init(parses: [], rejection: "typed_bound_missing", peakStates: peak)
                    }
                    let end = min(contextEnd, state.offset + maximum)
                    if state.offset < end {
                        for stop in (state.offset + 1)...end {
                            let range = NSRange(location: state.offset, length: stop - state.offset)
                            guard Range(range, in: original) != nil else { continue }
                            let value = ns.substring(with: range)
                            let allowed: Bool
                            switch part.type {
                            case "possessor": allowed = possessor(value, maxWords: part.max_words ?? 0)
                            case "number":
                                allowed = exact(number, value) && value.contains(where: { $0 >= "0" && $0 <= "9" })
                            case "identifier":
                                allowed = literalScopes.contains { ["url", "email", "handle", "code"].contains($0.kind) && $0.range == range }
                            default: allowed = false
                            }
                            guard allowed else { continue }
                            // Do not bind a prefix inside a longer word. The
                            // subsequent part still has to consume the exact
                            // remainder; no whitespace or case normalization.
                            let stopIndex = Range(range, in: original)!.upperBound
                            if stopIndex < original.endIndex,
                               original[stopIndex].unicodeScalars.contains(where: { CharacterSet.alphanumerics.union(.nonBaseCharacters).contains($0) }) {
                                continue
                            }
                            choices.append((value, nil))
                        }
                    }
                default: return .init(parses: [], rejection: "unknown_part_kind", peakStates: peak)
                }
                guard !choices.isEmpty else { continue }
                if part.kind != "typed" && choices.count > 32 {
                    return .init(parses: [], rejection: "finite_alternative_limit", peakStates: peak)
                }
                for (value, formID) in choices {
                    let length = value.utf16.count
                    guard length > 0, length <= (part.kind == "focus" ? 128 : 256),
                          state.offset + length <= contextEnd else { continue }
                    let range = NSRange(location: state.offset, length: length)
                    guard Range(range, in: original) != nil,
                          ns.substring(with: range).utf16.elementsEqual(value.utf16) else { continue }
                    next.append(.init(offset: NSMaxRange(range), bindings: state.bindings + [
                        .init(name: part.name, kind: part.kind, range: range,
                              original: ns.substring(with: range), formID: formID)]))
                    peak = max(peak, next.count)
                    if next.count > 128 { return .init(parses: [], rejection: "active_match_state_limit", peakStates: peak) }
                }
            }
            if next.isEmpty { return .init(parses: [], rejection: nil, peakStates: peak) }
            states = next
        }
        return .init(parses: states.filter { $0.offset == contextEnd }.map { .init(context: context, bindings: $0.bindings) },
                     rejection: nil, peakStates: peak)
    }
}
