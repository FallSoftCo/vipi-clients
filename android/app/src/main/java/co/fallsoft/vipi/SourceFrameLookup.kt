package co.fallsoft.vipi

import android.content.Context
import co.fallsoft.vipi.core.*
import org.json.JSONObject
import org.json.JSONArray

/** Finite approved source contexts; existing full-reference priority remains first. */
internal data class SourceFrameStarterCandidate(val entryID:String,val conceptID:String,val category:String,val rank:Int,val tokenCount:Int,
 val range:SourceLookupRange,val cost:Int,val reason:String?,val unit:SourceReferenceUnit)
internal class SourceFrameLookup(bytes:ByteArray,manifestBytes:ByteArray,private val target:String,private val baselineIdentity:String,private val source:String="en") {
 private val pack=JSONObject(bytes.also { require(it.size<=1048576 && manifestBytes.size<=8192 && source in SUPPORTED && target in SUPPORTED && source!=target) }.toString(Charsets.UTF_8));private val patterns=pack.getJSONArray("patterns")
 private val packSHA=JapaneseStarterLookup.sha(bytes)
 private val manifest=JSONObject(manifestBytes.toString(Charsets.UTF_8))
 private val allowed=(0 until patterns.length()).map{patterns.getJSONObject(it).getString("id")}.toSet()
 val identity="source-frames-v1:"+JapaneseStarterLookup.sha((packSHA+JapaneseStarterLookup.sha(manifestBytes)+baselineIdentity).toByteArray(Charsets.UTF_8))
 var trace=JSONArray();private set
 companion object {
  private val SUPPORTED=setOf("en","es","fr","de","it","pt","ar","zh","ja","ko","sw")
  const val PROMOTION_ENABLED=true
  fun bundled(context:Context,target:String,baseline:SourceLookupProvider,known:Set<String>,raw:()->List<SourceFrameStarterCandidate>):SourceLookupProvider {
   if(!PROMOTION_ENABLED || target !in setOf("ja","sw"))return baseline
   val owner=runCatching {
    val manifest=context.assets.open("immersion/source-frames-en-$target-catalog.json").use{it.readBytes()}
    val file=JSONObject(manifest.toString(Charsets.UTF_8)).getString("file")
    require(file.matches(Regex("source-frames-en-$target-[0-9]{3}\\.json")))
    SourceFrameLookup(context.assets.open("immersion/$file").use{it.readBytes()},manifest,target,baseline.cacheIdentity)
   }.getOrNull() ?: return baseline
   return owner.provider(baseline,known,raw,BundledImmersionCatalog(context))
  }
 }
 init {
  require(bytes.size<=1048576 && manifestBytes.size<=8192 && source in SUPPORTED && target in SUPPORTED && source!=target)
  require(manifest.getString("schema")=="vipi-source-frame-manifest-1" && manifest.getString("file").matches(Regex("source-frames-$source-$target-[0-9]{3}\\.json")))
  require(manifest.getString("sha256")==packSHA && manifest.getInt("bytes")==bytes.size && manifest.getString("version")==pack.getString("version") && manifest.getInt("patterns")==patterns.length())
  require(manifest.getString("source")==source && manifest.getString("target")==target && manifest.getString("policy")=="reference-first-source-frames-1")
  require(pack.getString("schema")=="vipi-source-frame-pack-1" && pack.getString("source")==source && pack.getString("target")==target && pack.getString("policy")==manifest.getString("policy"))
  require(pack.getString("approval_sha256").matches(Regex("[a-f0-9]{64}")) && patterns.length() in 1..256 && allowed.size==patterns.length())
  for(i in 0 until patterns.length()) {
   val p=patterns.getJSONObject(i);require(p.getBoolean("source_only_permission") && p.getString("pair")=="$source-$target")
   for(k in listOf("id","source","target","meaning","concept_id"))require(p.getString(k).isNotEmpty())
   require(p.opt("reading") is String);require(target !in setOf("ja","zh","ko","ar") || p.getString("reading").isNotEmpty());val variants=p.getJSONArray("variants");require(variants.length() in 1..1024)
   for(j in 0 until variants.length()) {
    val v=variants.getJSONObject(j);val text=v.getString("context");val f=v.getJSONArray("focus_utf16")
    require(!v.has("context_scope") || v.getString("context_scope") in setOf("local_phrase","whole_sentence"))
    require(!v.has("right_boundary") || v.getString("right_boundary")=="clause_or_end")
    require(text.length in 1..256 && f.length()==2);val a=f.getInt(0);val b=f.getInt(1)
    require(a>=0 && b>a && b<=text.length && (a==0 || !Character.isLowSurrogate(text[a])) && (b==text.length || !Character.isLowSurrogate(text[b])))
    require(text.substring(a,b)==p.getString("source"))
    carrierRange(v,p.getString("source"))
   }
  }
 }
 fun provider(baseline:SourceLookupProvider,known:Set<String>,raw:()->List<SourceFrameStarterCandidate>,catalog:BundledImmersionCatalog):SourceLookupProvider {
  val snapshot=known.toSet();val owner=this;val combinedIdentity=identity+":reference-first-v1"
  return object:SourceLookupProvider {
   override val cacheIdentity=combinedIdentity
   override suspend fun lookup(original:String,source:String,target:String,density:Double):SourceLookupEvidence {
    val b=baseline.lookup(original,source,target,density);val candidates=raw()
    val result=if(source!=owner.source || target!=owner.target || catalog.reference(original,source,target)!=null)b else owner.resolve(original,density,snapshot,b,candidates)
    return SourceLookupEvidence(result.original,result.source,result.target,cacheIdentity,result.partial,result.recognitions).also{require(it.isValid(original,source,target,cacheIdentity))}
   }
  }
 }
 private data class Hit(val pattern:JSONObject,val context:SourceLookupRange,val focus:SourceLookupRange,val contextCost:Int,val cost:Int,val id:String,var reason:String?)
 /** Explicit reviewed noun carrier only; never infer a stem from arbitrary input. */
 private fun carrierRange(variant:JSONObject,head:String):SourceLookupRange? {
  require(variant.has("carrier_utf16")==variant.has("carrier_rule"))
  if(!variant.has("carrier_utf16"))return null
  val text=variant.getString("context");val bounds=variant.getJSONArray("carrier_utf16");val focus=variant.getJSONArray("focus_utf16")
  require(bounds.length()==2)
  val a=bounds.getInt(0);val b=bounds.getInt(1);val start=focus.getInt(0);val end=focus.getInt(1)
  require(a>=0 && b>a && b<=text.length && a<=start && end<=b)
  val carrier=text.substring(a,b)
  when(variant.getString("carrier_rule")) {
   "supplied-singular-definite-article-1" -> {
    require(source=="ar" && head.length>=2 && !head.startsWith("ال") && head.all{it in '\u0620'..'\u064a'})
    require(carrier=="ال"+head && start==a+2 && end==b)
   }
   "hangul-noun-particles-1" -> {
    require(source=="ko" && head.isNotEmpty() && head.all{it in '\uac00'..'\ud7a3'})
    val consonant=(head.last().code-0xac00)%28!=0
    val suffixes=setOf(if(consonant)"은" else "는",if(consonant)"이" else "가",if(consonant)"을" else "를",if(consonant)"과" else "와","도","만","에","에서","의")
    require(start==a && end==a+head.length && carrier.startsWith(head) && carrier.substring(head.length) in suffixes)
   }
   else -> throw IllegalArgumentException("Unknown noun carrier rule")
  }
  return SourceLookupRange(a,b)
 }
 private fun overlaps(a:SourceLookupRange,b:SourceLookupRange)=a.overlaps(b)
 private fun union(ranges:List<SourceLookupRange>)=SourceLookupRange(ranges.minOf{it.start},ranges.maxOf{it.end})
 private fun nativeCost(words:List<IntRange>,range:SourceLookupRange):Int? {
  val touched=words.filter{it.first<range.end && range.start<=it.last}
  return if(touched.isNotEmpty() && touched.first().first==range.start && touched.last().last+1==range.end && touched.all{it.first>=range.start && it.last<range.end})touched.size else null
 }
 private fun sentenceCost(words:List<IntRange>,range:SourceLookupRange):Int? {
  val touched=words.filter{it.first<range.end && range.start<=it.last}
  return if(touched.isNotEmpty() && touched.all{it.first>=range.start && it.last<range.end})touched.size else null
 }
 private fun clauseOrEnd(original:String,end:Int):Boolean {
  var next=end
  while(next<original.length && (original[next]=='\t' || Character.getType(original[next])==Character.SPACE_SEPARATOR.toInt()))next++
  return next==original.length || original[next] in ".!?。！？,，;；\r\n"
 }
 private fun matches(original:String):List<Hit> {
  val words=LocalImmersion.words(original,source);val sentences=LocalImmersion.sentences(original,source)
  val hits=mutableListOf<Hit>();val seen=mutableSetOf<String>()
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
     val wholeSentence=v.optString("context_scope")=="whole_sentence"
     val cc=if(wholeSentence)sentenceCost(words,context) else nativeCost(words,context)
     val carrier=carrierRange(v,p.getString("source"))?.let{SourceLookupRange(a+it.start,a+it.end)}
     val fc=if(carrier==null)nativeCost(words,focus) else nativeCost(words,carrier)?.takeIf{it==1}
     val barrierText=if(wholeSentence)needle.trimEnd { it in ".!?。！？" } else needle
     val reason=when {
      wholeSentence && sentences.none{it.first==context.start && it.last+1==context.end}->"whole_sentence_scope"
      v.optString("right_boundary")=="clause_or_end" && !clauseOrEnd(original,context.end)->"right_boundary"
      cc==null || fc==null->"partial_native_word"
      barrierText.any{it in ".!?。！？;；\r\n"}->"context_barrier"
      else->null
     }
     hits+=Hit(p,context,focus,cc?:0,fc?:0,id,reason);require(hits.size<=4096)
    }
   }
  }
  return hits
 }
 fun geometry(original:String):JSONArray=JSONArray(matches(original).map{h->JSONObject().put("pattern_id",h.pattern.getString("id")).put("context",JSONArray(listOf(h.context.start,h.context.end))).put("focus",JSONArray(listOf(h.focus.start,h.focus.end))).put("reason",h.reason?:JSONObject.NULL)})
 fun resolve(original:String,density:Double,known:Set<String>,baseline:SourceLookupEvidence,raw:List<SourceFrameStarterCandidate>):SourceLookupEvidence {
  require(original.isNotEmpty() && original.length<=16384 && density.isFinite() && density in 0.0..0.75)
  require(baseline.catalogIdentity==baselineIdentity && baseline.isValid(original,source,target,baselineIdentity))
  trace=JSONArray();val native=LocalImmersion.words(original,source);val budget=if(density>0)maxOf(1,(native.size*density).toInt())else 0
  val literalRanges=TranslationIntegrity.protectedLiteralRanges(original).map{SourceLookupRange(it.first,it.last+1)}
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
  for(h in hits.filter{it.reason !in setOf("partial_native_word","context_barrier","whole_sentence_scope","right_boundary")}.sortedWith(compareBy<Hit>{it.focus.start}.thenBy{it.focus.end})) {
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
  val ordinary=raw.filter{it.reason==null && frameMasks.none{m->m.overlaps(it.range)}}.sortedWith(compareBy<SourceFrameStarterCandidate>{it.category!="content"}.thenByDescending{it.tokenCount}.thenBy{it.rank}.thenBy{it.range.start})
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
  val result=SourceLookupEvidence(original,source,target,identity,partial,recognition+fixed);require(result.isValid(original,source,target,identity));if(partial!=null)require(result.filterPartial(partial)==partial);return result
 }
}
