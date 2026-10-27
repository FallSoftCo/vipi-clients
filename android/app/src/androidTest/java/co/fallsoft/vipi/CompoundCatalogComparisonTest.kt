package co.fallsoft.vipi

import android.database.sqlite.SQLiteDatabase
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.security.MessageDigest

/** Diagnostic comparison of authored references, never a conversation precision score. */
@RunWith(AndroidJUnit4::class)
class CompoundCatalogComparisonTest {
    @Test fun compareQualifiedPreUnitBundleAgainstCurrentNativeCatalog() {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator")=="true")
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val baseline=File(context.filesDir,"bundled-frame-baseline-008")
        fun hash(bytes:ByteArray)=MessageDigest.getInstance("SHA-256").digest(bytes).joinToString(""){"%02x".format(it)}
        val indexBytes=File(baseline,"catalog.json").readBytes()
        check(hash(indexBytes)=="904f5c081ecb17394639d3a6dfebd7df6e12b5960ecbfe99df9b7eed9e787cba")
        val index=JSONObject(indexBytes.toString(Charsets.UTF_8));val rows=index.getJSONArray("references")
        val currentBytes=context.assets.open("immersion/catalog.json").use{it.readBytes()}
        val currentRows=JSONObject(currentBytes.toString(Charsets.UTF_8)).getJSONArray("references")
        val currentReferences=(0 until currentRows.length()).map{currentRows.getJSONObject(it)}
            .associate { (it.getString("pair") to it.getString("original")) to it.getString("translation") }
        assertEquals(currentRows.length(),currentReferences.size)
        repeat(rows.length()) { i -> val row=rows.getJSONObject(i)
            assertEquals("Existing whole references must remain unchanged",row.getString("translation"),
                currentReferences[row.getString("pair") to row.getString("original")])
        }
        for((group,suffix) in listOf("packs" to "","contexts" to "-contexts")) {
            val files=index.getJSONArray(group)
            repeat(files.length()) {i->val item=files.getJSONObject(i)
                assertEquals(item.getString("sha256"),hash(File(baseline,item.getString("id")+suffix+".sqlite").readBytes()))}
        }
        val output=File(context.filesDir,"compound-catalog-comparison-012.json");check(!output.exists())
        val catalog=BundledImmersionCatalog(context);val changes=JSONArray()
        var beforeCount=0;var afterCount=0;var lost=0;var gained=0
        val grouped=(0 until rows.length()).map{rows.getJSONObject(it)}.groupBy{it.getString("pair")}
        for((pair,cases) in grouped) {
            val (source,target)=pair.split("-")
            SQLiteDatabase.openDatabase(File(baseline,"$pair.sqlite").path,null,SQLiteDatabase.OPEN_READONLY).use {frame->
                SQLiteDatabase.openDatabase(File(baseline,"$pair-contexts.sqlite").path,null,SQLiteDatabase.OPEN_READONLY).use {exact->
                    for(row in cases) {
                        val original=row.getString("original");val translated=row.getString("translation")
                        val entries=ReviewedFrameLookup.entries(frame,original,translated,source,target)+ReviewedContextLookup.entries(exact,original,source,target)
                        val before=LocalImmersion.align(original,translated,entries,1.0,source,target)
                        val after=catalog.result(original,translated,source,target,1.0)
                        beforeCount+=before.spans.size;afterCount+=after.spans.size
                        if(before.spans.isNotEmpty() && after.spans.isEmpty())lost++
                        if(before.spans.isEmpty() && after.spans.isNotEmpty())gained++
                        if(before.spans!=after.spans)changes.put(JSONObject().put("pair",pair).put("original",original).put("translation",translated)
                            .put("before",JSONArray(before.spans.map{JSONObject().put("original",it.original).put("target",it.translated)}))
                            .put("after",JSONArray(after.spans.map{JSONObject().put("original",it.original).put("target",it.translated)})))
                    }
                }
            }
        }
        output.writeText(JSONObject().put("schema","vipi-authored-compound-comparison-1").put("baseline_catalog_sha256",hash(indexBytes))
            .put("current_catalog_sha256",hash(currentBytes)).put("references",rows.length()).put("before_spans",beforeCount)
            .put("after_spans",afterCount).put("lost_messages",lost).put("gained_messages",gained)
            .put("independent_linguistic_acceptance",false).put("changes",changes).toString(2))
        assertEquals("Equivalent assessed senses must not erase previously working messages",0,lost)
    }
}
