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
        /// Seen and due require a matching, independently established source/sense identity.
        public let seen: Bool
        public let due: Bool
        public init(range: NSRange, surface: String, partOfSpeech: PartOfSpeech,
                    evidence: Evidence, seen: Bool = false, due: Bool = false) {
            self.range = range; self.surface = surface; self.partOfSpeech = partOfSpeech
            self.evidence = evidence; self.seen = seen; self.due = due
        }
    }
    public struct Result: Sendable {
        public let selected: [Candidate]
        public let novelBudget: Int
        public let totalCeiling: Int
        public let rejected: [String: Int]
    }

    /// Ranges are UTF-16 coordinates into the exact supplied source text. An
    /// admitted candidate must cover complete native words and a grapheme-safe
    /// exact surface; multiword units require reviewed evidence. Protected and
    /// overlapping choices are never edited.
    public static func select(original: String, nativeWordRanges: [NSRange],
                              protectedRanges: [NSRange], candidates: [Candidate],
                              density: Double) -> Result? {
        guard density.isFinite, (0...0.75).contains(density), candidates.count <= 4096,
              protectedRanges.count <= 1024,
              let basis = NativeSourceTokenBasis(original: original, wordRanges: nativeWordRanges),
              basis.count > 0 else { return nil }
        let source = original as NSString
        guard protectedRanges.allSatisfy({ r in
            r.location >= 0 && r.location <= source.length && r.length > 0 &&
                r.length <= source.length-r.location && Range(r, in: original) != nil
        }) else { return nil }
        let ceiling = density == 0 ? 0 : min(basis.count, max(1, Int(Double(basis.count) * 0.75)))
        let budget = density == 0 ? 0 : min(ceiling, max(1, Int(Double(basis.count) * min(density, 0.75))))
        var rejected: [String:Int] = [:], eligible: [Candidate] = [], costs: [NSRange:Int] = [:]
        func reject(_ reason: String) { rejected[reason, default: 0] += 1 }
        for candidate in candidates {
            let r = candidate.range
            guard !candidate.due || candidate.seen else { reject("invalid_history"); continue }
            guard r.location >= 0, r.location <= source.length, r.length > 0,
                  r.length <= source.length-r.location, Range(r, in: original) != nil,
                  let cost = basis.exactWordCost(for: r), cost > 0,
                  (cost == 1 || candidate.evidence == .reviewedLexicon),
                  source.substring(with:r).utf16.elementsEqual(candidate.surface.utf16) else {
                reject("source_scope"); continue
            }
            guard !protectedRanges.contains(where: { NSIntersectionRange($0,r).length > 0 }) else {
                reject("protected_scope"); continue
            }
            eligible.append(candidate); costs[r] = cost
        }
        // Conflicting POS for the same exact word is ambiguous, even when each
        // analysis separately names a noun or verb. Require a reviewed resolver.
        var analyses: [NSRange:Set<PartOfSpeech>] = [:], history: [NSRange:Set<Bool>] = [:]
        for candidate in eligible {
            analyses[candidate.range, default: []].insert(candidate.partOfSpeech)
            history[candidate.range, default: []].insert(candidate.seen)
        }
        let conflicts = Set(analyses.compactMap { $0.value.count > 1 ? $0.key : nil })
            .union(history.compactMap { $0.value.count > 1 ? $0.key : nil })
        eligible.sort {
            if $0.due != $1.due { return $0.due }
            if $0.range.location != $1.range.location { return $0.range.location < $1.range.location }
            if $0.range.length != $1.range.length { return $0.range.length < $1.range.length }
            return $0.evidence.rawValue < $1.evidence.rawValue
        }
        var selected: [Candidate] = [], novel = 0, used = 0
        func admit(_ candidate: Candidate) -> Bool {
            let cost = costs[candidate.range]!
            guard !conflicts.contains(candidate.range), selected.count < 128,
                  used + cost <= ceiling, (candidate.seen || novel + cost <= budget),
                  !selected.contains(where: { NSIntersectionRange($0.range,candidate.range).length > 0 }) else { return false }
            selected.append(candidate); used += cost
            if !candidate.seen { novel += cost }
            return true
        }
        // Reserve a complete new word first; seen words add to the new-word
        // budget up to the independent 75% ceiling, never displacing all novelty.
        if budget > 0 {
            for candidate in eligible where !candidate.seen { if admit(candidate) { break } }
        }
        for candidate in eligible where candidate.seen { _ = admit(candidate) }
        for candidate in eligible where !candidate.seen && novel < budget { _ = admit(candidate) }
        for candidate in eligible {
            if conflicts.contains(candidate.range) { reject("conflicting_pos") }
            else if !selected.contains(where: { $0.range == candidate.range && $0.partOfSpeech == candidate.partOfSpeech }) {
                reject("not_selected")
            }
        }
        selected.sort { $0.range.location < $1.range.location }
        return .init(selected:selected,novelBudget:budget,totalCeiling:ceiling,rejected:rejected)
    }
}
