package co.fallsoft.vipi

import android.database.sqlite.SQLiteDatabase
import co.fallsoft.vipi.core.*
import org.json.JSONArray
import org.json.JSONObject

internal object ReviewedFrameLookup {
    private class Overflow:Exception()
    fun windows(text:String,language:String):Map<String,List<IntRange>>? {
        if(text.length>32768)return null
        val sentences=LocalImmersion.sentences(text,language)
        if(text.isNotEmpty() && sentences.isEmpty())return null
        val result=linkedMapOf<String,MutableList<IntRange>>();var count=0
        for(sentence in sentences) {
            val fragment=text.substring(sentence);val words=LocalImmersion.words(fragment,language)
            for(i in words.indices) {
                val starts=mutableListOf(words[i].first);val word=fragment.substring(words[i])
                val apostrophe=word.indexOfFirst{it=='\'' || it=='’'}
                if(language=="fr" && apostrophe>0 && apostrophe<word.lastIndex &&
                    word.substring(0,apostrophe).lowercase(java.util.Locale.ROOT) in setOf("j","l","d","t","m","n","s","c","qu"))
                    starts.add(words[i].first+apostrophe+1)
                for(j in i until minOf(words.size,i+8))for(start in starts) {
                val range=start..words[j].last
                if(range.last-range.first+1>256)continue
                val input=fragment.substring(range)
                if(input.any{it in ".!?。！？;；\r\n"})continue
                count++;if(count>4096)return null
                result.getOrPut(input){mutableListOf()}.add((sentence.first+range.first)..(sentence.first+range.last))
            }}
        }
        return result
    }
    private fun frame(payload:String,source:String,target:String,allowUnits:Boolean):ContextFrame {
        require(payload.toByteArray().size<=32768);val row=JSONObject(payload)
        require(row.getString("source_language")==source && row.getString("target_language")==target)
        fun parts(values:JSONArray,focus:String):List<ContextPart> = (0 until values.length()).map { i ->
            val part=values.getJSONObject(i);require(part.length()==1)
            when(val key=part.keys().next()) {
                "literal"->ContextPart.Literal(part.getString(key))
                "focus"->{require(part.getString(key)==focus);ContextPart.Focus(focus)}
                "slot"->{val list=part.getJSONArray(key);ContextPart.Slot((0 until list.length()).map{list.getString(it)})}
                else->error("Invalid frame part")
            }
        }
        val reading=row.getString("reading");require(reading.length<=256)
        val unit=if(row.has("lexical_unit")) row.get("lexical_unit").also { require(it is Boolean) } as Boolean else false
        require(!unit || allowUnits)
        return ContextFrame(row.getString("id"),row.getString("meaning"),source,target,
            parts(row.getJSONArray("source_parts"),row.getString("source")),parts(row.getJSONArray("target_parts"),row.getString("target")),reading,unit)
    }
    fun entries(db:SQLiteDatabase,original:String,translation:String,source:String,target:String):List<VocabularyEntry> {
        val allowUnits=db.rawQuery("SELECT user_version,(SELECT value FROM metadata WHERE key='schema'),(SELECT value FROM metadata WHERE key='context_policy') FROM pragma_user_version",null).use {
            require(it.moveToFirst())
            val unit=it.getInt(0)==7 && it.getString(1)=="vipi-reviewed-frame-2" && it.getString(2)=="reviewed-bidirectional-phrase-and-unit-2"
            require(unit || (it.getInt(0)==6 && it.getString(1)=="vipi-reviewed-frame-1" && it.getString(2)=="reviewed-bidirectional-phrase-1"))
            unit
        }
        val left=windows(original,source) ?: return emptyList();val right=windows(translation,target) ?: return emptyList()
        fun marks(count:Int)=List(count){"?"}.joinToString(",")
        fun query(sql:String,args:List<String>):List<Triple<String,String,String>> {
            val rows=mutableListOf<Triple<String,String,String>>()
            db.rawQuery(sql,args.toTypedArray()).use { c ->
                while(c.moveToNext()) {
                    rows+=Triple(c.getString(0),c.getString(1),c.getString(2))
                    if(rows.size>256)throw Overflow()
                }
            }
            return rows
        }
        val records=linkedMapOf<String,ContextFrame>()
        val sources=linkedMapOf<String,MutableSet<IntRange>>();val targets=linkedMapOf<String,MutableSet<IntRange>>()
        try {
            var count=0
            for(batch in left.keys.sorted().chunked(200)) {
                val rows=query("SELECT i.input,m.id,m.payload FROM source_inputs i JOIN mappings m ON m.id=i.mapping_id WHERE i.input IN (${marks(batch.size)}) LIMIT 257",batch)
                count+=rows.size;if(count>256)return emptyList()
                for((input,id,payload) in rows) {
                    if(id !in records) {val value=frame(payload,source,target,allowUnits);require(value.id==id);records[id]=value}
                    sources.getOrPut(id){linkedSetOf()}.addAll(left.getValue(input))
                }
            }
            val ids=records.keys.sorted();if(ids.isEmpty())return emptyList()
            count=0
            for(batch in right.keys.sorted().chunked(200)) {
                val rows=query("SELECT input,mapping_id,'' FROM target_inputs WHERE input IN (${marks(batch.size)}) AND mapping_id IN (${marks(ids.size)}) LIMIT 257",batch+ids)
                count+=rows.size;if(count>256)return emptyList()
                for((input,id,_) in rows)targets.getOrPut(id){linkedSetOf()}.addAll(right.getValue(input))
            }
            return ContextFrameMatcher.entries(original,translation,source,target,ids.map {
                ContextFrameHit(records.getValue(it),sources.getValue(it).toList(),targets[it]?.toList() ?: emptyList())})
        } catch(_:Overflow) {return emptyList()}
    }
}
