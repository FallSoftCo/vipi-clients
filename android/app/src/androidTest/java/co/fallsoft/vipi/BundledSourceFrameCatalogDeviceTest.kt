package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.File
import java.io.InputStream

class BundledSourceFrameCatalogDeviceTest {
    @Test fun pinnedBundledDirectionsPreserveKnowledgeAndFailClosed() = runBlocking {
        val inst = InstrumentationRegistry.getInstrumentation()
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = inst.targetContext
        val promoted = BundledStarterLookup.ALL_PAIR_PROMOTION_ENABLED
        val output = File(context.filesDir, "bundled-loader-${if (promoted) "on" else "off"}-001.json"); check(!output.exists())
        val baseline = BundledStarterLookup.compose(JapaneseStarterLookup.bundledIfPromoted(context), SwahiliStarterLookup.bundledIfPromoted(context))
        if (promoted) assertNotEquals(baseline?.cacheIdentity, BundledStarterLookup.provider(context)?.cacheIdentity)
        else assertEquals(baseline?.cacheIdentity, BundledStarterLookup.provider(context)?.cacheIdentity)
        val index = context.assets.open("immersion/${BundledSourceFrameCatalog.INDEX_FILE}").use { it.readBytes() }
        assertEquals(BundledSourceFrameCatalog.INDEX_BYTES, index.size)
        val entries = JSONObject(index.toString(Charsets.UTF_8)).getJSONArray("entries")
        val fixtures = JSONObject(File(context.filesDir, "all-pair-starter-candidate-r02/native-fixtures.json").readText()).getJSONArray("cases")
        val knownID = "candidate-common:needs_phone_charger"
        val providers = BundledSourceFrameCatalog.bundledProviders(context, emptySet())
        val knownProviders = BundledSourceFrameCatalog.bundledProviders(context, setOf(knownID))
        assertEquals(108, providers.size); assertEquals(108, knownProviders.size)
        assertFalse(providers.containsKey("en" to "ja")); assertFalse(providers.containsKey("en" to "sw"))
        val captured = JSONArray()
        for ((pair, provider) in providers) {
            val row = (0 until fixtures.length()).map { fixtures.getJSONObject(it) }.first {
                it.getString("pair") == "${pair.first}-${pair.second}" && it.getString("concept_id") == knownID
            }
            val original = row.getString("original")
            val evidence = provider.lookup(original, pair.first, pair.second, 0.5)
            assertTrue(evidence.isValid(original, pair.first, pair.second, provider.cacheIdentity))
            val span = requireNotNull(evidence.partial?.spans?.firstOrNull { it.original == row.getString("expected_source") })
            assertEquals(row.getString("expected_target"), span.translated)
            assertEquals(row.getString("reading"), span.romanization.orEmpty())
            val known = requireNotNull(knownProviders[pair]); assertNotEquals(provider.cacheIdentity, known.cacheIdentity)
            val suppressed = known.lookup(original, pair.first, pair.second, 0.5)
            assertFalse(suppressed.partial?.spans?.any { it.original == row.getString("expected_source") } ?: false)
            captured.put(JSONObject().put("pair", "${pair.first}-${pair.second}").put("target", span.translated)
                .put("reading", span.romanization ?: JSONObject.NULL).put("known_suppressed", true))
        }
        val first = entries.getJSONObject(0); val pair = first.getString("source") to first.getString("target")
        val row = (0 until fixtures.length()).map { fixtures.getJSONObject(it) }.first { it.getString("pair") == first.getString("pair") && it.getString("concept_id") == knownID }
        val reads = mutableListOf<String>()
        val streams: (String) -> InputStream = { name -> reads.add(name); context.assets.open("immersion/$name") }
        val lazy = BundledSourceFrameCatalog.qualificationProviders(context, index, openAsset = streams)
        assertTrue(reads.isEmpty())
        lazy.getValue(pair).lookup(row.getString("original"), pair.first, pair.second, 0.5)
        assertEquals(setOf(first.getString("file"), first.getString("manifest_file")), reads.toSet()); assertEquals(2, reads.size)
        lazy.getValue(pair).lookup(row.getString("original"), pair.first, pair.second, 0.5); assertEquals(2, reads.size)
        var corruptReads = 0
        val corrupt = BundledSourceFrameCatalog.qualificationProviders(context, index, openAsset = { name ->
            corruptReads++
            val bytes = context.assets.open("immersion/$name").use { it.readBytes() }
            if (name == first.getString("file")) bytes[0] = (bytes[0].toInt() xor 1).toByte()
            ByteArrayInputStream(bytes)
        })
        repeat(2) { assertNull(corrupt.getValue(pair).lookup(row.getString("original"), pair.first, pair.second, 0.5).partial) }
        assertEquals(1, corruptReads)
        var rejected = false
        try { BundledSourceFrameCatalog.qualificationProviders(context, index.copyOf().apply { this[0] = (this[0].toInt() xor 1).toByte() }, openAsset = streams) }
        catch (_: IllegalArgumentException) { rejected = true }
        assertTrue(rejected)
        output.writeText(JSONObject().put("complete", true).put("promotion", promoted)
            .put("index_sha256", JapaneseStarterLookup.sha(index)).put("pairs", captured)
            .put("lazy_selected_pair_only", true).put("corrupt_pack_abstained_and_cached", true)
            .put("corrupt_index_rejected", true).put("off_baseline_identity_unchanged", !promoted).toString(2))
    }
}
