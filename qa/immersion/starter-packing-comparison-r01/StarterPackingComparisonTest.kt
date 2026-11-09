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

/** Research-only wrapper: production matching and core presentation are reused unchanged. */
class StarterPackingComparisonTest {
    private class NoTranslation:LanguageTranslation {
        override suspend fun prepare(source:String,target:String,cellularAllowed:Boolean)=error("No preparation")
        override suspend fun translate(text:String,source:String,target:String):String=error("No translation")
        override fun close() {}
    }
    private fun spans(value:ImmersionPresentation?)=JSONArray(value?.spans?.map { s -> JSONObject().put("source",s.original).put("target",s.translated)
        .put("reading",s.romanization ?: JSONObject.NULL).put("source_utf16",JSONArray(listOf(s.start,s.end))) } ?: emptyList<JSONObject>())
    private fun same(a:JSONArray,b:JSONArray) { assertEquals(a.length(),b.length());for(i in 0 until a.length()) {
        val x=a.getJSONObject(i);val y=b.getJSONObject(i)
        for(k in listOf("source","target","reading")) assertEquals(x.opt(k),y.opt(k))
        assertEquals(x.getJSONArray("source_utf16").toString(),y.getJSONArray("source_utf16").toString())
    } }
    private class Packed(val target:String,val pack:JSONObject,val original:SourceLookupProvider,val trace:()->JSONArray):SourceLookupProvider {
        override val cacheIdentity="packing-r01:"+SwahiliStarterLookup.sha(original.cacheIdentity.toByteArray())
        private val entries=pack.getJSONArray("entries").let{a->(0 until a.length()).associate{a.getJSONObject(it).getString("id") to a.getJSONObject(it)}}
        var audit=JSONArray();private set
        var latest:SourceLookupEvidence?=null;private set
        data class Hit(val row:JSONObject,val entry:JSONObject,val start:Int,val end:Int,val cost:Int,val ordinal:Int)
        fun pack(text:String,density:Double,base:SourceLookupEvidence,rows:JSONArray):SourceLookupEvidence {
            val native=LocalImmersion.words(text,"en");val budget=if(density>0)maxOf(1,(native.size*density).toInt()) else 0
            val hits=(0 until rows.length()).map { n -> val row=rows.getJSONObject(n);val e=requireNotNull(entries[row.getString("entry_id")]);val range=row.getJSONArray("source_utf16");val a=range.getInt(0);val b=range.getInt(1)
                check(e.getString("record_sha256")==row.getString("record_sha256"));check(e.getString("target")==row.getString("target"));check(e.getString("concept_id")==row.getString("concept_id"));check(text.substring(a,b)==row.getString("source"))
                val touched=native.filter{it.first<b && a<=it.last}
                if(row.isNull("reason"))check(touched.isNotEmpty() && touched.first().first==a && touched.last().last+1==b && touched.all{it.first>=a && it.last<b})
                Hit(row,e,a,b,touched.size,n)
            }
            val order=hits.filter{it.row.isNull("reason")}.sortedWith(compareBy<Hit>{it.entry.getString("category")!="content"}.thenBy{it.entry.getInt("train_rank")}.thenByDescending{it.entry.getJSONArray("source_tokens").length()}.thenBy{it.start})
            val chosen=mutableListOf<Hit>();var used=0;audit=JSONArray()
            for(h in order) {
                val reason=when { chosen.any{it.start<h.end && h.start<it.end}->"selected_overlap";used+h.cost>budget->"remaining_native_budget";else->null }
                audit.put(JSONObject().put("entry_id",h.row.getString("entry_id")).put("scope",JSONArray(listOf(h.start,h.end))).put("cost",h.cost).put("ordinal",h.ordinal).put("reason",reason ?: JSONObject.NULL))
                if(reason==null){chosen+=h;used+=h.cost}
            }
            check(used<=budget)
            val units=chosen.sortedBy{it.start}.map { h ->SourceReferenceUnit(h.start,h.end,text.substring(h.start,h.end),h.row.getString("target"),if(h.row.isNull("reading"))null else h.row.getString("reading"),
                "${pack.getString("version")}:${pack.getString("_sha")}:${h.row.getString("entry_id")}",pack.getString("_sha"),h.cost,"${h.row.getString("entry_id")}@${h.start}:${h.end}") }
            val partial=SourceReferencePresentation.create(text,target,units,density,native.size)
            val filtered=partial?.let{base.filterPartial(it)}
            return SourceLookupEvidence(text,"en",target,cacheIdentity,filtered,base.recognitions).also{check(it.isValid(text,"en",target,cacheIdentity));check(it.recognitions==base.recognitions);latest=it}
        }
        override suspend fun lookup(original:String,source:String,target:String,density:Double):SourceLookupEvidence {
            val base=this.original.lookup(original,source,target,density)
            return pack(original,density,base,trace())
        }
    }
    @Test fun frozenComparison()=runBlocking {
        val args=InstrumentationRegistry.getArguments();org.junit.Assume.assumeTrue(args.getString("vipiStarterPacking")=="true");check(args.getString("vipiDedicatedEmulator")=="true")
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val spec=JSONObject(File(context.filesDir,"packing-input-manifest.json").readText())
        val output=File(context.filesDir,"starter-packing-output-r01.json");check(!output.exists())
        val rows=JSONArray();val report=JSONObject().put("schema",1).put("complete",false).put("activated",false).put("platform","android").put("cases",rows)
        fun save(){val f=File(output.path+".tmp");f.writeText(report.toString());check(f.length()<=16*1024*1024);check(f.renameTo(output))}
        save()
        for(target in listOf("ja","sw")) {
            val binding=spec.getJSONObject(target);val input=File(context.filesDir,binding.getString("file")).readBytes();check(SwahiliStarterLookup.sha(input)==binding.getString("sha256"))
            val previous=JSONObject(input.toString(Charsets.UTF_8));check(previous.getBoolean("complete"));val cases=previous.getJSONArray("cases");check(cases.length()==384)
            val manifest=context.assets.open("immersion/"+if(target=="ja")"starter-catalog.json" else "starter-sw-catalog.json").use{it.readBytes()}
            val manifestJSON=JSONObject(manifest.toString(Charsets.UTF_8));val bytes=context.assets.open("immersion/"+manifestJSON.getString("file")).use{it.readBytes()}
            check(SwahiliStarterLookup.sha(bytes)==previous.getString("pack_sha256"));val pack=JSONObject(bytes.toString(Charsets.UTF_8)).put("_sha",SwahiliStarterLookup.sha(bytes))
            for(state in 0..2) {
                val selected=(0 until cases.length()).map{cases.getJSONObject(it)}.filter{it.getInt("known_state")==state};check(selected.size==128)
                val ids=selected.first().getJSONArray("known_ids").let{a->(0 until a.length()).map{a.getString(it)}.toSet()}
                val ja=if(target=="ja")JapaneseStarterLookup(bytes,manifest,ids) else null;val sw=if(target=="sw")SwahiliStarterLookup(bytes,manifest,ids) else null
                val provider:SourceLookupProvider=ja ?: requireNotNull(sw);val trace={ja?.trace ?: requireNotNull(sw).trace};val packed=Packed(target,pack,provider,trace)
                ConversationImmersion(context,"en",target,.25,translator=NoTranslation(),qaModelsReady=false,sourceKnownConceptIDs=ids).use { baseline ->
                ConversationImmersion(context,"en",target,.25,translator=NoTranslation(),qaModelsReady=false,sourceKnownConceptIDs=ids,sourceLookup=packed).use { treatment ->
                    for(old in selected) {
                        val text=old.getString("original");val id=old.getString("id");val native=LocalImmersion.words(text,"en");assertEquals(old.getJSONArray("native_words").toString(),JSONArray(native.map{JSONArray(listOf(it.first,it.last+1))}).toString())
                        baseline.selectInputLanguage(id,"en");treatment.selectInputLanguage(id,"en")
                        val started=SystemClock.elapsedRealtimeNanos();val a=baseline.presentation(text,"en",id);val aMs=(SystemClock.elapsedRealtimeNanos()-started)/1e6
                        same(old.getJSONArray("spans"),spans(a));assertEquals(old.getString("mixed"),a?.let{ImmersionText.project(it)} ?: text)
                        val base=provider.lookup(text,"en",target,.25);same(old.getJSONArray("starter_spans"),spans(base.partial));val actualTrace=JSONArray(trace().toString());assertEquals(old.getJSONArray("trace").toString(),actualTrace.toString())
                        val direct=packed.pack(text,.25,base,actualTrace);val admission=JSONArray(packed.audit.toString())
                        val begun=SystemClock.elapsedRealtimeNanos();val b=treatment.presentation(text,"en",id);val bMs=(SystemClock.elapsedRealtimeNanos()-begun)/1e6
                        val ao=requireNotNull(baseline.lastOutcome);val bo=requireNotNull(treatment.lastOutcome);check(ao.localTranslationCalls==0 && bo.localTranslationCalls==0)
                        val recognitions=JSONArray(base.recognitions.map{r->JSONObject().put("rule",r.ruleID).put("record",r.recordSHA256).put("context",JSONArray(listOf(r.context.start,r.context.end))).put("mode",r.mode.name).put("mask",r.mask?.let{JSONArray(listOf(it.start,it.end))} ?: JSONObject.NULL).put("approved",JSONArray(r.approvedOutputs.map{JSONObject().put("id",it.outputID).put("scope",JSONArray(listOf(it.range.start,it.range.end)))}))})
                        rows.put(JSONObject().put("pair","en-$target").put("id",id).put("known_state",state).put("known_ids",old.getJSONArray("known_ids")).put("original",text).put("stratum",old.getString("stratum")).put("density",.25).put("native_words",old.getJSONArray("native_words")).put("budget",maxOf(1,(native.size*.25).toInt()))
                            .put("trace",actualTrace).put("admission",admission).put("recognitions",recognitions).put("a_spans",spans(a)).put("b_spans",spans(b)).put("a_direct",spans(base.partial)).put("b_direct",spans(direct.partial)).put("a_mixed",a?.let{ImmersionText.project(it)} ?: text).put("b_mixed",b?.let{ImmersionText.project(it)} ?: text).put("a_origin",ao.origin?.name ?: JSONObject.NULL).put("b_origin",bo.origin?.name ?: JSONObject.NULL).put("a_ms",aMs).put("b_ms",bMs));save()
                    }
                } }
            }
        }
        check(rows.length()==768);report.put("complete",true).put("baseline_parity_rows",768);save()
    }
}
