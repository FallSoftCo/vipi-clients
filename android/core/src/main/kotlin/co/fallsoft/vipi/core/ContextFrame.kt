package co.fallsoft.vipi.core

data class ContextFrame(val id:String,val meaning:String,val sourceLanguage:String,val targetLanguage:String,
    val sourceParts:List<ContextPart>,val targetParts:List<ContextPart>,val reading:String="",val lexicalUnit:Boolean=false,
    val sourceUnit:Boolean=lexicalUnit,val targetUnit:Boolean=lexicalUnit,val commonNounCaseVariants:Boolean=false)
data class ContextFrameHit(val frame:ContextFrame,val sourceWindows:List<IntRange>,val targetWindows:List<IntRange>)

/** Exact indexed phrase matches still require an explicitly assessed record.
 * A source meaning remains a competing claim even when its target is absent. */
object ContextFrameMatcher {
    fun entries(original:String,translation:String,source:String,target:String,hits:List<ContextFrameHit>):List<VocabularyEntry> {
        if(original.isEmpty() || translation.isEmpty() || original.length>16384 || translation.length>32768 ||
            source==target || hits.size>256 || hits.map{it.frame.id}.distinct().size!=hits.size)return emptyList()
        fun focuses(text:String,windows:List<IntRange>,parts:List<ContextPart>,unit:Boolean):Set<IntRange>? {
            if(windows.size>256)return null
            val whole=if(unit) (parts.singleOrNull() as? ContextPart.Focus)?.text?.takeIf{it.isNotBlank() && it.length<=128} ?: return null else null
            val result=linkedSetOf<IntRange>()
            for(window in windows) {
                if(window.first<0 || window.last<window.first || window.last>=text.length || window.last-window.first+1>256)return null
                if((window.first>0 && Character.isLowSurrogate(text[window.first])) ||
                    (window.last+1<text.length && Character.isLowSurrogate(text[window.last+1])))return null
                val fragment=text.substring(window)
                val focus=if(unit) {
                    if(fragment!=whole)return null
                    0 until fragment.length
                } else ContextMappingMatcher.focus(fragment,parts) ?: return null
                result+=(window.first+focus.first)..(window.first+focus.last)
            }
            return result
        }
        fun casePermitted(frame:ContextFrame,text:String,range:IntRange,language:String,unit:Boolean):Boolean {
            if(!frame.commonNounCaseVariants || !unit || language !in setOf("en","es","fr","it","pt","sw") ||
                !text[range.first].isUpperCase())return true
            return WrittenCase.sentenceInitial(text,range.first)
        }
        val groups=linkedMapOf<IntRange,MutableList<Pair<ContextFrame,IntRange?>>>()
        val blocked=linkedSetOf<IntRange>()
        for(hit in hits) {
            val frame=hit.frame
            if(frame.sourceLanguage!=source || frame.targetLanguage!=target || frame.id.isBlank() || frame.id.length>256 ||
                frame.meaning.isBlank() || frame.meaning.length>2048)return emptyList()
            if(frame.lexicalUnit != (frame.sourceUnit && frame.targetUnit))return emptyList()
            val left=focuses(original,hit.sourceWindows,frame.sourceParts,frame.sourceUnit) ?: return emptyList()
            val right=focuses(translation,hit.targetWindows,frame.targetParts,frame.targetUnit) ?: return emptyList()
            if(left.isEmpty())return emptyList()
            if(left.size>1 || right.size>1)blocked.addAll(left)
            for(focus in left)groups.getOrPut(focus){mutableListOf()}.add(frame to right.singleOrNull())
        }
        return groups.entries.sortedBy{it.key.first}.flatMap { (focus,group) ->
            if(focus in blocked || group.map{it.first.meaning}.distinct().size!=1)emptyList()
            else group.mapNotNull { (frame,targetFocus) ->
                targetFocus?.let { range ->
                    // A tokenizer may split a listed plural suffix (子ども + たち).
                    // For the same source focus and assessed sense, preserve the
                    // complete approved target unit. Separate occurrences and
                    // conflicting meanings/readings still use the normal guards.
                    if (frame.targetUnit && group.any { (other, parent) ->
                        other.targetUnit && parent != null && parent != range &&
                            parent.first <= range.first && parent.last >= range.last
                    }) return@let null
                    // Keep all source meanings and repeated occurrences in
                    // the groups above; casing cannot erase contrary evidence.
                    if(!casePermitted(frame,original,focus,source,frame.sourceUnit) ||
                        !casePermitted(frame,translation,range,target,frame.targetUnit))return@let null
                    val word=translation.substring(range)
                    VocabularyEntry(original.substring(focus),listOf(word),if(frame.reading.isEmpty())emptyMap() else mapOf(word to listOf(frame.reading)),
                        sourceScope=VocabularySourceScope(original,focus.first,focus.last+1),
                        targetScope=VocabularyTargetScope(translation,range.first,range.last+1))
                }
            }
        }.distinct()
    }
}

/** Written sentence boundaries for case aliases; offsets remain UTF-16. */
object WrittenCase {
    fun sentenceInitial(text:String,start:Int):Boolean {
        if(start !in 0..text.length)return false
        val before=text.substring(0,start).trimEnd { it.isWhitespace() || it in "¿¡\"'“‘«([{" }
        return before.isEmpty() || before.last() in ".!?。！？"
    }
}
