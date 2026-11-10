package co.fallsoft.vipi

import co.fallsoft.vipi.core.*
import org.json.JSONObject
import org.json.JSONArray

/** Private qualification overlay only. No bundled/default factory calls this adapter. */
internal data class FrameStarterCandidate(val entryID:String,val conceptID:String,val category:String,val rank:Int,val tokenCount:Int,
 val range:SourceLookupRange,val cost:Int,val reason:String?,val unit:SourceReferenceUnit)
internal class FrameContextAdapter(private val bytes:ByteArray,permissionBytes:ByteArray,private val target:String,private val baselineIdentity:String) {
 private val pack=JSONObject(bytes.toString(Charsets.UTF_8));private val patterns=pack.getJSONArray("patterns")
 private val packSHA=JapaneseStarterLookup.sha(bytes);private val permissionSHA=JapaneseStarterLookup.sha(permissionBytes)
 private val permission=JSONObject(permissionBytes.toString(Charsets.UTF_8))
 private val allowed=(0 until permission.getJSONArray("pattern_ids").length()).map{permission.getJSONArray("pattern_ids").getString(it)}.toSet()
 val identity="frame-test-v1:"+JapaneseStarterLookup.sha((packSHA+permissionSHA+baselineIdentity).toByteArray())
 var trace=JSONArray();private set
 init {
  require(pack.getString("schema")=="vipi-source-context-candidate-1" && pack.getString("source")=="en" && pack.getString("target")==target && !pack.getBoolean("runtime_enabled"))
  require(permission.getString("purpose")=="test_only_source_permission_proposal" && !permission.getBoolean("runtime_enabled"))
  require(permission.getJSONObject("pack_sha256").getString("en-$target")==packSHA && patterns.length() in 1..256)
  val ids=(0 until patterns.length()).map{patterns.getJSONObject(it).getString("id")};require(ids.toSet().size==ids.size && allowed.containsAll(ids))
  for(i in 0 until patterns.length()) require(!patterns.getJSONObject(i).getBoolean("source_only_permission"))
 }
 private data class Hit(val pattern:JSONObject,val context:SourceLookupRange,val focus:SourceLookupRange,val contextCost:Int,val cost:Int,val id:String,var reason:String?)
 private fun overlaps(a:SourceLookupRange,b:SourceLookupRange)=a.overlaps(b)
 private fun union(ranges:List<SourceLookupRange>)=SourceLookupRange(ranges.minOf{it.start},ranges.maxOf{it.end})
 private fun nativeCost(words:List<IntRange>,range:SourceLookupRange):Int? {
  val touched=words.filter{it.first<range.end && range.start<=it.last}
  return if(touched.isNotEmpty() && touched.first().first==range.start && touched.last().last+1==range.end && touched.all{it.first>=range.start && it.last<range.end})touched.size else null
 }
 private fun matches(original:String):List<Hit> {
  val words=LocalImmersion.words(original,"en");val hits=mutableListOf<Hit>();val seen=mutableSetOf<String>()
  for(i in 0 until patterns.length()) {
   val p=patterns.getJSONObject(i);val variants=p.getJSONArray("variants")
   require(variants.length() in 1..1024)
   for(j in 0 until variants.length()) {
    val v=variants.getJSONObject(j);val needle=v.getString("context");val rel=v.getJSONArray("focus_utf16");require(needle.isNotEmpty() && needle.length<=256)
    var from=0
    while(from<=original.length-needle.length) {
     val a=original.indexOf(needle,from);if(a<0)break;from=a+1
     val context=SourceLookupRange(a,a+needle.length);val focus=SourceLookupRange(a+rel.getInt(0),a+rel.getInt(1));require(context.contains(focus) && original.substring(focus.start,focus.end)==p.getString("source"))
     val id=p.getString("id")+"@$a:${context.end}:${focus.start}:${focus.end}"
     if(!seen.add(id))continue
     val cc=nativeCost(words,context);val fc=nativeCost(words,focus)
     val reason=if(cc==null || fc==null)"partial_native_word" else if(needle.any{it in ".!?。！？;；\r\n"})"context_barrier" else null
     hits+=Hit(p,context,focus,cc?:0,fc?:0,id,reason);require(hits.size<=4096)
    }
   }
  }
  return hits
 }
 fun geometry(original:String):JSONArray=JSONArray(matches(original).map{h->JSONObject().put("pattern_id",h.pattern.getString("id")).put("context",JSONArray(listOf(h.context.start,h.context.end))).put("focus",JSONArray(listOf(h.focus.start,h.focus.end))).put("reason",h.reason?:JSONObject.NULL)})
 fun resolve(original:String,density:Double,known:Set<String>,baseline:SourceLookupEvidence,raw:List<FrameStarterCandidate>):SourceLookupEvidence {
  require(original.isNotEmpty() && original.length<=16384 && density.isFinite() && density in 0.0..0.75)
  require(baseline.catalogIdentity==baselineIdentity && baseline.isValid(original,"en",target,baselineIdentity))
  trace=JSONArray();val native=LocalImmersion.words(original,"en");val budget=if(density>0)maxOf(1,(native.size*density).toInt())else 0
  val literalRanges=TranslationIntegrity.qaLiteralRanges(original).map{SourceLookupRange(it.first,it.last+1)}
  val hits=matches(original);val hardReasons=setOf("caller_known_concept","native_density_budget","unchanged_normalized_face")
  for(h in hits) {
   if(h.reason!=null)continue
   h.reason=when {
    literalRanges.any{it.overlaps(h.context)} || baseline.recognitions.any{it.mode in setOf(SourceAtomicMode.ATOMIC,SourceAtomicMode.AMBIGUOUS) && it.mask?.overlaps(h.context)==true}->"existing_source_mask"
    raw.any{it.range.overlaps(h.focus) && it.reason!=null && it.reason !in hardReasons}->"existing_starter_source_guard"
    !TranslationIntegrity.preservesIdentifiers(original,original.replaceRange(h.focus.start,h.focus.end,h.pattern.getString("target")))->"full_message_literal_integrity"
    h.pattern.getString("id") !in allowed ->"source_permission_absent"
    h.pattern.getString("source")==h.pattern.getString("target")->"unchanged_face"
    h.pattern.getString("concept_id") in known->"caller_known_concept"
    h.cost>budget->"native_density_budget"
    else->null
   }
  }
  val groups=mutableListOf<MutableList<Hit>>()
  for(h in hits.filter{it.reason !in setOf("partial_native_word","context_barrier")}.sortedWith(compareBy<Hit>{it.focus.start}.thenBy{it.focus.end})) {
   if(groups.isNotEmpty() && h.focus.start<groups.last().maxOf{it.focus.end})groups.last().add(h) else groups.add(mutableListOf(h))
  }
  val frameUnits=mutableListOf<Pair<Hit,SourceReferenceUnit>>();val frameRecognitions=mutableListOf<SourceRecognition>()
  for((n,g) in groups.withIndex()) {
   val ordered=g.sortedWith(compareByDescending<Hit>{it.contextCost}.thenByDescending{it.context.end-it.context.start}.thenByDescending{it.cost}.thenBy{it.focus.start}.thenBy{it.id})
   val best=ordered.first();val top=ordered.filter{it.contextCost==best.contextCost && it.context.end-it.context.start==best.context.end-best.context.start && it.cost==best.cost}
   val choices=top.map{listOf(it.focus.start.toString(),it.focus.end.toString(),it.pattern.getString("meaning"),it.pattern.getString("target"),it.pattern.getString("reading"))}.toSet()
   val ambiguous=choices.size!=1
   for(h in g)if(h !in top && h.reason==null)h.reason="stronger_context_recognized"
   if(ambiguous)for(h in top)h.reason="competing_strongest_contexts"
   val approved=if(!ambiguous && best.reason==null)listOf(SourceApprovedOutput(best.id,best.focus))else emptyList()
   if(approved.isNotEmpty())frameUnits+=best to SourceReferenceUnit(best.focus.start,best.focus.end,original.substring(best.focus.start,best.focus.end),best.pattern.getString("target"),best.pattern.getString("reading").takeIf{it.isNotEmpty()},"frame:$packSHA:${best.pattern.getString("id")}",packSHA,best.cost,best.id)
   frameRecognitions+=SourceRecognition("frame-group-$n",JapaneseStarterLookup.sha(g.map{it.id}.sorted().joinToString("\u0000").toByteArray()),union(g.map{it.context}),union(g.map{it.focus}),if(ambiguous)SourceAtomicMode.AMBIGUOUS else SourceAtomicMode.HEAD_BACKOFF,approved)
  }
  for(h in hits)trace.put(JSONObject().put("pattern_id",h.pattern.getString("id")).put("output_id",h.id).put("context",JSONArray(listOf(h.context.start,h.context.end))).put("focus",JSONArray(listOf(h.focus.start,h.focus.end))).put("reason",h.reason?:JSONObject.NULL))
  val frameMasks=frameRecognitions.mapNotNull{it.mask}
  val ordinary=raw.filter{it.reason==null && frameMasks.none{m->m.overlaps(it.range)}}.sortedWith(compareBy<FrameStarterCandidate>{it.category!="content"}.thenBy{it.rank}.thenByDescending{it.tokenCount}.thenBy{it.range.start})
  val frames=frameUnits.sortedWith(compareByDescending<Pair<Hit,SourceReferenceUnit>>{it.first.contextCost}.thenByDescending{it.first.context.end-it.first.context.start}.thenByDescending{it.first.cost}.thenBy{it.first.focus.start}.thenBy{it.first.id}).map{it.second}
  val fixed=baseline.recognitions.filter{it.mode!=SourceAtomicMode.HEAD_BACKOFF}+frameRecognitions.filter{it.mode!=SourceAtomicMode.HEAD_BACKOFF}+literalRanges.mapIndexed{n,r->SourceRecognition("native-literal-$n",packSHA,r,r,SourceAtomicMode.AMBIGUOUS,emptyList())}
  val candidates=(frames+ordinary.map{it.unit}).filter{u->val r=SourceLookupRange(u.start,u.end);fixed.all{n->n.mask?.overlaps(r)!=true || (n.mode!=SourceAtomicMode.AMBIGUOUS && n.approvedOutputs.any{it.outputID==u.outputID && it.range==r})}}
  val chosen=mutableListOf<SourceReferenceUnit>();var used=0
  for(u in candidates){if(chosen.size>=128)break;if(used+requireNotNull(u.nativeSourceTokens)>budget || chosen.any{it.start<u.end && u.start<it.end})continue;chosen+=u;used+=requireNotNull(u.nativeSourceTokens)}
  // Merge only overlapping mask intervals. No protected interval is removed or shortened.
  val nodes=(baseline.recognitions+frameRecognitions).filter{it.mode==SourceAtomicMode.HEAD_BACKOFF}.sortedWith(compareBy<SourceRecognition>{it.mask?.start?:it.context.start}.thenBy{it.mask?.end?:it.context.end});val merged=mutableListOf<MutableList<SourceRecognition>>()
  for(n in nodes){val range=n.mask?:n.context;if(merged.isNotEmpty() && range.start<merged.last().maxOf{(it.mask?:it.context).end})merged.last().add(n)else merged.add(mutableListOf(n))}
  val recognition=merged.mapIndexed{n,g->
   val mask=union(g.mapNotNull{it.mask});val ambiguous=g.any{it.mode==SourceAtomicMode.AMBIGUOUS};val context=union(g.map{it.context})
   val permitted=if(ambiguous)emptyList() else candidates.filter{mask.contains(SourceLookupRange(it.start,it.end))}.map{SourceApprovedOutput(requireNotNull(it.outputID),SourceLookupRange(it.start,it.end))}
   SourceRecognition("merged-$n",JapaneseStarterLookup.sha(g.map{it.recordSHA256}.sorted().joinToString("").toByteArray()),context,mask,if(ambiguous)SourceAtomicMode.AMBIGUOUS else SourceAtomicMode.HEAD_BACKOFF,permitted)
  }
  val partial=SourceReferencePresentation.create(original,target,chosen.sortedBy{it.start},density,native.size)
  val result=SourceLookupEvidence(original,"en",target,identity,partial,recognition+fixed);require(result.isValid(original,"en",target,identity));if(partial!=null)require(result.filterPartial(partial)==partial);return result
 }
}
