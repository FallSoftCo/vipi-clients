package co.fallsoft.vipi

import android.icu.text.BreakIterator
import co.fallsoft.vipi.core.ImmersionEngine
import co.fallsoft.vipi.core.VocabularyEntry
import java.util.Locale
import com.atilika.kuromoji.ipadic.Tokenizer

internal object LocalImmersion {
    private val japanese by lazy { Tokenizer() }
    /** Complete native sentences, preserving offsets in the original message. */
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
    fun words(text: String, language: String): List<IntRange> {
        // ICU's general word breaker can split 会おう into 会 + おう and let
        // a noun entry for 会 replace a fragment of the verb. Use morphology.
        if (language == "ja") return japanese.tokenize(text).mapNotNull { token ->
            if (token.surface.codePoints().anyMatch { Character.isLetter(it) })
                token.position until token.position + token.surface.length else null
        }
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
    fun align(original: String, translation: String, entries: List<VocabularyEntry>, density: Double, source: String, target: String): co.fallsoft.vipi.core.ImmersionResult {
        val sourceWords = words(original, source); val targetWords = words(translation, target)
        return ImmersionEngine().align(original, translation, entries, density, target,
            sourceWords.flatMap { listOf(it.first, it.last + 1) }.toSet(),
            targetWords.flatMap { listOf(it.first, it.last + 1) }.toSet(), sourceWords.size)
    }
}
