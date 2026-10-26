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

/** Replay actual model output, never substitute authored target references. */
@RunWith(AndroidJUnit4::class)
class FrameCaptureDeviceTest {
    @Test fun evaluateCapturedTranslationsWithSignedFrames() {
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val config=FrameQAConfiguration.read(context.filesDir)
        val root=File(context.filesDir,config.root);val output=File(context.filesDir,"frame-capture-native-${config.run}.json");check(!output.exists())
        fun sha(bytes:ByteArray)=MessageDigest.getInstance("SHA-256").digest(bytes).joinToString(""){"%02x".format(it)}
        val captureBytes=File(context.filesDir,config.capture).readBytes();val capture=JSONObject(captureBytes.toString(Charsets.UTF_8));assertTrue(capture.getBoolean("complete"))
        val rows=capture.getJSONArray("results");val fixture=JSONObject(File(root,"native-fixture.json").readText()).getJSONArray("rows")
        val expected=(0 until fixture.length()).associate {fixture.getJSONObject(it).let{r->r.getString("logical_id") to r}}
        if(!config.conversationProbe)assertEquals(expected.size,rows.length())
        assertEquals(capture.getInt("cases_expected"),rows.length());assertEquals(capture.getInt("cases_completed"),rows.length())
        assertEquals(rows.length(),(0 until rows.length()).map{rows.getJSONObject(it).let{r->listOf(r.getString("case"),r.getString("source"),r.getString("target"))}}.toSet().size)
        val buildBytes=File(root,"receipt.json").readBytes();val pairs=JSONObject(buildBytes.toString(Charsets.UTF_8)).getJSONArray("pairs")
        val key=File(root,"signing-public-key.der").readBytes();val keyID=pairs.getJSONObject(0).getString("key_id")
        val store=VocabularyPackStore(context,mapOf(keyID to key),VocabularyPackKind.REVIEWED_FRAME)
        repeat(pairs.length()){val folder=File(root,pairs.getJSONObject(it).getString("pack_id"));store.install(File(folder,"manifest.json").readBytes(),File(folder,"manifest.sig").readBytes(),File(folder,"frames.sqlite").readBytes())}
        val results=JSONArray()
        repeat(rows.length()){index->
            val row=rows.getJSONObject(index)
            val original=row.getString("original");val translation=row.getString("translation");val source=row.getString("source");val target=row.getString("target")
            assertEquals("executed",row.getString("status"))
            if(!config.conversationProbe){
                val reference=expected.getValue(row.getString("case"));assertEquals(reference.getString("source_context"),original)
                assertEquals(reference.getString("source_language"),source);assertEquals(reference.getString("target_language"),target)
            }
            val begin=System.nanoTime();val entries=store.entries("$source-$target",original,translation)
            val result=LocalImmersion.align(original,translation,entries,1.0,source,target);val elapsed=(System.nanoTime()-begin)/1e6
            if(!config.conversationProbe)result.spans.forEach{span->assertEquals(row.getInt("start"),span.start);assertEquals(row.getInt("end"),span.end)}
            results.put(JSONObject().put("case",row.getString("case")).put("source",source).put("target",target)
                .put("original",original).put("translation",translation).put("mapping_count",entries.size).put("lookup_alignment_ms",elapsed)
                .put("spans",JSONArray(result.spans.map{span->JSONObject().put("start",span.start).put("end",span.end).put("targetStart",span.targetStart).put("targetEnd",span.targetEnd).put("original",span.original).put("translated",span.translated).put("reading",span.romanization ?: JSONObject.NULL)})))
        }
        output.writeText(JSONObject().put("schema",if(config.conversationProbe)"vipi-frame-conversation-1" else "vipi-frame-capture-1").put("platform","Android").put("cases",results.length())
            .put("translation_capture_sha256",sha(captureBytes)).put("build_sha256",sha(buildBytes))
            .put("evidence","native frame lookup on retained actual ML Kit translations; not new model execution")
            .put("linguistic_acceptance",false).put("general_chat_integration",false).put("results",results).toString(2))
    }
}
