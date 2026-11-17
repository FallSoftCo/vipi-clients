package co.fallsoft.vipi

import co.fallsoft.vipi.core.TranslationIntegrity
import java.security.MessageDigest
import java.text.BreakIterator
import java.util.Locale
import kotlinx.coroutines.CancellationException

/** Immutable source selection. Displayed hybrid text is never a request input. */
internal data class ManualTranslationRequest(
    val messageID: String, val originalText: String, val startUTF16: Int, val endUTF16: Int,
    val knownLanguage: String, val learningLanguage: String, val inputLanguage: String?,
    val generation: Long, internal val ownerGeneration: Long
) {
    val selectionIdentity: String = MessageDigest.getInstance("SHA-256").digest(listOf(
        messageID, originalText, startUTF16.toString(), endUTF16.toString(), knownLanguage,
        learningLanguage, inputLanguage ?: "", generation.toString(), ownerGeneration.toString()
    ).joinToString("") { "${it.toByteArray(Charsets.UTF_8).size}:$it" }.toByteArray(Charsets.UTF_8))
        .joinToString("") { "%02x".format(it) }
}
internal data class ManualTranslationResult(val request: ManualTranslationRequest, val originalSlice: String,
    val targetText: String, val reading: FullReading?, val sourceLanguage: String, val targetLanguage: String)
internal enum class ManualTranslationStatus { READY, INVALID_INPUT, INVALID_LANGUAGE, MODEL_NOT_READY, INVALID_RESULT, STALE, TIMEOUT, ERROR }
internal data class ManualTranslationOutcome(val status: ManualTranslationStatus, val result: ManualTranslationResult? = null)
internal class ManualTranslationTimeout : Exception()

/** No alignment, lexical insertion, familiarity observation or remote fallback. */
internal object ManualTranslationResolver {
    private val supported = setOf("en", "es", "fr", "de", "it", "pt", "ar", "zh", "ja", "ko", "sw")
    private val latin = supported - setOf("ar", "zh", "ja", "ko")
    private fun scriptLanguage(text: String, pair: List<String>): String? {
        val unprotected = StringBuilder(text)
        TranslationIntegrity.protectedLiteralRanges(text).asReversed().forEach { unprotected.replace(it.first, it.last+1, " ") }
        val scripts = unprotected.toString().codePoints().toArray().filter { Character.isLetter(it) && it != 0x30FC }
            .map { Character.UnicodeScript.of(it) }.toSet()
        if (scripts.isEmpty()) return null
        val candidates = pair.filter { language -> scripts.all { script -> when (script) {
            Character.UnicodeScript.LATIN -> language in latin
            Character.UnicodeScript.HAN -> language in setOf("zh", "ja")
            Character.UnicodeScript.HIRAGANA, Character.UnicodeScript.KATAKANA -> language == "ja"
            Character.UnicodeScript.HANGUL -> language == "ko"
            Character.UnicodeScript.ARABIC -> language == "ar"
            else -> false
        } } }
        return candidates.singleOrNull()
    }
    fun slice(request: ManualTranslationRequest): String? {
        val text = request.originalText
        if (text.isEmpty() || text.toByteArray(Charsets.UTF_8).size > 32_768 || request.messageID.isEmpty() || request.generation < 0 ||
            request.startUTF16 < 0 || request.endUTF16 <= request.startUTF16 || request.endUTF16 > text.length ||
            text.codePoints().anyMatch { it in 0xD800..0xDFFF }) return null
        val boundaries = BreakIterator.getCharacterInstance(Locale.ROOT).apply { setText(text) }
        if (!boundaries.isBoundary(request.startUTF16) || !boundaries.isBoundary(request.endUTF16)) return null
        return text.substring(request.startUTF16, request.endUTF16).takeIf { it.isNotBlank() }
    }
    private data class Chunk(val text: String, val literal: Boolean)
    private fun chunks(text: String): List<Chunk> {
        val result = mutableListOf<Chunk>(); val protected = TranslationIntegrity.protectedLiteralRanges(text)
        val boundaries = BreakIterator.getCharacterInstance(Locale.ROOT).apply { setText(text) }
        var cursor = 0
        while (cursor < text.length) {
            val longLiteral = protected.firstOrNull { it.first == cursor && it.last + 1 - cursor > 8192 }
            if (longLiteral != null) { result += Chunk(text.substring(longLiteral), true); cursor = longLiteral.last + 1; continue }
            var end = minOf(text.length, cursor + 8192)
            protected.firstOrNull { end > it.first && end <= it.last }?.let { end = it.first }
            if (!boundaries.isBoundary(end)) end = boundaries.preceding(end)
            if (end <= cursor) return emptyList()
            if (end < text.length) {
                val natural = (end - 1 downTo cursor + (end-cursor)/2).firstOrNull { i ->
                    text[i].isWhitespace() && boundaries.isBoundary(i) && protected.none { i in it }
                }
                if (natural != null && natural > cursor) end = natural
            }
            val value = text.substring(cursor,end); val core = value.trim()
            if (core.isEmpty()) result += Chunk(value,true)
            else {
                val first = value.indexOfFirst { !it.isWhitespace() }; val last = value.indexOfLast { !it.isWhitespace() } + 1
                if (first > 0) result += Chunk(value.substring(0,first),true)
                result += Chunk(value.substring(first,last),false)
                if (last < value.length) result += Chunk(value.substring(last),true)
            }
            cursor=end
        }
        return result
    }
    private fun context(request: ManualTranslationRequest): String {
        if (request.originalText.length <= 16_384) return request.originalText
        val boundaries = BreakIterator.getCharacterInstance(Locale.ROOT).apply { setText(request.originalText) }
        val desired = maxOf(0, request.startUTF16-4096)
        val start = if (boundaries.isBoundary(desired)) desired else boundaries.following(desired)
        val desiredEnd = minOf(request.originalText.length,start+16_384)
        val end = if (boundaries.isBoundary(desiredEnd)) desiredEnd else boundaries.preceding(desiredEnd)
        return request.originalText.substring(start,end)
    }
    suspend fun resolve(request: ManualTranslationRequest, valid: () -> Boolean,
        reference: suspend (String, String, String) -> String?, identify: suspend (String) -> String?,
        modelsReady: suspend (String, String) -> Boolean, translate: suspend (String, String, String) -> String,
        reading: suspend (String, String) -> FullReading?): ManualTranslationOutcome {
        fun stop(status: ManualTranslationStatus) = ManualTranslationOutcome(if (valid()) status else ManualTranslationStatus.STALE)
        if (!valid()) return stop(ManualTranslationStatus.STALE)
        val slice = slice(request) ?: return stop(ManualTranslationStatus.INVALID_INPUT)
        val known = request.knownLanguage; val learning = request.learningLanguage; val pair = listOf(known, learning)
        if (known == learning || !supported.containsAll(pair) || request.inputLanguage?.let { it !in pair } == true)
            return stop(ManualTranslationStatus.INVALID_INPUT)
        try {
            var source = request.inputLanguage ?: scriptLanguage(slice, pair)
            if (source == null) {
                val forward = reference(request.originalText, known, learning)
                if (!valid()) return stop(ManualTranslationStatus.STALE)
                val reverse = if (forward == null) reference(request.originalText, learning, known) else null
                if (!valid()) return stop(ManualTranslationStatus.STALE)
                source = when { forward != null -> known; reverse != null -> learning; else -> identify(context(request)) }
                if (!valid()) return stop(ManualTranslationStatus.STALE)
                if (source !in pair && slice != request.originalText) source = identify(slice)
            }
            if (!valid()) return stop(ManualTranslationStatus.STALE)
            if (source !in pair) return stop(ManualTranslationStatus.INVALID_LANGUAGE)
            val from = requireNotNull(source); val to = if (from == known) learning else known
            val authored = reference(slice, from, to)
            if (!valid()) return stop(ManualTranslationStatus.STALE)
            val translated = authored ?: run {
                if (!modelsReady(from, to)) return stop(ManualTranslationStatus.MODEL_NOT_READY)
                if (!valid()) return stop(ManualTranslationStatus.STALE)
                val parts = chunks(slice)
                if (parts.isEmpty()) return stop(ManualTranslationStatus.INVALID_INPUT)
                buildString {
                    for (part in parts) {
                        if (!valid()) return stop(ManualTranslationStatus.STALE)
                        append(if (part.literal) part.text else translate(part.text, from, to))
                    }
                }
            }
            if (!valid()) return stop(ManualTranslationStatus.STALE)
            if (translated.isBlank() || translated.length > 65_536 || !TranslationIntegrity.preservesIdentifiers(slice, translated))
                return stop(ManualTranslationStatus.INVALID_RESULT)
            val guide = reading(translated, to)
            if (!valid()) return stop(ManualTranslationStatus.STALE)
            return ManualTranslationOutcome(ManualTranslationStatus.READY,
                ManualTranslationResult(request, slice, translated, guide, from, to))
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: ManualTranslationTimeout) { return stop(ManualTranslationStatus.TIMEOUT) }
        catch (_: Exception) { return stop(ManualTranslationStatus.ERROR) }
    }
}
