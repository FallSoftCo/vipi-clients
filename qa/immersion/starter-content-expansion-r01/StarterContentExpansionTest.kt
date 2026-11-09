package co.fallsoft.vipi
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.*
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import android.os.SystemClock

/** Private candidate bytes through unchanged native loaders; no production activation. */
class StarterContentExpansionTest {
 private class NoTranslation:LanguageTranslation {
  override suspend fun prepare(source:String,target:String,cellularAllowed:Boolean)=error("No preparation")
  override suspend fun translate(text:String,source:String,target:String):String=error("No translation")
  override fun close() {}
 }
 private fun strings(a:JSONArray)=(0 until a.length()).map{a.getString(it)}
 private fun objects(a:JSONArray)=(0 until a.length()).map{a.getJSONObject(it)}
 private fun spans(p:ImmersionPresentation?)=JSONArray(p?.spans?.map{JSONObject().put("source",it.original).put("target",it.translated).put("reading",it.romanization ?: JSONObject.NULL).put("source_utf16",JSONArray(listOf(it.start,it.end)))} ?: emptyList<JSONObject>())
 private fun refs(p:ImmersionPresentation?)=JSONArray((p as? PartialImmersionResult)?.references?.map{JSONObject().put("scope",JSONArray(listOf(it.start,it.end))).put("output_id",it.outputID).put("reference_id",it.referenceId).put("pack_sha",it.catalogSha256).put("native_cost",it.nativeSourceTokens)} ?: emptyList<JSONObject>())
 private fun same(a:JSONArray,b:JSONArray){assertEquals(a.length(),b.length());for(i in 0 until a.length()){val x=a.getJSONObject(i);val y=b.getJSONObject(i);for(k in listOf("source","target","reading"))assertEquals(x.opt(k),y.opt(k));assertEquals(x.getJSONArray("source_utf16").toString(),y.getJSONArray("source_utf16").toString())}}
 private data class Owner(val pack:JSONObject,val provider:SourceLookupProvider,val trace:()->JSONArray)
 private data class Hit(val id:String,val start:Int,val end:Int,val cost:Int,val category:String,val rank:Int,val width:Int)
 private fun hits(owner:Owner,trace:JSONArray,words:List<IntRange>):List<Hit>{
  val entries=objects(owner.pack.getJSONArray("entries")).associateBy{it.getString("id")}
  return objects(trace).filter{it.isNull("reason")}.map{r->val e=requireNotNull(entries[r.getString("entry_id")]);val scope=r.getJSONArray("source_utf16");val a=scope.getInt(0);val b=scope.getInt(1);val touched=words.filter{it.first<b && a<=it.last};check(touched.isNotEmpty() && touched.first().first==a && touched.last().last+1==b);Hit(e.getString("id")+"@$a:$b",a,b,touched.size,e.getString("category"),e.getInt("train_rank"),e.getJSONArray("source_tokens").length())}.sortedWith(compareBy<Hit>{it.category!="content"}.thenBy{it.rank}.thenByDescending{it.width}.thenBy{it.start})
 }
 private fun shape(hits:List<Hit>,budget:Int):Set<String>{val chosen=mutableListOf<Hit>();var used=0;for(h in hits){if(chosen.size==128)break;if(used+h.cost>budget || chosen.any{it.start<h.end && h.start<it.end})continue;chosen+=h;used+=h.cost};return chosen.map{it.id}.toSet()}
 private fun budget(n:Int,d:Double)=if(d>0)maxOf(1,(n*d).toInt()) else 0
 @Test fun frozenComparison()=runBlocking {
  val args=InstrumentationRegistry.getArguments();org.junit.Assume.assumeTrue(args.getString("vipiContentExpansion")=="true");check(args.getString("vipiDedicatedEmulator")=="true")
  val context=InstrumentationRegistry.getInstrumentation().targetContext;val directory=context.filesDir
  fun read(n:String)=File(directory,n).readBytes()
  val manifest=JSONObject(read("native-input-manifest.json").toString(Charsets.UTF_8));val bindings=manifest.getJSONObject("files");for(n in bindings.keys())check(SwahiliStarterLookup.sha(read(n))==bindings.getString(n))
  val input=JSONObject(read("comparison-inputs.json").toString(Charsets.UTF_8));val expected=JSONObject(read("baseline-expected.json").toString(Charsets.UTF_8))
  val potential=strings(manifest.getJSONArray("boundary_candidates")).toSet();val slider=manifest.getJSONArray("android_density_values");val domain=(0 until slider.length()).map{slider.getDouble(it)}
  fun owner(target:String,arm:String,known:Set<String>):Owner{val spec=manifest.getJSONObject("packs").getJSONObject(target).getJSONObject(arm);val raw=read(spec.getString("pack"));val meta=read(spec.getString("manifest"));val p=JSONObject(raw.toString(Charsets.UTF_8));val ja=if(target=="ja")JapaneseStarterLookup(raw,meta,known,packMultiple=true) else null;val sw=if(target=="sw")SwahiliStarterLookup(raw,meta,known,packMultiple=true) else null;return Owner(p,ja ?: requireNotNull(sw),{ja?.trace ?: requireNotNull(sw).trace})}
  val plans=mutableMapOf<String,List<Double>>();val plannedHits=mutableMapOf<String,List<Hit>>();val boundary=JSONArray();var prepass=0
  // Only geometry/order/IDs determine extra steps; freeze before opening predictions.
  for(target in listOf("ja","sw"))for(state in objects(input.getJSONObject("states").getJSONArray("en-$target"))){val sid=state.getString("id");val known=strings(state.getJSONArray("known_ids")).toSet();val owners=listOf("current","candidate").associateWith{owner(target,it,known)}
   for(c in objects(input.getJSONObject("pairs").getJSONArray("en-$target"))){val id=c.getString("id");val key="en-$target/$id/$sid";val selected=mutableSetOf(.25,.75)
    if("en-$target/$id" in potential){val text=c.getString("source");val words=LocalImmersion.words(text,"en");for((arm,o) in owners){o.provider.lookup(text,"en",target,.75);prepass++;val hs=hits(o,o.trace(),words);plannedHits["$key/$arm"]=hs
     val sets=domain.map{shape(hs,budget(words.size,it))};val edges=JSONArray();for(i in 1 until domain.size)if(!sets[i].containsAll(sets[i-1])){selected+=domain[i-1];selected+=domain[i];edges.put(JSONArray(listOf(domain[i-1],domain[i])))}
     boundary.put(JSONObject().put("key",key).put("arm",arm).put("native_words",JSONArray(words.map{JSONArray(listOf(it.first,it.last+1))})).put("source_hits",JSONArray(hs.map{JSONObject().put("id",it.id).put("scope",JSONArray(listOf(it.start,it.end))).put("cost",it.cost).put("rank",it.rank).put("category",it.category)})).put("nonmonotone_edges",edges))
    }};plans[key]=selected.sorted()
   }
  }
  check(prepass<=36);val plannedEvaluations=plans.values.sumOf{it.size}*2;check(plannedEvaluations<=6048)
  val planJSON=JSONObject().put("plans",JSONObject(plans.mapValues{JSONArray(it.value)})).put("boundary_proofs",boundary).put("prepass_calls",prepass).put("evaluations",plannedEvaluations).put("target_outputs_used_for_selection",false)
  File(directory,"content-boundary-freeze.json").writeText(planJSON.toString())
  val output=File(directory,"content-output.jsonl");check(!output.exists());output.createNewFile();var rows=0;var evaluations=0;var baselineDirect=0;var baselineRoute=0
  fun status(done:Boolean){File(directory,"content-status.json").writeText(JSONObject().put("complete",done).put("rows",rows).put("evaluations",evaluations).put("planned_evaluations",plannedEvaluations).put("baseline_direct_parity",baselineDirect).put("baseline_route_parity",baselineRoute).put("output_bytes",output.length()).put("boundary_sha256",SwahiliStarterLookup.sha(planJSON.toString().toByteArray())).put("activated",false).toString())};status(false)
  for(target in listOf("ja","sw"))for(state in objects(input.getJSONObject("states").getJSONArray("en-$target"))){val sid=state.getString("id");val known=strings(state.getJSONArray("known_ids")).toSet();val owners=listOf("current","candidate").associateWith{owner(target,it,known)};val engines=mutableMapOf<Pair<String,Double>,ConversationImmersion>()
   try{for(c in objects(input.getJSONObject("pairs").getJSONArray("en-$target"))){val id=c.getString("id");val text=c.getString("source");val key="en-$target/$id/$sid";val words=LocalImmersion.words(text,"en");val outputs=JSONObject();val evidence=JSONObject();val steps=JSONArray()
    for(density in requireNotNull(plans[key])){val b=budget(words.size,density);val arms=JSONObject()
     for(arm in listOf("current","candidate")){val o=requireNotNull(owners[arm]);val started=SystemClock.elapsedRealtimeNanos();val direct=o.provider.lookup(text,"en",target,density);val directMs=(SystemClock.elapsedRealtimeNanos()-started)/1e6;val trace=JSONArray(o.trace().toString());val hs=hits(o,trace,words)
      check(hs.none{it.cost>1} || "en-$target/$id" in potential)
      val model=plannedHits["$key/$arm"];if(model!=null)check(direct.partial?.references?.mapNotNull{it.outputID}?.toSet().orEmpty()==shape(model,b))
      check((direct.partial?.references?.sumOf{requireNotNull(it.nativeSourceTokens)} ?: 0)<=b)
      val rs=JSONArray(direct.recognitions.map{z->JSONObject().put("rule",z.ruleID).put("record",z.recordSHA256).put("context",JSONArray(listOf(z.context.start,z.context.end))).put("mode",z.mode.name).put("mask",z.mask?.let{JSONArray(listOf(it.start,it.end))} ?: JSONObject.NULL).put("approved",JSONArray(z.approvedOutputs.map{JSONObject().put("id",it.outputID).put("scope",JSONArray(listOf(it.range.start,it.range.end)))}))})
      val ev=JSONObject().put("trace",trace).put("recognitions",rs);val eh=SwahiliStarterLookup.sha(ev.toString().toByteArray());evidence.put(eh,ev)
      val engine=engines.getOrPut(arm to density){ConversationImmersion(context,"en",target,density,translator=NoTranslation(),qaModelsReady=false,sourceKnownConceptIDs=known,sourceLookup=o.provider)}
      engine.selectInputLanguage(id,"en");val began=SystemClock.elapsedRealtimeNanos();val full=engine.presentation(text,"en",id);val routeMs=(SystemClock.elapsedRealtimeNanos()-began)/1e6;val outcome=requireNotNull(engine.lastOutcome);check(outcome.localTranslationCalls==0)
      val result=JSONObject().put("direct_spans",spans(direct.partial)).put("direct_mixed",direct.partial?.let{ImmersionText.project(it)} ?: text).put("direct_references",refs(direct.partial)).put("route_spans",spans(full)).put("route_mixed",full?.let{ImmersionText.project(it)} ?: text).put("route_references",refs(full)).put("origin",outcome.origin?.name ?: JSONObject.NULL).put("status",outcome.status.name).put("provider_identity",o.provider.cacheIdentity).put("pack_sha256",SwahiliStarterLookup.sha(read(manifest.getJSONObject("packs").getJSONObject(target).getJSONObject(arm).getString("pack"))))
      val oh=SwahiliStarterLookup.sha(result.toString().toByteArray());outputs.put(oh,result)
      val ek="$key/${java.lang.Long.toHexString(java.lang.Double.doubleToRawLongBits(density))}";if(arm=="current" && expected.has(ek)){val e=expected.getJSONObject(ek);same(e.getJSONArray("direct_spans"),spans(direct.partial));baselineDirect++;if(e.has("route_spans")){same(e.getJSONArray("route_spans"),spans(full));baselineRoute++}}
      arms.put(arm,JSONObject().put("output",oh).put("evidence",eh).put("direct_ms",directMs).put("route_ms",routeMs).put("cache_hit",outcome.cacheHit).put("translation_calls",outcome.localTranslationCalls));evaluations++
     };steps.put(JSONObject().put("density",density).put("density_bits",java.lang.Long.toHexString(java.lang.Double.doubleToRawLongBits(density))).put("budget",b).put("arms",arms))
    }
    output.appendText(JSONObject().put("pair","en-$target").put("id",id).put("source",text).put("stratum",c.getString("stratum")).put("state",sid).put("known_ids",state.getJSONArray("known_ids")).put("native_words",JSONArray(words.map{JSONArray(listOf(it.first,it.last+1))})).put("steps",steps).put("outputs",outputs).put("evidence",evidence).toString()+"\n");check(output.length()<=32*1024*1024);rows++;if(rows%32==0)status(false)
   }}finally{engines.values.forEach{it.close()}}
  }
  check(rows==1386 && evaluations==plannedEvaluations && baselineDirect==1536 && baselineRoute==768)
  val controls=JSONArray()
  for(target in listOf("ja","sw")){val spec=manifest.getJSONObject("packs").getJSONObject(target).getJSONObject("candidate");val p=JSONObject(read(spec.getString("pack")).toString(Charsets.UTF_8));val all=objects(p.getJSONArray("entries")).map{it.getString("concept_id")}.toSet();val o=owner(target,"candidate",all);val text="My family and my family enjoy pizza.";val result=o.provider.lookup(text,"en",target,.75);check(result.partial==null && result.recognitions.isNotEmpty());controls.put(JSONObject().put("pair","en-$target").put("all_candidate_known_empty",true))}
  File(directory,"content-controls.json").writeText(controls.toString());status(true)
 }
}
