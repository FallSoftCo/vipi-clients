package co.fallsoft.vipi

import android.text.Spannable
import android.text.SpannableStringBuilder
import android.text.TextDirectionHeuristic
import android.text.style.ReplacementSpan
import java.util.WeakHashMap

/** MeasuredParagraph copies a paragraph through GetChars, masks replacement spans
 * with U+FFFC, then asks the heuristic about that array at offset zero. Preserve
 * the source range at that public copy boundary, rather than guessing paragraph
 * identity from equal masked text or from the order of layout callbacks.
 *
 * This bridges the AOSP Android 9/16 copy-before-bidi implementation; it changes
 * neither source characters nor spans. Array keys have identity equality and are
 * weak, and records are consumed once and scoped to the current native buffer. */
internal class SourceParagraphDirection(private val fallback: () -> TextDirectionHeuristic) : TextDirectionHeuristic {
    private data class Copy(val source: SourceText, val start: Int, val count: Int, val destinationStart: Int)
    private val copies = WeakHashMap<CharArray, Copy>()
    private var current: SourceText? = null

    val factory = object : Spannable.Factory() {
        override fun newSpannable(source: CharSequence): Spannable = SourceText(source, this@SourceParagraphDirection).also {
            synchronized(copies) { copies.clear(); current = it }
        }
    }

    private class SourceText(source: CharSequence, registry: SourceParagraphDirection) : SpannableStringBuilder(source) {
        // getChars can be called while the superclass is still constructing us.
        private var registry: SourceParagraphDirection? = null
        val original = source.toString()
        init { this.registry = registry }
        override fun getChars(start: Int, end: Int, destination: CharArray, destinationStart: Int) {
            super.getChars(start, end, destination, destinationStart)
            registry?.copied(this, start, end, destination, destinationStart)
        }
    }

    private fun copied(source: SourceText, start: Int, end: Int, destination: CharArray, destinationStart: Int) {
        synchronized(copies) {
            // A pooled array may already have been used by a previous layout.
            copies.remove(destination)
            if (source !== current || start < 0 || end < start || end > source.original.length ||
                destinationStart < 0 || destinationStart > destination.size - (end - start)) return
            // Text is selectable, not editable; nevertheless do not trust a
            // record if an external Editable caller changed its characters.
            for (i in start until end) if (destination[destinationStart + i - start] != source.original[i]) return
            copies[destination] = Copy(source, start, end - start, destinationStart)
        }
    }

    override fun isRtl(text: CharArray, start: Int, count: Int): Boolean {
        val copied = synchronized(copies) { copies.remove(text)?.takeIf { it.source === current } }
        if (copied != null && start >= copied.destinationStart && count >= 0 &&
            start - copied.destinationStart <= copied.count - count && start <= text.size - count) {
            val sourceStart = copied.start + start - copied.destinationStart
            val sourceEnd = sourceStart + count
            val spans = copied.source.getSpans(sourceStart, sourceEnd, ReplacementSpan::class.java)
            val replaced = BooleanArray(count)
            spans.forEach { span ->
                val from = maxOf(sourceStart, copied.source.getSpanStart(span)) - sourceStart
                val to = minOf(sourceEnd, copied.source.getSpanEnd(span)) - sourceStart
                if (from < to) replaced.fill(true, from, to)
            }
            val matches = (0 until count).all { offset ->
                val position = sourceStart + offset
                val character = text[start + offset]
                character == copied.source.original[position] || (character == '\uFFFC' && replaced[offset])
            }
            if (matches) return fallback().isRtl(copied.source.original, sourceStart, count)
        }
        return fallback().isRtl(text, start, count)
    }

    override fun isRtl(text: CharSequence, start: Int, count: Int): Boolean {
        val original = synchronized(copies) { (text as? SourceText)?.takeIf { it === current }?.original }
        return fallback().isRtl(original ?: text, start, count)
    }
}
