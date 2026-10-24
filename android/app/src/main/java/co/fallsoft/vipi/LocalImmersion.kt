package co.fallsoft.vipi

import android.icu.text.BreakIterator
import co.fallsoft.vipi.core.ImmersionEngine
import co.fallsoft.vipi.core.VocabularyEntry
import java.util.Locale

internal object LocalImmersion {
    fun words(text: String, language: String): List<IntRange> {
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
