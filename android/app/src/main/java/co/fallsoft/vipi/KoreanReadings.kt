package co.fallsoft.vipi

/** Spelling-based display metadata; never modifies source or audio. */
internal object KoreanReadings {
    data class Piece(val startUTF16: Int, val endUTF16: Int, val source: String,
                     val rendered: String, val kind: String, val insertedSeparator: Boolean)
    data class Result(val reading: String?, val inspection: String,
                      val pieces: List<Piece>, val issues: Set<String>)
    private val opaque = listOf(
        Regex("```[\\s\\S]*?```"), Regex("`[^`\\r\\n]+`"),
        Regex("(?i)(?:https?://|www\\.)[^\\s<>\"“”‘’，。！？；、]+"),
        Regex("[\\p{IsLatin}\\p{M}\\p{N}._%+\\-]+@[\\p{IsLatin}\\p{M}\\p{N}.\\-]+\\.[\\p{IsLatin}\\p{M}]{2,}"),
        Regex("[\\p{IsLatin}\\p{M}\\p{N}]++(?:[\\-_'’./:][\\p{IsLatin}\\p{M}\\p{N}]++)*+"),
    )

    private fun emailLocalPoint(point: Int): Boolean =
        Character.UnicodeScript.of(point) == Character.UnicodeScript.LATIN ||
            Character.getType(point) in setOf(Character.NON_SPACING_MARK.toInt(),
                Character.COMBINING_SPACING_MARK.toInt(), Character.ENCLOSING_MARK.toInt(),
                Character.DECIMAL_DIGIT_NUMBER.toInt(), Character.LETTER_NUMBER.toInt(),
                Character.OTHER_NUMBER.toInt()) || point in "._%+-".map(Char::code)

    private fun emailMatches(text: String): Sequence<MatchResult> = sequence {
        // Start at each actual @ token instead of retrying a greedy email
        // expression from every position of a long non-email identifier.
        for (at in text.indices) if (text[at] == '@') {
            var start = at
            while (start > 0) {
                val point = text.codePointBefore(start)
                if (!emailLocalPoint(point)) break
                start -= Character.charCount(point)
            }
            if (start < at) opaque[3].matchAt(text, start)?.let { yield(it) }
        }
    }

    private fun endsAlphanumeric(value: CharSequence): Boolean {
        var end = value.length
        while (end > 0) {
            val point = Character.codePointBefore(value, end)
            val category = Character.getType(point)
            if (category !in setOf(Character.NON_SPACING_MARK.toInt(),
                    Character.COMBINING_SPACING_MARK.toInt(), Character.ENCLOSING_MARK.toInt()))
                return Character.isLetterOrDigit(point)
            end -= Character.charCount(point)
        }
        return false
    }

    fun resolve(text: String): Result {
        if (text.isEmpty() || text.length > FullReadingLimits.MAX_TEXT_UTF16)
            return Result(null, text, emptyList(), setOf("input_length"))
        val mask = BooleanArray(text.length)
        for ((patternIndex, pattern) in opaque.withIndex()) for (match in
            if (patternIndex == 3) emailMatches(text) else pattern.findAll(text)) {
            if (match.range.any { mask[it] }) continue
            for (index in match.range) mask[index] = true
        }
        fun kind(index: Int): String {
            val point = text.codePointAt(index)
            val length = Character.charCount(point)
            if ((index until index + length).all { mask[it] }) return "opaque"
            if (point in 0xAC00..0xD7A3) return "hangul"
            return if (Character.isLetter(point) && Character.UnicodeScript.of(point) != Character.UnicodeScript.LATIN)
                "unresolved" else "literal"
        }
        val pieces = mutableListOf<Piece>()
        val issues = linkedSetOf<String>()
        val output = StringBuilder()
        var index = 0
        var previousConverted = false
        var convertedAny = false
        while (index < text.length) {
            val start = index
            val type = kind(index)
            index += Character.charCount(text.codePointAt(index))
            while (index < text.length && kind(index) == type)
                index += Character.charCount(text.codePointAt(index))
            val source = text.substring(start, index)
            val converted = type == "hangul"
            val rendered = if (converted) KoreanLetterRules.romanize(source) else source
            val separator = (previousConverted || converted) && output.isNotEmpty() && rendered.isNotEmpty() &&
                endsAlphanumeric(output) &&
                Character.isLetterOrDigit(rendered.codePointAt(0))
            if (separator) output.append(' ')
            output.append(rendered)
            pieces += Piece(start, index, source, rendered,
                if (converted) "converted" else type, separator)
            if (type == "unresolved") issues += "untranscribed_script"
            previousConverted = converted
            convertedAny = convertedAny || converted
        }
        check(pieces.joinToString("") { it.source } == text)
        check(pieces.zipWithNext().all { (a, b) -> a.endUTF16 == b.startUTF16 })
        if (output.length > FullReadingLimits.MAX_READING_UTF16) issues += "output_length"
        val inspection = output.toString()
        return Result(if (issues.isEmpty() && convertedAny) inspection else null,
            inspection, pieces.toList(), issues.toSet())
    }
}
