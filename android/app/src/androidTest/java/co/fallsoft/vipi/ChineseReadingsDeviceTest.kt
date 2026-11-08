package co.fallsoft.vipi
import android.os.Debug
import android.os.SystemClock
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.MessageDigest

class ChineseReadingsDeviceTest {
    private fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
    @Test fun nativeReplayMatchesFrozenSwiftSelectionPiecesAndBounds() {
        val base=InstrumentationRegistry.getInstrumentation().targetContext
        fun input(name:String,hash:String):JSONObject { val bytes=File(base.filesDir,name).readBytes();assertEquals(hash,sha(bytes));return JSONObject(bytes.toString(Charsets.UTF_8)) }
        val reference=input("android-chinese-reference-r01.json","e219575e9ffab2f18111d7c05d180fad252d424f71a070918d17996802af8c9b")
        val resources=input("android-chinese-resource-inputs-r01.json","70eafa6fe19180ae286843bc8a393c5b7757314b2235879c7e21b2df22de8a83")
        val resourceReference=input("android-chinese-resource-reference-r01.json","82d8f78d6ed98ed24aced7077d6af27a57d28eda5ffd533bc12e09197f58aad2")
        val data=base.assets.open("readings/chinese-ordinary.json").use{it.readBytes()};assertEquals(ChineseReadings.DATA_SHA256,sha(data))
        val started=SystemClock.elapsedRealtimeNanos();val reader=ChineseReadings(data);val load=(SystemClock.elapsedRealtimeNanos()-started)/1e6
        assertTrue(runCatching{ChineseReadings(data.clone().apply{this[5]=(this[5].toInt() xor 1).toByte()})}.exceptionOrNull() is IllegalArgumentException)
        val rows=JSONArray();val checks=JSONArray();val report=JSONObject().put("complete",false).put("cases",rows).put("resources",checks)
            .put("load_ms",load).put("data_sha256",sha(data)).put("sdk",android.os.Build.VERSION.SDK_INT).put("new_models",0)
        val out=File(base.filesDir,"android-chinese-native-001.json");fun save()=out.writeText(report.toString(2))
        fun memory():Int{val info=Debug.MemoryInfo();Debug.getMemoryInfo(info);return info.totalPss};report.put("pss_before_kib",memory())
        fun equal(expected:JSONObject,value:ChineseReadings.Result,text:String) {
            assertEquals(if(expected.isNull("reading"))null else expected.getString("reading"),value.reading)
            val pieces=expected.getJSONArray("pieces");assertEquals(pieces.length(),value.pieces.size)
            for((i,p)in value.pieces.withIndex()){
                val e=pieces.getJSONObject(i);assertEquals(e.getInt("start_utf16"),p.startUTF16);assertEquals(e.getInt("end_utf16"),p.endUTF16)
                assertEquals(e.getString("source"),p.source);assertEquals(e.getString("reading"),p.reading)
                assertEquals(e.getBoolean("protected"),p.protected);assertEquals(e.getBoolean("converted"),p.converted)
                assertEquals(text.substring(p.startUTF16,p.endUTF16),p.source);if(p.protected)assertEquals(p.source,p.reading)
            }
            assertEquals(text,value.pieces.joinToString(""){it.source})
            val u=expected.getJSONArray("unresolved_utf16");assertEquals(u.length(),value.unresolved.size)
            for((i,r)in value.unresolved.withIndex()){assertEquals(u.getJSONArray(i).getInt(0),r.first);assertEquals(u.getJSONArray(i).getInt(1),r.last+1)}
        }
        try {
            val cases=reference.getJSONArray("cases");assertEquals(332,cases.length())
            for(i in 0 until cases.length()){
                val c=cases.getJSONObject(i);val text=c.getString("source");val row=JSONObject().put("id",c.getString("id"));rows.put(row)
                val start=SystemClock.elapsedRealtimeNanos();val raw=reader.resolve(text,false);val first=reader.resolve(text);val warm=reader.resolve(text)
                equal(c.getJSONObject("raw_parity"),raw,text);equal(c.getJSONObject("first"),first,text);equal(c.getJSONObject("warm"),warm,text);assertEquals(first,warm)
                row.put("first_reading",first.reading?:JSONObject.NULL).put("raw_and_guarded_exact",true).put("three_calls_ms",(SystemClock.elapsedRealtimeNanos()-start)/1e6)
                if(i%32==0)save()
            }
            val casesResource=resources.getJSONArray("cases");val expected=resourceReference.getJSONArray("rows");assertEquals(5,casesResource.length())
            for(i in 0 until casesResource.length()) for(pass in 0..1) {
                val c=casesResource.getJSONObject(i);val text=c.getString("text");val e=expected.getJSONObject(i*2+pass);val row=JSONObject().put("id",c.getString("id")).put("pass",pass);checks.put(row)
                val start=SystemClock.elapsedRealtimeNanos()
                if(c.getBoolean("expectInvalid")){assertTrue(runCatching{reader.resolve(text)}.exceptionOrNull() is IllegalArgumentException);row.put("status","invalid_input")}
                else {
                    val raw=reader.resolve(text,false);val value=reader.resolve(text)
                    assertEquals(e.getString("raw_reading_sequence_sha256"),sha(raw.pieces.joinToString("\u0000"){it.reading}.toByteArray()))
                    assertEquals(if(e.isNull("guarded_reading_sha256"))null else e.getString("guarded_reading_sha256"),value.reading?.let{sha(it.toByteArray())})
                    assertEquals(text,value.pieces.joinToString(""){it.source});assertTrue(value.pieces.filter{it.protected}.all{it.source==it.reading&&!it.converted})
                    row.put("status","resolved").put("exact_reference_hashes",true)
                }
                row.put("elapsed_ms",(SystemClock.elapsedRealtimeNanos()-start)/1e6);save()
            }
            // Java-specific regression: same language/literal policy, maximum
            // repeated separators that previously exhausted recursive regex.
            val separator="a-".repeat(8188)+"a 银";val raw=reader.resolve(separator);assertTrue(raw.reading!!.startsWith("a-".repeat(8188)+"a "))
            assertEquals(separator,raw.pieces.joinToString(""){it.source});report.put("java_repeated_identifier_guard",true).put("complete",true)
        }finally{report.put("pss_after_kib",memory());save()}
    }
    @Test fun bundledDefaultCacheAndAuthoredPriorityNeedNoModelDownload(): Unit=runBlocking(Dispatchers.Default){
        val base=InstrumentationRegistry.getInstrumentation().targetContext;val bytes=File(base.filesDir,"android-default-chinese-chat-plan-r01.json").readBytes()
        assertEquals("bcd53867f55988bc719140e14560ce359a6a77d8d295225e715176571b37ee37",sha(bytes));val cases=JSONObject(bytes.toString(Charsets.UTF_8)).getJSONArray("cases")
        val engine=ConversationImmersion(base,"en","zh",.25);val rows=JSONArray();val report=JSONObject().put("complete",false).put("cases",rows).put("default_producer",true)
        try{engine.checkDownloads();report.put("translation_model_installed",engine.ready)
            for(i in 0 until cases.length()){
                val c=cases.getJSONObject(i);val text=c.getString("text");val first=engine.reading(text)
                assertEquals(if(c.isNull("reading"))null else c.getString("reading"),first?.text)
                assertEquals(if(c.isNull("provenance"))null else c.getString("provenance"),first?.provenance?.name)
                assertSame(first,engine.reading(text));rows.put(JSONObject().put("id",c.getString("id")).put("reading",first?.text?:JSONObject.NULL).put("cached_identity",true))
            }
            engine.close();assertNull(engine.reading(cases.getJSONObject(0).getString("text")))
            val license=base.assets.open("legal/upstream/pinyin-pro-3.29.5-LICENSE.txt").use{it.readBytes()};assertEquals("824f6069c5a59b0c1650d0fb9f8d091866c6019eb761c8e658dfc03f001eabd2",sha(license))
            report.put("packaged_license_sha256",sha(license)).put("complete",true)
        }finally{engine.close();File(base.filesDir,"android-chinese-default-cache-001.json").writeText(report.toString(2))}
    }
}
