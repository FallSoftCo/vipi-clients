package co.fallsoft.vipi

import co.fallsoft.vipi.core.TranslationIntegrity
import java.text.BreakIterator
import java.util.Locale

/** Actual original-source range translated, never a target-word projection. */
internal data class ManualSourceContext(val text:String,val startUTF16:Int,val endUTF16:Int)
internal object ManualTranslationContext {
    private val closing=")]}'\"”’»〉」』】〕〗）］｝".toSet()
    private val terminal=".!?…。！？؟".toSet()
    private val abbreviation=Regex("(?iu)(?:\\b(?:mr|mrs|ms|dr|prof|sr|jr|st|vs|etc|fig|no|m|mme|mlle|sig|dott|sra)|(?:\\b\\p{L}\\.)+\\p{L}|\\b\\p{L})\\.$")
    fun enclosing(text:String,start:Int,end:Int,language:String?):ManualSourceContext {
        fun whole()=ManualSourceContext(text,0,text.length)
        if(start==0&&end==text.length)return whole()
        if(start<0||end<=start||end>text.length)return whole()
        return try {
            val protected=TranslationIntegrity.protectedLiteralRanges(text)
            val characters=BreakIterator.getCharacterInstance(Locale.ROOT).apply{setText(text)}
            fun insideLiteral(offset:Int)=protected.any{offset>it.first&&offset<=it.last}
            val sentences=BreakIterator.getSentenceInstance(language?.let(Locale::forLanguageTag)?:Locale.ROOT).apply{setText(text)}
            val boundaries=sortedSetOf(0,text.length)
            var boundary=sentences.first()
            while(boundary!=BreakIterator.DONE){
                var candidate=boundary
                while(candidate>0&&text[candidate-1].isWhitespace())candidate--
                while(candidate<text.length&&text[candidate] in closing)candidate++
                if(candidate in 1 until text.length&&characters.isBoundary(candidate)&&!insideLiteral(candidate)){
                    var punctuation=candidate
                    while(punctuation>0&&text[punctuation-1] in closing)punctuation--
                    val complete=punctuation>0&&text[punctuation-1] in terminal
                    val prefix=text.substring(0,punctuation)
                    if(complete&&!abbreviation.containsMatchIn(prefix))boundaries+=candidate
                }
                boundary=sentences.next()
            }
            var from=boundaries.lastOrNull{it<=start}?:0
            var to=boundaries.firstOrNull{it>=end}?:text.length
            // Whitespace outside the actual gesture is not part of a sentence.
            while(from<start&&text[from].isWhitespace())from++
            while(to>end&&text[to-1].isWhitespace())to--
            if(from>start||to<end||from>=to||!characters.isBoundary(from)||!characters.isBoundary(to)||insideLiteral(from)||insideLiteral(to))return whole()
            val pairs=mapOf('(' to ')','[' to ']','{' to '}','“' to '”','«' to '»','「' to '」','『' to '』')
            val stack=mutableListOf<Char>();var quotes=false
            for(i in from until to){
                if(protected.any{i in it})continue
                val c=text[i]
                if(c=='"')quotes=!quotes
                if(c in pairs)stack+=pairs.getValue(c)
                else if(c in pairs.values){if(stack.isEmpty()||stack.removeAt(stack.lastIndex)!=c)return whole()}
            }
            if(stack.isNotEmpty()||quotes)return whole()
            ManualSourceContext(text.substring(from,to),from,to)
        }catch(_:Exception){whole()}
    }
}
