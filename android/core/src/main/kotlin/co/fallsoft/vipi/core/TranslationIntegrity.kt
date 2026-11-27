package co.fallsoft.vipi.core

/** Literal preservation only. Passing this check says nothing about meaning. */
object TranslationIntegrity {
    // Bounded underscore/common-file recognition, not arbitrary paths or names.
    // Ordinary chat may omit spaces after a period, so dotted words alone do
    // not establish a literal file.
    private val technicalTokens =
        """(?<![\p{L}\p{N}\p{M}_.-])(?=[\p{L}\p{N}\p{M}_.-]*_)[\p{L}\p{N}\p{M}_.-]*[\p{L}\p{N}\p{M}_-](?![\p{L}\p{N}\p{M}_-]|\.[\p{L}\p{N}\p{M}_.-]*[\p{L}\p{N}\p{M}_-])|(?<![\p{L}\p{N}\p{M}_.])[\p{L}\p{N}\p{M}_-]+(?:\.[\p{L}\p{N}\p{M}_-]+)*\.(?i:txt|md|pdf|csv|tsv|json|jsonl|xml|yaml|yml|toml|ini|log|zip|gz|tar|jpg|jpeg|png|svg|webp|gif|heic|mp3|wav|m4a|mp4|mov|html|css|js|ts|py|swift|kt|kts|sql|apk|ipa|vipihistory)(?:\.[\p{L}\p{N}\p{M}_-]+)*(?![\p{L}\p{N}\p{M}_])"""
    private val literals =
        Regex(
            "```[\\s\\S]*?(?:```|$)|`[^`]*(?:`|$)|(?i:https?://|www\\.)[^\\s<>\"「」『』]+|[\\p{L}\\p{N}\\p{M}_.+-]+@[\\p{L}\\p{N}\\p{M}_.-]+\\.[\\p{L}\\p{M}]{2,}|[@#][\\p{L}\\p{N}\\p{M}_]+|" +
                technicalTokens
        )
    private val punctuation = ".,!?;:。！？、，；：…"

    /** UTF16 ranges from the same matcher and URL trimming used for preservation. */
    fun protectedLiteralRanges(text: String): List<IntRange> =
        literals
            .findAll(text)
            .map { match ->
                var value = match.value
                if (
                    value.startsWith("http://", true) ||
                        value.startsWith("https://", true) ||
                        value.startsWith("www.", true)
                ) {
                    // Sentence punctuation is not part of an address. Preserve balanced
                    // URL parentheses, query strings and fragments exactly as received.
                    while (value.isNotEmpty()) {
                        val last = value.last()
                        val opening =
                            when (last) {
                                ')' -> '('
                                ']' -> '['
                                '}' -> '{'
                                else -> null
                            }
                        if (
                            last in punctuation ||
                                (opening != null &&
                                    value.count { it == last } > value.count { it == opening })
                        )
                            value = value.dropLast(1)
                        else break
                    }
                }
                match.range.first until match.range.first + value.length
            }
            .filter { !it.isEmpty() }
            .toList()

    internal fun identifiers(text: String): Map<String, Int> =
        protectedLiteralRanges(text).map { text.substring(it) }.groupingBy { it }.eachCount()

    fun preservesIdentifiers(original: String, translation: String): Boolean =
        identifiers(original) == identifiers(translation)
}
