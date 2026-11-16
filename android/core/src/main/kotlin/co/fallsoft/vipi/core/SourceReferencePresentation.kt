package co.fallsoft.vipi.core

/** Complete and partial presentations share source slots, never a fabricated translation. */
interface ImmersionPresentation {
    val original: String
    val translation: String?
    val spans: List<ImmersionSpan>
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

data class ApprovedLearningIdentity(val patternId: String, val meaning: String, val reading: String)
data class ApprovedStarterIdentity(val entryId: String, val conceptId: String, val pos: String, val guard: String,
                                   val canonicalSource: String, val recordSha256: String)
data class SourceReferenceUnit(val start: Int, val end: Int, val original: String, val translated: String,
                               val reading: String?, val referenceId: String, val catalogSha256: String,
                               val nativeSourceTokens: Int? = null,
                               val outputID: String? = null,
                               val learningIdentity: ApprovedLearningIdentity? = null,
                               val selectionPriority: Int? = null,
                               val starterIdentity: ApprovedStarterIdentity? = null)
/** targetStart/End refer to the exact corresponding reference's translation, NOT a full message. */
data class PartialImmersionResult(override val original: String, override val spans: List<ImmersionSpan>,
                                  val references: List<SourceReferenceUnit>,
                                  val completeTranslation: String? = null,
                                  val nativeSourceTokenCount: Int? = null,
                                  val targetLanguage: String) : ImmersionPresentation {
    override val translation: String? get() = completeTranslation
}

object SourceReferencePresentation {
    fun create(original: String, target: String, units: List<SourceReferenceUnit>, density: Double,
               nativeSourceTokenCount: Int): PartialImmersionResult? {
        if (original.isEmpty() || original.length > 16_384 || units.isEmpty() || units.size > 128 ||
            !density.isFinite() || density <= 0 || nativeSourceTokenCount < 0) return null
        var previous = 0
        for (unit in units) {
            if (unit.start < previous || unit.end <= unit.start || unit.end > original.length ||
                original.substring(unit.start, unit.end) != unit.original || unit.original.length > 128 ||
                unit.translated.isBlank() || unit.translated.length > 128 || unit.referenceId.isBlank() ||
                !unit.catalogSha256.matches(Regex("[a-f0-9]{64}")) ||
                unit.nativeSourceTokens == null || unit.nativeSourceTokens <= 0 || unit.nativeSourceTokens > nativeSourceTokenCount ||
                !TranslationIntegrity.preservesIdentifiers(unit.original, unit.translated)) return null
            previous = unit.end
        }
        if (units.sumOf { requireNotNull(it.nativeSourceTokens) } > nativeSourceTokenCount) return null
        // This temporary coordinate basis is NEVER returned as a full translation.
        val basis = units.joinToString("\n") { it.translated }
        if (basis.length > 32_768) return null
        var offset = 0
        val entries = units.map { unit ->
            val start = offset; offset += unit.translated.length + 1
            VocabularyEntry(unit.original, listOf(unit.translated),
                unit.reading?.let { mapOf(unit.translated to listOf(it)) } ?: emptyMap(),
                sourceScope = VocabularySourceScope(original, unit.start, unit.end),
                targetScope = VocabularyTargetScope(basis, start, start + unit.translated.length))
        }
        val selected = ImmersionEngine().align(original, basis, entries, density, target,
            sourceTokenCount = nativeSourceTokenCount,
            sourceUnitTokenCounts = units.associate { (it.start to it.end) to requireNotNull(it.nativeSourceTokens) }).spans
        if (selected.isEmpty()) return null
        val proofs = selected.map { span -> units.single { it.start == span.start && it.end == span.end } }
        return PartialImmersionResult(original, selected.map { it.copy(targetStart = 0, targetEnd = it.translated.length) }, proofs, nativeSourceTokenCount = nativeSourceTokenCount, targetLanguage = target)
            .takeIf { isAnchored(it, target) }
    }
    /** Structural proof only; the exact internal catalog producer owns source authorization. */
    fun isAnchored(value: PartialImmersionResult, target: String): Boolean {
        if (value.targetLanguage != target || value.original.length > 16_384 || value.spans.isEmpty() || value.spans.size > 128 ||
            value.references.size != value.spans.size || value.nativeSourceTokenCount == null ||
            value.nativeSourceTokenCount < 0 ||
            value.references.sumOf { it.nativeSourceTokens ?: 0 } > value.nativeSourceTokenCount) return false
        var end = 0
        val boundaries = Regex("\\X").findAll(value.original).map { it.range.last + 1 }.toSet() + 0
        for ((span, unit) in value.spans.zip(value.references)) {
            if (span.start < end || span.end <= span.start || span.end > value.original.length ||
                span.start !in boundaries || span.end !in boundaries ||
                span.start != unit.start || span.end != unit.end || span.original != unit.original ||
                value.original.substring(span.start, span.end) != span.original ||
                span.translated != unit.translated || span.targetStart != 0 || span.targetEnd != unit.translated.length ||
                unit.referenceId.isBlank() || !unit.catalogSha256.matches(Regex("[a-f0-9]{64}")) ||
                unit.nativeSourceTokens == null || unit.nativeSourceTokens <= 0 ||
                (target.substringBefore('-') in setOf("ar", "zh", "ja", "ko") &&
                    (span.romanization == null || span.romanization != unit.reading))) return false
            end = span.end
        }
        return true
    }
}
