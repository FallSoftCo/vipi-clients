package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.*
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File

/** Frozen concept-informed probes: execution evidence, not broad language accuracy. */
class AllDirectionFloorDeviceTest {
 @Test fun bundledAutomaticDirectAndEmittedSpeech() = runBlocking {
  val inst=InstrumentationRegistry.getInstrumentation(); val context=inst.targetContext
  check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator")=="true")
  val dir=File(context.filesDir,"all-direction-floor-20261116").apply{mkdirs()}
  val out=File(dir,"report.json"); check(!out.exists())
  val fixture=JSONObject(File(dir,"fixtures.json").readText()); val cases=fixture.getJSONArray("cases")
  val rows=JSONArray(); val voices=JSONArray(); val emitted=linkedMapOf<String,String>()
  val report=JSONObject().put("complete",false).put("cases",rows).put("voices",voices)
   .put("evidence","concept-informed probes; synthesis is not listening or pronunciation acceptance")
  fun save(){out.writeText(report.toString(2))}
  val provider=requireNotNull(BundledStarterLookup.provider(context))
  for(i in 0 until cases.length()) {
   val f=cases.getJSONObject(i); val source=f.getString("source_language");val target=f.getString("target_language");val text=f.getString("original")
   val owner=ConversationImmersion(context,source,target,.25)
   try {
    val p=owner.presentation(text);val o=requireNotNull(owner.lastOutcome)
    val direct=provider.lookup(text,source,target,.5)
    fun spans(p:ImmersionPresentation?)=JSONArray(p?.spans.orEmpty().map{s->
     assertEquals(s.original,text.substring(s.start,s.end))
     JSONObject().put("id",s.id).put("source",s.original).put("target",s.translated).put("start",s.start).put("end",s.end).put("reading",s.romanization?:JSONObject.NULL)
    })
    p?.spans?.firstOrNull()?.let{emitted.putIfAbsent(target,it.translated)}
    rows.put(JSONObject().put("id",f.getString("id")).put("source",source).put("target",target).put("original",text)
     .put("status",o.status.name).put("source_evidence",o.sourceEvidence?.toString()?:JSONObject.NULL)
     .put("automatic_spans",spans(p)).put("direct_spans",spans(direct.partial))
     .put("mixed_reading",p?.let{ImmersionText.project(it)}?:text)
     .put("translation_calls",o.localTranslationCalls).put("readiness_calls",owner.lastInvocation.readiness))
    assertEquals(0,o.localTranslationCalls);assertEquals(0,owner.lastInvocation.readiness);save()
   }finally{owner.close()}
  }
  for((language,text) in emitted){
   val voice=withContext(Dispatchers.Main){LocalVoice(context,language)}
   val row=JSONObject().put("language",language).put("text",text)
   try{row.put("selected_voice",voice.select());val audio=voice.render(text,File(dir,"$language.wav"));row.put("duration_ms",audio.milliseconds).put("sample_rate",audio.sampleRate).put("status","rendered")}
   catch(e:Exception){row.put("status","unavailable").put("error",e.javaClass.simpleName)}
   finally{withContext(Dispatchers.Main){voice.close()};voices.put(row);save()}
  }
  assertEquals(330,rows.length());report.put("complete",true);save()
 }
}
