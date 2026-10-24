package co.fallsoft.vipi.core

data class VocabularyEntry(val source: String, val targets: List<String>)
data class ImmersionSpan(val start: Int, val end: Int, val original: String, val translated: String) {
    val id: Int get() = start
}
data class SpeechSpan(val text: String, val language: String)
data class ImmersionResult(val original: String, val translation: String, val spans: List<ImmersionSpan>) {
    fun speech(source: String, target: String, revealed: Set<Int> = emptySet()): List<SpeechSpan> = buildList {
        var cursor = 0
        for (span in spans) {
            if (cursor < span.start) add(SpeechSpan(original.substring(cursor, span.start), source))
            val showOriginal = span.id in revealed
            add(SpeechSpan(if (showOriginal) span.original else span.translated, if (showOriginal) source else target))
            cursor = span.end
        }
        if (cursor < original.length) add(SpeechSpan(original.substring(cursor), source))
    }
}

class ImmersionEngine {
    private val words = Regex("[\\p{L}\\p{M}]+")
    private val protected = Regex("https?://\\S+|www\\.\\S+|[\\w.+-]+@[\\w.-]+\\.[\\p{L}]{2,}|```[\\s\\S]*?```|`[^`]*`|[@#][\\p{L}\\p{N}_]+|\\p{N}+(?:[.,:]\\p{N}+)*")
    private data class Candidate(val span: ImmersionSpan, val target: IntRange)

    fun align(original: String, translation: String, entries: List<VocabularyEntry>, density: Double): ImmersionResult {
        val empty = ImmersionResult(original, translation, emptyList())
        if (original.isEmpty() || translation.isEmpty() || !density.isFinite() || density <= 0 || original.length > 16_384 || translation.length > 32_768) return empty
        val protectedRanges = protected.findAll(original).map { it.range }.toList()
        val candidates = entries.mapNotNull { entry ->
            if (entry.source.isEmpty() || entry.source.length > 128) return@mapNotNull null
            val source = occurrences(entry.source, original).singleOrNull() ?: return@mapNotNull null
            if (protectedRanges.any { overlaps(it, source) }) return@mapNotNull null
            val targets = entry.targets.distinct().filter { it.isNotEmpty() && it.length <= 128 }.flatMap { occurrences(it, translation) }.distinct()
            val target = targets.singleOrNull() ?: return@mapNotNull null
            val sourceSurface = original.substring(source)
            val targetSurface = translation.substring(target)
            if (sourceSurface.equals(targetSurface, ignoreCase = true)) return@mapNotNull null
            Candidate(ImmersionSpan(source.first, source.last + 1, sourceSurface, targetSurface), target)
        }
        val unique = candidates.filter { candidate ->
            candidates.none { other ->
                (other.span.start == candidate.span.start && other.span.end == candidate.span.end && other.target != candidate.target) ||
                    (other.span.start != candidate.span.start &&
                    !overlaps(other.span.start until other.span.end, candidate.span.start until candidate.span.end) && overlaps(other.target, candidate.target))
            }
        }.sortedWith(compareByDescending<Candidate> { it.span.end - it.span.start }.thenBy { it.span.start })
        val budget = maxOf(1, (words.findAll(original).count() * density.coerceAtMost(1.0)).toInt())
        var used = 0
        val selected = mutableListOf<ImmersionSpan>()
        for (candidate in unique) {
            val count = maxOf(1, words.findAll(candidate.span.original).count())
            if (used + count > budget || selected.any { overlaps(it.start until it.end, candidate.span.start until candidate.span.end) }) continue
            selected += candidate.span
            used += count
        }
        return ImmersionResult(original, translation, selected.sortedBy { it.start })
    }

    private fun occurrences(phrase: String, text: String): List<IntRange> =
        Regex("(?<![\\p{L}\\p{M}\\p{N}_])" + Regex.escape(phrase) + "(?![\\p{L}\\p{M}\\p{N}_])", RegexOption.IGNORE_CASE).findAll(text).map { it.range }.toList()
    private fun overlaps(a: IntRange, b: IntRange) = a.first <= b.last && b.first <= a.last
}
