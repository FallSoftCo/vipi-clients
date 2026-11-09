package co.fallsoft.vipi

import co.fallsoft.vipi.FrozenContextTokenizer.Range
import co.fallsoft.vipi.core.ImmersionEngine
import org.json.JSONObject
import org.json.JSONTokener

/** Research adapter over the existing immutable owner. No chat call site or output permission. */
internal class FrozenNativeCandidateProvider(private val owner:SourceContextEvidenceOwner,
    private val catalog:FrozenCandidateCatalog,private val tokenizer:FrozenContextTokenizer,
    private val sourceCase:FrozenSourceCase) {
    data class Snapshot(val input:FrozenCandidateProducer.Input,val recognition:LexicalSourceRecognition.Snapshot,val role:EnglishRoleEvidence)
    data class Prepared(val snapshot:Snapshot,val output:FrozenCandidateProducer.Output,val dictionarySHA256:String,
        val qualifiedIndices:List<Int>,val currentEvidence:Map<String,FrozenHeadAdmission.Assessment>)
    private val producer=FrozenCandidateProducer(tokenizer,sourceCase)
    fun prepare(original:String,suppliedProtection:List<Range>):Prepared {
        val expected=catalog.metadata.getValue("dictionary_en_sha256")
        return owner.withCandidateDependencies(expected){pack,db->
            require(pack.contentSHA256==catalog.contextPackSHA256)
            val inspection=owner.inspect(original,emptyMap(),suppliedProtection)
            require(inspection is SourceContextEvidenceOwner.Inspection.Evidence){"Native source evidence unavailable"}
            val recognition=inspection.recognition;val role=inspection.roles;val words=inspection.nativeWords
            val meta=JSONObject(catalog.metadata.getValue("dictionary_en_metadata_json"))
            fun value(key:String)=JSONTokener(meta.getString(key)).nextValue() as String
            require(recognition.matches(original,"en",value("release_id"),value("source_inventory_sha256"),suppliedProtection))
            require(role.matches(original,"en",words,suppliedProtection,SourceContextAssetPins.models))
            val windows=checkNotNull(ReviewedFrameLookup.windows(original,"en")){"Native windows unavailable"}
                .values.flatten().map{Range(it.first,it.last+1)}.sortedWith(FrozenCandidateProducer.rangeOrder)
            val roles=role.observations.associate{ob->ob.range to FrozenCandidateProducer.Observation(
                ob.rawTag?.let{listOf(it,ob.rawScore)},if(role.status==EnglishRoleEvidence.Status.READY)when(ob.rawTag){"NOUN"->"noun";"ADJ"->"adj";"ADV"->"adv";else->null}else null)}
            val masks=recognition.phraseRanges.mapIndexed{i,r->mapOf<String,Any?>("unit_id" to "native-phrase-$i","utf16" to FrozenCandidateProducer.pair(r))}+
                recognition.units.mapIndexedNotNull{i,u->if(u.protectsInner)mapOf<String,Any?>("unit_id" to "native-unit-$i","utf16" to FrozenCandidateProducer.pair(u.range))else null}
            val guards=mutableSetOf<Range>()
            for(unit in recognition.units){
                if(!unit.hasNameGuard || !unit.sourceBlocked || unit.targetBlocked || unit.range !in words ||
                    unit.forms.none{it.partOfSpeech=="noun" && it.mode in 1..2 && it.intrinsicRange==Range(0,it.written.length)})continue
                db.rawQuery("SELECT blocked,target_blocked,reason FROM guards WHERE normalized=?",arrayOf(ImmersionEngine.lookupKey(unit.original))).use{c->
                    if(c.moveToFirst() && c.getInt(0)!=0 && c.getInt(1)==0 && c.getString(2)=="name")guards+=unit.range
                }
            }
            val input=FrozenCandidateProducer.Input(original,words,windows,suppliedProtection+recognition.namedPlaces,masks,roles,guards,
                "Actual Android dictionary/OpenNLP/window snapshot; generic name protection unavailable; no display approval")
            val snapshot=Snapshot(input,recognition,role);val output=producer.produce(input,catalog,pack)
            val current=linkedMapOf<String,FrozenHeadAdmission.Assessment>();val conditional=mutableSetOf<Int>()
            val admission=FrozenHeadAdmission(tokenizer,sourceCase)
            for((focusKey,gate) in output.gates){
                val indices=(gate.getValue("candidate_indices") as List<*>).map{(it as Number).toInt()}
                val focus=FrozenCandidateProducer.range(output.candidates[indices.first()]["focus_utf16"])
                val keys=(gate.getValue("source_keys") as List<*>).map{it as String}
                val scope=FrozenHeadAdmission.KeyScope(original,focus,keys,output.inputIdentity,input.basis)
                val evidence=admission.assess(pack,original,focus,scope,recognition,role,emptyList())
                require(evidence.chosenRuleID==gate["chosen_rule_id"]){"Current tuple assessment changed fixed winner"}
                current[focusKey]=evidence
                val supported=evidence.heads.filter{it.conditionallyEligible}.map{it.headID}.toSet()
                conditional+=output.qualifiedIndices.filter{it>=output.ordinaryCount && it in indices && output.candidates[it]["head_id"] in supported}
            }
            Prepared(snapshot,output,expected,output.qualifiedIndices.filter{it<output.ordinaryCount || it in conditional},current.toMap())
        }
    }
    fun select(prepared:Prepared,knownFamilyIDs:Set<String>,withholdFunction:Boolean,density:Double):Map<String,Any?> {
        require(prepared.dictionarySHA256==catalog.metadata.getValue("dictionary_en_sha256"))
        return producer.select(prepared.output,prepared.snapshot.input,prepared.qualifiedIndices,knownFamilyIDs,withholdFunction,density,catalog.bundleIdentity)
    }
}
