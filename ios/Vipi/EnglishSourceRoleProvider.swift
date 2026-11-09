import Foundation
import NaturalLanguage

/// Source annotation only. No catalog, translation or customer call site is
/// installed by this component. A noun tag is not evidence of a word's meaning.
struct EnglishSourceRoleProvider {
    enum Status: String, Sendable { case ready, empty, unsupportedLanguage, invalidInput, nativeGeometryMismatch, lexicalSchemeUnavailable, nameSchemeUnavailable }
    enum Role: String, Sendable { case noun, nonNoun, unknown }
    struct Observation: Sendable, Equatable {
        let range: NSRange
        let original: String
        let role: Role
        let rawLexicalTag: String?
        let unknownReason: String?
        let overlapsProtection: Bool
        let nounEligible: Bool
    }
    struct Snapshot: Sendable {
        let original: String
        let language: String
        let wordRanges: [NSRange]
        let suppliedProtection: [NSRange]
        let detectedNames: [NSRange]
        let protectedRanges: [NSRange]
        let status: Status
        let availableSchemes: [String]
        let observations: [Observation]
        // Exact text identity; Swift String equality alone permits canonically
        // equivalent spellings with different UTF16 coordinates.
        func matches(original text: String, language: String, wordRanges: [NSRange], protectedRanges: [NSRange]) -> Bool {
            original.utf8.elementsEqual(text.utf8) && self.language == language &&
                self.wordRanges == wordRanges && suppliedProtection == protectedRanges
        }
    }
    func inspect(original: String, language: String, wordRanges: [NSRange], protectedRanges: [NSRange]) -> Snapshot {
        func result(_ status: Status, schemes: [String] = [], names: [NSRange] = [], union: [NSRange]? = nil,
                    observations: [Observation] = []) -> Snapshot {
            .init(original: original, language: language, wordRanges: wordRanges, suppliedProtection: protectedRanges,
                  detectedNames: names, protectedRanges: union ?? protectedRanges, status: status,
                  availableSchemes: schemes, observations: observations)
        }
        guard language == "en" else { return result(.unsupportedLanguage) }
        guard original.utf16.count <= 16_384, wordRanges.count <= 16_384, protectedRanges.count <= 4096 else { return result(.invalidInput) }
        let length = original.utf16.count
        let edges = Set(original.indices.map { $0.utf16Offset(in: original) } + [length])
        func valid(_ r: NSRange) -> Bool {
            r.location >= 0 && r.location <= length && r.length > 0 && r.length <= length-r.location &&
                edges.contains(r.location) && edges.contains(r.location+r.length)
        }
        var end = 0
        for r in wordRanges {
            guard valid(r), r.location >= end else { return result(.invalidInput) }
            end = r.location+r.length
        }
        guard protectedRanges.allSatisfy(valid) else { return result(.invalidInput) }
        guard !original.isEmpty else { return result(.empty) }
        let tokenizer = NLTokenizer(unit: .word)
        tokenizer.string = original; tokenizer.setLanguage(.english)
        var nativeWords: [NSRange] = []
        tokenizer.enumerateTokens(in: original.startIndex..<original.endIndex) { range, _ in
            if original[range].unicodeScalars.contains(where: { CharacterSet.letters.contains($0) }) {
                nativeWords.append(NSRange(range, in: original))
            }
            return true
        }
        guard nativeWords == wordRanges else { return result(.nativeGeometryMismatch) }
        let available = NLTagger.availableTagSchemes(for: .word, language: .english)
        let schemeNames = available.map(\.rawValue).sorted()
        guard available.contains(.lexicalClass) else { return result(.lexicalSchemeUnavailable, schemes: schemeNames) }
        let namesAvailable = available.contains(.nameType)
        let tagger = NLTagger(tagSchemes: namesAvailable ? [.lexicalClass, .nameType] : [.lexicalClass])
        tagger.string = original
        tagger.setLanguage(.english, range: original.startIndex..<original.endIndex)
        struct Lexical { let range: NSRange; let tag: NLTag? }
        var lexical: [NSRange: [Lexical]] = [:]
        tagger.enumerateTags(in: original.startIndex..<original.endIndex, unit: .word, scheme: .lexicalClass, options: []) { tag, range in
            let r = NSRange(range, in: original)
            lexical[r, default: []].append(.init(range: r, tag: tag))
            return true
        }
        var names: [NSRange] = []
        var nameGeometryValid = true
        if namesAvailable {
            tagger.enumerateTags(in: original.startIndex..<original.endIndex, unit: .word, scheme: .nameType, options: [.joinNames]) { tag, range in
                if tag == .personalName || tag == .placeName || tag == .organizationName {
                    let r = NSRange(range, in: original)
                    if valid(r) { names.append(r) } else { nameGeometryValid = false }
                }
                return true
            }
        }
        // Merge only overlapping/touching protection. Never replace or remove
        // a supplied mask based on a lexical tag or failure to detect a name.
        var union: [NSRange] = []
        for r in (protectedRanges+names).sorted(by: { ($0.location, $0.length) < ($1.location, $1.length) }) {
            if let last = union.last, r.location <= NSMaxRange(last) {
                union[union.count-1] = NSRange(location: last.location, length: max(NSMaxRange(last), NSMaxRange(r))-last.location)
            } else { union.append(r) }
        }
        let observations = wordRanges.map { r -> Observation in
            let entries = lexical[r] ?? []
            let exact = entries.count == 1 ? entries[0].tag : nil
            let role: Role = exact == nil ? .unknown : exact == .noun ? .noun : .nonNoun
            let overlaps = union.contains { NSIntersectionRange($0, r).length > 0 }
            let reason = entries.count != 1 ? "lexical_geometry_not_single_exact_word" : exact == nil ? "missing_lexical_tag" : nil
            return .init(range: r, original: (original as NSString).substring(with: r), role: role,
                         rawLexicalTag: exact?.rawValue, unknownReason: reason, overlapsProtection: overlaps,
                         nounEligible: role == .noun && namesAvailable && nameGeometryValid && !overlaps)
        }
        return result(nameGeometryValid ? (namesAvailable ? .ready : .nameSchemeUnavailable) : .invalidInput,
                      schemes: schemeNames, names: names, union: union, observations: observations)
    }
}
