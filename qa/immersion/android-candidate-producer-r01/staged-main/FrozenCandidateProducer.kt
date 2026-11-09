package co.fallsoft.vipi
import co.fallsoft.vipi.FrozenContextTokenizer.Range
import org.json.JSONArray
import org.json.JSONObject
import java.util.Base64

/** Frozen parity producer, separate from current-tuple diagnostics and display. */
internal class FrozenCandidateProducer(private val tokenizer:FrozenContextTokenizer,private val sourceCase:FrozenSourceCase) {
    data class Observation(val raw:List<Any?>?,val mapped:String?)
    data class Input(val original:String,val words:List<Range>,val windows:List<Range>,val protected:List<Range>,
        val sourceMasks:List<Map<String,Any?>>,val roles:Map<Range,Observation>,val sourceNameOnlyGuards:Set<Range>,val basis:String)
    data class Output(val inputIdentity:String,val bundleIdentity:String,val candidates:List<Map<String,Any?>>,
        val ordinaryCount:Int,val geometryRejections:List<Map<String,Any?>>,val conditionalGeometryRejections:List<Map<String,Any?>>,
        val gates:Map<String,Map<String,Any?>>,val qualifiedIndices:List<Int>)
    fun produce(input:Input,catalog:FrozenCandidateCatalog,pack:FrozenContextPackReader):Output {
        require(pack.contentSHA256==catalog.contextPackSHA256)
        val text=input.original
        require(text.length<=16384 && input.words.size<=16384 && input.windows.size<=65536 && input.protected.size<=4096 && input.sourceMasks.size<=16384 && input.basis.isNotEmpty())
        val offsets=linkedMapOf(0 to 0);var offset=0;var scalar=0
        while(offset<text.length){val cp=text.codePointAt(offset);require(cp !in 0xd800..0xdfff);offset+=Character.charCount(cp);offsets[offset]=++scalar}
        var last=0
        for(r in input.words){require(r.start>=last && r.end>r.start && r.start in offsets && r.end in offsets);last=r.end}
        for(r in input.windows+input.protected)require(r.start>=0 && r.end>r.start && r.start in offsets && r.end in offsets)
        require(input.windows==input.windows.sortedWith(rangeOrder) && input.windows.toSet().size==input.windows.size)
        val tokens=tokenizer.tokenize(text);val starts=tokens.mapIndexed{i,t->t.range.start to i}.toMap();val ends=tokens.mapIndexed{i,t->t.range.end to i+1}.toMap()
        val cs=mutableListOf<Map<String,Any?>>();val rejected=mutableListOf<Map<String,Any?>>();val conditionalRejected=mutableListOf<Map<String,Any?>>()
        var ordinaryCount=0
        for(ordinary in listOf(true,false)) {
            for(window in input.windows) {
                val key=tokenizer.normalize(text.substring(window.start,window.end))
                for(head in catalog.heads(key,ordinary)) {
                    val record=head.record
                    fun reject(reason:String){val r=mapOf("head" to head.id,"window" to pair(window),"reason" to reason);if(ordinary)rejected+=r else conditionalRejected+=r}
                    val first=starts[window.start];val end=ends[window.end]
                    if(first==null || end==null){reject("training_token_boundary");continue}
                    val actual=tokens.subList(first,end)
                    if(actual.map{it.normalized}!=strings(record.getJSONArray("source_context_token_text"))){reject("context_token_sequence");continue}
                    val relative=ints(record.getJSONArray("source_focus_relative_tokens"));require(relative.size==2 && relative[0]>=0 && relative[1]>relative[0] && relative[1]<=actual.size)
                    val focus=Range(actual[relative[0]].range.start,actual[relative[1]-1].range.end);val (cost,error)=cost(focus,input.words)
                    if(error!=null){reject(error);continue}
                    val original=text.substring(focus.start,focus.end);val norm=tokenizer.normalize(original)
                    val words=tokenizer.tokenize(original).filter{tokenizer.originalHasAlphabeticScalar(it.original)}.map{it.normalized}
                    val nonfunction=words.filter{!pack.candidateClassifier.isFunction(it)}
                    val anchors=nonfunction.filter{pack.candidateClassifier.roles(it).intersect(setOf("noun","adj","adv","verb")).isNotEmpty()}
                    val category=if(anchors.isNotEmpty())"content" else if(nonfunction.isNotEmpty())"unresolved" else "function"
                    val knowledge=nonfunction.map{pack.candidateClassifier.family(it)?:"unmapped:$it"}.toSet().sorted()
                    val role=input.roles[focus];val reasons=mutableListOf<String>()
                    if(relative[1]-relative[0]!=1 || cost!=1)reasons+="not_single_token_head"
                    if(role?.mapped==null)reasons+="role_unassessed" else if(role.mapped !in strings(record.getJSONArray("source_pos")))reasons+="role_conflict"
                    if(category!="content")reasons+="not_content_classified"
                    val target=record.getString("target_face");val readings=record.getJSONArray("head_readings");val fixed=record.getBoolean("fixed")
                    if(!ordinary){
                        if(role?.mapped!="noun")reasons+="rescue_requires_actual_NOUN"
                        if(category!="content")reasons+="rescue_requires_content"
                        if(cost!=1 || "not_single_token_head" in reasons)reasons+="rescue_requires_exact_single_token"
                        if(!sourceCase.isLower(original))reasons+="rescue_requires_lowercase_source"
                        if(focus !in input.sourceNameOnlyGuards)reasons+="rescue_requires_exact_current_source_name_guard"
                    }
                    cs+=linkedMapOf("id" to "${head.id}@${window.start}:${window.end}","head_id" to head.id,"context_id" to head.contextID,
                        "fixed" to fixed,"focus_utf16" to pair(focus),"context_utf16" to pair(window),"source" to original,"target" to target,
                        "reading" to (0 until readings.length()).mapNotNull{readings.getJSONObject(it).opt("text") as? String}.toSet().sorted(),
                        "identical_face" to (tokenizer.normalize(target)==norm),"category" to category,"content_anchor_words" to anchors,
                        "knowledge_ids" to knowledge,"concept_id" to (pack.candidateClassifier.family(norm)?:"lexical:$norm"),"train_rank" to head.rank,
                        "cost" to requireNotNull(cost),"source_key" to key,"context_native_cost" to input.words.count{it.start>=window.start && it.end<=window.end},
                        "role" to mapOf("raw" to role?.raw,"mapped" to role?.mapped),"filter_reasons" to reasons.toList(),
                        "output_codepoints" to listOf(offsets.getValue(focus.start),offsets.getValue(focus.end)))
                    require(cs.size<=65536)
                }
            }
            if(ordinary)ordinaryCount=cs.size
        }
        val groups=linkedMapOf<Range,MutableList<Int>>();val keep=mutableListOf<Int>();val gates=linkedMapOf<String,Map<String,Any?>>()
        for((i,c) in cs.withIndex())if((c.getValue("filter_reasons") as List<*>).isEmpty()){
            if(i<ordinaryCount)keep+=i else groups.getOrPut(range(c.getValue("focus_utf16"))){mutableListOf()}.add(i)
        }
        for(focus in groups.keys.sortedWith(rangeOrder)) {
            val indices=groups.getValue(focus);val keys=indices.flatMap{catalog.keys(cs[it].getValue("head_id") as String)}.toSet().sorted()
            val match=pack.assess(text,input.words,focus,keys);val winner=match.winner
            val admitted=indices.filter{winner!=null && cs[it]["head_id"] in winner.rule.headIDs && cs[it]["target"]==winner.rule.target}
            keep+=admitted;gates["[${focus.start},${focus.end}]"]=linkedMapOf("candidate_indices" to indices.toList(),"admitted_indices" to admitted,
                "source_keys" to keys,"chosen_rule_id" to winner?.rule?.id,"chosen_context_utf16" to winner?.contextRange?.let(::pair),
                "reason" to if(admitted.isNotEmpty())"qualified_context" else if(winner==null)"no_qualified_multiword_context" else "winner_without_original_supported_head")
        }
        return Output(identity(input),catalog.bundleIdentity,cs.toList(),ordinaryCount,rejected.toList(),conditionalRejected.toList(),gates.toMap(),keep.sorted())
    }
    companion object {
        val rangeOrder=compareBy<Range>{it.start}.thenBy{it.end-it.start}
        fun pair(r:Range)=listOf(r.start,r.end)
        fun range(value:Any?):Range {val v=value as List<*>;require(v.size==2);return Range((v[0] as Number).toInt(),(v[1] as Number).toInt())}
        fun strings(a:JSONArray)=(0 until a.length()).map{a.getString(it)}
        fun ints(a:JSONArray)=(0 until a.length()).map{a.getInt(it)}
        fun overlap(a:Range,b:Range)=a.start<b.end && b.start<a.end
        fun cost(r:Range,words:List<Range>):Pair<Int?,String?> {
            val inside=words.filter{overlap(r,it)}
            if(inside.isEmpty())return null to "no_native_words"
            if(inside.any{it.start<r.start || it.end>r.end})return null to "partial_native_word"
            if(inside.first().start!=r.start || inside.last().end!=r.end)return null to "not_exact_native_boundaries"
            return inside.size to null
        }
        fun canonical(value:Any?):String=when(value){
            null,JSONObject.NULL->"null"
            is String->JSONObject.quote(value)
            is Boolean,is Number->value.toString()
            is Map<*,*>->value.keys.map{it as String}.sorted().joinToString(",","{","}"){JSONObject.quote(it)+":"+canonical(value[it])}
            is Iterable<*>->value.joinToString(",","[","]"){canonical(it)}
            else->error("Unsupported canonical input")
        }
        fun identity(input:Input):String {
            val roles=input.roles.keys.sortedWith(rangeOrder).map{mapOf("range" to pair(it),"raw" to input.roles.getValue(it).raw,"mapped" to input.roles.getValue(it).mapped)}
            val value=mapOf("original_utf8" to Base64.getEncoder().encodeToString(input.original.toByteArray()),"words" to input.words.map(::pair),"windows" to input.windows.map(::pair),"protected" to input.protected.map(::pair),"masks" to input.sourceMasks,"roles" to roles,"guards" to input.sourceNameOnlyGuards.sortedWith(rangeOrder).map(::pair),"basis" to input.basis)
            val bytes=canonical(value).toByteArray();require(bytes.size<=(16 shl 20))
            return FrozenCandidateCatalog.hash(Base64.getEncoder().encodeToString(bytes))
        }
    }
}
