package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Test
import java.io.File

class AllDirectionDetectorDeviceTest {
 @Test fun identifyFrozenOriginals() = runBlocking {
  val inst=InstrumentationRegistry.getInstrumentation()
  check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator")=="true")
  val dir=File(inst.targetContext.filesDir,"all-direction-floor-20261116")
  val file=File(dir,"detection.json");check(!file.exists())
  val cases=JSONObject(File(dir,"fixtures.json").readText()).getJSONArray("cases")
  val rows=JSONArray()
  val traces=JSONArray()
  val entries=JSONObject(inst.targetContext.assets.open("immersion/"+BundledSourceFrameCatalog.INDEX_FILE).bufferedReader().use{it.readText()}).getJSONArray("entries")
  MessageLanguage().use { detector ->
   for(i in 0 until cases.length()) {
    val row=cases.getJSONObject(i)
    rows.put(JSONObject().put("id",row.getString("id")).put("detected_language",detector.identify(row.getString("original"))?:JSONObject.NULL))
    val source=row.getString("source_language");val target=row.getString("target_language")
    if(source in setOf("ar","zh","ko") && target=="en") {
     val entry=(0 until entries.length()).map{entries.getJSONObject(it)}.first{it.getString("source")==source&&it.getString("target")==target}
     fun asset(name:String)=inst.targetContext.assets.open("immersion/"+name).use{it.readBytes()}
     val frame=SourceFrameLookup(asset(entry.getString("file")),asset(entry.getString("manifest_file")),target,"diagnostic-empty",source)
     val text=row.getString("original")
     val baseline=co.fallsoft.vipi.core.SourceLookupEvidence(text,source,target,"diagnostic-empty",null,emptyList())
     frame.resolve(text,.5,emptySet(),baseline,emptyList())
     traces.put(JSONObject().put("id",row.getString("id")).put("geometry",frame.geometry(text)).put("trace",frame.trace)
      .put("native_words",JSONArray(LocalImmersion.words(text,source).map{JSONObject().put("start",it.first).put("end",it.last+1).put("text",text.substring(it))})))
    }
   }
  }
  file.writeText(JSONObject().put("complete",true).put("cases",rows).put("frame_diagnostics",traces).toString(2))
 }
}
