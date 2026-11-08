package co.fallsoft.vipi

import android.icu.lang.UCharacter
import co.fallsoft.vipi.core.*
import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest
import java.text.Normalizer

/** Frozen research input only. Not bundled in the app and never a default production policy. */
internal class ReviewedSourceUnitQa(bytes: ByteArray) : SourceUnitQaPolicy {
    companion object {
        const val SHA256 = "67f041f3024c0e3679d54de9afa2debcebba1ad42e0a79b7bb0e4aacb90f2f60"
        const val VERSION = "reviewed-source-starter-en-v002"
        private val words = Regex("[\\p{L}\\p{Nl}\\p{No}]+(?:['’][\\p{L}\\p{Nl}\\p{No}]+)*")
        private val protectedPattern = Regex("https?://\\S+|\\b[^\\s@]+@[^\\s@]+\\.[^\\s@]+|```[\\s\\S]*?```|`[^`]*`")
        fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
        private fun fold(text: String) = UCharacter.foldCase(text, true).replace('’', '\'')
        private fun faceKey(text: String) = UCharacter.foldCase(Normalizer.normalize(text, Normalizer.Form.NFKC), true)
    }
    override val cacheIdentity = "$VERSION:$SHA256"
    private data class Entry(val id:String,val tokens:List<String>,val target:String,val reading:String?,val category:String,
        val rank:Int,val guard:String?,val following:Set<String>)
    private val entries:Map<String,List<Entry>>
    private val nounLeft:Set<String>
    private val copulas:Set<String>
    var lastDiagnostic = JSONObject()
        private set
    init {
        require(sha(bytes)==SHA256)
        val root=JSONObject(bytes.toString(Charsets.UTF_8))
        require(root.getString("schema")=="vipi-reviewed-source-unit-native-candidate-2")
        require(root.getString("pack_version")==VERSION && !root.getBoolean("production"))
        fun strings(array:JSONArray)= (0 until array.length()).map { array.getString(it) }
        val sets=root.getJSONObject("source_context_sets")
        nounLeft=listOf("determiners","prepositions","object_verbs").flatMap { strings(sets.getJSONArray(it)) }.toSet()
        copulas=strings(sets.getJSONArray("copulas")).toSet()
        val pairs=root.getJSONObject("pairs")
        entries=mapOf("sw" to 109,"ja" to 46,"es" to 43).mapValues { (target,count) ->
            val rows=pairs.getJSONObject("en-$target").getJSONArray("entries");require(rows.length()==count)
            (0 until rows.length()).map { index ->
                val row=rows.getJSONObject(index);val tokens=strings(row.getJSONArray("source_tokens"))
                require(tokens.isNotEmpty() && tokens.joinToString(" ")==row.getString("source"))
                val reading=if(row.isNull("reading")) null else row.getString("reading")
                if(target=="ja") require(!reading.isNullOrBlank() && row.getString("reading_kana").isNotBlank())
                val guard=if(row.isNull("guard")) null else row.getString("guard")
                require(guard in setOf(null,"interrogative","ordinary_noun_context"))
                val category=row.getString("category");require(category in setOf("content","function"))
                Entry(row.getString("id"),tokens,row.getString("target"),reading,category,row.getInt("train_rank"),guard,
                    row.optJSONArray("following")?.let(::strings)?.toSet() ?: emptySet())
            }.also { list -> require(list.map { it.id }.distinct().size==list.size) }
        }
    }
    override fun partial(original:String,source:String,target:String,density:Double):PartialImmersionResult? {
        require(source=="en" && target in entries && density==.10)
        val native=LocalImmersion.words(original,source)
        val tokens=words.findAll(original).toList();val keys=tokens.map { fold(it.value) }
        val protectedRanges=protectedPattern.findAll(original).map { it.range }.toList()
        val budget=maxOf(1,(native.size*density.coerceAtMost(1.0)).toInt())
        val rejected=JSONArray();val eligible=JSONArray()
        data class Candidate(val entry:Entry,val unit:SourceReferenceUnit)
        val found=mutableListOf<Candidate>()
        fun reject(entry:Entry,start:Int,end:Int,reason:String) {
            rejected.put(JSONObject().put("id",entry.id).put("start_utf16",start).put("end_utf16",end).put("reason",reason))
        }
        for(i in tokens.indices) for(entry in requireNotNull(entries[target])) {
            val j=i+entry.tokens.size
            if(j>tokens.size || keys.subList(i,j)!=entry.tokens) continue
            val start=tokens[i].range.first;val end=tokens[j-1].range.last+1
            val before=original.substring(0,start).trimEnd().trimEnd('"','\'','“','”','‘','’')
            val initial=before.isEmpty() || before.last() in ".!?"
            val token=tokens[i].value
            fun gap(k:Int)=original.substring(tokens[k].range.last+1,tokens[k+1].range.first)
            val upper=token.any { it.isUpperCase() } && token.none { it.isLowerCase() }
            val overlaps=native.filter { it.first<end && start<=it.last }
            val complete=overlaps.isNotEmpty() && overlaps.first().first==start && overlaps.last().last+1==end &&
                overlaps.all { it.first>=start && it.last<end }
            val reason=when {
                protectedRanges.any { it.first<end && start<=it.last } -> "protected_identifier_or_code"
                keys[i]!="i" && upper && token.codePointCount(0,token.length)>1 -> "uppercase_identifier"
                keys[i]!="i" && token.first().isUpperCase() && !initial -> "mid_sentence_capital"
                entry.guard=="interrogative" && !initial -> "question_not_sentence_initial"
                entry.guard=="interrogative" && (j>=keys.size || keys[j] !in entry.following) -> "question_right_context_absent"
                entry.guard=="interrogative" && (i until j).any { gap(it).isNotBlank() } -> "noncontiguous_question_context"
                entry.guard=="ordinary_noun_context" && run {
                    val left=if(i>0 && gap(i-1).isBlank()) keys[i-1] else null
                    val right=keys.getOrNull(j)
                    left !in nounLeft && !(initial && right in copulas)
                } -> "noun_context_absent"
                !complete -> "incomplete_native_source_word"
                faceKey(original.substring(start,end))==faceKey(entry.target) -> "unchanged_normalized_face"
                !TranslationIntegrity.preservesIdentifiers(original,original.replaceRange(start,end,entry.target)) -> "full_message_literal_integrity"
                overlaps.size>budget -> "native_density_budget"
                else -> null
            }
            if(reason!=null) { reject(entry,start,end,reason);continue }
            val unit=SourceReferenceUnit(start,end,original.substring(start,end),entry.target,entry.reading,
                "$VERSION:${entry.id}",SHA256,overlaps.size)
            found+=Candidate(entry,unit)
            eligible.put(JSONObject().put("id",entry.id).put("start_utf16",start).put("end_utf16",end)
                .put("native_source_tokens",overlaps.size).put("category",entry.category).put("train_rank",entry.rank))
        }
        val chosen=found.sortedWith(compareBy<Candidate> { it.entry.category!="content" }.thenBy { it.entry.rank }
            .thenByDescending { it.entry.tokens.size }.thenBy { it.unit.start }).firstOrNull()
        val result=chosen?.let { SourceReferencePresentation.create(original,target,listOf(it.unit),density,native.size) }
        if(chosen!=null && result==null) reject(chosen.entry,chosen.unit.start,chosen.unit.end,"source_presentation_validation")
        lastDiagnostic=JSONObject().put("pack_version",VERSION).put("pack_sha256",SHA256).put("native_source_tokens",native.size)
            .put("native_token_budget",budget).put("scanner_token_count",tokens.size).put("eligible",eligible).put("rejected",rejected)
            .put("selected_id",if(result!=null) chosen?.entry?.id else JSONObject.NULL)
        return result
    }
}
