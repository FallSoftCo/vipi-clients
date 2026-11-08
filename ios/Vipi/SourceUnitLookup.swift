import Foundation
import VipiCore

/// Optional native integration seam, inactive unless an owner supplies a
/// verified catalog. No research file or default resource is loaded here.
@MainActor struct SourceUnitLookup {
    struct Context: Sendable {
        let original: String
        let pair: TranslationPair
        let density: Double
        let knownConceptIDs: Set<String>
    }
    /// Catalog version and content identity belong here. Replacing a provider
    /// requires a new conversation owner; changing its knowledge snapshot uses
    /// configure(), which invalidates pending work and all cached presentations.
    let identity: String
    typealias Resolver = @MainActor (Context) async throws -> SourceLookupEvidence
    /// Always return recognition, even when known/budget/target admission
    /// yields no partial. Empty recognition is an explicit no-match result.
    let resolve: Resolver
    init(identity: String, resolve: @escaping Resolver) {
        precondition(!identity.isEmpty)
        self.identity = identity; self.resolve = resolve
    }
}
