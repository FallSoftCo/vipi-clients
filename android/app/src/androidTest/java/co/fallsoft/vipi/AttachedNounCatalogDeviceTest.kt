package co.fallsoft.vipi

import android.database.sqlite.SQLiteDatabase
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Exercise the actual bundled catalog for every finite new attachment. */
@RunWith(AndroidJUnit4::class)
class AttachedNounCatalogDeviceTest {
    @Test fun everyListedAttachmentPreservesTheSurroundingNativeGrammar() {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val index=JSONObject(context.assets.open("immersion/catalog.json").bufferedReader().use { it.readText() })
        val catalog=BundledImmersionCatalog(context)
        val packs=index.getJSONArray("packs");var records=0;var cases=0;var unchanged=0;val directions=mutableSetOf<String>()
        for(i in 0 until packs.length()) {
            val pair=packs.getJSONObject(i).getString("id");val (source,target)=pair.split("-")
            val temporary=File.createTempFile("attached-noun-qa-",".sqlite",context.cacheDir)
            try {
                context.assets.open("immersion/$pair.sqlite").use { input -> temporary.outputStream().use { input.copyTo(it) } }
                SQLiteDatabase.openDatabase(temporary.path,null,SQLiteDatabase.OPEN_READONLY or SQLiteDatabase.NO_LOCALIZED_COLLATORS).use { db ->
                    fun forms(side:String,id:String):List<String> = db.rawQuery("SELECT input FROM ${side}_inputs WHERE mapping_id=? ORDER BY input",arrayOf(id)).use { cursor ->
                        buildList { while(cursor.moveToNext())add(cursor.getString(0)) }
                    }
                    db.rawQuery("SELECT id,payload FROM mappings WHERE id LIKE 'vipi-authored-r1:attached_noun_%' ORDER BY id",null).use { cursor ->
                        while(cursor.moveToNext()) {
                            val id=cursor.getString(0);val row=JSONObject(cursor.getString(1));val noun=row.getString("source");val replacement=row.getString("target")
                            val left=forms("source",id);val right=forms("target",id)
                            assertTrue(left.isNotEmpty() && right.isNotEmpty())
                            for(a in left)for(b in right) {
                                val original="$a.";val translation="$b."
                                val result=catalog.result(original,translation,source,target,1.0)
                                assertEquals(original,result.original);assertEquals(translation,result.translation)
                                assertEquals("$pair:$id:$a",original,result.speech(source,target,result.spans.map{it.id}.toSet()).joinToString(""){it.text})
                                if(noun.equals(replacement,ignoreCase=true) && target !in setOf("ar","zh","ja","ko")) {
                                    assertTrue(result.spans.isEmpty());unchanged++
                                } else {
                                    assertEquals("$pair:$id:$a -> $b",1,result.spans.size)
                                    assertEquals(noun,result.spans.single().original)
                                    assertEquals("$pair:$id:$a",original.replace(noun,replacement),result.speech(source,target).joinToString(""){it.text})
                                    if(target in setOf("ar","zh","ja","ko"))assertEquals(row.getString("reading"),result.spans.single().romanization)
                                }
                                cases++
                            }
                            records++;directions+=pair
                        }
                    }
                }
            }finally {check(temporary.delete())}
        }
        assertEquals(2551,records);assertEquals(38,directions.size);assertTrue(cases>records)
        val output=File(context.filesDir,"attached-noun-catalog-002.json");check(!output.exists())
        output.writeText(JSONObject().put("records",records).put("cases",cases).put("directions",directions.size)
            .put("unchanged_forms",unchanged).put("runtime_path","app-bundled-native-catalog")
            .put("independent_linguistic_acceptance",false).toString(2))
    }
}
