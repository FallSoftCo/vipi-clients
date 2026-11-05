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
            if (gap.isEmpty() && needsSeparator(output.toString(), value, target)) output.append(' ')
            output.append(gap).append(value); end = range.last + 1
        }
        val tail = original.substring(end)
        return if (tail.all(Char::isWhitespace)) output.append(tail).toString() else null
    }

    /** Shared exact-sentence boundary rule. A displayed reading uses word spacing;
     * target script retains its own zh/ja no-added-space convention. This only
     * decides a separator, never rewrites either approved face or source gap.
     */
    fun needsSeparator(left: String, right: String, target: String, readingFace: Boolean = false): Boolean =
        left.isNotEmpty() && right.isNotEmpty() &&
        (readingFace || target.substringBefore('-') !in setOf("zh", "ja")) &&
        left.last() in ".!?。！？”’\"'" &&
        (Character.isLetterOrDigit(right.codePointAt(0)) || right.first() in "¿¡“‘\"'")

}
