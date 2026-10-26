package co.fallsoft.vipi.core

data class ContextFrame(val id:String,val meaning:String,val sourceLanguage:String,val targetLanguage:String,
    val sourceParts:List<ContextPart>,val targetParts:List<ContextPart>,val reading:String="")
data class ContextFrameHit(val frame:ContextFrame,val sourceWindows:List<IntRange>,val targetWindows:List<IntRange>)

/** Exact indexed phrase matches still require an explicitly assessed record.
 * A source meaning remains a competing claim even when its target is absent. */
object ContextFrameMatcher {
    fun entries(original:String,translation:String,source:String,target:String,hits:List<ContextFrameHit>):List<VocabularyEntry> {
        if(original.isEmpty() || translation.isEmpty() || original.length>16384 || translation.length>32768 ||
            source==target || hits.size>256 || hits.map{it.frame.id}.distinct().size!=hits.size)return emptyList()
        fun focuses(text:String,windows:List<IntRange>,parts:List<ContextPart>):Set<IntRange>? {
            if(windows.size>256)return null
            val result=linkedSetOf<IntRange>()
            for(window in windows) {
                if(window.first<0 || window.last<window.first || window.last>=text.length || window.last-window.first+1>256)return null
                if((window.first>0 && Character.isLowSurrogate(text[window.first])) ||
                    (window.last+1<text.length && Character.isLowSurrogate(text[window.last+1])))return null
                val focus=ContextMappingMatcher.focus(text.substring(window),parts) ?: return null
                result+=(window.first+focus.first)..(window.first+focus.last)
            }
            return result
        }
        val groups=linkedMapOf<IntRange,MutableList<Pair<ContextFrame,IntRange?>>>()
        val blocked=linkedSetOf<IntRange>()
        for(hit in hits) {
            val frame=hit.frame
            if(frame.sourceLanguage!=source || frame.targetLanguage!=target || frame.id.isBlank() || frame.id.length>256 ||
                frame.meaning.isBlank() || frame.meaning.length>2048)return emptyList()
            val left=focuses(original,hit.sourceWindows,frame.sourceParts) ?: return emptyList()
            val right=focuses(translation,hit.targetWindows,frame.targetParts) ?: return emptyList()
            if(left.isEmpty())return emptyList()
            if(left.size>1 || right.size>1)blocked.addAll(left)
            for(focus in left)groups.getOrPut(focus){mutableListOf()}.add(frame to right.singleOrNull())
        }
        return groups.entries.sortedBy{it.key.first}.flatMap { (focus,group) ->
            if(focus in blocked || group.map{it.first.meaning}.distinct().size!=1)emptyList()
            else group.mapNotNull { (frame,targetFocus) ->
                targetFocus?.let { range ->
                    val word=translation.substring(range)
                    VocabularyEntry(original.substring(focus),listOf(word),if(frame.reading.isEmpty())emptyMap() else mapOf(word to listOf(frame.reading)),
                        sourceScope=VocabularySourceScope(original,focus.first,focus.last+1),
                        targetScope=VocabularyTargetScope(translation,range.first,range.last+1))
                }
            }
        }.distinct()
    }
}
