package co.fallsoft.vipi

import android.content.Context
import android.icu.text.BreakIterator
import co.fallsoft.vipi.core.SpeechSpan
import java.util.Locale

/** Coordinates are UTF-16 offsets into the two actual faces of a message. */
internal data class PlayingWord(val script: IntRange, val reading: IntRange?)

internal data class SpeechPiece(val text: String, val start: Int, val pauseBefore: Boolean = false)

internal object MessageSpeech {
    const val GAP_MS = 160

    fun pieces(value: FullMessageTranslation): List<SpeechPiece> {
        val words = value.words
        val text = value.practiceText
        if (words == null) return fullMessagePieces(text, value.practiceLanguage)
        val runs =
            buildList<IntRange> {
                val ranges = WordReplacement.ranges(words, reading = false)
                for (range in ranges) {
                    val previous = lastOrNull()
                    val separate =
                        previous == null ||
                            text.substring(previous.last + 1, range.first).codePoints().anyMatch {
                                Character.isLetterOrDigit(it) ||
                                    Character.getType(it) == Character.OTHER_SYMBOL.toInt()
                            }
                    if (separate) add(range) else this[lastIndex] = previous.first..range.last
                }
            }
        return runs.flatMapIndexed { index, run ->
            val part = text.substring(run)
            var offset = 0
            SpeechChunks.plan(listOf(SpeechSpan(part, value.practiceLanguage))).map { spans ->
                val chunk = spans.joinToString("") { it.text }
                // SpeechChunks omits whitespace-only chunks on very long messages.
                val start = part.indexOf(chunk, offset)
                offset = start + chunk.length
                SpeechPiece(chunk, run.first + start, index > 0 && start == 0)
            }
        }
    }

    private fun fullMessagePieces(text: String, language: String): List<SpeechPiece> {
        require(text.length <= SpeechChunks.MAX_MESSAGE_UTF16)
        // Bound buffering, cancellation latency and PCM memory on long posts.
        // Ordinary chat turns fit in one render, including their punctuation.
        val limit = 480
        if (text.length <= limit) return listOf(SpeechPiece(text, 0))
        val sentences =
            BreakIterator.getSentenceInstance(Locale.forLanguageTag(language)).apply {
                setText(text)
            }
        val words =
            BreakIterator.getWordInstance(Locale.forLanguageTag(language)).apply { setText(text) }
        return buildList {
            var start = 0
            while (start < text.length) {
                var end = minOf(start + limit, text.length)
                if (end < text.length) {
                    val sentenceEnd = sentences.preceding(end + 1)
                    val wordEnd = if (sentenceEnd > start) sentenceEnd else words.preceding(end + 1)
                    if (wordEnd > start) end = wordEnd
                    else if (Character.isHighSurrogate(text[end - 1])) end--
                }
                val piece = text.substring(start, end)
                if (piece.isNotBlank()) add(SpeechPiece(piece, start))
                start = end
            }
        }
    }

    fun lexicalRanges(text: String, language: String): List<IntRange> {
        val iterator = BreakIterator.getWordInstance(Locale.forLanguageTag(language))
        iterator.setText(text)
        return buildList {
            var start = iterator.first()
            var end = iterator.next()
            while (end != BreakIterator.DONE) {
                if (text.substring(start, end).codePoints().anyMatch(Character::isLetterOrDigit))
                    add(start until end)
                start = end
                end = iterator.next()
            }
        }
    }
}

/**
 * Uses offsets supplied by the same reading producers that drew the bubble. A cached reading with a
 * different spelling cannot acquire unrelated offsets.
 */
internal class SpeechProjection(
    private val identity: Boolean,
    private val entries: List<PlayingWord>,
) {
    fun word(range: IntRange): PlayingWord {
        if (identity) return PlayingWord(range, range)
        val found = entries.binarySearch { it.script.last.compareTo(range.first) }
        val index = if (found >= 0) found else -found - 1
        val first = entries.getOrNull(index) ?: return PlayingWord(range, null)
        if (first.script.first > range.last) return PlayingWord(range, null)
        var last = first
        var next = index + 1
        while (next < entries.size && entries[next].script.first <= range.last) last =
            entries[next++]
        val start = first.reading?.first
        val end = last.reading?.last
        return PlayingWord(range, if (start != null && end != null) start..end else null)
    }

    companion object {
        fun build(context: Context, value: FullMessageTranslation): SpeechProjection {
            val guide = value.practiceReading ?: return SpeechProjection(true, emptyList())
            val entries = mutableListOf<PlayingWord>()
            fun align(text: String, reading: String, base: Int, guideBase: Int) {
                val marks =
                    FullMessageReadings.spokenAlignment(
                        context,
                        text,
                        reading,
                        value.practiceLanguage,
                    )
                for (mark in marks) {
                    val r = mark.reading ?: continue
                    entries +=
                        PlayingWord(
                            base + mark.script.first..base + mark.script.last,
                            guideBase + r.first..guideBase + r.last,
                        )
                }
            }
            val words = value.words
            if (words == null) align(value.practiceText, guide, 0, 0)
            else {
                val script = WordReplacement.ranges(words, false)
                val roman = WordReplacement.ranges(words, true)
                for ((i, word) in words.withIndex()) align(
                    word.target,
                    word.reading ?: word.target,
                    script[i].first,
                    roman[i].first,
                )
            }
            return SpeechProjection(false, entries)
        }
    }
}
