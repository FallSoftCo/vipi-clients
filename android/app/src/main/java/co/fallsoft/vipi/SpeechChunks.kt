package co.fallsoft.vipi

import co.fallsoft.vipi.core.SpeechSpan

/** Preserve every character and language while bounding the first render. */
internal object SpeechChunks {
    fun plan(spans: List<SpeechSpan>): List<List<SpeechSpan>> {
        require(spans.isNotEmpty() && spans.sumOf { it.text.length } <= 16_384)
        val pieces = mutableListOf<SpeechSpan>()
        for (span in spans) {
            var text = span.text
            while (text.length > 160) {
                var end = 160
                val boundary = text.take(160).indexOfLast { it.isWhitespace() || it in ".!?。！？،,;；" }
                if (boundary >= 60) end = boundary + 1
                else if (Character.isHighSurrogate(text[end - 1])) end--
                pieces += span.copy(text = text.substring(0, end)); text = text.substring(end)
            }
            if (text.isNotEmpty()) pieces += span.copy(text = text)
        }
        val result = mutableListOf<List<SpeechSpan>>()
        var current = mutableListOf<SpeechSpan>(); var size = 0
        for (piece in pieces) {
            val punctuationOnly = piece.text.all { it.isWhitespace() || it in ".,!?;:。！？、؛،" }
            if (size > 0 && size + piece.text.length > 160 && !punctuationOnly) { result += current; current = mutableListOf(); size = 0 }
            current += piece; size += piece.text.length
        }
        if (current.isNotEmpty()) result += current
        return result.filter { chunk -> chunk.any { it.text.isNotBlank() } }
    }
}
