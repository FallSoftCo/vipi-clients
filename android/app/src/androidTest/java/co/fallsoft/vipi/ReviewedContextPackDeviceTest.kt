package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.security.MessageDigest

@RunWith(AndroidJUnit4::class)
class ReviewedContextPackDeviceTest {
    @Test fun signedReviewedContextsUseNativeIndexedLookup() {
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val root=File(context.filesDir,"reviewed-contexts-001")
        val receipt=File(context.filesDir,"reviewed-context-native-001.json");check(!receipt.exists())
        val buildBytes=File(root,"receipt.json").readBytes();val build=JSONObject(buildBytes.toString(Charsets.UTF_8))
        val pairs=build.getJSONArray("pairs");assertEquals(90,pairs.length())
        val key=File(root,"signing-public-key.der").readBytes()
        val keyID=pairs.getJSONObject(0).getString("key_id")
        val store=VocabularyPackStore(context,mapOf(keyID to key),VocabularyPackKind.REVIEWED_CONTEXT)
        repeat(pairs.length()) { index ->
            val pair=pairs.getJSONObject(index);val id=pair.getString("pack_id");val folder=File(root,id)
            val manifest=File(folder,"manifest.json").readBytes();val signature=File(folder,"manifest.sig").readBytes()
            val database=File(folder,"contexts.sqlite").readBytes()
            assertEquals(id,store.install(manifest,signature,database))
            assertTrue(store.entries(id,"unmatched context 729348").isEmpty())
            if (index==0) {
                fun rejects(action:()->Unit) {var rejected=false;try {action()}catch(_:Exception){rejected=true};assertTrue(rejected)}
                rejects{VocabularyPackStore(context,mapOf(keyID to key)).install(manifest,signature,database)}
                rejects{store.install(manifest,signature.copyOf().apply{this[lastIndex]=(this[lastIndex].toInt() xor 1).toByte()},database)}
                rejects{store.install(manifest,signature,database.copyOf().apply{this[lastIndex]=(this[lastIndex].toInt() xor 1).toByte()})}
            }
        }
        val results=JSONArray();var withMappings=0;var withImmersion=0
        for (name in listOf("phrase-observations-003.json","phrase-observations-005.json")) {
            val capture=JSONObject(File(context.filesDir,name).readText());assertTrue(capture.getBoolean("complete"))
            val rows=capture.getJSONArray("results")
            repeat(rows.length()) { index ->
                val row=rows.getJSONObject(index);val source=row.getString("source");val target=row.getString("target")
                val original=row.getString("original");val begin=System.nanoTime()
                val entries=store.entries("$source-$target",original)
                val result=LocalImmersion.align(original,row.getString("translation"),entries,1.0,source,target)
                val elapsed=(System.nanoTime()-begin)/1e6
                if(entries.isNotEmpty())withMappings++;if(result.spans.isNotEmpty())withImmersion++
                result.spans.forEach {span->
                    assertEquals(row.getInt("start"),span.start);assertEquals(row.getInt("end"),span.end)
                    if(target in setOf("ar","zh","ja","ko"))assertFalse(span.romanization.isNullOrEmpty())
                }
                results.put(JSONObject().put("case",row.getString("case")).put("source",source).put("target",target)
                    .put("mapping_count",entries.size).put("spans",JSONArray(result.spans.map {span->JSONObject()
                        .put("start",span.start).put("end",span.end).put("target",span.translated).put("reading",span.romanization ?: JSONObject.NULL)}))
                    .put("lookup_alignment_ms",elapsed))
            }
        }
        assertEquals(3582,results.length());assertEquals(3564,withMappings)
        val variant="Can we bring our books?"
        val entries=store.entries("en-es",variant)
        assertEquals("books",entries.single().source)
        assertTrue(store.entries("en-es","Can we book our flights?").isEmpty())
        store.remove("en-es");assertTrue(store.entries("en-es",variant).isEmpty())
        receipt.writeText(JSONObject().put("schema","vipi-reviewed-context-native-1").put("platform","Android")
            .put("build_sha256",MessageDigest.getInstance("SHA-256").digest(buildBytes).joinToString(""){"%02x".format(it)})
            .put("cases",results.length()).put("cases_with_mappings",withMappings).put("cases_with_immersion",withImmersion)
            .put("signed_pairs_installed",90).put("linguistic_acceptance",false).put("general_chat_integration",false)
            .put("results",results).toString(2))
    }
}
