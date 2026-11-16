package co.fallsoft.vipi

import android.content.Context
import co.fallsoft.vipi.core.SourceLookupEvidence

/** Pair dispatch only; no new lexical permission, normalization or selection. */
internal object BundledStarterLookup {
    fun provider(context: Context, knownIDs: Set<String> = emptySet()): SourceLookupProvider? {
        val japanese = JapaneseStarterLookup.bundledIfPromoted(context, knownIDs)
        val swahili = if (SwahiliStarterLookup.PROMOTION_ENABLED) SwahiliStarterLookup.bundledIfPromoted(context, knownIDs) else null
        val additional = if (ALL_PAIR_PROMOTION_ENABLED) BundledSourceFrameCatalog.bundledProviders(context, knownIDs) else emptyMap()
        return composeProviders(japanese, swahili, additional)
    }

    const val ALL_PAIR_PROMOTION_ENABLED = true

    /** Explicit candidate composition is only used by isolated qualification. */
    fun compose(japanese: SourceLookupProvider?, swahili: SourceLookupProvider?,
        candidatePairs: Map<Pair<String, String>, SourceLookupProvider> = emptyMap()): SourceLookupProvider? {
        require(candidatePairs.isEmpty() || BuildConfig.DEBUG)
        return composeProviders(japanese, swahili, candidatePairs)
    }

    private fun composeProviders(japanese: SourceLookupProvider?, swahili: SourceLookupProvider?,
        candidatePairs: Map<Pair<String, String>, SourceLookupProvider>): SourceLookupProvider? {
        val supported = setOf("en", "es", "fr", "de", "it", "pt", "ar", "zh", "ja", "ko", "sw")
        require(candidatePairs.keys.all { (source, target) -> source in supported && target in supported && source != target })
        val candidates = candidatePairs.toMap()
        if (swahili == null && candidates.isEmpty()) return japanese
        if (japanese == null && candidates.isEmpty()) return swahili
        val identity = "starter-pairs-v1:" + JapaneseStarterLookup.sha(
            ("en-ja\u0000" + japanese?.cacheIdentity.orEmpty() + "\u0000en-sw\u0000" + swahili?.cacheIdentity.orEmpty() +
                candidates.toSortedMap(compareBy<Pair<String, String>> { it.first }.thenBy { it.second }).entries.joinToString("") { (pair, provider) ->
                    "\u0000${pair.first}-${pair.second}\u0000${provider.cacheIdentity}"
                }).toByteArray(Charsets.UTF_8))
        return object : SourceLookupProvider {
            override val cacheIdentity = identity
            override suspend fun lookup(original: String, source: String, target: String, density: Double): SourceLookupEvidence {
                val selected = when {
                    source == "en" && target == "ja" && japanese != null -> japanese
                    source == "en" && target == "sw" && swahili != null -> swahili
                    else -> candidates[source to target]
                } ?: return SourceLookupEvidence(original, source, target, identity, null, emptyList())
                val evidence = selected.lookup(original, source, target, density)
                require(evidence.isValid(original, source, target, selected.cacheIdentity))
                return SourceLookupEvidence(evidence.original, evidence.source, evidence.target, identity,
                    evidence.partial, evidence.recognitions, evidence.candidatePool, evidence.poolNativeSourceTokens).also { require(it.isValid(original, source, target, identity)) }
            }
        }
    }
}
