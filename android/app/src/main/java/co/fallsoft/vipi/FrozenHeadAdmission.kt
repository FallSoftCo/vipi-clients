package co.fallsoft.vipi
import co.fallsoft.vipi.FrozenContextTokenizer.Range
import co.fallsoft.vipi.core.ImmersionEngine
import org.json.JSONArray
import org.json.JSONObject
import org.json.JSONTokener

/** Current tuple evidence. It is not SourceLookupEvidence or display admission. */
internal class FrozenHeadAdmission(private val tokenizer:FrozenContextTokenizer,private val sourceCase:FrozenSourceCase) {
    data class KeyScope(val original:String,val focus:Range,val keys:List<String>,val identity:String,val basis:String)
    data class HeadEvidence(val headID:String,val originalContext:Range?,val target:String,val readingsJSON:String,
        val supportedTuples:List<FrozenContextTupleEvidence.Link>,val rejectionReasons:List<String>){val conditionallyEligible get()=rejectionReasons.isEmpty() && supportedTuples.isNotEmpty()}
    data class Assessment(val original:String,val focus:Range,val packSHA256:String,val keyScopeIdentity:String,val keyScopeBasis:String,
        val chosenRuleID:String?,val learnedContext:Range?,val classification:String,val knowledgeIDs:List<String>,
        val heads:List<HeadEvidence>,val rejectionReasons:List<String>,val qualificationLimits:List<String>)
    fun assess(pack:FrozenContextPackReader,original:String,focus:Range,keyScope:KeyScope,recognition:LexicalSourceRecognition.Snapshot,
        role:EnglishRoleEvidence,knownFamilyIDs:List<String>):Assessment {
        require(original.length<=16384 && knownFamilyIDs.size<=65536 && knownFamilyIDs.all{it.isNotEmpty() && it.toByteArray().size<=4096} && keyScope.keys.size<=256 && keyScope.identity.isNotEmpty() && keyScope.identity.toByteArray().size<=256 && keyScope.basis.toByteArray().size<=1024)
        val reasons=mutableListOf<String>()
        val limits=listOf("Conditional research evidence only; no meaning/display certification","Android source geometry/POS differs from Apple and frozen observations","Generic name detection unavailable; tuple support retained separately","No fallback after fixed winner")
        fun finish(w:FrozenContextPackReader.Match?,category:String="unassessed",knowledge:List<String> = emptyList(),heads:List<HeadEvidence> = emptyList())=Assessment(original,focus,pack.contentSHA256,keyScope.identity,keyScope.basis,w?.rule?.id,w?.contextRange,category,knowledge,heads,reasons.toList(),limits)
        if(keyScope.original!=original || keyScope.focus!=focus || !LexicalSourceRecognition.valid(focus,original)){reasons+="invalid_or_stale_key_scope";return finish(null)}
        val native=LocalImmersion.words(original,"en").map{Range(it.first,it.last+1)}
        val metadata=JSONObject(pack.metadata.getValue("dictionary_en_metadata_json"))
        fun id(k:String)=JSONTokener(metadata.getString(k)).nextValue() as String
        if(!role.matches(original,"en",native,recognition.suppliedProtection,SourceContextAssetPins.models) ||
            !recognition.matches(original,"en",id("release_id"),id("source_inventory_sha256"),role.suppliedProtection) || focus !in native){reasons+="snapshot_or_dictionary_identity_mismatch";return finish(null)}
        val winner=pack.assess(original,native,focus,keyScope.keys).winner
        if(winner==null){reasons+="no_qualified_context_rule";return finish(null)}
        val source=original.substring(focus.start,focus.end)
        val words=tokenizer.tokenize(source).filter{tokenizer.originalHasAlphabeticScalar(it.original)}.map{it.normalized}
        val nonfunction=words.filter{!pack.candidateClassifier.isFunction(it)};val anchors=nonfunction.filter{pack.candidateClassifier.roles(it).intersect(setOf("noun","adj","adv","verb")).isNotEmpty()}
        val category=if(anchors.isNotEmpty())"content" else if(nonfunction.isNotEmpty())"unresolved" else "function"
        val knowledge=nonfunction.map{pack.candidateClassifier.family(it)?:"unmapped:$it"}.toSet().sorted()
        if(knowledge.isNotEmpty() && knowledge.all{it in knownFamilyIDs})reasons+="known_families"
        if(category!="content")reasons+="not_content_classified"
        if(!sourceCase.isLower(source))reasons+="requires_lowercase_source"
        val observations=role.observations.filter{it.range==focus}
        if(role.status!=EnglishRoleEvidence.Status.READY || observations.size!=1 || observations.firstOrNull()?.role!=EnglishRoleEvidence.Role.NOUN)reasons+="actual_android_noun_unavailable"
        if(role.namedProtection==EnglishRoleEvidence.NamedProtection.UNAVAILABLE)reasons+="native_name_protection_unavailable"
        if(observations.firstOrNull()?.overlapsSuppliedProtection!=false)reasons+="source_role_or_name_protection"
        if(recognition.hasStructuralProtection(focus))reasons+="native_source_structural_protection"
        if(role.suppliedProtection.any{FrozenCandidateProducer.overlap(it,focus)})reasons+="supplied_or_detected_name_protection"
        val units=recognition.units.filter{it.range==focus}
        if(units.isEmpty()){reasons+="no_current_dictionary_focus";return finish(winner,category,knowledge)}
        if(units.none{it.hasNameGuard && it.sourceBlocked && !it.targetBlocked})reasons+="not_source_name_only_guard"
        if(units.any{it.targetBlocked || (it.sourceBlocked && !it.hasNameGuard)})reasons+="other_current_dictionary_guard"
        val windows=ReviewedFrameLookup.windows(original,"en")
        if(windows==null){reasons+="native_context_window_unavailable";return finish(winner,category,knowledge)}
        val contextWindows=windows.values.flatten().map{Range(it.first,it.last+1)}.toSet();val tokens=tokenizer.tokenize(original);val position=tokens.indexOfFirst{it.range==focus}
        if(position<0){reasons+="not_exact_single_research_token";return finish(winner,category,knowledge)}
        val evidence=mutableListOf<HeadEvidence>()
        for(headID in winner.rule.headIDs){
            val head=pack.heads.getValue(headID);val rejected=reasons.toMutableList();var context:Range?=null;val supported=mutableListOf<FrozenContextTupleEvidence.Link>()
            if(head.focusEnd-head.focusStart!=1)rejected+="not_single_token_original_head"
            val start=position-head.focusStart;val after=start+head.tokens.size
            if(start>=0 && after<=tokens.size && head.focusEnd-head.focusStart==1){val actual=tokens.subList(start,after);val r=Range(tokens[start].range.start,tokens[after-1].range.end)
                if(actual.map{it.normalized}==head.tokens && tokenizer.normalize(original.substring(r.start,r.end))==head.sourceKey && r in contextWindows)context=r}
            if(context==null)rejected+="original_head_context_missing_or_not_native_window"
            if("noun" !in FrozenCandidateProducer.strings(JSONArray(head.posJSON)))rejected+="original_head_noun_role_missing"
            if(head.target!=winner.rule.target)rejected+="head_target_not_winner"
            if(tokenizer.normalize(source)==tokenizer.normalize(head.target))rejected+="identical_target_face"
            if(head.target.trim().isEmpty())rejected+="empty_target_face"
            for(link in pack.tupleEvidence.linksByRuleHead[winner.rule.id to headID].orEmpty()){
                val sf=pack.tupleEvidence.forms.getValue(link.sourceFormID);val tf=pack.tupleEvidence.forms.getValue(link.targetFormID)
                val st=pack.tupleEvidence.terms.getValue(link.sourceTermID);val tt=pack.tupleEvidence.terms.getValue(link.targetTermID)
                if(!(sf.language=="en" && tf.language=="es" && sf.pos=="noun" && tf.pos=="noun" && sf.complete && tf.complete && sf.mode in 1..2 && tf.mode in 1..2 && sf.number==tf.number && sf.reasons==setOf("dictionary_guard") && tf.reasons.isEmpty() && sf.targetSafe && tf.targetSafe && st.eligible && tt.eligible && st.explicit && tt.explicit && st.reasons.isEmpty() && tt.reasons.isEmpty() && st.senseID==tt.senseID && ImmersionEngine.lookupKey(tf.surface)==ImmersionEngine.lookupKey(head.target) && ImmersionEngine.lookupKey(sf.surface)==ImmersionEngine.lookupKey(source)))continue
                val current=units.flatMap{it.forms}.any{f->f.intrinsicRange==sf.range && f.lexemeID==sf.lexeme.toString() && f.written==sf.surface && f.number==sf.number && f.mode==sf.mode && f.features==sf.features && f.partOfSpeech==sf.pos && f.sourceSafe==sf.sourceSafe && f.targetSafe==sf.targetSafe}
                if(!current || (sf.surface!=source && sourceCase.firstIsUpper(sf.surface)))continue
                supported+=link
            }
            if(supported.isEmpty())rejected+="no_exact_original_supported_form_term_tuple"
            evidence+=HeadEvidence(headID,context,head.target,head.readingsJSON,supported,rejected.toSet().sorted())
        }
        if(winner.rule.headIDs.isEmpty())reasons+="winner_has_no_supported_original_head"
        return finish(winner,category,knowledge,evidence)
    }
}
