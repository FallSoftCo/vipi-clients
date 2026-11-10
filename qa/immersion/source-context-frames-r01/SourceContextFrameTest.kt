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

class SourceContextFrameTest {
 private fun objects(a:JSONArray)=(0 until a.length()).map{a.getJSONObject(it)}
 private fun strings(a:JSONArray)=(0 until a.length()).map{a.getString(it)}
 private fun range(a:SourceLookupRange?)=a?.let{JSONArray(listOf(it.start,it.end))} ?: JSONObject.NULL
 private fun spans(p:ImmersionPresentation?)=JSONArray(p?.spans?.map{JSONObject().put("source",it.original).put("target",it.translated).put("reading",it.romanization?:JSONObject.NULL).put("source_utf16",JSONArray(listOf(it.start,it.end)))} ?: emptyList<JSONObject>())
 private fun references(p:PartialImmersionResult?)=JSONArray(p?.references?.map{JSONObject().put("scope",JSONArray(listOf(it.start,it.end))).put("original",it.original).put("target",it.translated).put("reading",it.reading?:JSONObject.NULL).put("reference",it.referenceId).put("pack_sha",it.catalogSha256).put("cost",it.nativeSourceTokens).put("output_id",it.outputID?:JSONObject.NULL)} ?: emptyList<JSONObject>())
 private fun evidence(e:SourceLookupEvidence)=JSONObject().put("original",e.original).put("source",e.source).put("target",e.target).put("identity",e.catalogIdentity).put("spans",spans(e.partial)).put("references",references(e.partial)).put("recognitions",JSONArray(e.recognitions.map{r->JSONObject().put("rule",r.ruleID).put("record_sha",r.recordSHA256).put("context",range(r.context)).put("mask",range(r.mask)).put("mode",r.mode.name).put("approved",JSONArray(r.approvedOutputs.map{JSONObject().put("id",it.outputID).put("scope",range(it.range))}))}))
 private data class Owner(val provider:SourceLookupProvider,val trace:()->JSONArray,val raw:()->List<FrameStarterCandidate>)
 private class NoTranslation:LanguageTranslation {
  override suspend fun prepare(source:String,target:String,cellularAllowed:Boolean)=error("No model calls")
  override suspend fun translate(text:String,source:String,target:String):String=error("No translation calls")
  override fun close(){}
 }
 @Test fun frozenFrameComparison()=runBlocking {
  val args=InstrumentationRegistry.getArguments();org.junit.Assume.assumeTrue(args.getString("vipiSourceFrames")=="true");check(args.getString("vipiDedicatedEmulator")=="true")
  val context=InstrumentationRegistry.getInstrumentation().targetContext;val dir=context.filesDir
  fun read(n:String)=File(dir,n).readBytes()
  val manifest=JSONObject(read("manifest.json").toString(Charsets.UTF_8));val files=manifest.getJSONObject("files")
  for(n in files.keys())assertEquals(files.getString(n),JapaneseStarterLookup.sha(read(n)))
  val cases=JSONObject(read("cases.json").toString(Charsets.UTF_8));val baseline=JSONObject(read("baseline-cases.json").toString(Charsets.UTF_8))
  val output=File(dir,"frame-output.jsonl");check(!output.exists());val started=SystemClock.elapsedRealtime();var parity=0;var rows=0;var geometry=0;val mechanisms=JSONArray()
  fun write(value:JSONObject){output.appendText(value.toString()+"\n");check(output.length()<=32*1024*1024);check(SystemClock.elapsedRealtime()-started<300000)}
  fun owner(target:String,known:Set<String>,reference:Boolean=false):Owner {
   val spec=manifest.getJSONObject("packs").getJSONObject(target);val bytes=read(spec.getString("pack"));val meta=read(spec.getString("manifest"))
   if(reference){if(target=="ja"){val x=ReferenceJapaneseStarterLookup(bytes,meta,known,packMultiple=true);return Owner(x,{x.trace},{emptyList()})};val x=ReferenceSwahiliStarterLookup(bytes,meta,known,packMultiple=true);return Owner(x,{x.trace},{emptyList()})}
   if(target=="ja"){val x=JapaneseStarterLookup(bytes,meta,known,packMultiple=true);return Owner(x,{x.trace},{x.rawCandidates})};val x=SwahiliStarterLookup(bytes,meta,known,packMultiple=true);return Owner(x,{x.trace},{x.rawCandidates})
  }
  for(target in listOf("ja","sw"))for(state in objects(baseline.getJSONObject("states").getJSONArray("en-"+target))) {
   val known=strings(state.getJSONArray("known_ids")).toSet();val x=owner(target,known);val ref=owner(target,known,true)
   for(c in objects(baseline.getJSONObject("pairs").getJSONArray("en-"+target)))for(d in listOf(.25,.75)){
    val text=c.getString("source");val a=ref.provider.lookup(text,"en",target,d);val b=x.provider.lookup(text,"en",target,d)
    assertEquals(evidence(a).toString(),evidence(b).toString());assertEquals(ref.trace().toString(),x.trace().toString());parity++
   }
  }
  assertEquals(1536,parity);File(dir,"frame-baseline-parity.json").writeText(JSONObject().put("comparisons",parity).put("all_fields_equal",true).toString())
  for(target in listOf("ja","sw")) {
   val spec=manifest.getJSONObject("packs").getJSONObject(target);val pack=JSONObject(read(spec.getString("pack")).toString(Charsets.UTF_8));val frameBytes=read(spec.getString("patterns"));val patternPack=JSONObject(frameBytes.toString(Charsets.UTF_8))
   val empty=owner(target,emptySet());val g=FrameContextAdapter(frameBytes,read("permission-proposal.json"),target,empty.provider.cacheIdentity)
   for(p in objects(patternPack.getJSONArray("patterns")))for(v in objects(p.getJSONArray("variants"))){
    val hits=objects(g.geometry(v.getString("context")));assertTrue(hits.any{it.getString("pattern_id")==p.getString("id") && it.isNull("reason") && it.getJSONArray("focus").toString()==v.getJSONArray("focus_utf16").toString()});geometry++
   }
   val mechanismSource="Need a phone charger.";val focus=SourceLookupRange(7,20)
   val mechanismBase=empty.provider.lookup(mechanismSource,"en",target,.75)
   val everyFrame=objects(patternPack.getJSONArray("patterns")).map{it.getString("concept_id")}.toSet()
   val withheld=g.resolve(mechanismSource,.75,everyFrame,mechanismBase,empty.raw())
   assertFalse(withheld.partial?.spans?.any{it.start<focus.end && focus.start<it.end} ?: false)
   assertTrue(withheld.recognitions.any{it.mask?.contains(focus)==true})
   val protected=SourceLookupEvidence(mechanismSource,"en",target,empty.provider.cacheIdentity,null,listOf(SourceRecognition("caller-protection",JapaneseStarterLookup.sha(frameBytes),SourceLookupRange(0,mechanismSource.length),SourceLookupRange(0,mechanismSource.length),SourceAtomicMode.AMBIGUOUS,emptyList())))
   val blocked=g.resolve(mechanismSource,.75,emptySet(),protected,emptyList());assertNull(blocked.partial);assertFalse(blocked.allowsLegacy(7,20))
   val atomic=SourceLookupEvidence(mechanismSource,"en",target,empty.provider.cacheIdentity,null,listOf(SourceRecognition("caller-atomic",JapaneseStarterLookup.sha(frameBytes),SourceLookupRange(0,mechanismSource.length),SourceLookupRange(0,mechanismSource.length),SourceAtomicMode.ATOMIC,emptyList())))
   val atomicResult=g.resolve(mechanismSource,.75,emptySet(),atomic,emptyList());assertNull(atomicResult.partial);assertTrue(atomicResult.recognitions.any{it.ruleID=="caller-atomic" && it.mode==SourceAtomicMode.ATOMIC && it.mask==SourceLookupRange(0,mechanismSource.length)})
   val repeated="I need help. ".repeat(140);val repeatBase=empty.provider.lookup(repeated,"en",target,.75);val repeatResult=g.resolve(repeated,.75,emptySet(),repeatBase,empty.raw());assertEquals(128,repeatResult.partial?.spans?.size)
   mechanisms.put(JSONObject().put("pair","en-"+target).put("known_withheld",evidence(withheld)).put("protected",evidence(blocked)).put("atomic",evidence(atomicResult)).put("cap",evidence(repeatResult)))
   for(state in listOf("none","current_starter_concepts_excluded")){
    val known=if(state=="none")emptySet()else objects(pack.getJSONArray("entries")).map{it.getString("concept_id")}.toSet();val x=owner(target,known);val ref=owner(target,known,true)
    val adapter=FrameContextAdapter(frameBytes,read("permission-proposal.json"),target,x.provider.cacheIdentity);val expectedTarget=target
    val provider=object:SourceLookupProvider {override val cacheIdentity=adapter.identity;override suspend fun lookup(original:String,source:String,target:String,density:Double):SourceLookupEvidence {
     require(source=="en" && target==expectedTarget);val b=x.provider.lookup(original,source,target,density);return adapter.resolve(original,density,known,b,x.raw())
    }}
    for(c in objects(cases.getJSONArray("cases")).filter{it.getString("pair")=="en-"+target})for(d in (listOf(.25,.75)+if(c.getString("id") in setOf("control-32","control-33"))listOf(0.0,.05)else emptyList()).sorted()){
     val text=c.getString("source");val a=ref.provider.lookup(text,"en",target,d);val b=x.provider.lookup(text,"en",target,d)
     assertEquals(evidence(a).toString(),evidence(b).toString());assertEquals(ref.trace().toString(),x.trace().toString())
     val raw=JSONArray(x.trace().toString());val candidate=adapter.resolve(text,d,known,b,x.raw());val frameTrace=JSONArray(adapter.trace.toString())
     if(c.getString("id")=="control-32" && d in listOf(0.0,.05,.25)){
      assertFalse(candidate.partial?.spans?.any{it.start<20 && 7<it.end} ?: false)
      assertTrue(candidate.recognitions.any{it.mask?.contains(SourceLookupRange(7,20))==true})
     }
     if(c.getString("id").startsWith("context-literal-"))assertFalse(candidate.partial?.references?.any{it.referenceId.startsWith("frame:")} ?: false)
     val route=JSONObject()
     for((arm,p) in listOf("baseline" to x.provider,"candidate" to provider)){
      val engine=ConversationImmersion(context,"en",target,d,translator=NoTranslation(),qaModelsReady=false,sourceKnownConceptIDs=known,sourceLookup=p)
      try {val id=state+"/"+c.getString("id")+"/"+d+"/"+arm;engine.selectInputLanguage(id,"en");val value=engine.presentation(text,"en",id);assertEquals(0,requireNotNull(engine.lastOutcome).localTranslationCalls);route.put(arm,JSONObject().put("spans",spans(value)).put("mixed",if(value==null)text else ImmersionText.project(value)).put("origin",engine.lastOutcome?.origin?.name))}
      finally{engine.close()}
     }
     write(JSONObject().put("pair","en-"+target).put("id",c.getString("id")).put("source",text).put("state",state).put("known_ids",JSONArray(known.sorted())).put("density",d).put("native_words",JSONArray(LocalImmersion.words(text,"en").map{JSONArray(listOf(it.first,it.last+1))})).put("baseline",evidence(b)).put("candidate",evidence(candidate)).put("starter_trace",raw).put("frame_trace",frameTrace).put("route",route));rows++
    }
   }
  }
  File(dir,"frame-mechanisms.json").writeText(mechanisms.toString())
  assertEquals(780,geometry);assertEquals(656,rows)
  File(dir,"frame-status.json").writeText(JSONObject().put("complete",true).put("rows",rows).put("baseline_comparisons",parity).put("geometry_variants",geometry).put("seconds",(SystemClock.elapsedRealtime()-started)/1000.0).toString())
 }
}
