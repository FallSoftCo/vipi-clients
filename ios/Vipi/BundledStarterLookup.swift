import Foundation
import VipiCore

/// Pair dispatch only. The original pack provenance and all permissions survive.
@MainActor enum BundledStarterLookup {
    static func provider() -> SourceUnitLookup? {
        let japanese = JapaneseStarterLookup.bundledIfPromoted()
        guard SwahiliStarterLookup.promotionEnabled else { return japanese }
        return compose(japanese: japanese, swahili: SwahiliStarterLookup.bundledIfPromoted())
    }

    /// Explicit candidate composition is available to isolated qualification.
    static func compose(japanese: SourceUnitLookup?, swahili: SourceUnitLookup?) -> SourceUnitLookup? {
        guard let swahili else { return japanese }
        guard let japanese else { return swahili }
        let identity = "starter-pairs-v1:" + JapaneseStarterLookup.digest(Data(
            ("en-ja\u{0}" + japanese.identity + "\u{0}en-sw\u{0}" + swahili.identity).utf8))
        return SourceUnitLookup(identity: identity) { context in
            let selected: SourceUnitLookup?
            if context.pair.source == "en" && context.pair.target == "ja" { selected = japanese }
            else if context.pair.source == "en" && context.pair.target == "sw" { selected = swahili }
            else { selected = nil }
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
                recognitions: evidence.recognitions)
            guard result.validated(text: context.original, sourceLanguage: context.pair.source,
                targetLanguage: context.pair.target, identity: identity) != nil else {
                throw SwahiliStarterLookup.Invalid.input
            }
            return result
        }
    }
}
