package co.fallsoft.vipi

import android.database.sqlite.SQLiteDatabase
import org.json.JSONObject
import org.json.JSONTokener

/** Experimental reference evidence, supplied explicitly by native QA. */
internal class ContextWitnessLookup private constructor(
    private val cues:Map<Pair<String,String>,List<String>>,
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
    fun supports(word:String,counterpart:String,focus:IntRange,text:String,windows:Map<String,List<IntRange>>):Boolean {
        if(words.isEmpty())return false
        return cues[word to counterpart].orEmpty().any { cue ->
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
            sources:Set<String>,targets:Set<String>):ContextWitnessLookup? {
            if(sources.size>256 || targets.size>256 || sources.isEmpty() || targets.isEmpty())return null
            val meta=mutableMapOf<String,String>()
            db.rawQuery("SELECT key,value FROM metadata WHERE key IN ('schema','policy','source_release_id','minimum_support','minimum_agreement','pairs','whole_verb_context_policy')",null).use { c ->
                while(c.moveToNext())meta[c.getString(0)]=c.getString(1)
            }
            fun string(name:String)=JSONTokener(requireNotNull(meta[name])).nextValue() as String
            require(string("schema")=="vipi-context-witnesses-1" && string("policy")=="experimental-direct-reference-agreement-1")
            require(string("source_release_id")==release)
            if(sources.any{it.startsWith("@past:")} || targets.any{it.startsWith("@past:")})
                require(string("whole_verb_context_policy")=="attested-positive-past-lemma-1")
            val minimum=requireNotNull(meta["minimum_support"]).toInt();val agreement=requireNotNull(meta["minimum_agreement"]).toDouble()
            require(minimum>=3 && agreement.isFinite() && agreement>=0.98 && agreement<=1)
            if(!JSONObject(requireNotNull(meta["pairs"])).has("$source-$target"))return null
            val rows=mutableMapOf<Pair<String,String>,MutableList<String>>();var count=0
            fun marks(n:Int)=List(n){"?"}.joinToString(",")
            for(left in sources.sorted().chunked(100))for(right in targets.sorted().chunked(100)) {
                val args=listOf(source,target)+left+right
                db.rawQuery("SELECT word,counterpart,cue,support,total FROM witnesses WHERE source=? AND target=? AND word IN (${marks(left.size)}) AND counterpart IN (${marks(right.size)})",args.toTypedArray()).use { c ->
                    while(c.moveToNext()) {
                        count++;if(count>8192)return null
                        val cue=c.getString(2);val n=c.getLong(3);val total=c.getLong(4)
                        require(n>=minimum && total>=n && n.toDouble()/total>=agreement)
                        require(cue=="@whole" || ((cue.startsWith("L:") || cue.startsWith("R:")) && cue.length>2))
                        if(cue.length<=130)rows.getOrPut(c.getString(0) to c.getString(1)){mutableListOf()}.add(cue)
                    }
                }
            }
            return ContextWitnessLookup(rows,LocalImmersion.words(original,source))
        }
    }
}
