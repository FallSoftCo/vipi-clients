package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.ImmersionSpan
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.security.MessageDigest

/** A small conversation development replay through the same bundled reader as chat.
 * Reused translations do not measure translator accuracy or population coverage. */
@RunWith(AndroidJUnit4::class)
class BundledConversationReplayDeviceTest {
    @Test fun selectedPairConversationReplay() {
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("vipiDedicatedEmulator") == "true")
        val revision = requireNotNull(args.getString("vipiBundledRun"))
        require(revision.matches(Regex("[0-9]{3}")))
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val input = File(context.filesDir, "bundled-conversation-cases.json")
        val expectedHash = requireNotNull(args.getString("vipiCasesSha"))
        require(expectedHash.matches(Regex("[a-f0-9]{64}")))
        val bytes = input.readBytes()
        assertEquals(expectedHash, MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) })
        val cases = JSONArray(bytes.toString(Charsets.UTF_8))
        val catalogHash = context.assets.open("lexical/catalog.json").use { stream ->
            MessageDigest.getInstance("SHA-256").digest(stream.readBytes()).joinToString("") { "%02x".format(it) }
        }
        val output = File(context.filesDir, "bundled-conversations-$revision.json")
        check(!output.exists())
        // Dedicated public-data scratch keeps this cross-pair replay from installing
        // every language in the user's selected-pair cache.
        val root = File(context.cacheDir, "bundled-conversation-replay-$revision")
        check(!root.exists())
        val baseline = BundledImmersionCatalog(context)
        val outcomes = JSONArray()
        val failures = JSONArray()
        val timings = JSONArray()
        var pair = ""
        fun spans(values: List<ImmersionSpan>): JSONArray = JSONArray().also { array ->
            values.forEach { s -> array.put(JSONObject().put("source",s.original).put("target",s.translated)
                .put("start",s.start).put("end",s.end).put("target_start",s.targetStart).put("target_end",s.targetEnd)
                .put("reading",s.romanization ?: JSONObject.NULL)) }
        }
        fun save(complete: Boolean) {
            output.writeText(JSONObject().put("schema","vipi-bundled-conversation-replay-1").put("run",revision)
                .put("complete",complete).put("cases_sha256",expectedHash).put("platform","android")
                .put("translation_reused",true).put("population_coverage_claim",false).put("bundled_catalog_sha256",catalogHash)
                .put("independent_semantic_acceptance",false).put("failures",failures)
                .put("pair_preparation",timings).put("outcomes",outcomes).toString())
        }
        try {
            val ordered=(0 until cases.length()).map{cases.getJSONObject(it)}.sortedBy { listOf(it.getString("source"),it.getString("target")).sorted().joinToString("-") }
            val lexical=BundledLexicalCatalog(context,root=root)
            for(row in ordered) {
                val source=row.getString("source");val target=row.getString("target")
                val nextPair=listOf(source,target).sorted().joinToString("-")
                if(nextPair!=pair) {
                    check(root.deleteRecursively())
                    val start=System.nanoTime()
                    check(lexical.prepare(source,target))
                    timings.put(JSONObject().put("pair",nextPair).put("elapsed_ms",(System.nanoTime()-start)/1e6)
                        .put("expanded_bytes",root.listFiles().orEmpty().sumOf{it.length()}))
                    pair=nextPair
                }
                val original=row.getString("original");val translation=row.getString("translation")
                val start=System.nanoTime()
                val diagnostics=mutableMapOf<String,Int>()
                val entries=lexical.entries(original,translation,source,target) { reason -> diagnostics[reason]=(diagnostics[reason] ?: 0)+1 }
                val result=baseline.result(original,translation,source,target,1.0,entries)
                val elapsed=(System.nanoTime()-start)/1e6
                val previous=baseline.result(original,translation,source,target,1.0)
                val retained=previous.spans.all{it in result.spans}
                if(!retained)failures.put(row.getString("id")+": lost starter span")
                if(row.has("forbidden_source") && result.spans.any {
                    it.original==row.getString("forbidden_source") && it.translated==row.getString("forbidden_target") &&
                        (!row.has("forbidden_source_start") || it.start==row.getInt("forbidden_source_start"))
                })failures.put(row.getString("id")+": known meaning/scope error")
                if(row.has("expected_source") && result.spans.none {
                    it.original==row.getString("expected_source") && it.translated==row.getString("expected_target")
                })failures.put(row.getString("id")+": missing retained mapping")
                assertEquals(original,result.original)
                assertEquals(original,result.speech(source,target,result.spans.map{it.id}.toSet()).joinToString(""){it.text})
                if(target in setOf("ar","zh","ja","ko"))assertTrue(result.spans.all{!it.romanization.isNullOrBlank()})
                outcomes.put(JSONObject().put("id",row.getString("id")).put("dataset",row.getString("dataset"))
                    .put("source",source).put("target",target).put("original",original).put("translation",translation)
                    .put("baseline_spans",spans(previous.spans)).put("combined_spans",spans(result.spans))
                    .put("elapsed_ms",elapsed).put("baseline_retained",retained).put("diagnostics",JSONObject(diagnostics as Map<*,*>)))
                if(outcomes.length()%10==0)save(false)
            }
            save(true)
            assertEquals(failures.toString(),0,failures.length())
        } finally { root.deleteRecursively() }
    }
}
