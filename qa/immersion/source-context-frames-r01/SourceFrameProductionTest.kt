package co.fallsoft.vipi
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.*
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test
import android.os.SystemClock
import java.io.File

class SourceFrameProductionTest {
 private class NoTranslation:LanguageTranslation {
  override suspend fun prepare(source:String,target:String,cellularAllowed:Boolean)=error("No model calls")
  override suspend fun translate(text:String,source:String,target:String):String=error("No translation calls")
  override fun close(){}
 }
 @Test fun bundledProductionRoute()=runBlocking {
  val args=InstrumentationRegistry.getArguments();org.junit.Assume.assumeTrue(args.getString("vipiFrameProduction")=="true");check(args.getString("vipiDedicatedEmulator")=="true")
  check(SourceFrameLookup.PROMOTION_ENABLED)
  val context=InstrumentationRegistry.getInstrumentation().targetContext;val dir=context.filesDir
  val manifest=JSONObject(File(dir,"manifest.json").readText());for(n in manifest.keys())assertEquals(manifest.getString(n),JapaneseStarterLookup.sha(File(dir,n).readBytes()))
  val prior=File(dir,"prior-android-routing.jsonl").readLines().filter{it.isNotBlank()}.map{JSONObject(it)};assertEquals(656,prior.size)
  var rejected=0
  for(target in listOf("ja","sw")) {
   val meta=context.assets.open("immersion/source-frames-en-$target-catalog.json").use{it.readBytes()};val m=JSONObject(meta.toString(Charsets.UTF_8));val bytes=context.assets.open("immersion/"+m.getString("file")).use{it.readBytes()}
   SourceFrameLookup(bytes,meta,target,"baseline-control")
   fun reject(label:String,b:ByteArray,mm:ByteArray,t:String=target){assertTrue(label,runCatching{SourceFrameLookup(b,mm,t,"baseline-control")}.isFailure);rejected++}
   reject("hash",bytes+byteArrayOf(32),meta)
   reject("wrong pair",bytes,meta,if(target=="ja")"sw" else "ja")
   for(change in listOf("permission","focus")+if(target=="ja")listOf("reading")else emptyList()) {
    val p=JSONObject(bytes.toString(Charsets.UTF_8));val first=p.getJSONArray("patterns").getJSONObject(0)
    when(change){"permission"->first.put("source_only_permission",false);"focus"->first.getJSONArray("variants").getJSONObject(0).put("focus_utf16",JSONArray(listOf(0,1)));"reading"->first.put("reading","")}
    val b=p.toString().toByteArray(Charsets.UTF_8);val mm=JSONObject(meta.toString(Charsets.UTF_8)).put("sha256",JapaneseStarterLookup.sha(b)).put("bytes",b.size).toString().toByteArray(Charsets.UTF_8);reject(change,b,mm)
   }
  }
  val output=File(dir,"production-output.jsonl");check(!output.exists());val started=SystemClock.elapsedRealtime();var rows=0;var corrected=0
  for(p in prior){
   val original=p.getString("source");val target=p.getString("pair").removePrefix("en-");val density=p.getDouble("density");val ka=p.getJSONArray("known_ids");val known=(0 until ka.length()).map{ka.getString(it)}.toSet()
   val expectedRoute=p.getJSONObject("route").getJSONObject("candidate");val expected=JSONArray(expectedRoute.getJSONArray("spans").toString())
   if(target=="sw" && p.getString("routing_branch")=="reference_miss_frame_evidence") {
    val refs=p.getJSONObject("candidate").getJSONArray("references")
    for(i in 0 until expected.length())for(j in 0 until refs.length()) {
     val e=expected.getJSONObject(i);val r=refs.getJSONObject(j)
     if(r.getJSONArray("scope").toString()==e.getJSONArray("source_utf16").toString())for((id,face) in mapOf("frame-4dc1128ff5c7283136d7125c" to "sherehe","frame-43431e9665d734366a927b81" to "nambari ya simu"))if(r.getString("reference").endsWith(":"+id)){e.put("target",face);corrected++}
    }
   }
   // Actual default factory: no source lookup/provider/target/span injection.
   val owner=ConversationImmersion(context,"en",target,density,translator=NoTranslation(),qaModelsReady=false,sourceKnownConceptIDs=known)
   try {
    val id="production-$rows";owner.selectInputLanguage(id,"en");val result=owner.presentation(original,"en",id);val spans=result?.spans?:emptyList()
    assertEquals("row $rows",expected.length(),spans.size)
    for((i,s) in spans.withIndex()){val e=expected.getJSONObject(i);assertEquals(e.getString("source"),s.original);assertEquals(e.getString("target"),s.translated);assertEquals(if(e.isNull("reading"))null else e.getString("reading"),s.romanization);assertEquals(e.getJSONArray("source_utf16").toString(),JSONArray(listOf(s.start,s.end)).toString())}
    assertEquals(0,requireNotNull(owner.lastOutcome).localTranslationCalls);assertEquals(if(expectedRoute.isNull("origin"))null else expectedRoute.getString("origin"),owner.lastOutcome?.origin?.name)
    val actual=JSONArray(spans.map{JSONObject().put("source",it.original).put("target",it.translated).put("reading",it.romanization?:JSONObject.NULL).put("source_utf16",JSONArray(listOf(it.start,it.end)))})
    output.appendText(JSONObject().put("id",p.getString("id")).put("pair",p.getString("pair")).put("source",original).put("state",p.getString("state")).put("density",density).put("spans",actual).put("mixed",if(result==null)original else ImmersionText.project(result)).put("origin",owner.lastOutcome?.origin?.name?:JSONObject.NULL).put("translation_calls",0).toString()+"\n")
   }finally{owner.close()}
   rows++;check(output.length()<8*1024*1024 && SystemClock.elapsedRealtime()-started<300000)
  }
  assertEquals(8,corrected)
  File(dir,"production-status.json").writeText(JSONObject().put("complete",true).put("rows",rows).put("corrected_display_spans",corrected).put("malformed_rejected",rejected).put("seconds",(SystemClock.elapsedRealtime()-started)/1000.0).put("default_factory",true).put("supplied_provider_or_spans",false).toString())
 }
}
