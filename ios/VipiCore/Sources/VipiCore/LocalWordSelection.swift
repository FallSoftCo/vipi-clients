import Foundation

/// Selects source words only. Callers supply actual native or reviewed lexical
/// evidence and a previously established due flag; this type neither guesses
/// POS nor translates, renders, persists, or treats a selection as exposure.
public enum LocalWordSelection {
    public enum PartOfSpeech: String, Sendable { case noun, verb }
    public enum Evidence: String, Sendable { case nativeTagger, reviewedLexicon }
    public struct Candidate: Sendable {
        public let range: NSRange
        public let surface: String
        public let partOfSpeech: PartOfSpeech
        public let evidence: Evidence
        /// True only when a caller has a matching source/sense exposure record.
        public let due: Bool
        public init(range: NSRange, surface: String, partOfSpeech: PartOfSpeech,
                    evidence: Evidence, due: Bool = false) {
            self.range = range; self.surface = surface; self.partOfSpeech = partOfSpeech
            self.evidence = evidence; self.due = due
        }
    }
    public struct Result: Sendable {
        public let selected: [Candidate]
        public let budget: Int
        public let rejected: [String: Int]
    }

    /// Ranges are UTF-16 coordinates into the exact supplied source text. An
    /// admitted candidate must be one complete native word and a grapheme-safe
    /// exact surface; protected ranges and overlapping choices are never edited.
    public static func select(original: String, nativeWordRanges: [NSRange],
                              protectedRanges: [NSRange], candidates: [Candidate],
                              density: Double) -> Result? {
        guard density.isFinite, density >= 0, candidates.count <= 4096,
              protectedRanges.count <= 1024,
              let basis = NativeSourceTokenBasis(original: original, wordRanges: nativeWordRanges),
              basis.count > 0 else { return nil }
        let source = original as NSString
        guard protectedRanges.allSatisfy({ r in
            r.location >= 0 && r.location <= source.length && r.length > 0 &&
                r.length <= source.length-r.location && Range(r, in: original) != nil
        }) else { return nil }
        let budget = density == 0 ? 0 : max(1, Int(Double(basis.count) * min(density, 1)))
        var rejected: [String:Int] = [:], eligible: [Candidate] = []
        func reject(_ reason: String) { rejected[reason, default: 0] += 1 }
        for candidate in candidates {
            let r = candidate.range
            guard r.location >= 0, r.location <= source.length, r.length > 0,
                  r.length <= source.length-r.location, Range(r, in: original) != nil,
                  basis.exactWordCost(for: r) == 1,
                  source.substring(with:r).utf16.elementsEqual(candidate.surface.utf16) else {
                reject("source_scope"); continue
            }
            guard !protectedRanges.contains(where: { NSIntersectionRange($0,r).length > 0 }) else {
                reject("protected_scope"); continue
            }
            eligible.append(candidate)
        }
        // Conflicting POS for the same exact word is ambiguous, even when each
        // analysis separately names a noun or verb. Require a reviewed resolver.
        var analyses: [NSRange:Set<PartOfSpeech>] = [:]
        for candidate in eligible { analyses[candidate.range, default: []].insert(candidate.partOfSpeech) }
        let conflicts = Set(analyses.compactMap { $0.value.count > 1 ? $0.key : nil })
        eligible.sort {
            if $0.due != $1.due { return $0.due }
            if $0.range.location != $1.range.location { return $0.range.location < $1.range.location }
            if $0.range.length != $1.range.length { return $0.range.length < $1.range.length }
            return $0.evidence.rawValue < $1.evidence.rawValue
        }
        var selected: [Candidate] = []
        for candidate in eligible {
            if conflicts.contains(candidate.range) { reject("conflicting_pos"); continue }
            if selected.contains(where: { NSIntersectionRange($0.range,candidate.range).length > 0 }) { reject("overlap"); continue }
            if selected.count >= min(budget,128) { reject("budget"); continue }
            selected.append(candidate)
        }
        selected.sort { $0.range.location < $1.range.location }
        return .init(selected:selected,budget:budget,rejected:rejected)
    }
}
