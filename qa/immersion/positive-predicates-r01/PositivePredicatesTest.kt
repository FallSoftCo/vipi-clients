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

/** Frozen source-only inputs through actual default routing; zeros/errors remain rows. */
class PositivePredicatesTest {
 private class NoTranslation:LanguageTranslation {
  override suspend fun prepare(source:String,target:String,cellularAllowed:Boolean)=error("No model calls")
  override suspend fun translate(text:String,source:String,target:String):String=error("No translation calls")
  override fun close(){}
 }
 private fun range(r:SourceLookupRange?)=r?.let{JSONArray(listOf(it.start,it.end))}?:JSONObject.NULL
 @Test fun currentPredicateDepth()=runBlocking {
  val args=InstrumentationRegistry.getArguments();org.junit.Assume.assumeTrue(args.getString("vipiPositivePredicates")=="true");check(args.getString("vipiDedicatedEmulator")=="true")
  val context=InstrumentationRegistry.getInstrumentation().targetContext;val dir=context.filesDir;check(SourceFrameLookup.PROMOTION_ENABLED)
  val manifest=JSONObject(File(dir,"manifest.json").readText());for(n in manifest.keys()){check(!n.contains('/'));assertEquals(manifest.getString(n),JapaneseStarterLookup.sha(File(dir,n).readBytes()))}
  val input=JSONObject(File(dir,"messages.json").readText());check(input.getString("schema")=="vipi-conversation-depth-input-1");val cases=input.getJSONArray("cases");assertEquals(80,cases.length())
  val output=File(dir,"android-output.jsonl");check(!output.exists());val started=SystemClock.elapsedRealtime();val catalog=BundledImmersionCatalog(context)
  val packManifest=context.assets.open("immersion/starter-sw-catalog.json").use{it.readBytes()}
  val packName=JSONObject(packManifest.toString(Charsets.UTF_8)).getString("file")
  val packBytes=context.assets.open("immersion/$packName").use{it.readBytes()}
  val rawAudit=SwahiliStarterLookup(packBytes,packManifest,packMultiple=true)
  var rows=0;var calls=0;var errors=0
  for(i in 0 until cases.length()) {
   val item=cases.getJSONObject(i);val original=item.getString("source");val id=item.getString("id")
   for(target in listOf("sw"))for(density in listOf(.25,.75)) {
    val setup=SystemClock.elapsedRealtimeNanos()
    val owner=ConversationImmersion(context,"en",target,density,translator=NoTranslation(),qaModelsReady=false,sourceKnownConceptIDs=emptySet())
    var failure:Throwable?=null;var result:ImmersionPresentation?=null
    owner.selectInputLanguage(id,"en");val callStart=SystemClock.elapsedRealtimeNanos()
    try {result=owner.presentation(original,"en",id)}catch(e:Exception){failure=e;errors++}
    val elapsed=(SystemClock.elapsedRealtimeNanos()-callStart)/1_000_000.0
    try {
     val outcome=owner.lastOutcome;val spans=result?.spans?:emptyList();val references=(result as? PartialImmersionResult)?.references?:emptyList();val evidence=outcome?.sourceEvidence
     val count=outcome?.localTranslationCalls?:0;calls+=count
     val proof=JSONObject().put("identity",evidence?.catalogIdentity?:JSONObject.NULL).put("selected_route_only",true)
      .put("references",JSONArray(references.map{u->JSONObject().put("scope",JSONArray(listOf(u.start,u.end))).put("reference",u.referenceId).put("pack_sha",u.catalogSha256).put("native_source_tokens",u.nativeSourceTokens).put("concept_id",JSONObject.NULL).put("output_id",u.outputID?:JSONObject.NULL)}))
      .put("recognitions",JSONArray(evidence?.recognitions?.map{n->JSONObject().put("rule",n.ruleID).put("record_sha",n.recordSHA256).put("context",range(n.context)).put("mask",range(n.mask)).put("mode",n.mode.name).put("approved",JSONArray(n.approvedOutputs.map{JSONObject().put("id",it.outputID).put("scope",range(it.range))}))}?:emptyList<JSONObject>()))
     // Separate direct producer audit; never injected into the actual route above.
     rawAudit.resolve(original,"en",target,density)
     val producerTrace=JSONArray(rawAudit.trace.toString())
     val row=JSONObject().put("id",id).put("stratum",item.getString("stratum")).put("pair","en-$target").put("source",original).put("density",density).put("known_ids",JSONArray())
      .put("native_words",JSONArray(LocalImmersion.words(original,"en").map{JSONArray(listOf(it.first,it.last+1))}))
      .put("spans",JSONArray(spans.map{JSONObject().put("source",it.original).put("target",it.translated).put("reading",it.romanization?:JSONObject.NULL).put("source_utf16",JSONArray(listOf(it.start,it.end)))}))
      .put("mixed_script",result?.let{ImmersionText.project(it,showScript=true)}?:original).put("mixed_reading",result?.let{ImmersionText.project(it)}?:original)
      .put("origin",outcome?.origin?.name?:JSONObject.NULL).put("status",if(failure!=null)"EXCEPTION" else outcome?.status?.name?:"OUTCOME_UNAVAILABLE")
      .put("error_class",failure?.javaClass?.name?:JSONObject.NULL).put("translation_calls",count).put("elapsed_ms",elapsed).put("setup_ms",(callStart-setup)/1_000_000.0)
      .put("producer_audit_trace",producerTrace).put("producer_audit_is_selected_route_evidence",false)
      .put("reference_hit",catalog.reference(original,"en",target)!=null).put("source_evidence",proof).put("actual_default_factory",true).put("provider_target_spans_injected",false).put("input_language_override","en")
     output.appendText(row.toString()+"\n");rows++
    }finally{owner.close()}
    check(output.length()<16*1024*1024 && SystemClock.elapsedRealtime()-started<300000)
   }
  }
  File(dir,"android-status.json").writeText(JSONObject().put("rows",rows).put("translation_calls",calls).put("captured_exceptions",errors).put("seconds",(SystemClock.elapsedRealtime()-started)/1000.0).put("actual_default_factory",true).put("semantic_acceptance_asserted",false).toString())
  assertEquals(160,rows);assertEquals(0,calls)
  val controlsInput=JSONObject(File(dir,"controls.json").readText());check(controlsInput.getString("schema")=="vipi-predicate-controls-1")
  val controls=controlsInput.getJSONArray("cases");assertEquals(37,controls.length());val captured=JSONArray()
  val controlOutput=File(dir,"android-controls.json");check(!controlOutput.exists())
  for(n in 0 until controls.length()) {
   val c=controls.getJSONObject(n);val text=c.getString("source");val d=c.getDouble("density")
   val known=c.getJSONArray("known_ids").let{a->(0 until a.length()).map{a.getString(it)}.toSet()}
   val masks=c.getJSONArray("source_masks").let{a->(0 until a.length()).map{a.getJSONArray(it).let{r->SourceLookupRange(r.getInt(0),r.getInt(1))}}}
   val provider=SwahiliStarterLookup(packBytes,packManifest,known,packMultiple=true)
   val value=provider.resolve(text,"en","sw",d,sourceMasks=masks);val selected=value.partial?.spans.orEmpty()
   val predicateCount=value.partial?.references.orEmpty().count{it.referenceId.contains(":clause-en-sw-")}
   val trace=JSONArray(provider.trace.toString())
   val row=JSONObject().put("id",c.getString("id")).put("group",c.getString("group")).put("source",text).put("density",d).put("known_ids",c.getJSONArray("known_ids")).put("source_masks",c.getJSONArray("source_masks"))
    .put("expected_predicate_count",c.getInt("expected_predicate_count")).put("actual_predicate_count",predicateCount)
    .put("spans",JSONArray(selected.map{JSONObject().put("source",it.original).put("target",it.translated).put("reading",it.romanization?:JSONObject.NULL).put("source_utf16",JSONArray(listOf(it.start,it.end)))}))
    .put("mixed_script",value.partial?.let{ImmersionText.project(it,showScript=true)}?:text).put("mixed_reading",value.partial?.let{ImmersionText.project(it)}?:text)
    .put("native_words",JSONArray(LocalImmersion.words(text,"en").map{JSONArray(listOf(it.first,it.last+1))})).put("trace",trace)
    .put("recognitions",JSONArray(value.recognitions.map{r->JSONObject().put("context",range(r.context)).put("mask",range(r.mask)).put("approved",JSONArray(r.approvedOutputs.map{it.outputID}))}))
    .put("raw_provider_control_not_default_route",true).put("semantic_approval",false)
   captured.put(row);controlOutput.writeText(JSONObject().put("complete",false).put("rows",captured).toString())
   assertEquals(c.getString("id"),c.getInt("expected_predicate_count"),predicateCount)
   for(t in 0 until trace.length()) {
    val h=trace.getJSONObject(t)
    if(h.getString("entry_id").startsWith("clause-en-sw-") && !h.isNull("reason")) {
     val scope=h.getJSONArray("source_utf16");val a=scope.getInt(0);val b=scope.getInt(1)
     assertTrue("No inner rescue: "+c.getString("id"),selected.none{it.start>=a && it.end<=b})
     assertFalse(value.allowsLegacy(a,b))
    }
   }
  }
  controlOutput.writeText(JSONObject().put("complete",true).put("rows",captured).put("translation_calls",0).toString())
 }
}
