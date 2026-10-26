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

internal data class FrameQAConfiguration(val root:String,val run:String,val capture:String,val conversationProbe:Boolean=false) {
    companion object {
        fun read(files:File):FrameQAConfiguration {
            val config=JSONObject(File(files,"frame-qa.json").readText())
            val root=config.getString("pack_root");val run=config.getString("run_id");val capture=config.getString("capture_file")
            require(root.matches(Regex("reviewed-frames-[0-9]{3}")) && run.matches(Regex("[0-9]{3}")) && capture.matches(Regex("phrase-observations-[0-9]{3}\\.json")))
            return FrameQAConfiguration(root,run,capture,config.optBoolean("conversation_probe",false))
        }
    }
}

@RunWith(AndroidJUnit4::class)
class ReviewedFramePackDeviceTest {
    @Test fun signedFramesBindBothSidesAcrossNativeLanguages() {
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        for(apostrophe in listOf("'","’"))assertEquals(listOf(5 until 25),ReviewedFrameLookup.windows("🙂 J${apostrophe}écoute de la musique.","fr")?.get("écoute de la musique"))
        assertFalse(ReviewedFrameLookup.windows("O’Neill arrive.","fr")?.containsKey("Neill") ?: true)
        assertFalse(ReviewedFrameLookup.windows("l’orange","en")?.containsKey("orange") ?: true)
        val config=FrameQAConfiguration.read(context.filesDir)
        val root=File(context.filesDir,config.root);val output=File(context.filesDir,"reviewed-frame-native-${config.run}.json")
        check(!output.exists())
        fun sha(bytes:ByteArray)=MessageDigest.getInstance("SHA-256").digest(bytes).joinToString(""){"%02x".format(it)}
        val buildBytes=File(root,"receipt.json").readBytes();val build=JSONObject(buildBytes.toString(Charsets.UTF_8));val pairs=build.getJSONArray("pairs")
        val key=File(root,"signing-public-key.der").readBytes();val keyID=pairs.getJSONObject(0).getString("key_id")
        val store=VocabularyPackStore(context,mapOf(keyID to key),VocabularyPackKind.REVIEWED_FRAME)
        repeat(pairs.length()) {index->
            val id=pairs.getJSONObject(index).getString("pack_id");val folder=File(root,id)
            val manifest=File(folder,"manifest.json").readBytes();val signature=File(folder,"manifest.sig").readBytes();val database=File(folder,"frames.sqlite").readBytes()
            assertEquals(id,store.install(manifest,signature,database))
            if(index==0) {
                fun rejects(action:()->Unit) {var rejected=false;try{action()}catch(_:Exception){rejected=true};assertTrue(rejected)}
                for(kind in listOf(VocabularyPackKind.VOCABULARY,VocabularyPackKind.REVIEWED_CONTEXT))rejects{VocabularyPackStore(context,mapOf(keyID to key),kind).install(manifest,signature,database)}
                rejects{store.install(manifest,signature.copyOf().apply{this[lastIndex]=(this[lastIndex].toInt() xor 1).toByte()},database)}
                rejects{store.install(manifest,signature,database.copyOf().apply{this[lastIndex]=(this[lastIndex].toInt() xor 1).toByte()})}
            }
        }
        val fixtureBytes=File(root,"native-fixture.json").readBytes();val rows=JSONObject(fixtureBytes.toString(Charsets.UTF_8)).getJSONArray("rows");val results=JSONArray()
        repeat(rows.length()) {index->
            val row=rows.getJSONObject(index);val source=row.getString("source_language");val target=row.getString("target_language");val id="$source-$target"
            val original="🙂 "+row.getString("source_context")+" 🙂";val translation="🙂 "+row.getString("target_context")+" 🙂"
            val word=row.getString("source");val targetWord=row.getString("target");val caseID=row.getString("logical_id")
            val begin=System.nanoTime();val entries=store.entries(id,original,translation)
            val result=LocalImmersion.align(original,translation,entries,1.0,source,target);val elapsed=(System.nanoTime()-begin)/1e6
            val expected=if(word.equals(targetWord,ignoreCase=true) && target !in setOf("ar","zh","ja","ko"))0 else 1
            assertEquals(caseID,1,entries.size);assertEquals(caseID,expected,result.spans.size)
            result.spans.forEach{span->
                assertEquals(caseID,original.indexOf(word),span.start);assertEquals(caseID,original.indexOf(word)+word.length,span.end)
                assertEquals(caseID,translation.indexOf(targetWord),span.targetStart);assertEquals(caseID,targetWord,span.translated)
                assertEquals(caseID,original.substring(0,span.start)+targetWord+original.substring(span.end),result.speech(source,target).joinToString(""){it.text})
                if(target in setOf("ar","zh","ja","ko"))assertFalse(span.romanization.isNullOrEmpty())
            }
            assertTrue(store.entries(id,original).isEmpty());assertTrue(store.entries(id,original,"unmatched 348273").isEmpty())
            assertTrue(caseID,store.entries(id,"$original $original",translation).isEmpty())
            assertTrue(caseID,store.entries(id,original,"$translation $translation").isEmpty())
            results.put(JSONObject().put("case",caseID).put("source",source).put("target",target).put("mapping_count",entries.size).put("span_count",result.spans.size).put("lookup_alignment_ms",elapsed))
        }
        val original="I am reading a book now.";val translation="Estoy leyendo un libro ahora. Otro libro."
        assertEquals(1,LocalImmersion.align(original,translation,store.entries("en-es",original,translation),1.0,"en","es").spans.size)
        val code="```\n$original\n```"
        assertTrue(LocalImmersion.align(code,translation,store.entries("en-es",code,translation),1.0,"en","es").spans.isEmpty())
        assertNull(ReviewedFrameLookup.windows("word ".repeat(1000),"en"))
        assertFalse(ReviewedFrameLookup.windows("reading. a book","en")!!.containsKey("reading. a book"))
        store.remove("en-es");assertTrue(store.entries("en-es",original,translation).isEmpty())
        assertEquals(90,pairs.length());assertEquals(build.getInt("records"),results.length())
        output.writeText(JSONObject().put("schema","vipi-reviewed-frame-native-1").put("platform","Android").put("cases",results.length())
            .put("build_sha256",sha(buildBytes)).put("fixture_sha256",sha(fixtureBytes)).put("reference_translations",true)
            .put("linguistic_acceptance",false).put("general_chat_integration",false).put("results",results).toString(2))
    }
}
