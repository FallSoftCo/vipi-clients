package co.fallsoft.vipi.core

data class VocabularyEntry(val source: String, val targets: List<String>, val romanizations: Map<String, List<String>> = emptyMap(), val contextHints: List<String> = emptyList(), val requiresContext: Boolean = false)
data class ImmersionSpan(val start: Int, val end: Int, val original: String, val translated: String,
                         val targetStart: Int = 0, val targetEnd: Int = 0, val romanization: String? = null) {
    val id: Int get() = start
    val displayedTarget: String get() = romanization ?: translated
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
    private data class Candidate(val span: ImmersionSpan, val target: IntRange, val entry: VocabularyEntry)

    fun align(original: String, translation: String, entries: List<VocabularyEntry>, density: Double,
              targetLanguage: String? = null, sourceBoundaries: Set<Int>? = null,
              targetBoundaries: Set<Int>? = null, sourceTokenCount: Int? = null): ImmersionResult {
        val empty = ImmersionResult(original, translation, emptyList())
        if (original.isEmpty() || translation.isEmpty() || !density.isFinite() || density <= 0 || original.length > 16_384 || translation.length > 32_768) return empty
        val protectedRanges = protected.findAll(original).map { it.range }.toList()
        val protectedTargetRanges = protected.findAll(translation).map { it.range }.toList()
        val stops = Regex("[.!?。！？\\n]").findAll(original).map { it.range }.filter { stop -> protectedRanges.none { overlaps(it, stop) } }.toList()
        val supported = entries.filter { entry ->
            val range = occurrences(entry.source, original, sourceBoundaries).firstOrNull() ?: return@filter false
            val lower = stops.lastOrNull { it.last < range.first }?.let { it.last + 1 } ?: 0
            val upper = stops.firstOrNull { it.first > range.last }?.first ?: original.length
            entry.contextHints.any { hint -> hint.isNotEmpty() && hint.length <= 64 && occurrences(hint, original, sourceBoundaries).any { cue ->
                cue.first >= lower && cue.last < upper && !overlaps(cue, range) && protectedRanges.none { overlaps(it, cue) }
            } }
        }.toSet()
        val claims = entries.associateWith { entry ->
            val source = if (entry.source.isNotEmpty() && entry.source.length <= 128) occurrences(entry.source, original, sourceBoundaries) else emptyList()
            val targets = if (source.isEmpty()) emptyList() else entry.targets.distinct().filter { it.isNotEmpty() && it.length <= 128 }
                .flatMap { occurrences(it, translation, targetBoundaries) }.distinct()
            source to targets
        }
        val candidates = entries.mapNotNull { entry ->
            if (entry.source.isEmpty() || entry.source.length > 128) return@mapNotNull null
            val source = claims.getValue(entry).first.singleOrNull() ?: return@mapNotNull null
            if (protectedRanges.any { overlaps(it, source) }) return@mapNotNull null
            val targets = claims.getValue(entry).second
            val target = targets.singleOrNull() ?: return@mapNotNull null
            if (protectedTargetRanges.any { overlaps(it, target) }) return@mapNotNull null
            val sourceSurface = original.substring(source)
            val targetSurface = translation.substring(target)
            if (sourceSurface.equals(targetSurface, ignoreCase = true)) return@mapNotNull null
            val needsReading = targetLanguage?.substringBefore('-') in setOf("ar", "zh", "ja", "ko")
            val readings = entry.romanizations.filterKeys { lookupKey(it) == lookupKey(targetSurface) }.values.flatten().distinct()
            val reading = readings.singleOrNull()?.takeIf { it.length <= 256 && readableRomanization(it) }
            if (needsReading && reading == null) return@mapNotNull null
            Candidate(ImmersionSpan(source.first, source.last + 1, sourceSurface, targetSurface,
                target.first, target.last + 1, if (needsReading) reading else null), target, entry)
        }
        val unique = candidates.filter { candidate ->
            val source = candidate.span.start until candidate.span.end
            claims.none { (entry, claim) ->
                val (sources, targets) = claim
                val competingSense = source in sources && targets.any { it != candidate.target }
                val conflictingReading = source in sources && candidate.target in targets && candidate.span.romanization != null &&
                    entry.romanizations.filterKeys { lookupKey(it) == lookupKey(candidate.span.translated) }.values.flatten().any { it != candidate.span.romanization }
                competingSense || conflictingReading || (sources.any { other -> !overlaps(other, source) && protectedRanges.none { overlaps(it, other) } } && targets.any { overlaps(it, candidate.target) })
            } && candidates.none { other ->
                (other.span.start == candidate.span.start && other.span.end == candidate.span.end &&
                    (other.target != candidate.target || other.span.romanization != candidate.span.romanization)) ||
                    (other.span.start != candidate.span.start &&
                    !overlaps(other.span.start until other.span.end, candidate.span.start until candidate.span.end) && overlaps(other.target, candidate.target))
            }
        }.filter { candidate -> !candidate.entry.requiresContext || candidate.entry in supported }
            .filter { candidate -> candidate.entry in supported || supported.none { lookupKey(it.source) == lookupKey(candidate.entry.source) } }
            .sortedWith(compareByDescending<Candidate> { it.span.end - it.span.start }.thenBy { it.span.start })
        val budget = maxOf(1, ((sourceTokenCount ?: words.findAll(original).count()) * density.coerceAtMost(1.0)).toInt())
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

    private fun readableRomanization(value: String): Boolean =
        Regex("\\p{IsLatin}").containsMatchIn(value) && value.matches(Regex("[\\p{IsLatin}\\p{M} '’.-]+")) &&
            value.codePoints().noneMatch { it in 0x0250..0x02FF || it in 0x1D00..0x1DBF }

    private fun occurrences(phrase: String, text: String, boundaries: Set<Int>? = null): List<IntRange> {
        val escaped = lookupKey(phrase).map { char -> Regex.escape(char.toString()) + if (char.code in 0x0620..0x064A) "[\\u0640\\u064B-\\u0652\\u0670]*" else "" }.joinToString("")
        if (escaped.isEmpty()) return emptyList()
        val pattern = if (boundaries == null) "(?<![\\p{L}\\p{M}\\p{N}_])" + escaped + "(?![\\p{L}\\p{M}\\p{N}_])" else escaped
        return Regex(pattern, RegexOption.IGNORE_CASE).findAll(text).map { it.range }
            .filter { boundaries == null || (it.first in boundaries && it.last + 1 in boundaries) }.toList()
    }
    private fun overlaps(a: IntRange, b: IntRange) = a.first <= b.last && b.first <= a.last
    companion object {
        fun lookupKey(value: String): String = java.text.Normalizer.normalize(value, java.text.Normalizer.Form.NFC)
            .lowercase(java.util.Locale.ROOT).filter { it.code != 0x0640 && it.code !in 0x064B..0x0652 && it.code != 0x0670 }
    }
}
