package co.fallsoft.vipi

import android.database.sqlite.SQLiteDatabase
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Synthetic scope fixtures: qualification of native windows and schema, not linguistic coverage. */
@RunWith(AndroidJUnit4::class)
class SideUnitFrameDeviceTest {
    private fun database(source:String,target:String,word:String,targetWord:String,suffix:String,reverse:Boolean):SQLiteDatabase {
        val db=SQLiteDatabase.create(null)
        db.execSQL("PRAGMA user_version=8")
        db.execSQL("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        db.execSQL("INSERT INTO metadata VALUES ('schema','vipi-reviewed-frame-3'),('context_policy','reviewed-bidirectional-side-unit-3')")
        db.execSQL("CREATE TABLE mappings(id TEXT PRIMARY KEY,payload TEXT NOT NULL)")
        db.execSQL("CREATE TABLE source_inputs(input TEXT,mapping_id TEXT)")
        db.execSQL("CREATE TABLE target_inputs(input TEXT,mapping_id TEXT)")
        val attached=JSONArray().put(JSONObject().put("focus",word)).put(JSONObject().put("literal",suffix))
        val unit=JSONArray().put(JSONObject().put("focus",targetWord))
        val payload=JSONObject().put("id","fixture").put("meaning","specific noun")
            .put("source_language",source).put("target_language",target)
            .put("source",if(reverse)targetWord else word).put("target",if(reverse)word else targetWord)
            .put("source_parts",if(reverse)unit else attached).put("target_parts",if(reverse)attached else unit)
            .put("reading",if(target=="ko")"chaek" else "").put("lexical_unit",false)
            .put("source_lexical_unit",reverse).put("target_lexical_unit",!reverse)
        db.execSQL("INSERT INTO mappings VALUES (?,?)",arrayOf("fixture",payload.toString()))
        db.execSQL("INSERT INTO source_inputs VALUES (?,?)",arrayOf(if(reverse)targetWord else word+suffix,"fixture"))
        db.execSQL("INSERT INTO target_inputs VALUES (?,?)",arrayOf(if(reverse)word+suffix else targetWord,"fixture"))
        return db
    }
    @Test fun nativeWindowsKeepKoreanParticlesAndSwahiliLocativesOutsideTheFlip() {
        data class Case(val language:String,val source:String,val target:String,val noun:String,val suffix:String,val translated:String)
        for(case in listOf(Case("ko","책을 가져왔어요.","I brought the book.","책","을","book"),
            Case("sw","Tutakutana shuleni.","We will meet at school.","shule","ni","school"))) {
            for(reverse in listOf(false,true)) {
                val source=if(reverse)"en" else case.language;val target=if(reverse)case.language else "en"
                val original=if(reverse)case.target else case.source;val translation=if(reverse)case.source else case.target
                database(source,target,case.noun,case.translated,case.suffix,reverse).use { db ->
                    fun entries(a:String=original,b:String=translation)=ReviewedFrameLookup.entries(db,a,b,source,target)
                    val result=LocalImmersion.align(original,translation,entries(),1.0,source,target)
                    assertEquals(1,result.spans.size)
                    val noun=if(reverse)case.translated else case.noun;val replacement=if(reverse)case.noun else case.translated
                    assertEquals(original.replace(noun,replacement),result.speech(source,target).joinToString(""){it.text})
                    if(target=="ko")assertEquals("chaek",result.spans.single().romanization)
                    assertTrue(entries("$original $original").isEmpty())
                    assertTrue(entries(b="$translation $translation").isEmpty())
                    if(!reverse)assertTrue(entries(original.replace(case.noun+case.suffix,(if(case.language=="ko")"공" else "ki")+case.noun+case.suffix)).isEmpty())
                    // New scope fields cannot be smuggled through the older policy.
                    db.execSQL("PRAGMA user_version=7")
                    db.execSQL("UPDATE metadata SET value='vipi-reviewed-frame-2' WHERE key='schema'")
                    db.execSQL("UPDATE metadata SET value='reviewed-bidirectional-phrase-and-unit-2' WHERE key='context_policy'")
                    var rejected=false;try { entries() }catch(_:IllegalArgumentException){rejected=true}
                    assertTrue(rejected)
                }
            }
        }
    }
}
