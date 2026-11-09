package co.fallsoft.vipi

import android.content.Context
import co.fallsoft.vipi.core.SourceLookupEvidence

/** Pair dispatch only; no new lexical permission, normalization or selection. */
internal object BundledStarterLookup {
    fun provider(context: Context, knownIDs: Set<String> = emptySet()): SourceLookupProvider? {
        val japanese = JapaneseStarterLookup.bundledIfPromoted(context, knownIDs)
        if (!SwahiliStarterLookup.PROMOTION_ENABLED) return japanese
        return compose(japanese, SwahiliStarterLookup.bundledIfPromoted(context, knownIDs))
    }

    /** Explicit candidate composition is only used by isolated qualification. */
    fun compose(japanese: SourceLookupProvider?, swahili: SourceLookupProvider?): SourceLookupProvider? {
        if (swahili == null) return japanese
        if (japanese == null) return swahili
        val identity = "starter-pairs-v1:" + JapaneseStarterLookup.sha(
            ("en-ja\u0000" + japanese.cacheIdentity + "\u0000en-sw\u0000" + swahili.cacheIdentity).toByteArray(Charsets.UTF_8))
        return object : SourceLookupProvider {
            override val cacheIdentity = identity
            override suspend fun lookup(original: String, source: String, target: String, density: Double): SourceLookupEvidence {
                val selected = when {
                    source == "en" && target == "ja" -> japanese
                    source == "en" && target == "sw" -> swahili
                    else -> null
                } ?: return SourceLookupEvidence(original, source, target, identity, null, emptyList())
                val evidence = selected.lookup(original, source, target, density)
                require(evidence.isValid(original, source, target, selected.cacheIdentity))
                return SourceLookupEvidence(evidence.original, evidence.source, evidence.target, identity,
                    evidence.partial, evidence.recognitions).also { require(it.isValid(original, source, target, identity)) }
            }
        }
    }
}
