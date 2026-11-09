package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Test
import org.junit.runner.RunWith
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.json.JSONObject
import org.json.JSONArray
import java.io.File
import co.fallsoft.vipi.FrozenContextTokenizer.Range

@RunWith(AndroidJUnit4::class)
class FrozenCandidateQualificationTest {
    private fun decode(v:Any?):Any?=when(v){JSONObject.NULL,null->null;is JSONObject->v.keys().asSequence().associateWith{decode(v.get(it))};is JSONArray->(0 until v.length()).map{decode(v.get(it))};else->v}
    private fun ranges(a:JSONArray)=(0 until a.length()).map{val r=a.getJSONArray(it);Range(r.getInt(0),r.getInt(1))}
    private fun memory():Map<String,Any?> {
        val rt=Runtime.getRuntime();val p=android.os.Debug.MemoryInfo();android.os.Debug.getMemoryInfo(p)
        return mapOf("java_used_bytes" to rt.totalMemory()-rt.freeMemory(),"pss_kib" to p.totalPss,"proc_status" to File("/proc/self/status").readLines().filter{it.startsWith("VmHWM:")||it.startsWith("VmRSS:")})
    }
    @Test fun frozenAndActual() {
        val inst=InstrumentationRegistry.getInstrumentation();val ctx=inst.targetContext
        val root=File(InstrumentationRegistry.getArguments().getString("sourceContextInputs")!!).canonicalFile
        require(root.canonicalPath.startsWith(ctx.filesDir.canonicalPath+"/"))
        val owner=SourceContextEvidenceOwner(ctx.assets,File(root,"context.sqlite"),File(root,"d-en.sqlite"),File(root,"d-es.sqlite"))
        val begin=System.nanoTime();val before=memory()
        try {
            check(owner.initialize().phase==SourceContextEvidenceOwner.Phase.READY)
            val tokenizer=FrozenContextTokenizer(ctx.assets.open("source-context/unicode15.json").use{it.readBytes()})
            val sourceCase=FrozenSourceCase(File(root,"source-case-unicode15.json").readBytes(),"12412ea3f7de5e1246d9701574303b045a3a0bde2eab2cd339158e69d059c52a")
            val referenceFile=File(root,"reference.json");require(FrozenCandidateCatalog.digest(referenceFile,16L shl 20)=="34048ad4a8754c4097d0bf7c7a7eeddc4245df24817b4206a8f78381f9782be3")
            val reference=JSONObject(referenceFile.readText());val family=FrozenCandidateProducer.strings(reference.getJSONArray("frozen_test_family_order")).take(300).toSet()
            owner.withCandidateDependencies("5b16dafff9b2a27474792104bad11195ba8aff2236c134cf0265257b92727d68"){pack,db->
                FrozenCandidateCatalog(File(root,"catalog.sqlite"),File(root,"manifest.json"),"9c0d7af245a599bfaadc07dc6fb84c41a3bf72b5e657adcee0b7b68efa96a281",pack).use{catalog->
                    val initialized=System.nanoTime()-begin;val producer=FrozenCandidateProducer(tokenizer,sourceCase)
                    val provider=FrozenNativeCandidateProvider(owner,catalog,tokenizer,sourceCase)
                    fun result(input:FrozenCandidateProducer.Input,out:FrozenCandidateProducer.Output,elapsed:Long):Map<String,Any?> {
                        fun rejects(changed:FrozenCandidateProducer.Input,bundle:String=catalog.bundleIdentity):Boolean {
                            return try{producer.select(out,changed,out.qualifiedIndices,emptySet(),false,.25,bundle);false}catch(e:IllegalArgumentException){true}
                        }
                        check(rejects(input.copy(original="#"+input.original.drop(1))))
                        check(rejects(input.copy(protected=input.protected+Range(0,1))))
                        check(rejects(input,"0".repeat(64)))
                        val selections=linkedMapOf<String,Any?>()
                        for((name,known) in listOf("all_function" to emptySet(),"all_function_global300" to family)){
                            val base=out.candidates.indices.filter{it<out.ordinaryCount && (out.candidates[it]["filter_reasons"] as List<*>).isEmpty()}
                            val all=out.candidates.indices.filter{(out.candidates[it]["filter_reasons"] as List<*>).isEmpty()}
                            selections[name]=mapOf("baseline" to producer.select(out,input,base,known,true,.25,catalog.bundleIdentity),"experimental" to producer.select(out,input,all,known,true,.25,catalog.bundleIdentity),"qualified" to producer.select(out,input,out.qualifiedIndices,known,true,.25,catalog.bundleIdentity))
                        }
                        return mapOf("candidates" to out.candidates,"baseline_candidate_count" to out.ordinaryCount,"geometry_rejections" to out.geometryRejections,"experimental_geometry_rejections" to out.conditionalGeometryRejections,"gates" to out.gates,"selections" to selections,"empty_actual_known_selection" to producer.select(out,input,out.qualifiedIndices,emptySet(),false,.25,catalog.bundleIdentity),"elapsed_ns" to elapsed,"input_identity" to out.inputIdentity,"bundle_identity" to out.bundleIdentity,"stale_text_rejected" to true,"changed_protection_rejected" to true,"changed_bundle_rejected" to true,"native_words_utf16" to input.words.map{FrozenCandidateProducer.pair(it)},"protected_ranges_utf16" to input.protected.map{FrozenCandidateProducer.pair(it)},"source_masks" to input.sourceMasks,"basis" to input.basis)
                    }
                    val rows=reference.getJSONArray("cases");check(rows.length()==52);val records=mutableListOf<Map<String,Any?>>()
                    for(i in 0 until rows.length()){
                        val row=rows.getJSONObject(i);val text=row.getString("original");val words=ranges(row.getJSONArray("native_words_utf16"));val protection=ranges(row.getJSONArray("protected_ranges_utf16"));val roles=linkedMapOf<Range,FrozenCandidateProducer.Observation>()
                        val candidates=row.getJSONArray("candidates")
                        for(j in 0 until candidates.length()){val c=candidates.getJSONObject(j);val role=c.getJSONObject("role");roles[ranges(JSONArray().put(c.getJSONArray("focus_utf16"))).single()]=FrozenCandidateProducer.Observation(decode(role.opt("raw")) as? List<Any?>,decode(role.opt("mapped")) as? String)}
                        val guards=words.filter{r->db.rawQuery("SELECT blocked,target_blocked,reason FROM guards WHERE normalized=?",arrayOf(tokenizer.normalize(text.substring(r.start,r.end)))).use{c->c.moveToFirst() && c.getInt(0)!=0 && c.getInt(1)==0 && c.getString(2)=="name"}}.toSet()
                        @Suppress("UNCHECKED_CAST") val masks=decode(row.getJSONArray("source_masks")) as List<Map<String,Any?>>
                        val input=FrozenCandidateProducer.Input(text,words,ranges(row.getJSONArray("native_windows_utf16")),protection,masks,roles,guards,"Frozen geometry/masks/OpenNLP observations; actual immutable dictionary guard read; diagnostic only")
                        val tick=System.nanoTime();val out=producer.produce(input,catalog,pack);val diagnostic=result(input,out,System.nanoTime()-tick)
                        val nativeTick=System.nanoTime();val prepared=provider.prepare(text,protection);val native=result(prepared.snapshot.input,prepared.output,System.nanoTime()-nativeTick)
                        val evidence=prepared.currentEvidence.mapValues{(_,a)->mapOf("chosen_rule_id" to a.chosenRuleID,"rejection_reasons" to a.rejectionReasons,"heads" to a.heads.map{h->mapOf("head_id" to h.headID,"supported_tuple_count" to h.supportedTuples.size,"conditionally_eligible" to h.conditionallyEligible,"rejection_reasons" to h.rejectionReasons)},"qualification_limits" to a.qualificationLimits)}
                        records+=mapOf("case_id" to row.getString("case_id"),"diagnostic" to diagnostic,"actual" to native,"current_evidence" to evidence,"current_qualified_indices" to prepared.qualifiedIndices,"current_empty_known_selection" to provider.select(prepared,emptySet(),false,.25))
                    }
                    val output=mapOf("cases" to records,"identity_preparation_ns" to initialized,"whole_probe_ns" to System.nanoTime()-begin,"manifest_sha256" to catalog.manifestSHA256,"catalog_sha256" to catalog.sha256,"bundle_identity" to catalog.bundleIdentity,"memory_before" to before,"memory_after" to memory(),"limits" to "Frozen observations establish implementation parity only. Actual Android generic name protection unavailable. No display approval or activation.")
                    val bytes=FrozenCandidateProducer.canonical(output).toByteArray();check(bytes.size<=16*1024*1024)
                    File(root,"output.json").outputStream().use{it.write(bytes)}
                    inst.sendStatus(0,android.os.Bundle().apply{putString("stream","CANDIDATE_QUALIFICATION cases=52 bytes=${bytes.size}\n")})
                }
            }
            check(owner.status().phase==SourceContextEvidenceOwner.Phase.READY)
        }finally{owner.close()}
    }
}
