package co.fallsoft.vipi.core

import java.util.concurrent.CancellationException

/** Routing, not a matcher or linguistic-confidence model. No partial translation type. */
data class LookupFirstRequest(val text: String, val source: String, val target: String, val inputLanguage: String? = null)
enum class ImmersionOrigin { LOOKUP_REFERENCE, SOURCE_REFERENCE_PARTIAL, LOCAL_FULL_CONTEXT }
enum class ImmersionStatus { READY, PARTIAL, INVALID_INPUT, INVALID_LANGUAGE, MODEL_NOT_READY, INVALID_RESULT, STALE, ERROR }
data class LookupFirstOutcome(val result: ImmersionPresentation?, val origin: ImmersionOrigin?,
                              val status: ImmersionStatus, val localTranslationCalls: Int,
                              val fallbackStatus: ImmersionStatus? = null, val cacheHit: Boolean = false) {
    fun cachedInvocation(): LookupFirstOutcome = copy(localTranslationCalls = 0, cacheHit = true)
}

object LookupFirst {
    suspend fun resolve(request: LookupFirstRequest, valid: () -> Boolean,
                        reference: suspend (String, String, String) -> String?,
                        identify: suspend (String) -> String?, modelsReady: () -> Boolean,
                        translate: suspend (String, String, String) -> String,
                        align: suspend (String, String) -> ImmersionResult,
                        partialReference: suspend (String, String, String) -> PartialImmersionResult? = { _, _, _ -> null },
                        onPartial: (PartialImmersionResult) -> Unit = {}): LookupFirstOutcome {
        var calls = 0
        var origin: ImmersionOrigin? = null
        var partial: PartialImmersionResult? = null
        fun stop(status: ImmersionStatus): LookupFirstOutcome =
            if (partial != null && valid() && status != ImmersionStatus.STALE)
                LookupFirstOutcome(partial, ImmersionOrigin.SOURCE_REFERENCE_PARTIAL, ImmersionStatus.PARTIAL, calls, status)
            else LookupFirstOutcome(null, origin, status, calls)
        if (!valid()) return stop(ImmersionStatus.STALE)
        val (text, source, target, input) = request
        if (text.isBlank() || text.length > 16_384 || source == target ||
            (input != null && input !in listOf(source, target))) return stop(ImmersionStatus.INVALID_INPUT)
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
            if (detected == source && sourcePartial != null) {
                if (sourcePartial.original != text || sourcePartial.translation != null ||
                    !SourceReferencePresentation.isAnchored(sourcePartial, target)) return stop(ImmersionStatus.INVALID_RESULT)
                partial = sourcePartial
                onPartial(sourcePartial)
            }
            val reversed = detected == target
            val known = forward ?: reverse
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
            val result = align(original, targetText)
            if (!valid()) return stop(ImmersionStatus.STALE)
            if (result.original != original || result.translation != targetText || !anchored(result))
                return stop(ImmersionStatus.INVALID_RESULT)
            // Known exact source units keep their source-authorized faces even if a
            // valid full-context translation uses different wording. Do not silently
            // replace them with target-dependent guesses or a zero-span result.
            partial?.let {
                return LookupFirstOutcome(it.copy(completeTranslation = targetText),
                    ImmersionOrigin.SOURCE_REFERENCE_PARTIAL, ImmersionStatus.PARTIAL, calls, ImmersionStatus.READY)
            }
            return LookupFirstOutcome(result, origin, ImmersionStatus.READY, calls)
        } catch (cancelled: CancellationException) { throw cancelled }
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
