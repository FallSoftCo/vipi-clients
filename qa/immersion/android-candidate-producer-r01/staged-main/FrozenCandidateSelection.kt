package co.fallsoft.vipi
import co.fallsoft.vipi.FrozenContextTokenizer.Range
import co.fallsoft.vipi.FrozenCandidateProducer.Companion.cost
import co.fallsoft.vipi.FrozenCandidateProducer.Companion.range
import co.fallsoft.vipi.FrozenCandidateProducer.Companion.overlap

/** Caller-known IDs are mandatory input. No frequency-derived production default. */
internal fun FrozenCandidateProducer.select(output:FrozenCandidateProducer.Output,input:FrozenCandidateProducer.Input,
    indices:List<Int>,knownFamilyIDs:Set<String>,withholdFunction:Boolean,density:Double,expectedBundleIdentity:String):Map<String,Any?> {
    require(expectedBundleIdentity.matches(Regex("[0-9a-f]{64}")) && output.bundleIdentity==expectedBundleIdentity)
    require(output.inputIdentity==FrozenCandidateProducer.identity(input))
    require(density.isFinite() && density>0 && density<=1 && knownFamilyIDs.size<=65536 && indices.size<=65536 && indices.toSet().size==indices.size && indices.all{it in output.candidates.indices})
    val cs=output.candidates;val budget=maxOf(1,kotlin.math.floor(input.words.size*density).toInt())
    val masks=input.sourceMasks.map { m ->require((m["unit_id"] as? String)?.isNotEmpty()==true);range(m["utf16"]).also{require(it.start>=0 && it.end>it.start && it.end<=input.original.length)}}
    val admitted=mutableListOf<Int>();val rejected=linkedMapOf<Int,List<String>>();val costs=mutableMapOf<Int,Int>();val depths=mutableMapOf<Int,Int>();val ranges=mutableMapOf<Int,Range>()
    val categories=mapOf("content" to 0,"unresolved" to 1,"function" to 2)
    for(i in indices) {
        val c=cs[i];val focus=range(c["focus_utf16"]);val context=range(c["context_utf16"]);val reasons=mutableListOf<String>()
        if(!(context.start<=focus.start && focus.end<=context.end))reasons+="focus_outside_context"
        val (cost,error)=cost(focus,input.words);val (depth,contextError)=cost(context,input.words)
        if(error!=null)reasons+="focus_$error";if(contextError!=null)reasons+="context_$contextError"
        if(c["identical_face"] as Boolean)reasons+="identical_face"
        if(withholdFunction && c["category"]=="function")reasons+="known_function"
        val knowledge=c["knowledge_ids"] as List<*>
        if(knowledge.isNotEmpty() && knowledge.all{it in knownFamilyIDs})reasons+="known_vocabulary"
        if(input.protected.any{overlap(it,focus)})reasons+="protected_focus"
        if(masks.any{it!=focus && it.start<=focus.start && focus.end<=it.end})reasons+="inside_recognized_source_unit"
        if(reasons.isEmpty()){admitted+=i;costs[i]=requireNotNull(cost);depths[i]=requireNotNull(depth);ranges[i]=focus}else rejected[i]=reasons.toSet().sorted()
    }
    admitted.sortWith(compareByDescending<Int>{depths.getValue(it)}.thenBy{categories.getValue(cs[it]["category"] as String)}
        .thenBy{(cs[it]["train_rank"] as Number).toInt()}.thenByDescending{costs.getValue(it)}.thenBy{ranges.getValue(it).start}.thenBy{cs[it]["id"] as String})
    val over=admitted.filter{costs.getValue(it)>budget};val selected=mutableListOf<Int>();val occupied=mutableListOf<Range>();val concepts=mutableSetOf<String>();var remaining=budget
    for(i in admitted){
        val concept=cs[i]["concept_id"] as String;val reasons=mutableListOf<String>()
        if(concept in concepts)reasons+="repeated_concept"
        if(occupied.any{overlap(it,ranges.getValue(i))})reasons+="overlapping_selected_focus"
        if(costs.getValue(i)>budget)reasons+="over_total_budget" else if(costs.getValue(i)>remaining)reasons+="exceeds_remaining_budget"
        if(reasons.isEmpty()){selected+=i;occupied+=ranges.getValue(i);concepts+=concept;remaining-=costs.getValue(i)}else rejected[i]=reasons
    }
    val mixed=StringBuilder(input.original)
    for(i in selected.sortedByDescending{ranges.getValue(it).start}){val r=ranges.getValue(i);mixed.replace(r.start,r.end,cs[i]["target"] as String)}
    return linkedMapOf("selected_indices" to selected,"pre_budget_indices" to admitted,"budget_only_indices" to over,"budget" to budget,
        "rejected" to rejected.keys.sorted().map{mapOf("index" to it,"reasons" to rejected.getValue(it))},"mixed_output" to mixed.toString())
}
