import Foundation

/// Selection of already admitted source-only entries. This layer does not
/// infer senses, POS, protected scopes, readings or acquisition from exposure.
public enum SourceUnitSelection {
    public enum Category: String, Sendable { case content, function }
    public struct Candidate: Sendable {
        public let unit: SourceReferenceUnit
        public let lexiconID: String
        public let category: Category
        public let rank: Int
        public init(unit: SourceReferenceUnit, lexiconID: String, category: Category, rank: Int) {
            self.unit = unit; self.lexiconID = lexiconID; self.category = category; self.rank = rank
        }
    }
    public struct Result: Sendable {
        public let partial: PartialImmersionResult?
        public let budget: Int
        public let selectedConceptIDs: [String]
        public let usedSourceTokens: Int
        public let rejected: [String: Int]
    }

    public static func select(original: String, target: String, candidates: [Candidate],
                              nativeWordRanges: [NSRange], protectedRanges: [NSRange],
                              density: Double, knownConceptIDs: Set<String> = []) -> Result? {
        guard density.isFinite, density > 0, candidates.count <= 65_536,
              let basis = NativeSourceTokenBasis(original: original, wordRanges: nativeWordRanges),
              basis.count > 0 else { return nil }
        let source = original as NSString
        guard protectedRanges.count <= 16_384, protectedRanges.allSatisfy({ range in
            range.location >= 0 && range.location <= source.length && range.length > 0 &&
                range.length <= source.length-range.location && Range(range, in: original) != nil
        }) else { return nil }
        let budget = max(1, Int(Double(basis.count) * min(density, 1)))
        var eligible: [Candidate] = [], rejected: [String: Int] = [:]
        func reject(_ reason: String) { rejected[reason, default: 0] += 1 }
        for candidate in candidates {
            let unit = candidate.unit
            guard let concept = unit.conceptID, !concept.isEmpty, concept.utf16.count <= 256,
                  !unit.referenceID.isEmpty, !candidate.lexiconID.isEmpty,
                  candidate.rank >= 0 else { reject("invalid_identity"); continue }
            guard let cost = basis.exactWordCost(for: unit.range), cost == unit.nativeSourceTokens,
                  source.substring(with: unit.range).utf16.elementsEqual(unit.original.utf16) else { reject("native_source_scope"); continue }
            guard !protectedRanges.contains(where: { NSIntersectionRange($0, unit.range).length > 0 }) else {
                reject("protected_source_scope"); continue
            }
            guard !knownConceptIDs.contains(concept) else { reject("known_concept"); continue }
            guard cost <= budget else { reject("unit_exceeds_budget"); continue }
            eligible.append(candidate)
        }
        eligible.sort { a, b in
            if a.category != b.category { return a.category == .content }
            if a.rank != b.rank { return a.rank < b.rank }
            if a.unit.nativeSourceTokens != b.unit.nativeSourceTokens { return a.unit.nativeSourceTokens > b.unit.nativeSourceTokens }
            if a.unit.range.location != b.unit.range.location { return a.unit.range.location < b.unit.range.location }
            return a.lexiconID < b.lexiconID
        }
        var selected: [SourceReferenceUnit] = [], concepts = Set<String>(), used = 0
        for candidate in eligible {
            let unit = candidate.unit
            guard !concepts.contains(unit.conceptID!) else { reject("same_concept"); continue }
            guard !selected.contains(where: { NSIntersectionRange($0.range, unit.range).length > 0 }) else {
                reject("overlap"); continue
            }
            guard used + unit.nativeSourceTokens <= budget else { reject("remaining_budget"); continue }
            guard selected.count < 128 else { reject("selected_unit_limit"); continue }
            selected.append(unit); concepts.insert(unit.conceptID!); used += unit.nativeSourceTokens
        }
        selected.sort { $0.range.location < $1.range.location }
        // Density was applied once above. The established factory still checks
        // exact source/target scopes, identifiers, graphemes and required readings.
        // Its legacy smallest-unit fallback cannot exceed our preselected budget.
        let partial = SourceReferencePresentation.create(original: original, target: target, units: selected,
            density: 1, nativeSourceTokenCount: basis.count)
        let accepted = partial?.references ?? []
        if accepted.count != selected.count { rejected["presentation_rejected", default: 0] += selected.count-accepted.count }
        return .init(partial: partial, budget: budget, selectedConceptIDs: accepted.compactMap(\.conceptID),
            usedSourceTokens: accepted.reduce(0) { $0 + $1.nativeSourceTokens }, rejected: rejected)
    }
}
