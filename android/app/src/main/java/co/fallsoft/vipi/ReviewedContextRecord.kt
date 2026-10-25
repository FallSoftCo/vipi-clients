package co.fallsoft.vipi

import co.fallsoft.vipi.core.ContextMapping
import co.fallsoft.vipi.core.ContextPart
import co.fallsoft.vipi.core.VocabularyTargetForm
import org.json.JSONObject

/** Verified context-pack payload only. The matcher grants the message scope. */
object ReviewedContextRecord {
    fun mapping(payload:String,source:String,target:String):ContextMapping {
        require(payload.toByteArray().size<=32768)
        val row=JSONObject(payload)
        require(row.getString("source_language")==source && row.getString("target_language")==target)
        val context=row.getString("target_context");val span=row.getJSONArray("target_span")
        require(span.length()==2)
        val a=span.getInt(0);val b=span.getInt(1);val word=row.getString("target")
        require(a>=0 && b>a && b<=context.length && context.substring(a,b)==word)
        val rawParts=row.getJSONArray("parts")
        val parts=(0 until rawParts.length()).map { index ->
            val part=rawParts.getJSONObject(index);require(part.length()==1)
            when {
                part.has("literal") -> ContextPart.Literal(part.getString("literal"))
                part.has("focus") -> ContextPart.Focus(part.getString("focus"))
                part.has("slot") -> ContextPart.Slot(part.getJSONArray("slot").let { values -> (0 until values.length()).map(values::getString) })
                else -> error("Invalid context part")
            }
        }
        val touching=LocalImmersion.words(context,target).filter { it.first<b && it.last+1>a }
        val forms=if (touching.isEmpty()) emptyList() else {
            val start=minOf(a,touching.first().first);val end=maxOf(b,touching.last().last+1)
            listOf(VocabularyTargetForm(context.substring(start,end),word,a-start,b-start))
        }
        val reading=row.getString("reading")
        return ContextMapping(row.getString("id"),row.getString("meaning"),source,target,parts,listOf(word),
            if (reading.isEmpty()) emptyMap() else mapOf(word to listOf(reading)),forms)
    }
}
