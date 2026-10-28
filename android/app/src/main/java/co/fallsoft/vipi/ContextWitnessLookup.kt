package co.fallsoft.vipi

import android.database.sqlite.SQLiteDatabase
import co.fallsoft.vipi.core.ImmersionEngine
import org.json.JSONArray
import org.json.JSONObject
import org.json.JSONTokener

/** Experimental reference evidence, supplied explicitly by native QA. */
internal class ContextWitnessLookup private constructor(
    private val cues:Map<Pair<String,String>,List<String>>,
    private val alternatives:Map<Pair<String,String>,List<Pair<String,Set<String>>>>,
    private val nounAlternatives:Map<Pair<String,String>,List<Pair<String,Set<String>>>>,
    private val adjectiveAlternatives:Map<Pair<String,String>,List<Pair<String,Set<String>>>>,
    private val words:List<IntRange>
) {
    private fun nearby(range:IntRange,focus:IntRange,text:String):Boolean {
        val left=range.last<focus.first;val right=range.first>focus.last
        if(!left && !right)return false
        val start=if(left)range.last+1 else focus.last+1
        val end=if(left)focus.first else range.first
        return text.substring(start,end).none{it in ".!?。！？;；\r\n"} && words.count{it.first>=start && it.last<end}<6
    }
    fun hasNearbyContext(focus:IntRange,text:String,windows:Map<String,List<IntRange>>):Boolean =
        windows.values.any{ranges->ranges.any{nearby(it,focus,text)}}
    fun supports(word:String,counterpart:String,focus:IntRange,text:String,windows:Map<String,List<IntRange>>,allowedMeanings:Set<String> = emptySet(),allowedNounMeanings:Set<String> = emptySet(),allowedAdjectiveMeanings:Set<String> = emptySet()):Boolean {
        if(words.isEmpty())return false
        val accepted=cues[word to counterpart].orEmpty()+alternatives[word to counterpart].orEmpty()
            .filter{(_,senses)->senses.any{it in allowedMeanings}}.map{it.first}+
            nounAlternatives[word to counterpart].orEmpty().filter{(_,senses)->senses.any{it in allowedNounMeanings}}.map{it.first}+
            adjectiveAlternatives[word to counterpart].orEmpty().filter{(_,senses)->senses.any{it in allowedAdjectiveMeanings}}.map{it.first}
        return accepted.any { cue ->
            if(cue=="@whole")words.all{it.first>=focus.first && it.last<=focus.last}
            else windows[cue.substring(2)].orEmpty().any { range ->
                val left=cue.startsWith("L:") && range.last<focus.first
                val right=cue.startsWith("R:") && range.first>focus.last
                (left || right) && nearby(range,focus,text)
            }
        }
    }
    companion object {
        fun load(db:SQLiteDatabase,original:String,source:String,target:String,release:String,
            sources:Set<String>,targets:Set<String>,contextKeys:Set<String>?=null):ContextWitnessLookup? {
            if(sources.size>256 || targets.size>256 || sources.isEmpty() || targets.isEmpty())return null
            val sourceWords=LocalImmersion.words(original,source)
            // A cue absent from the actual message cannot support a candidate.
            // Filter before the unchanged row cap; keep corpus denominators intact.
            val possibleContexts=contextKeys ?: (ReviewedFrameLookup.windows(original,source) ?: return null)
                .keys.map(ImmersionEngine::lookupKey).toSet()
            // Include native subword windows (for example French elision and
            // Japanese compounds), not just the platform's single-token split.
            val activeCues=(listOf("@whole")+possibleContexts.filter{it.length<=128 && it.none(Char::isWhitespace)}
                .flatMap{listOf("L:"+it,"R:"+it)}).distinct().sorted()
            val meta=mutableMapOf<String,String>()
            db.rawQuery("SELECT key,value FROM metadata WHERE key IN ('schema','policy','source_release_id','minimum_support','minimum_agreement','pairs','whole_verb_context_policy','whole_present_context_policy','semantic_alternative_policy','noun_semantic_alternative_policy','adjective_semantic_alternative_policy')",null).use { c ->
                while(c.moveToNext())meta[c.getString(0)]=c.getString(1)
            }
            fun string(name:String)=JSONTokener(requireNotNull(meta[name])).nextValue() as String
            require(string("schema")=="vipi-context-witnesses-1" && string("policy")=="experimental-direct-reference-agreement-1")
            require(string("source_release_id")==release)
            if(sources.any{it.startsWith("@past:")} || targets.any{it.startsWith("@past:")})
                require(string("whole_verb_context_policy")=="attested-positive-past-lemma-1")
            if(sources.any{it.startsWith("@present:")} || targets.any{it.startsWith("@present:")})
                require(string("whole_present_context_policy")=="attested-positive-present-lemma-1")
            val minimum=requireNotNull(meta["minimum_support"]).toInt();val agreement=requireNotNull(meta["minimum_agreement"]).toDouble()
            require(minimum>=3 && agreement.isFinite() && agreement>=0.98 && agreement<=1)
            if(!JSONObject(requireNotNull(meta["pairs"])).has("$source-$target"))return null
            val rows=mutableMapOf<Pair<String,String>,MutableList<String>>()
            val alternatives=mutableMapOf<Pair<String,String>,MutableList<Pair<String,Set<String>>>>()
            val nounAlternatives=mutableMapOf<Pair<String,String>,MutableList<Pair<String,Set<String>>>>()
            val adjectiveAlternatives=mutableMapOf<Pair<String,String>,MutableList<Pair<String,Set<String>>>>();var count=0
            val semantic=meta.containsKey("semantic_alternative_policy")
            if(semantic)require(string("semantic_alternative_policy")=="shared-explicit-verb-alternatives-1")
            fun marks(n:Int)=List(n){"?"}.joinToString(",")
            for(left in sources.sorted().chunked(100))for(right in targets.sorted().chunked(100))for(context in activeCues.chunked(100)) {
                val args=listOf(source,target)+left+right+context
                db.rawQuery("SELECT word,counterpart,cue,support,total FROM witnesses WHERE source=? AND target=? AND word IN (${marks(left.size)}) AND counterpart IN (${marks(right.size)}) AND cue IN (${marks(context.size)})",args.toTypedArray()).use { c ->
                    while(c.moveToNext()) {
                        count++;if(count>8192)return null
                        val cue=c.getString(2);val n=c.getLong(3);val total=c.getLong(4)
                        require(n>=minimum && total>=n && n.toDouble()/total>=agreement)
                        require(cue=="@whole" || ((cue.startsWith("L:") || cue.startsWith("R:")) && cue.length>2))
                        if(cue.length<=130)rows.getOrPut(c.getString(0) to c.getString(1)){mutableListOf()}.add(cue)
                    }
                }
            }
            val nounSemantic=meta.containsKey("noun_semantic_alternative_policy")
            if(nounSemantic)require(string("noun_semantic_alternative_policy")=="shared-explicit-noun-alternatives-1")
            val adjectiveSemantic=meta.containsKey("adjective_semantic_alternative_policy")
            if(adjectiveSemantic)require(string("adjective_semantic_alternative_policy")=="shared-explicit-adjective-alternatives-1")
            for(kind in listOf("present","noun","adjective")) {
                if(!when(kind){"noun"->nounSemantic;"adjective"->adjectiveSemantic;else->semantic})continue
                val table=if(kind=="present")"semantic_alternatives" else kind+"_semantic_alternatives"
                val destination=when(kind){"noun"->nounAlternatives;"adjective"->adjectiveAlternatives;else->alternatives}
                fun selected(word:String)=if(kind=="present")word.startsWith("@present:") else !word.startsWith("@")
                for(left in sources.filter(::selected).sorted().chunked(100))
                for(right in targets.filter(::selected).sorted().chunked(100))for(context in activeCues.chunked(100)) {
                    val args=listOf(source,target)+left+right+context
                    db.rawQuery("SELECT word,counterpart,cue,support,total,counterpart_support,candidate_senses FROM $table WHERE source=? AND target=? AND word IN (${marks(left.size)}) AND counterpart IN (${marks(right.size)}) AND cue IN (${marks(context.size)})",args.toTypedArray()).use { c ->
                        while(c.moveToNext()) {
                            count++;if(count>8192)return null
                            val cue=c.getString(2);val n=c.getLong(3);val total=c.getLong(4);val specific=c.getLong(5)
                            require(n>=minimum && total>=n && specific>=minimum && specific<=n && n.toDouble()/total>=agreement)
                            require(cue=="@whole" || ((cue.startsWith("L:") || cue.startsWith("R:")) && cue.length>2))
                            val raw=JSONArray(c.getString(6));require(raw.length() in 1..128)
                            val senses=(0 until raw.length()).map{raw.getString(it)}.toSet()
                            require(senses.all{it.length==64 && it.all{c->c in "0123456789abcdef"}})
                            if(cue.length<=130)destination.getOrPut(c.getString(0) to c.getString(1)){mutableListOf()}.add(cue to senses)
                        }
                    }
                }
            }
            return ContextWitnessLookup(rows,alternatives,nounAlternatives,adjectiveAlternatives,sourceWords)
        }
    }
}
