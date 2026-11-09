package co.fallsoft.vipi.contextqa

import co.fallsoft.vipi.contextqa.FrozenContextTokenizer.Range

/** Proposed source-only adapter output, not an implementation of POS inference. */
internal data class EnglishRoleEvidence(
    val original: String,
    val language: String,
    val nativeWordRanges: List<Range>,
    val suppliedProtection: List<Range>,
    val modelIdentities: Map<String, String>,
    val observations: List<Observation>,
    val status: Status,
    val namedProtection: NamedProtection = NamedProtection.UNAVAILABLE
) {
    enum class Status { READY, EMPTY, UNSUPPORTED_LANGUAGE, INVALID_INPUT, MODEL_UNAVAILABLE, GEOMETRY_MISMATCH }
    enum class NamedProtection { UNAVAILABLE }
    enum class Role { NOUN, NON_NOUN, UNKNOWN }
    data class Observation(val range: Range, val original: String, val rawTag: String?,
        val rawScore: Double?, val role: Role, val overlapsSuppliedProtection: Boolean,
        val unknownReason: String?)

    // No nounEligible/approvedOutputs field: POS and name capability remain separate.
    // Caller dictionary masks and existing protections do not disappear when this
    // optional research adapter is unavailable. Existing app UX is unchanged.
}
