package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.*
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test
import org.junit.Rule
import androidx.compose.material3.Slider
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performSemanticsAction
import java.io.File
import android.os.SystemClock

/** Research-only wrapper: production matching and core presentation are reused unchanged. */
class StarterPackingDensityTest {
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
    @get:Rule val compose=createComposeRule()
    @Test fun densityRange()=runBlocking {
        val args=InstrumentationRegistry.getArguments();org.junit.Assume.assumeTrue(args.getString("vipiStarterDensity")=="true");check(args.getString("vipiDedicatedEmulator")=="true")
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val slider=mutableStateOf(0f);val callbacks=mutableListOf<Float>()
        compose.setContent { Slider(value=slider.value,onValueChange={slider.value=it;callbacks.add(it)},valueRange=0f..0.75f,steps=14,modifier=Modifier.testTag("actual-density-slider")) }
        val actual=mutableListOf(0.0)
        for(step in 1..15) { compose.onNodeWithTag("actual-density-slider").performSemanticsAction(SemanticsActions.SetProgress){it(step/20f)};compose.waitForIdle();compose.runOnIdle{actual.add(slider.value.toDouble())} }
        check(actual.size==16 && actual.zipWithNext().all{it.first<it.second} && actual.last()==.75)
        val densities=linkedMapOf<Long,Pair<Double,MutableList<String>>>()
        for(step in 0..15) for((label,density) in listOf("canonical-double-$step" to step/20.0,"android-slider-$step" to actual[step])) {
            densities.getOrPut(java.lang.Double.doubleToRawLongBits(density)){density to mutableListOf()}.second.add(label)
        }
        val spec=JSONObject(File(context.filesDir,"density-input-manifest.json").readText())
        val priorBytes=File(context.filesDir,"packing-reference.json").readBytes();check(SwahiliStarterLookup.sha(priorBytes)==spec.getString("packing_reference_sha256"))
        val prior=JSONObject(priorBytes.toString(Charsets.UTF_8)).getJSONArray("cases");val priorByKey=(0 until prior.length()).associate { n->val c=prior.getJSONObject(n); "${c.getString("pair")}/${c.getString("id")}/${c.getInt("known_state")}" to c }
        val output=File(context.filesDir,"starter-density-output-r01.jsonl");check(!output.exists());output.createNewFile()
        val status=File(context.filesDir,"starter-density-status-r01.json");var completed=0;var evaluations=0;var parity=0
        val densityRecords=JSONArray(densities.map{(bits,v)->JSONObject().put("bits",java.lang.Long.toHexString(bits)).put("value",v.first).put("labels",JSONArray(v.second))})
        fun save(done:Boolean){status.writeText(JSONObject().put("complete",done).put("activated",false).put("cases",completed).put("evaluations",evaluations).put("parity_025",parity).put("actual_slider_values",JSONArray(actual)).put("density_records",densityRecords).put("output_bytes",output.length()).toString())}
        save(false)
        for(target in listOf("ja","sw")) {
            val binding=spec.getJSONObject(target);val input=File(context.filesDir,binding.getString("file")).readBytes();check(SwahiliStarterLookup.sha(input)==binding.getString("sha256"));val previous=JSONObject(input.toString(Charsets.UTF_8));val cases=previous.getJSONArray("cases");check(cases.length()==384)
            val manifest=context.assets.open("immersion/"+if(target=="ja")"starter-catalog.json" else "starter-sw-catalog.json").use{it.readBytes()};val m=JSONObject(manifest.toString(Charsets.UTF_8));val bytes=context.assets.open("immersion/"+m.getString("file")).use{it.readBytes()};check(SwahiliStarterLookup.sha(bytes)==previous.getString("pack_sha256"));val pack=JSONObject(bytes.toString(Charsets.UTF_8)).put("_sha",SwahiliStarterLookup.sha(bytes))
            for(state in 0..2) {
                val selected=(0 until cases.length()).map{cases.getJSONObject(it)}.filter{it.getInt("known_state")==state};check(selected.size==128)
                val ids=selected.first().getJSONArray("known_ids").let{a->(0 until a.length()).map{a.getString(it)}.toSet()}
                val ja=if(target=="ja")JapaneseStarterLookup(bytes,manifest,ids) else null;val sw=if(target=="sw")SwahiliStarterLookup(bytes,manifest,ids) else null;val provider:SourceLookupProvider=ja ?: requireNotNull(sw);val trace={ja?.trace ?: requireNotNull(sw).trace};val packed=Packed(target,pack,provider,trace)
                for(old in selected) {
                    val text=old.getString("original");val id=old.getString("id");val native=LocalImmersion.words(text,"en");assertEquals(old.getJSONArray("native_words").toString(),JSONArray(native.map{JSONArray(listOf(it.first,it.last+1))}).toString())
                    val reference=requireNotNull(priorByKey["en-$target/$id/$state"]);val outputs=JSONObject();val evidence=JSONObject();val steps=JSONArray()
                    for((bits,d) in densities) {
                        val density=d.first;val start=SystemClock.elapsedRealtimeNanos();val a=provider.lookup(text,"en",target,density);val tr=JSONArray(trace().toString());val b=packed.pack(text,density,a,tr)
                        val mask=JSONArray(a.recognitions.map{z->JSONObject().put("rule",z.ruleID).put("record",z.recordSHA256).put("context",JSONArray(listOf(z.context.start,z.context.end))).put("mode",z.mode.name).put("mask",z.mask?.let{JSONArray(listOf(it.start,it.end))} ?: JSONObject.NULL).put("approved",JSONArray(z.approvedOutputs.map{JSONObject().put("id",it.outputID).put("scope",JSONArray(listOf(it.range.start,it.range.end)))}))})
                        val ev=JSONObject().put("trace",tr).put("recognitions",mask).put("admission",JSONArray(packed.audit.toString()));val eh=SwahiliStarterLookup.sha(ev.toString().toByteArray());if(!evidence.has(eh))evidence.put(eh,ev)
                        val o=JSONObject().put("spans",spans(b.partial)).put("mixed",b.partial?.let{ImmersionText.project(it)} ?: text).put("references",JSONArray(b.partial?.references?.map{z->JSONObject().put("scope",JSONArray(listOf(z.start,z.end))).put("output_id",z.outputID).put("reference_id",z.referenceId).put("pack_sha",z.catalogSha256).put("native_cost",z.nativeSourceTokens)} ?: emptyList<JSONObject>()));val oh=SwahiliStarterLookup.sha(o.toString().toByteArray());if(!outputs.has(oh))outputs.put(oh,o)
                        val budget=if(density>0)maxOf(1,(native.size*density).toInt()) else 0;check((b.partial?.references?.sumOf{requireNotNull(it.nativeSourceTokens)} ?: 0)<=budget)
                        if(density==.25) { same(reference.getJSONArray("b_direct"),spans(b.partial));same(reference.getJSONArray("a_direct"),spans(a.partial));assertEquals(reference.getJSONArray("trace").toString(),tr.toString());parity++ }
                        if(density==0.0 || state==2)check(b.partial==null)
                        steps.put(JSONObject().put("density_bits",java.lang.Long.toHexString(bits)).put("budget",budget).put("output",oh).put("evidence",eh).put("elapsed_ms",(SystemClock.elapsedRealtimeNanos()-start)/1e6));evaluations++
                    }
                    val row=JSONObject().put("pair","en-$target").put("id",id).put("known_state",state).put("known_ids",old.getJSONArray("known_ids")).put("source",text).put("native_words",old.getJSONArray("native_words")).put("stratum",old.getString("stratum")).put("steps",steps).put("outputs",outputs).put("evidence",evidence)
                    output.appendText(row.toString()+"\n");check(output.length()<=32*1024*1024);completed++;if(completed%32==0)save(false)
                }
            }
        }
        check(completed==768 && parity==768);save(true)
    }
}
