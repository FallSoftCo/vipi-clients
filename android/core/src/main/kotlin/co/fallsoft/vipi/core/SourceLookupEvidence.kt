package co.fallsoft.vipi.core

/** Original UTF16 ranges, never coordinates in a translated or normalized string. */
data class SourceLookupRange(val start: Int, val end: Int) {
    fun overlaps(other: SourceLookupRange) = start < other.end && other.start < end
    fun contains(other: SourceLookupRange) = start <= other.start && end >= other.end
}
data class SourceApprovedOutput(val outputID: String, val range: SourceLookupRange)
enum class SourceAtomicMode { NONE, ATOMIC, HEAD_BACKOFF, AMBIGUOUS }
data class SourceRecognition(val ruleID: String, val recordSHA256: String, val context: SourceLookupRange,
    val mask: SourceLookupRange?, val mode: SourceAtomicMode, val approvedOutputs: List<SourceApprovedOutput>)

/**
 * Immutable request-bound source evidence. Recognition remains present when a
 * known-word/density/target-availability decision produces no displayed face.
 * The trusted producer owns meaning resolution and must mark unresolved senses
 * ambiguous; this container does not infer authorization from matching text.
 */
class SourceLookupEvidence(val original: String, val source: String, val target: String,
    val catalogIdentity: String, partial: PartialImmersionResult?, recognitions: List<SourceRecognition>) {
    val partial = partial?.copy(spans = partial.spans.toList(), references = partial.references.toList())
    val recognitions = recognitions.map { it.copy(approvedOutputs = it.approvedOutputs.toList()) }

    fun isValid(text: String, sourceLanguage: String, targetLanguage: String, identity: String): Boolean {
        if (original != text || source != sourceLanguage || target != targetLanguage || source.isBlank() || target.isBlank() || source == target ||
            catalogIdentity != identity || !catalogIdentity.matches(Regex("[A-Za-z0-9._:-]{1,160}")) ||
            original.isEmpty() || original.length > 16_384 || recognitions.size > 4096 ||
            recognitions.sumOf { it.approvedOutputs.size.toLong() } > 4096) return false
        val boundaries = Regex("\\X").findAll(original).map { it.range.last + 1 }.toSet() + 0
        fun validRange(range: SourceLookupRange) = range.start >= 0 && range.end > range.start &&
            range.end <= original.length && range.start in boundaries && range.end in boundaries
        for (recognition in recognitions) {
            if (recognition.ruleID.isBlank() || recognition.ruleID.length > 160 ||
                !recognition.recordSHA256.matches(Regex("[a-f0-9]{64}")) || !validRange(recognition.context) ||
                (recognition.mode == SourceAtomicMode.NONE) != (recognition.mask == null)) return false
            recognition.mask?.let { if (!validRange(it) || !recognition.context.contains(it)) return false }
            if (recognition.approvedOutputs.any { it.outputID.isBlank() || it.outputID.length > 160 ||
                    !validRange(it.range) || !recognition.context.contains(it.range) }) return false
            when (recognition.mode) {
                SourceAtomicMode.ATOMIC -> if (recognition.approvedOutputs.any { it.range != recognition.mask }) return false
                SourceAtomicMode.HEAD_BACKOFF -> if (recognition.approvedOutputs.any { recognition.mask?.contains(it.range) != true }) return false
                SourceAtomicMode.AMBIGUOUS -> if (recognition.approvedOutputs.isNotEmpty()) return false
                SourceAtomicMode.NONE -> Unit
            }
        }
        return partial == null || (partial.original == text && partial.translation == null &&
            SourceReferencePresentation.isAnchored(partial, targetLanguage))
    }

    private fun permits(range: SourceLookupRange, outputID: String?): Boolean = recognitions.all { recognition ->
        val mask = recognition.mask
        mask == null || !mask.overlaps(range) || (recognition.mode != SourceAtomicMode.AMBIGUOUS &&
            outputID != null && recognition.approvedOutputs.any { it.outputID == outputID && it.range == range })
    }
    fun allowsLegacy(start: Int, end: Int) = permits(SourceLookupRange(start, end), null)

    /** Legacy aligned spans have no source approval ID, even if their text matches an approved face. */
    fun filterLegacy(value: ImmersionResult): ImmersionResult {
        require(value.original == original)
        return value.copy(spans = value.spans.filter { permits(SourceLookupRange(it.start, it.end), null) })
    }

    /** Keep existing budget/order. Filtering cannot select another candidate or infer a new approval. */
    fun filterPartial(value: PartialImmersionResult): PartialImmersionResult? {
        require(value.original == original && SourceReferencePresentation.isAnchored(value, target))
        val retained = value.spans.zip(value.references).filter { (span, proof) ->
            permits(SourceLookupRange(span.start, span.end), proof.outputID)
        }
        if (retained.isEmpty()) return null
        return value.copy(spans = retained.map { it.first }, references = retained.map { it.second })
    }
}
