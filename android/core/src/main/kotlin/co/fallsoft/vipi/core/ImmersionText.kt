package co.fallsoft.vipi.core

import java.text.BreakIterator
import java.util.Locale

/** Logical selection-copy/accessibility text, NOT native WordSlot layout.
 * Keep the original UTF16 anchors, punctuation, case and chosen faces unchanged.
 * Only distinct touching slots can gain a separator; at least one must be showing
 * an imported target/reading face. Fully revealed original text stays byte-exact.
 */
object ImmersionText {
    fun project(value: ImmersionPresentation, revealed: Set<Int> = emptySet(), showScript: Boolean = false,
                start: Int = 0, end: Int = value.original.length): String {
        require(start in 0..end && end <= value.original.length)
        if (start == end) return ""
        val partial = value as? PartialImmersionResult
        // Only the typed partial producer authorizes WHOLE catalog sentence units.
        // Complete/ordinary word slots keep C1's existing letter-edge policy.
        val sentenceUnits = partial?.references?.associateBy { it.start to it.end }.orEmpty()
        fun isSentence(word: ImmersionSpan): Boolean = sentenceUnits[word.start to word.end]?.let {
            it.original == word.original && it.translated == word.translated &&
                word.targetStart == 0 && word.targetEnd == it.translated.length
        } == true
        return buildString {
            var cursor = start
            var previous: ImmersionSpan? = null
            var previousFace = ""
            var previousOriginal = true
            var previousWholeFace = false
            var characters: BreakIterator? = null
            for (word in value.spans.filter { it.start < end && it.end > start }) {
                if (word.start > cursor) append(value.original.substring(cursor, word.start))
                val showingOriginal = word.id in revealed
                val face = if (showingOriginal)
                    value.original.substring(maxOf(start, word.start), minOf(end, word.end))
                else if (showScript) word.translated else word.displayedTarget
                if (previous?.end == word.start && !(previousOriginal && showingOriginal)) {
                    // Imported faces remain atomic under partial source selection;
                    // a revealed face must be selected whole for the sentence rule.
                    val wholeFace = !showingOriginal || (start <= word.start && end >= word.end)
                    val readingFace = !showScript &&
                        ((!previousOriginal && previous!!.romanization != null) ||
                         (!showingOriginal && word.romanization != null))
                    val sentenceBoundary = partial != null && previousWholeFace && wholeFace &&
                        isSentence(previous!!) && isSentence(word) &&
                        ReferenceComposition.needsSeparator(previousFace, face, partial.targetLanguage, readingFace)
                    val boundary = characters ?: BreakIterator.getCharacterInstance(Locale.ROOT).also { characters = it }
                    if (sentenceBoundary || (latinEdge(previousFace, false, boundary) && latinEdge(face, true, boundary))) append(' ')
                }
                append(face)
                cursor = minOf(word.end, end)
                previous = word; previousFace = face; previousOriginal = showingOriginal
                previousWholeFace = !showingOriginal || (start <= word.start && end >= word.end)
            }
            if (cursor < end) append(value.original.substring(cursor, end))
        }
    }

    // Standard platform character boundaries + Unicode script/category checks;
    // no custom segmenter, normalization, case folding or transliteration.
    private fun latinEdge(face: String, first: Boolean, characters: BreakIterator): Boolean {
        if (face.isEmpty()) return false
        characters.setText(face)
        val start = if (first) 0 else characters.preceding(face.length)
        val end = if (first) characters.following(0) else face.length
        if (start == BreakIterator.DONE || end == BreakIterator.DONE || start >= end) return false
        fun latinLetter(cp: Int) = Character.isLetter(cp) && Character.UnicodeScript.of(cp) == Character.UnicodeScript.LATIN
        if (!latinLetter(face.codePointAt(start))) return false
        var cursor = start
        while (cursor < end) {
            val cp = face.codePointAt(cursor)
            val mark = when (Character.getType(cp)) {
                Character.NON_SPACING_MARK.toInt(), Character.COMBINING_SPACING_MARK.toInt(), Character.ENCLOSING_MARK.toInt() -> true
                else -> false
            }
            if (!latinLetter(cp) && !mark) return false
            cursor += Character.charCount(cp)
        }
        return true
    }
}
