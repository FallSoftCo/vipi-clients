package co.fallsoft.vipi

import android.content.Context
import co.fallsoft.vipi.core.SourceLookupEvidence
import org.json.JSONObject
import java.io.InputStream

/** Immutable app assets for the additional 108 directions; loading never grants promotion. */
internal class BundledSourceFrameCatalog private constructor(
    context: Context,
    indexBytes: ByteArray,
    knownIDs: Set<String>,
    private val openAsset: (String) -> InputStream
) {
    companion object {
        const val INDEX_FILE = "all-pair-source-catalog-001.json"
        const val INDEX_BYTES = 35_807
        const val INDEX_SHA256 = "16b2198d52dfd0eb780e56669ce7863ae64d8521c960ed902484144917a98e7a"
        private val languages = setOf("en", "es", "fr", "de", "it", "pt", "ar", "zh", "ja", "ko", "sw")
        private fun pinnedRead(open: (String) -> InputStream, file: String, size: Int, maximum: Int, sha: String): ByteArray {
            require(size in 1..maximum && sha.matches(Regex("[a-f0-9]{64}")))
            val bytes = ByteArray(size)
            open(file).use { input ->
                var offset = 0
                while (offset < size) {
                    val count = input.read(bytes, offset, size - offset)
                    require(count > 0); offset += count
                }
                require(input.read() == -1)
            }
            require(JapaneseStarterLookup.sha(bytes) == sha)
            return bytes
        }
        fun bundledProviders(context: Context, knownIDs: Set<String>): Map<Pair<String, String>, SourceLookupProvider> = runCatching {
            val open: (String) -> InputStream = { context.assets.open("immersion/$it") }
            BundledSourceFrameCatalog(context, pinnedRead(open, INDEX_FILE, INDEX_BYTES, 131_072, INDEX_SHA256), knownIDs, open).providers()
        }.getOrElse { emptyMap() }

        /** Isolated instrumentation can substitute streams, never a release filesystem root. */
        fun qualificationProviders(context: Context, indexBytes: ByteArray, knownIDs: Set<String> = emptySet(),
            openAsset: (String) -> InputStream): Map<Pair<String, String>, SourceLookupProvider> {
            check(BuildConfig.DEBUG)
            return BundledSourceFrameCatalog(context, indexBytes, knownIDs, openAsset).providers()
        }
    }
    private data class Entry(val source: String, val target: String, val file: String, val bytes: Int, val sha: String,
        val manifestFile: String, val manifestBytes: Int, val manifestSHA: String) {
        val pair get() = source to target
    }
    private val known = knownIDs.toSet()
    private val binding = JapaneseStarterLookup.sha((INDEX_SHA256 + "\u0000" + known.sorted().joinToString("\u0000")).toByteArray(Charsets.UTF_8))
    private val catalog = BundledImmersionCatalog(context)
    private val entries: List<Entry>
    private val loaded = mutableMapOf<Pair<String, String>, SourceLookupProvider?>()
    init {
        require(indexBytes.size == INDEX_BYTES && JapaneseStarterLookup.sha(indexBytes) == INDEX_SHA256)
        val index = JSONObject(indexBytes.toString(Charsets.UTF_8))
        require(index.getString("schema") == "vipi-bundled-source-frame-index-1")
        val rows = index.getJSONArray("entries"); require(rows.length() == 108)
        entries = (0 until rows.length()).map { offset ->
            val row = rows.getJSONObject(offset); val source = row.getString("source"); val target = row.getString("target")
            val pair = "$source-$target"
            require(source in languages && target in languages && source != target && pair !in setOf("en-ja", "en-sw") && row.getString("pair") == pair)
            val file = row.getString("file"); val manifest = row.getString("manifest_file")
            require(file.matches(Regex("source-frames-$pair-[0-9]{3}\\.json")) && manifest == "source-frames-$pair-catalog.json")
            val bytes = row.getLong("bytes"); val manifestBytes = row.getLong("manifest_bytes")
            require(bytes in 1..1_048_576L && manifestBytes in 1..8_192L)
            val sha = row.getString("sha256"); val manifestSHA = row.getString("manifest_sha256")
            require(listOf(sha, manifestSHA).all { it.matches(Regex("[a-f0-9]{64}")) })
            Entry(source, target, file, bytes.toInt(), sha, manifest, manifestBytes.toInt(), manifestSHA)
        }
        require(entries.map { it.pair }.toSet().size == 108)
    }
    private fun load(entry: Entry): SourceLookupProvider? = synchronized(loaded) {
        if (loaded.containsKey(entry.pair)) return@synchronized loaded[entry.pair]
        val provider = runCatching {
            val bytes = pinnedRead(openAsset, entry.file, entry.bytes, 1_048_576, entry.sha)
            val manifest = pinnedRead(openAsset, entry.manifestFile, entry.manifestBytes, 8_192, entry.manifestSHA)
            require(JSONObject(manifest.toString(Charsets.UTF_8)).getString("file") == entry.file)
            val baseline = object : SourceLookupProvider {
                override val cacheIdentity = "bundled-source-empty-v1:$binding:${entry.source}-${entry.target}"
                override suspend fun lookup(original: String, source: String, target: String, density: Double) =
                    SourceLookupEvidence(original, source, target, cacheIdentity, null, emptyList())
            }
            SourceFrameLookup(bytes, manifest, entry.target, baseline.cacheIdentity, entry.source)
                .provider(baseline, known, { emptyList() }, catalog)
        }.getOrNull()
        loaded[entry.pair] = provider
        provider
    }
    private fun providers(): Map<Pair<String, String>, SourceLookupProvider> = entries.associate { entry ->
        entry.pair to object : SourceLookupProvider {
            override val cacheIdentity = "bundled-source-pair-v2:$binding:${entry.source}-${entry.target}"
            override suspend fun lookup(original: String, source: String, target: String, density: Double): SourceLookupEvidence = lookupMode(original, source, target, density, false)
            override suspend fun lookupForFull(original: String, source: String, target: String, density: Double): SourceLookupEvidence = lookupMode(original, source, target, density, true)
            private suspend fun lookupMode(original: String, source: String, target: String, density: Double, full: Boolean): SourceLookupEvidence {
                if (source != entry.source || target != entry.target)
                    return SourceLookupEvidence(original, source, target, cacheIdentity, null, emptyList())
                val provider = load(entry) ?: return SourceLookupEvidence(original, source, target, cacheIdentity, null, emptyList())
                val evidence = if (full) provider.lookupForFull(original, source, target, density) else provider.lookup(original, source, target, density)
                require(evidence.isValid(original, source, target, provider.cacheIdentity))
                return SourceLookupEvidence(original, source, target, cacheIdentity, evidence.partial, evidence.recognitions, evidence.candidatePool, evidence.poolNativeSourceTokens)
                    .also { require(it.isValid(original, source, target, cacheIdentity)) }
            }
        }
    }
}
