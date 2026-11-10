package co.fallsoft.vipi
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
class SourceFrameReadingValidationTest {
 @Test fun readingTypesAndValidFrozenPacks() {
  val args=InstrumentationRegistry.getArguments();org.junit.Assume.assumeTrue(args.getString("vipiFrameReadingValidation")=="true");check(args.getString("vipiDedicatedEmulator")=="true")
  val context=InstrumentationRegistry.getInstrumentation().targetContext;var valid=0;var rejected=0
  for(target in listOf("ja","sw")) {
   val manifest=context.assets.open("immersion/source-frames-en-$target-catalog.json").use{it.readBytes()};val m=JSONObject(manifest.toString(Charsets.UTF_8));val bytes=context.assets.open("immersion/"+m.getString("file")).use{it.readBytes()}
   SourceFrameLookup(bytes,manifest,target,"validation");valid++
   for(change in listOf("number","boolean","object")+if(target=="sw")listOf("missing")else emptyList()) {
    val p=JSONObject(bytes.toString(Charsets.UTF_8));val pattern=p.getJSONArray("patterns").getJSONObject(0)
    when(change){"number"->pattern.put("reading",17);"boolean"->pattern.put("reading",false);"object"->pattern.put("reading",JSONObject().put("unexpected",true));"missing"->pattern.remove("reading")}
    val changed=p.toString().toByteArray(Charsets.UTF_8);val meta=JSONObject(manifest.toString(Charsets.UTF_8)).put("sha256",JapaneseStarterLookup.sha(changed)).put("bytes",changed.size).toString().toByteArray(Charsets.UTF_8)
    assertTrue("$target $change",runCatching{SourceFrameLookup(changed,meta,target,"validation")}.isFailure);rejected++
   }
  }
  File(context.filesDir,"reading-validation.json").writeText(JSONObject().put("valid_frozen_packs",valid).put("invalid_reading_rejections",rejected).put("selector_executions",0).toString())
 }
}
