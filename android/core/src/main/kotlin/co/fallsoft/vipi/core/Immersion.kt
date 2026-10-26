package co.fallsoft.vipi.core

/** Ephemeral focus proved by an exact context match; bound to this message. */
data class VocabularySourceScope(val original: String, val start: Int, val end: Int)
/** Ephemeral target focus from a matched context, bound to the actual translation. */
data class VocabularyTargetScope(val translation: String, val start: Int, val end: Int)
/** Explicit lexical focus inside an attested target word, e.g. 시간 inside 시간이. */
data class VocabularyTargetForm(val surface: String, val target: String, val start: Int, val end: Int)
data class VocabularyEntry(val source: String, val targets: List<String>, val romanizations: Map<String, List<String>> = emptyMap(), val contextHints: List<String> = emptyList(), val requiresContext: Boolean = false, val sourceScope: VocabularySourceScope? = null, val targetForms: List<VocabularyTargetForm> = emptyList(), val targetScope: VocabularyTargetScope? = null, val protectInner: Boolean = false, val unresolvedNativeSenses: Boolean = false)
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
            val range = sourceOccurrences(entry, original, sourceBoundaries).firstOrNull() ?: return@filter false
            val lower = stops.lastOrNull { it.last < range.first }?.let { it.last + 1 } ?: 0
            val upper = stops.firstOrNull { it.first > range.last }?.first ?: original.length
            entry.contextHints.any { hint -> hint.isNotEmpty() && hint.length <= 64 && occurrences(hint, original, sourceBoundaries).any { cue ->
                cue.first >= lower && cue.last < upper && !overlaps(cue, range) && protectedRanges.none { overlaps(it, cue) }
            } }
        }.toSet()
        val claims = entries.associateWith { entry ->
            val source = if (entry.source.isNotEmpty() && entry.source.length <= 128) sourceOccurrences(entry, original, sourceBoundaries) else emptyList()
            val targets = if (source.isEmpty()) emptyList() else entry.targets.distinct().filter { it.isNotEmpty() && it.length <= 128 }
                .flatMap { targetOccurrences(entry,it,translation,targetBoundaries) }.distinct()
            source to targets
        }
        val candidates = entries.mapNotNull { entry ->
            if (entry.source.isEmpty() || entry.source.length > 128) return@mapNotNull null
            val source = claims.getValue(entry).first.singleOrNull() ?: return@mapNotNull null
            if (protectedRanges.any { overlaps(it, source) }) return@mapNotNull null
            // A missing target translation cannot dissolve a known source
            // compound or erase native meanings omitted by a pivot dictionary.
            // Explicitly assessed scopes are qualified separately.
            if(entry.sourceScope==null && claims.any { (guard,claim) ->
                claim.first.any { whole ->
                    (guard.unresolvedNativeSenses && whole==source) ||
                    (guard.protectInner && whole.first<=source.first && whole.last>=source.last && whole!=source)
                }
            }) return@mapNotNull null
            val targets = claims.getValue(entry).second
            val target = targets.singleOrNull() ?: return@mapNotNull null
            if (protectedTargetRanges.any { overlaps(it, target) }) return@mapNotNull null
            val sourceSurface = original.substring(source)
            val targetSurface = translation.substring(target)
            val needsReading = targetLanguage?.substringBefore('-') in setOf("ar", "zh", "ja", "ko")
            // Shared ideographs can have different readings, e.g. Chinese/Japanese 水.
            if(sourceSurface.equals(targetSurface,ignoreCase=true) && !(needsReading && entry.targetScope!=null))return@mapNotNull null
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
            .filter { candidate -> supported.none {
                lookupKey(it.source) == lookupKey(candidate.entry.source) && candidate.target !in claims.getValue(it).second
            } }
            .sortedWith(compareByDescending<Candidate> { it.span.end - it.span.start }.thenBy { it.span.start })
        // A qualified whole compound owns its nested nouns on both sides.
        // A small density budget must not turn "train ticket" into "treni ticket".
        val complete = unique.filter { child -> unique.none { parent ->
            parent.entry.sourceScope != null && parent.entry.targetScope != null &&
                parent.span.end-parent.span.start > child.span.end-child.span.start &&
                parent.span.start <= child.span.start && parent.span.end >= child.span.end &&
                parent.target.first <= child.target.first && parent.target.last >= child.target.last
        } }
        val budget = maxOf(1, ((sourceTokenCount ?: words.findAll(original).count()) * density.coerceAtMost(1.0)).toInt())
        var used = 0
        val selected = mutableListOf<ImmersionSpan>()
        for (candidate in complete) {
            val count = maxOf(1, words.findAll(candidate.span.original).count())
            if (used + count > budget || selected.any { overlaps(it.start until it.end, candidate.span.start until candidate.span.end) }) continue
            selected += candidate.span
            used += count
        }
        // Density is a target, not permission to split a vocabulary item.
        // If every approved item exceeds the rounded budget, expose just the
        // smallest one. All context, ambiguity and reading checks run above.
        if (selected.isEmpty()) {
            complete.minWithOrNull(compareBy<Candidate> { maxOf(1, words.findAll(it.span.original).count()) }
                .thenBy { it.span.start })?.let { selected += it.span }
        }
        return ImmersionResult(original, translation, selected.sortedBy { it.start })
    }

    private fun sourceOccurrences(entry: VocabularyEntry, original: String, boundaries: Set<Int>?): List<IntRange> {
        val scope=entry.sourceScope ?: return occurrences(entry.source,original,boundaries)
        if(scope.original!=original || scope.start<0 || scope.end<=scope.start || scope.end>original.length ||
            original.substring(scope.start,scope.end)!=entry.source) return emptyList()
        if((scope.start>0 && Character.isLowSurrogate(original[scope.start])) ||
            (scope.end<original.length && Character.isLowSurrogate(original[scope.end]))) return emptyList()
        return listOf(scope.start until scope.end)
    }

    private fun targetOccurrences(entry: VocabularyEntry, target: String, translation: String, boundaries: Set<Int>?): List<IntRange> {
        entry.targetScope?.let { scope ->
            if(entry.sourceScope==null || scope.translation!=translation || scope.start<0 || scope.end<=scope.start ||
                scope.end>translation.length || translation.substring(scope.start,scope.end)!=target) return emptyList()
            if((scope.start>0 && Character.isLowSurrogate(translation[scope.start])) ||
                (scope.end<translation.length && Character.isLowSurrogate(translation[scope.end]))) return emptyList()
            return listOf(scope.start until scope.end)
        }
        val plain=occurrences(target,translation,boundaries)
        if(entry.sourceScope==null || entry.targetForms.size>16) return plain
        val explicit=entry.targetForms.filter { form ->
            form.target==target && form.surface.length<=256 && form.start>=0 && form.end>form.start &&
                form.end<=form.surface.length && form.surface.substring(form.start,form.end)==target
        }.flatMap { form ->
            occurrences(form.surface,translation,boundaries).mapNotNull { whole ->
                // Preserve exact offsets. Normalization must not move a focus
                // across Arabic marks or another multi-code-unit character.
                val actual=translation.substring(whole)
                if(actual.length!=form.surface.length || !actual.replace('’','\'').equals(form.surface.replace('’','\''),ignoreCase=true)) null
                else (whole.first+form.start until whole.first+form.end).takeIf {
                    translation.substring(it).replace('’','\'').equals(target.replace('’','\''),ignoreCase=true)
                }
            }
        }
        return (plain+explicit).distinct()
    }

    private fun readableRomanization(value: String): Boolean =
        Regex("\\p{IsLatin}").containsMatchIn(value) && value.matches(Regex("[\\p{IsLatin}\\p{M} '’.-]+")) &&
            value.codePoints().noneMatch { it in 0x0250..0x02FF || it in 0x1D00..0x1DBF }

    private fun occurrences(phrase: String, text: String, boundaries: Set<Int>? = null): List<IntRange> {
        val escaped = lookupKey(phrase).map { char ->
            if(char=='\'' || char=='’') "['’]" else Regex.escape(char.toString()) + if (char.code in 0x0620..0x064A) "[\\u0640\\u064B-\\u0652\\u0670]*" else ""
        }.joinToString("")
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
