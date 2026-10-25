package co.fallsoft.vipi.core

/** Literal preservation only. Passing this check says nothing about meaning. */
object TranslationIntegrity {
    private val literals = Regex("```[\\s\\S]*?(?:```|$)|`[^`]*(?:`|$)|(?i:https?://|www\\.)[^\\s<>\"「」『』]+|[\\p{L}\\p{N}_.+-]+@[\\p{L}\\p{N}_.-]+\\.[\\p{L}]{2,}|[@#][\\p{L}\\p{N}_]+")
    private val punctuation = ".,!?;:。！？、，；：…"

    internal fun identifiers(text: String): Map<String, Int> = literals.findAll(text).map { match ->
        var value = match.value
        if (value.startsWith("http://", true) || value.startsWith("https://", true) || value.startsWith("www.", true)) {
            // Sentence punctuation is not part of an address. Keep balanced URL
            // parentheses, query strings and fragments exactly as received.
            while (value.isNotEmpty()) {
                val last = value.last()
                val opening = when (last) { ')' -> '('; ']' -> '['; '}' -> '{'; else -> null }
                if (last in punctuation || (opening != null && value.count { it == last } > value.count { it == opening })) value = value.dropLast(1)
                else break
            }
        }
        value
    }.groupingBy { it }.eachCount()

    fun preservesIdentifiers(original: String, translation: String): Boolean =
        identifiers(original) == identifiers(translation)
}
