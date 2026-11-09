package co.fallsoft.vipi.contextqa
import android.icu.text.BreakIterator
import java.util.Locale
internal object NativeGeometry {
    fun sentences(text:String,language:String):List<IntRange> {
        val iterator=BreakIterator.getSentenceInstance(Locale.forLanguageTag(language));iterator.setText(text)
        val ranges=mutableListOf<IntRange>();var start=iterator.first();var end=iterator.next()
        while(end!=BreakIterator.DONE) {
            var a=start;var b=end
            while(a<b && text[a].isWhitespace())a++
            while(a<b && text[b-1].isWhitespace())b--
            if(a<b)ranges+=a until b
            if(ranges.size>128)return emptyList()
            start=end;end=iterator.next()
        }
        return ranges
    }
    fun words(text:String,language:String):List<IntRange> {
        require(language=="en")
        val iterator = BreakIterator.getWordInstance(Locale.forLanguageTag(language))
        iterator.setText(text)
        return buildList {
            var start = iterator.first()
            var end = iterator.next()
            while (end != BreakIterator.DONE) {
                if (text.substring(start, end).codePoints().anyMatch { Character.isLetter(it) }) add(start until end)
                start = end; end = iterator.next()
            }
        }
    }
    fun lookupKey(value:String)=java.text.Normalizer.normalize(value,java.text.Normalizer.Form.NFC).lowercase(Locale.ROOT).filter { it.code != 0x0640 && it.code !in 0x064B..0x0652 && it.code != 0x0670 }
}
