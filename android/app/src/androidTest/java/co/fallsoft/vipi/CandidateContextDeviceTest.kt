package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.SourceLookupEvidence
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Test
import java.io.File

class CandidateContextDeviceTest {
 @Test fun inspectInactiveCandidate() {
  val inst=InstrumentationRegistry.getInstrumentation()
  check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator")=="true")
  val dir=File(inst.targetContext.filesDir,requireNotNull(InstrumentationRegistry.getArguments().getString("candidateDir")))
  val output=File(dir,"report.json");check(!output.exists())
  val cases=listOf("zh" to "听音乐会", "zh" to "这本书房", "zh" to "一本书店", "ko" to "책에서도", "ko" to "책에서의", "ar" to "كتابي", "ar" to "والكتاب", "it" to "la musica", "it" to "La musica è", "it" to "questa musica", "ar" to "الماء", "ko" to "책을", "zh" to "音乐很", "zh" to "听音乐")
  val rows=JSONArray()
  for((source,text) in cases) {
   val f=SourceFrameLookup(File(dir,"source-frames-$source-en-008.json").readBytes(),File(dir,"source-frames-$source-en-catalog.json").readBytes(),"en","candidate-diagnostic",source)
   val result=f.resolve(text,.5,emptySet(),SourceLookupEvidence(text,source,"en","candidate-diagnostic",null,emptyList()),emptyList())
   rows.put(JSONObject().put("source",source).put("text",text).put("emitted",result.partial!=null).put("trace",f.trace).put("geometry",f.geometry(text)))
  }
  output.writeText(JSONObject().put("candidate",dir.name+" inactive").put("cases",rows).toString(2))
 }
}
