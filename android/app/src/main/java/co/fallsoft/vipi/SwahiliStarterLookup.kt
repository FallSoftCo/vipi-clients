package co.fallsoft.vipi

import android.content.Context
import android.icu.lang.UCharacter
import co.fallsoft.vipi.core.*
import org.json.JSONObject
import org.json.JSONArray
import java.security.MessageDigest
import java.text.Normalizer

/** Source-only versioned Swahili starter; reviewed bounded content increment. */
internal class SwahiliStarterLookup(bytes: ByteArray, manifest: ByteArray, knownIDs: Set<String> = emptySet(), private val packMultiple: Boolean = false) : SourceLookupProvider {
    companion object {
        const val PROMOTION_ENABLED = true
        const val PACKING_ENABLED = true // Qualified native packing; see starter-packing-density-r01.
        fun whitespaceGap(value:String)=value.isNotEmpty() && value.all { it.isWhitespace() }
        fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
        fun bundledIfPromoted(context: Context, knownIDs: Set<String> = emptySet()): SourceLookupProvider? {
            if (!PROMOTION_ENABLED) return null
            return runCatching {
                val manifest=context.assets.open("immersion/starter-sw-catalog.json").use { it.readBytes() }
                val file=JSONObject(manifest.toString(Charsets.UTF_8)).getString("file")
                require(file.matches(Regex("starter-en-sw-[0-9]{3}\\.json")))
                val baseline=SwahiliStarterLookup(context.assets.open("immersion/$file").use { it.readBytes() },manifest,knownIDs,packMultiple=PACKING_ENABLED)
                SourceFrameLookup.bundled(context,"sw",baseline,knownIDs){baseline.rawCandidates}
            }.getOrNull()
        }
        private val words = Regex("[\\p{L}\\p{Nl}\\p{No}]+(?:['’][\\p{L}\\p{Nl}\\p{No}]+)*")
        private val literals = Regex("https?://\\S+|\\b[^\\s@]+@[^\\s@]+\\.[^\\s@]+|```[\\s\\S]*?```|`[^`]*`")
        private fun fold(text: String) = UCharacter.foldCase(text, true).replace('’','\'')
        private fun face(text: String) = fold(Normalizer.normalize(text, Normalizer.Form.NFKC))
        private fun strings(a: JSONArray) = (0 until a.length()).map { a.getString(it) }
    }
    private data class Entry(val id:String,val tokens:List<String>,val target:String,val reading:String?,val category:String,
        val rank:Int,val guard:String?,val following:Set<String>,val concept:String,val record:String,
        val followingContexts:List<List<String>>,val rejectFollowing:Set<String>)
    private val known = knownIDs.toSet()
    private val entries: List<Entry>
    private val lefts: Set<String>
    private val copulas: Set<String>
    private val predicatePolicyPresent: Boolean
    private val predicateLeftOperators: Set<String>
    private val predicateRejectFollowing: Set<String>
    private val packSHA: String
    private val version: String
    override val cacheIdentity: String
    var rawCandidates: List<SourceFrameStarterCandidate> = emptyList(); private set
    var trace = JSONArray(); private set
    init {
        val m=JSONObject(manifest.toString(Charsets.UTF_8));val p=JSONObject(bytes.toString(Charsets.UTF_8))
        packSHA=sha(bytes);version=p.getString("version")
        require(m.getString("schema")=="vipi-source-starter-manifest-1" && m.getString("file").matches(Regex("starter-en-sw-[0-9]{3}\\.json")) &&
            m.getInt("bytes")==bytes.size && bytes.size<=1048576 && m.getString("sha256")==packSHA && m.getString("version")==version)
        require(p.getString("schema")=="vipi-source-starter-1" && p.getString("source")=="en" && p.getString("target")=="sw")
        fun policyTokens(a:JSONArray):List<String> {
            require(a.length()<=256)
            return (0 until a.length()).map { n ->
                val token=a.get(n);require(token is String && token.isNotEmpty() && token.length<=64 && Regex("[a-z]+(?:'[a-z]+)?").matches(token));token
            }
        }
        predicatePolicyPresent=p.has("positive_predicate_policy")
        val predicatePolicy=if(predicatePolicyPresent)p.getJSONObject("positive_predicate_policy")else null
        if(predicatePolicy!=null)require(predicatePolicy.getString("schema")=="vipi-positive-predicate-policy-1")
        predicateLeftOperators=predicatePolicy?.getJSONArray("left_operators")?.let(::policyTokens)?.toSet() ?: emptySet()
        predicateRejectFollowing=predicatePolicy?.getJSONArray("reject_following")?.let(::policyTokens)?.toSet() ?: emptySet()
        if(predicatePolicy!=null) {
            require(predicatePolicy.getJSONArray("left_operators").length() in 1..64)
            require(policyTokens(predicatePolicy.getJSONArray("reject_following"))==listOf("not"))
        }
        val rows=p.getJSONArray("entries");require(rows.length() in 1..512 && rows.length()==m.getInt("entries"))
        entries=(0 until rows.length()).map { n -> val e=rows.getJSONObject(n)
            val guard=if(e.isNull("guard")) null else e.getString("guard")
            require(guard in setOf(null,"interrogative","ordinary_noun_context","withheld_contextual_sense","positive_first_person_predicate"))
            require(e.isNull("reading") && e.isNull("reading_kana") && e.getString("concept_id").isNotBlank())
            require(e.getString("record_sha256").matches(Regex("[a-f0-9]{64}")))
            val contexts=(if(e.has("following_contexts"))e.getJSONArray("following_contexts")else null)?.let { all ->
                require(all.length() in 1..256)
                (0 until all.length()).map { n -> policyTokens(all.getJSONArray(n)).also{require(it.size in 1..2)} }
            } ?: emptyList()
            val reject=(if(e.has("reject_following"))e.getJSONArray("reject_following")else null)?.let(::policyTokens)?.toSet() ?: emptySet()
            val sourceTokens=strings(e.getJSONArray("source_tokens"))
            if(guard=="positive_first_person_predicate")require(predicatePolicyPresent && sourceTokens.size==2 && sourceTokens[0]=="i" && policyTokens(e.getJSONArray("source_tokens"))==sourceTokens && e.getString("source")==sourceTokens.joinToString(" ") && e.getString("category")=="content")
            Entry(e.getString("id"),sourceTokens,e.getString("target"),null,e.getString("category"),
                e.getInt("train_rank"),guard,e.optJSONArray("following")?.let(::strings)?.toSet() ?: emptySet(),e.getString("concept_id"),e.getString("record_sha256"),contexts,reject)
        }
        require(entries.map { it.id }.distinct().size==entries.size && entries.all { it.id.isNotBlank() && it.tokens.isNotEmpty() && it.target.isNotBlank() && it.category in setOf("content","function") })
        val c=p.getJSONObject("source_context_sets");lefts=(strings(c.getJSONArray("determiners"))+strings(c.getJSONArray("prepositions"))+strings(c.getJSONArray("object_verbs"))).toSet();copulas=strings(c.getJSONArray("copulas")).toSet()
        cacheIdentity="$version:$packSHA:"+sha(known.sorted().joinToString("\u0000").toByteArray()) + if(packMultiple) ":packing-1" else ""
    }
    override suspend fun lookup(original:String,source:String,target:String,density:Double):SourceLookupEvidence =
        resolve(original,source,target,density)
    fun resolve(original:String,source:String,target:String,density:Double,
                protectedRanges:List<SourceLookupRange> = emptyList(),sourceMasks:List<SourceLookupRange> = emptyList()):SourceLookupEvidence {
        trace=JSONArray();rawCandidates=emptyList()
        fun evidence(partial:PartialImmersionResult?,rs:List<SourceRecognition>)=SourceLookupEvidence(original,source,target,cacheIdentity,partial,rs)
        if(source!="en" || target!="sw") return evidence(null,emptyList())
        require(original.isNotEmpty() && original.length<=16384 && density.isFinite() && density in 0.0..1.0)
        val native=LocalImmersion.words(original,source);val tokens=words.findAll(original).toList();val keys=tokens.map{fold(it.value)}
        val budget=if(density>0) maxOf(1,(native.size*density).toInt()) else 0
        val protection=protectedRanges+sourceMasks+literals.findAll(original).map{SourceLookupRange(it.range.first,it.range.last+1)}.toList()
        val predicateProtection=protection+TranslationIntegrity.protectedLiteralRanges(original).map{SourceLookupRange(it.first,it.last+1)}
        data class Hit(val entry:Entry,val range:SourceLookupRange,val context:SourceLookupRange,val cost:Int,val outputID:String,var reason:String?)
        val hits=mutableListOf<Hit>()
        for(i in tokens.indices) for(e in entries) {
            val j=i+e.tokens.size;if(j>keys.size || keys.subList(i,j)!=e.tokens) continue
            val start=tokens[i].range.first;val end=tokens[j-1].range.last+1;val range=SourceLookupRange(start,end)
            val before=original.substring(0,start).trimEnd().trimEnd('"','\'','“','”','‘','’');val initial=before.isEmpty() || before.last() in ".!?"
            val first=tokens[i].value;fun gap(k:Int)=original.substring(tokens[k].range.last+1,tokens[k+1].range.first)
            val touched=native.filter{it.first<end && start<=it.last};val complete=touched.isNotEmpty() && touched.first().first==start && touched.last().last+1==end && touched.all{it.first>=start && it.last<end}
            val predicate=e.guard=="positive_first_person_predicate"
            val matchedContext=if(predicate)e.followingContexts.filter { sequence ->
                val k=j+sequence.size
                k<=keys.size && keys.subList(j,k)==sequence && (j-1 until k-1).all{whitespaceGap(gap(it))}
            }.maxByOrNull{it.size}else null
            val contextEnd=matchedContext?.let{tokens[j+it.size-1].range.last+1} ?: end
            val predicateContext=SourceLookupRange(start,contextEnd)
            val contextWords=native.filter{it.first<contextEnd && start<=it.last}
            val contextComplete=contextWords.isNotEmpty() && contextWords.first().first==start && contextWords.last().last+1==contextEnd && contextWords.all{it.first>=start && it.last<contextEnd} &&
                (!predicate || (i until (j+(matchedContext?.size ?: 0))).all { n -> native.any{it.first==tokens[n].range.first && it.last==tokens[n].range.last} })
            val left=if(i>0 && whitespaceGap(gap(i-1)))keys[i-1]else null
            val right=if(j<keys.size && whitespaceGap(gap(j-1)))keys[j]else null
            val reason=when {
                protection.any{it.overlaps(range)} -> "protected_source"
                keys[i]!="i" && first.codePointCount(0,first.length)>1 && first.any{it.isUpperCase()} && first.none{it.isLowerCase()} -> "uppercase_identifier"
                keys[i]!="i" && first.first().isUpperCase() && !initial -> "mid_sentence_capital"
                (i until j-1).any { !whitespaceGap(gap(it)) } -> "noncontiguous_source_unit"
                predicate && tokens[j-1].value.length>1 && tokens[j-1].value.any{it.isUpperCase()} && tokens[j-1].value.none{it.isLowerCase()} -> "uppercase_predicate"
                predicate && left in predicateLeftOperators -> "external_predicate_operator"
                predicate && right in predicateRejectFollowing -> "negative_predicate_scope"
                predicate && right in e.rejectFollowing -> "unsupported_predicate_complement"
                predicate && e.followingContexts.isNotEmpty() && matchedContext==null -> "predicate_right_context_absent"
                predicate && (!contextComplete || touched.size!=2) -> "partial_native_predicate_context"
                predicate && predicateProtection.any{it.overlaps(predicateContext)} -> "protected_predicate_context"
                e.guard=="withheld_contextual_sense" -> "unqualified_source_sense"
                e.guard=="interrogative" && !initial -> "question_not_sentence_initial"
                e.guard=="interrogative" && (j>=keys.size || keys[j] !in e.following) -> "question_right_context_absent"
                e.guard=="interrogative" && (i until j).any{gap(it).isNotBlank()} -> "noncontiguous_question_context"
                e.guard=="ordinary_noun_context" && run { val left=if(i>0 && gap(i-1).isBlank()) keys[i-1] else null; left !in lefts && !(initial && keys.getOrNull(j) in copulas) } -> "noun_context_absent"
                !complete -> "partial_native_word"
                face(original.substring(start,end))==face(e.target) -> "unchanged_normalized_face"
                !TranslationIntegrity.preservesIdentifiers(original,original.replaceRange(start,end,e.target)) -> "full_message_literal_integrity"
                e.concept in known -> "caller_known_concept"
                touched.size>budget -> "native_density_budget"
                else -> null
            }
            hits+=Hit(e,range,predicateContext,touched.size,"${e.id}@$start:$end",reason)
            require(hits.size<=4096)
        }
        val predicates=hits.filter{it.entry.guard=="positive_first_person_predicate"}
        for(h in hits)if(h.reason==null && h.entry.guard!="positive_first_person_predicate" && predicates.any{it.range.contains(h.range) && it.range!=h.range})h.reason="stronger_predicate_recognized"
        for(h in hits) {
            val row=JSONObject().put("entry_id",h.entry.id).put("concept_id",h.entry.concept).put("source",original.substring(h.range.start,h.range.end)).put("target",h.entry.target).put("reading",h.entry.reading ?: JSONObject.NULL)
                .put("source_utf16",JSONArray(listOf(h.range.start,h.range.end))).put("reason",h.reason ?: JSONObject.NULL).put("record_sha256",h.entry.record)
            if(h.entry.guard=="positive_first_person_predicate")row.put("predicate_context_utf16",JSONArray(listOf(h.context.start,h.context.end)))
            trace.put(row)
        }
        rawCandidates=hits.map { h -> SourceFrameStarterCandidate(h.entry.id,h.entry.concept,h.entry.category,h.entry.rank,h.entry.tokens.size,h.range,h.cost,h.reason,
            SourceReferenceUnit(h.range.start,h.range.end,original.substring(h.range.start,h.range.end),h.entry.target,null,
                "$version:$packSHA:${h.entry.id}",packSHA,h.cost,h.outputID)) }
        val ordered=hits.filter{it.reason==null}.sortedWith(compareBy<Hit>{it.entry.category!="content"}.thenBy{it.entry.rank}.thenByDescending{it.entry.tokens.size}.thenBy{it.range.start})
        val chosen=mutableListOf<Hit>();var used=0
        for(hit in ordered) {
            // The existing presentation contract accepts at most 128 whole units.
            if(chosen.size >= if(packMultiple) 128 else 1) break
            if(used+hit.cost>budget || chosen.any{it.range.overlaps(hit.range)}) continue
            chosen+=hit;used+=hit.cost
        }
        val units=chosen.sortedBy{it.range.start}.map{SourceReferenceUnit(it.range.start,it.range.end,original.substring(it.range.start,it.range.end),it.entry.target,it.entry.reading,
            "$version:$packSHA:${it.entry.id}",packSHA,it.cost,it.outputID)}
        val partial=SourceReferencePresentation.create(original,target,units,density,native.size)
        val groups=mutableListOf<MutableList<Hit>>()
        for(h in hits.sortedWith(compareBy<Hit>{it.range.start}.thenBy{it.range.end})) {
            if(groups.isNotEmpty() && h.range.start<groups.last().maxOf{it.range.end}) groups.last().add(h) else groups.add(mutableListOf(h))
        }
        val recognitions=groups.mapIndexed { n,g -> val range=SourceLookupRange(g.minOf{it.range.start},g.maxOf{it.range.end})
            SourceRecognition("starter-$n",sha(g.map{it.entry.record}.sorted().joinToString("").toByteArray()),SourceLookupRange(g.minOf{it.context.start},g.maxOf{it.context.end}),range,SourceAtomicMode.HEAD_BACKOFF,
                g.filter{it.reason==null}.map{SourceApprovedOutput(it.outputID,it.range)})
        }+protection.mapIndexed { n,r -> SourceRecognition("protection-$n",packSHA,r,r,SourceAtomicMode.AMBIGUOUS,emptyList()) }
        return evidence(partial,recognitions).also{require(it.isValid(original,source,target,cacheIdentity))}
    }
}
