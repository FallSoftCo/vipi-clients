package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.*
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File

/** Exact release-data packaging and bounded ordinary-route regression; no private injection. */
class DirectionalDictionaryCatalogDeviceTest {
 @Test fun directionalBundledAssetsAndOrdinaryMessages()=runBlocking {
  val inst=InstrumentationRegistry.getInstrumentation();val context=inst.targetContext
  check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator")=="true")
  val out=File(context.filesDir,"directional-dictionary-007-r01.json");check(!out.exists())
  val fixture=JSONObject(inst.context.assets.open("directional-dictionary-007-smoke.json").bufferedReader().use{it.readText()})
  val pins=fixture.getJSONArray("pins");assertEquals(110,pins.length())
  val index=context.assets.open("immersion/${BundledSourceFrameCatalog.INDEX_FILE}").use{it.readBytes()}
  assertEquals(BundledSourceFrameCatalog.INDEX_SHA256,JapaneseStarterLookup.sha(index));assertEquals(BundledSourceFrameCatalog.INDEX_BYTES,index.size)
  for(i in 0 until pins.length()){
   val p=pins.getJSONObject(i);val manifest=context.assets.open("immersion/"+p.getString("manifest")).use{it.readBytes()}
   val bytes=context.assets.open("immersion/"+p.getString("file")).use{it.readBytes()}
   assertEquals(p.getInt("bytes"),bytes.size);assertEquals(p.getString("sha256"),JapaneseStarterLookup.sha(bytes))
   assertEquals(p.getInt("manifest_bytes"),manifest.size);assertEquals(p.getString("manifest_sha256"),JapaneseStarterLookup.sha(manifest))
   SourceFrameLookup(bytes,manifest,p.getString("target"),"packaged-validation",p.getString("source"))
  }
  val report=JSONObject().put("complete",false).put("index_sha256",JapaneseStarterLookup.sha(index)).put("integrity_pairs",110)
  val results=JSONArray();report.put("cases",results);out.writeText(report.toString(2))
  val provider=requireNotNull(BundledStarterLookup.provider(context));val catalog=BundledImmersionCatalog(context)
  for((key,negative) in listOf("cases" to false,"controls" to true)){
   val rows=fixture.getJSONArray(key)
   for(i in 0 until rows.length()){
    val f=rows.getJSONObject(i);val source=f.getString("source_language");val target=f.getString("target_language");val text=f.getString("original")
    assertNull(catalog.reference(text,source,target));assertNull(catalog.reference(text,target,source))
    val owner=ConversationImmersion(context,source,target,.25)
    try {
     val presentation=owner.presentation(text);val outcome=requireNotNull(owner.lastOutcome)
     assertEquals(0,outcome.localTranslationCalls);assertEquals(0,owner.lastInvocation.readiness)
     assertEquals(text,presentation?.original?:text)
     val spans=JSONArray(presentation?.spans.orEmpty().map{s->
      assertEquals(s.original,text.substring(s.start,s.end))
      if(f.has("focus_utf16")){val range=f.getJSONArray("focus_utf16");if(s.start==range.getInt(0)&&s.end==range.getInt(1)){
       assertEquals(f.getString("expected_target"),s.translated)
       if(target in setOf("ar","zh","ja","ko"))assertEquals(f.getString("reading"),s.romanization.orEmpty())
      }}
      JSONObject().put("start",s.start).put("end",s.end).put("original",s.original).put("target",s.translated).put("reading",s.romanization?:JSONObject.NULL)
     })
     val direct=provider.lookup(text,source,target,.5)
     if(negative){
      val focus=f.getString("forbidden_focus");val prefix=f.getString("forbidden_pattern_prefix")
      for(value in listOf(presentation,direct.partial)) {
       val refs=(value as? PartialImmersionResult)?.references.orEmpty()
       assertFalse(refs.any{it.original==focus && it.referenceId.contains(":"+prefix)})
      }
     }else if(f.has("focus_utf16")){
      val range=f.getJSONArray("focus_utf16")
      for(span in direct.partial?.spans.orEmpty()) if(span.start==range.getInt(0)&&span.end==range.getInt(1)) {
       assertEquals(f.getString("expected_target"),span.translated)
       if(target in setOf("ar","zh","ja","ko"))assertEquals(f.getString("reading"),span.romanization.orEmpty())
      }
     }
     results.put(JSONObject().put("fixture",f).put("negative",negative).put("status",outcome.status.name)
      .put("original_preserved",true).put("spans",spans).put("mixed_reading",presentation?.let{ImmersionText.project(it)}?:text)
      .put("mixed_script",presentation?.let{ImmersionText.project(it,showScript=true)}?:text)
      .put("direct_spans",JSONArray(direct.partial?.spans.orEmpty().map{v->JSONObject().put("start",v.start).put("end",v.end).put("original",v.original).put("target",v.translated).put("reading",v.romanization?:JSONObject.NULL)}))
      .put("translation_calls",outcome.localTranslationCalls).put("readiness_calls",owner.lastInvocation.readiness))
     out.writeText(report.toString(2))
    }finally{owner.close()}
   }
  }
  report.put("complete",true);out.writeText(report.toString(2))
 }
}
