package co.fallsoft.vipi.core

import java.util.concurrent.CancellationException

/** Routing intent never changes the source producer's linguistic authorization. */
enum class ImmersionIntent { AUTOMATIC_IMMERSION, FULL_TRANSLATION }
class ImmersionTranslationTimeout : Exception()
data class LookupFirstRequest(val text: String, val source: String, val target: String, val inputLanguage: String? = null,
                              val intent: ImmersionIntent = ImmersionIntent.AUTOMATIC_IMMERSION,
                              val allowModelTranslation: Boolean = true)
enum class ImmersionOrigin { LOOKUP_REFERENCE, SOURCE_REFERENCE_PARTIAL, LOCAL_FULL_CONTEXT }
enum class ImmersionStatus { READY, PARTIAL, INVALID_INPUT, INVALID_LANGUAGE, MODEL_NOT_READY, NO_LOCAL_MATCH, INVALID_RESULT, STALE, ERROR, TIMEOUT }
data class LookupFirstOutcome(val result: ImmersionPresentation?, val origin: ImmersionOrigin?,
                              val status: ImmersionStatus, val localTranslationCalls: Int,
                              val fallbackStatus: ImmersionStatus? = null, val cacheHit: Boolean = false,
                              val sourceEvidence: SourceLookupEvidence? = null) {
    fun cachedInvocation(): LookupFirstOutcome = copy(localTranslationCalls = 0, cacheHit = true)
}

object LookupFirst {
    suspend fun resolve(request: LookupFirstRequest, valid: () -> Boolean,
                        reference: suspend (String, String, String) -> String?,
                        identify: suspend (String) -> String?, modelsReady: () -> Boolean,
                        translate: suspend (String, String, String) -> String,
                        align: suspend (String, String, SourceLookupEvidence?) -> ImmersionResult,
                        partialReference: suspend (String, String, String) -> PartialImmersionResult? = { _, _, _ -> null },
                        onPartial: (PartialImmersionResult) -> Unit = {},
                        sourceEvidenceIdentity: String? = null,
                        sourceEvidence: (suspend (String, String, String) -> SourceLookupEvidence)? = null): LookupFirstOutcome {
        var calls = 0
        var origin: ImmersionOrigin? = null
        var partial: PartialImmersionResult? = null
        var constraints: SourceLookupEvidence? = null
        fun stop(status: ImmersionStatus): LookupFirstOutcome =
            if (partial != null && valid() && status != ImmersionStatus.STALE)
                LookupFirstOutcome(partial, ImmersionOrigin.SOURCE_REFERENCE_PARTIAL, ImmersionStatus.PARTIAL, calls, status, sourceEvidence = constraints)
            else LookupFirstOutcome(null, origin, status, calls, sourceEvidence = constraints.takeIf { valid() && status != ImmersionStatus.STALE })
        if (!valid()) return stop(ImmersionStatus.STALE)
        val (text, source, target, input) = request
        if (text.isBlank() || text.length > 16_384 || source == target ||
            (input != null && input !in listOf(source, target)) ||
            (sourceEvidence == null) != (sourceEvidenceIdentity == null)) return stop(ImmersionStatus.INVALID_INPUT)
        try {
            val forward = if (input != target) reference(text, source, target) else null
            if (!valid()) return stop(ImmersionStatus.STALE)
            val reverse = if (forward == null && input != source) reference(text, target, source) else null
            if (!valid()) return stop(ImmersionStatus.STALE)
            // Only exact catalog sentence units may become source-only partial output.
            // Frame/lexical target-dependent candidates are NOT passed to this callback.
            val sourcePartial = if (forward == null && reverse == null && input != target)
                partialReference(text, source, target) else null
            if (!valid()) return stop(ImmersionStatus.STALE)
            val detected = when { forward != null -> source; reverse != null -> target; input != null -> input; else -> identify(text) }
            if (!valid()) return stop(ImmersionStatus.STALE)
            if (detected !in listOf(source, target)) return stop(ImmersionStatus.INVALID_LANGUAGE)
            // Recognition is independent of faces, including whole-reference hits,
            // but a forward-only producer must never run on target-language input.
            val evidence = if (detected == source) sourceEvidence?.invoke(text, source, target) else null
            if (!valid()) return stop(ImmersionStatus.STALE)
            if (detected == source && evidence != null) {
                if (!evidence.isValid(text, source, target, requireNotNull(sourceEvidenceIdentity))) return stop(ImmersionStatus.INVALID_RESULT)
                constraints = evidence
            }
            if (detected == source) {
                if (sourcePartial != null && (sourcePartial.original != text || sourcePartial.translation != null ||
                    !SourceReferencePresentation.isAnchored(sourcePartial, target))) return stop(ImmersionStatus.INVALID_RESULT)
                partial = sourcePartial?.let { constraints?.filterPartial(it) ?: it.takeIf { constraints == null } }
                if (partial == null && (forward == null || request.intent == ImmersionIntent.AUTOMATIC_IMMERSION))
                    partial = constraints?.partial?.let { constraints?.filterPartial(it) }
            }
            partial?.let { admitted ->
                onPartial(admitted)
                if (!valid()) return stop(ImmersionStatus.STALE)
                if (request.intent == ImmersionIntent.AUTOMATIC_IMMERSION)
                    return LookupFirstOutcome(admitted, ImmersionOrigin.SOURCE_REFERENCE_PARTIAL, ImmersionStatus.PARTIAL, 0, sourceEvidence = constraints)
            }
            val reversed = detected == target
            val known = forward ?: reverse
            // No readiness check, translator or model download on a local miss.
            if (known == null && !request.allowModelTranslation) return stop(ImmersionStatus.NO_LOCAL_MATCH)
            if (known == null && !modelsReady()) return stop(ImmersionStatus.MODEL_NOT_READY)
            if (!valid()) return stop(ImmersionStatus.STALE)
            origin = if (known != null) ImmersionOrigin.LOOKUP_REFERENCE else ImmersionOrigin.LOCAL_FULL_CONTEXT
            val translated = known ?: run {
                calls++
                translate(text, if (reversed) target else source, if (reversed) source else target)
            }
            if (!valid()) return stop(ImmersionStatus.STALE)
            if (translated.isBlank() || translated.length > 32_768 || !TranslationIntegrity.preservesIdentifiers(text, translated))
                return stop(ImmersionStatus.INVALID_RESULT)
            val original = if (reversed) translated else text
            val targetText = if (reversed) text else translated
            // The user requested a complete reference, not new guessed slots.
            // Existing source authorization and whole-string integrity suffice;
            // target-dependent alignment would be computed only to discard it.
            partial?.let {
                return LookupFirstOutcome(it.copy(completeTranslation = targetText),
                    ImmersionOrigin.SOURCE_REFERENCE_PARTIAL, ImmersionStatus.PARTIAL, calls, ImmersionStatus.READY, sourceEvidence = constraints)
            }
            val result = align(original, targetText, constraints)
            if (!valid()) return stop(ImmersionStatus.STALE)
            if (result.original != original || result.translation != targetText || !anchored(result))
                return stop(ImmersionStatus.INVALID_RESULT)
            val admitted = constraints?.filterLegacy(result) ?: result
            return LookupFirstOutcome(admitted, origin, ImmersionStatus.READY, calls, sourceEvidence = constraints)
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: ImmersionTranslationTimeout) { return stop(if (valid()) ImmersionStatus.TIMEOUT else ImmersionStatus.STALE) }
        catch (_: Exception) { return stop(if (valid()) ImmersionStatus.ERROR else ImmersionStatus.STALE) }
    }

    private fun anchored(result: ImmersionResult): Boolean {
        var end = 0
        for (span in result.spans) {
            if (span.start < end || span.end <= span.start || span.end > result.original.length ||
                span.targetStart < 0 || span.targetEnd <= span.targetStart || span.targetEnd > result.translation.length ||
                result.original.substring(span.start, span.end) != span.original ||
                result.translation.substring(span.targetStart, span.targetEnd) != span.translated) return false
            end = span.end
        }
        return true
    }
}
