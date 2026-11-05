package co.fallsoft.vipi.core

/** Exact authored sentence values only; caller owns native sentence segmentation.
 * A separator between adjacent known sentences is not a new translation/mapping.
 */
object ReferenceComposition {
    fun compose(original: String, sentences: List<IntRange>, target: String,
                lookup: (String) -> String?): String? {
        if (sentences.isEmpty()) return null
        var end = 0
        val output = StringBuilder()
        for (range in sentences) {
            if (range.first < end || range.last < range.first || range.last >= original.length) return null
            val gap = original.substring(end, range.first)
            if (!gap.all(Char::isWhitespace)) return null
            val value = lookup(original.substring(range)) ?: return null
            if (gap.isEmpty() && output.isNotEmpty() && value.isNotEmpty() &&
                target.substringBefore('-') !in setOf("zh", "ja") &&
                output.last() in ".!?。！？”’\"'" &&
                (Character.isLetterOrDigit(value.codePointAt(0)) || value.first() in "¿¡“‘\"'")) output.append(' ')
            output.append(gap).append(value); end = range.last + 1
        }
        val tail = original.substring(end)
        return if (tail.all(Char::isWhitespace)) output.append(tail).toString() else null
    }
}
