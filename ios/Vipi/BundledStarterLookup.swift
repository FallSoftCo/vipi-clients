import Foundation
import VipiCore

/// Pair dispatch only. The original pack provenance and all permissions survive.
@MainActor enum BundledStarterLookup {
    static func provider() -> SourceUnitLookup? {
        let japanese = JapaneseStarterLookup.bundledIfPromoted()
        let swahili = SwahiliStarterLookup.promotionEnabled ? SwahiliStarterLookup.bundledIfPromoted() : nil
        let additional = allPairPromotionEnabled ? BundledSourceFrameCatalog.bundledProviders() : [:]
        return compose(japanese: japanese, swahili: swahili, candidates: additional)
    }

    /// Candidate promotion is intentionally separate from the shipped catalog.
    static let allPairPromotionEnabled = true

    /// Explicit candidate composition is available to isolated qualification.
    static func compose(japanese: SourceUnitLookup?, swahili: SourceUnitLookup?,
                        candidates: [String: SourceUnitLookup] = [:]) -> SourceUnitLookup? {
        guard !candidates.isEmpty else {
            guard let swahili else { return japanese }
            guard let japanese else { return swahili }
            return dispatch(japanese: japanese, swahili: swahili, candidates: [:])
        }
        return dispatch(japanese: japanese, swahili: swahili, candidates: candidates)
    }

    private static func dispatch(japanese: SourceUnitLookup?, swahili: SourceUnitLookup?,
                                 candidates: [String: SourceUnitLookup]) -> SourceUnitLookup {
        let candidateIdentity = candidates.keys.sorted().map { $0 + "\u{0}" + candidates[$0]!.identity }.joined(separator: "\u{0}")
        let identity = "starter-pairs-v1:" + JapaneseStarterLookup.digest(Data(
            ("en-ja\u{0}" + (japanese?.identity ?? "absent") + "\u{0}en-sw\u{0}" + (swahili?.identity ?? "absent") + (candidateIdentity.isEmpty ? "" : "\u{0}candidate\u{0}" + candidateIdentity)).utf8))
        return SourceUnitLookup(identity: identity) { context in
            let selected: SourceUnitLookup?
            if context.pair.source == "en" && context.pair.target == "ja" { selected = japanese }
            else if context.pair.source == "en" && context.pair.target == "sw" { selected = swahili }
            else { selected = candidates[context.pair.source + "-" + context.pair.target] }
            guard let selected else {
                return SourceLookupEvidence(original: context.original, source: context.pair.source,
                    target: context.pair.target, catalogIdentity: identity, partial: nil, recognitions: [])
            }
            let evidence = try await selected.resolve(context)
            guard evidence.validated(text: context.original, sourceLanguage: context.pair.source,
                targetLanguage: context.pair.target, identity: selected.identity) != nil else {
                throw SwahiliStarterLookup.Invalid.input
            }
            let result = SourceLookupEvidence(original: evidence.original, source: evidence.source,
                target: evidence.target, catalogIdentity: identity, partial: evidence.partial,
                recognitions: evidence.recognitions, eligiblePool: evidence.eligiblePool,
                nativeSourceTokenCount: evidence.nativeSourceTokenCount)
            guard result.validated(text: context.original, sourceLanguage: context.pair.source,
                targetLanguage: context.pair.target, identity: identity) != nil else {
                throw SwahiliStarterLookup.Invalid.input
            }
            return result
        }
    }
}
