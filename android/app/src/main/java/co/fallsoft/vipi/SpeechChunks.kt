package co.fallsoft.vipi

import co.fallsoft.vipi.core.SpeechSpan

/** Preserve every character and language while bounding the first render. */
internal object SpeechChunks {
    // A completed persisted translation must fit the encrypted record's2MiB
    // bound. Stream the whole derived message instead of reapplying the old
    // per-render16KiB limit to the full utterance. Individual renders stay small.
    const val MAX_MESSAGE_UTF16 = 2_097_152
    fun plan(spans: List<SpeechSpan>): List<List<SpeechSpan>> {
        require(spans.isNotEmpty() && spans.sumOf { it.text.length.toLong() } <= MAX_MESSAGE_UTF16)
        val pieces = mutableListOf<SpeechSpan>()
        for (span in spans) {
            val text = span.text
            var start = 0
            while (start < text.length) {
                var end = minOf(start + 160, text.length)
                if (end < text.length) {
                    val boundary = (start until end).lastOrNull { text[it].isWhitespace() || text[it] in ".!?。！？،,;；" }
                    if (boundary != null && boundary - start >= 60) end = boundary + 1
                    else if (Character.isHighSurrogate(text[end - 1])) end--
                }
                pieces += span.copy(text = text.substring(start, end))
                start = end
            }
        }
        val result = mutableListOf<List<SpeechSpan>>()
        var current = mutableListOf<SpeechSpan>(); var size = 0
        for (piece in pieces) {
            if (size > 0 && size + piece.text.length > 160) { result += current; current = mutableListOf(); size = 0 }
            current += piece; size += piece.text.length
        }
        if (current.isNotEmpty()) result += current
        return result.filter { chunk -> chunk.any { it.text.isNotBlank() } }
    }
}
