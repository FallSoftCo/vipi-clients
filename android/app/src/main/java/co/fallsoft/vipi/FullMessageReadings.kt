package co.fallsoft.vipi

import android.content.Context
import android.icu.text.Transliterator
import kotlinx.coroutines.CancellationException

internal enum class FullMessageReadingStatus { NOT_NEEDED, AVAILABLE, UNAVAILABLE }
internal enum class FullMessageReadingFailure { INPUT_LIMIT, OUTPUT_LIMIT, UNRESOLVED, UNSUPPORTED, PRODUCER_FAILURE }

/** Display metadata, independent of complete translation and native speech. */
internal data class FullMessageReading(
    val status: FullMessageReadingStatus,
    val text: String? = null,
    val failure: FullMessageReadingFailure? = null
) {
    init {
        require(when (status) {
            FullMessageReadingStatus.NOT_NEEDED -> text == null && failure == null
            FullMessageReadingStatus.AVAILABLE -> !text.isNullOrBlank() && failure == null
            FullMessageReadingStatus.UNAVAILABLE -> text == null && failure != null
        })
    }
    companion object {
        fun notNeeded() = FullMessageReading(FullMessageReadingStatus.NOT_NEEDED)
        fun available(text: String) = FullMessageReading(FullMessageReadingStatus.AVAILABLE, text)
        fun unavailable(reason: FullMessageReadingFailure) = FullMessageReading(FullMessageReadingStatus.UNAVAILABLE, failure = reason)
    }
}

/** Live reading only. No source detection, phrase overrides or translation gate.
 * Native practice text remains audio authority; authored original remains copy authority. */
internal object FullMessageReadings {
    private val languages = setOf("ja", "ko", "zh", "ar")
    fun supports(language: String) = language in languages
    fun policy(language: String): String = listOf("full-message-readings-3:status-1:full-text-65536:kana-65536:ja-native-span-16384:reading-720896", language,
        if (language == "zh") "${ChineseReadings.POLICY}:${ChineseReadings.DATA_SHA256}" else "native-reader-1",
        android.os.Build.VERSION.SDK_INT.toString(), android.os.Build.VERSION.INCREMENTAL).joinToString(":")
    private var chinese: ChineseReadings? = null
    @Synchronized private fun chinese(context: Context): ChineseReadings? {
        if (chinese == null) chinese = runCatching {
            ChineseReadings(context.assets.open("readings/chinese-ordinary.json").use { it.readBytes() })
        }.getOrNull()
        return chinese
    }

    // Generic literal protection only; these ranges never authorize or prevent
    // translation. Actual @ anchors avoid rescanning long non-email identifiers.
    private val literals = Regex("```[\\s\\S]*?(?:```|$)|`[^`\\r\\n]*(?:`|$)|(?i:https?://|www\\.)[^\\s<>\\\"「」『』，。！？；、]+")
    private val email = Regex("[\\p{L}\\p{N}\\p{M}_.+%-]+@[\\p{L}\\p{N}\\p{M}_.-]+\\.[\\p{L}\\p{M}]{2,}")
    private val emailCategories = setOf(Character.NON_SPACING_MARK.toInt(), Character.COMBINING_SPACING_MARK.toInt(),
        Character.ENCLOSING_MARK.toInt(), Character.LETTER_NUMBER.toInt(), Character.OTHER_NUMBER.toInt())
    private val literalScripts = setOf(Character.UnicodeScript.LATIN, Character.UnicodeScript.COMMON, Character.UnicodeScript.INHERITED)
    private fun emailLocal(point: Int) = Character.isLetterOrDigit(point) ||
        Character.getType(point) in emailCategories || "_.+%-".any { it.code == point }
    private fun protectedRanges(text: String): List<IntRange> {
        val ranges = literals.findAll(text).map { it.range }.toMutableList()
        for (at in text.indices) if (text[at] == '@') {
            var start = at
            while (start > 0) {
                val point = text.codePointBefore(start)
                if (!emailLocal(point)) break
                start -= Character.charCount(point)
            }
            if (start < at) email.matchAt(text, start)?.let { ranges += it.range }
        }
        return ranges.sortedBy { it.first }.fold(mutableListOf<IntRange>()) { merged, range ->
            if (merged.isNotEmpty() && range.first <= merged.last().last + 1)
                merged[merged.lastIndex] = merged.last().first..maxOf(merged.last().last, range.last)
            else merged += range
            merged
        }
    }
    private fun nonLatinLetter(point: Int) = Character.isLetter(point) && Character.UnicodeScript.of(point) !in literalScripts
    private fun needsReading(text: String, protected: List<IntRange>): Boolean {
        var offset = 0; var range = 0
        while (offset < text.length) {
            while (range < protected.size && protected[range].last < offset) range++
            if (range < protected.size && offset in protected[range]) { offset = protected[range].last + 1; continue }
            val point = text.codePointAt(offset)
            if (nonLatinLetter(point)) return true
            offset += Character.charCount(point)
        }
        return false
    }
    private fun platform(text: String, id: String, protected: List<IntRange>): String {
        val converter = Transliterator.getInstance(id); val output = StringBuilder(); var offset = 0
        for (range in protected) {
            output.append(converter.transliterate(text.substring(offset, range.first)))
            output.append(text, range.first, range.last + 1); offset = range.last + 1
        }
        output.append(converter.transliterate(text.substring(offset)))
        return output.toString()
    }
    private fun complete(text: String?): FullMessageReading = when {
        text.isNullOrBlank() -> FullMessageReading.unavailable(FullMessageReadingFailure.UNRESOLVED)
        text.length > FullReadingLimits.MAX_READING_UTF16 -> FullMessageReading.unavailable(FullMessageReadingFailure.OUTPUT_LIMIT)
        needsReading(text, protectedRanges(text)) -> FullMessageReading.unavailable(FullMessageReadingFailure.UNRESOLVED)
        else -> FullMessageReading.available(text)
    }
    fun spokenAlignment(context: Context, text: String, displayed: String, language: String): List<PlayingWord> {
        if (text == displayed) return MessageSpeech.lexicalRanges(text, language).map { PlayingWord(it, it) }
        val pieces: List<Pair<IntRange, String>> = when (language) {
            "zh" -> chinese(context)?.resolve(text)?.pieces.orEmpty().map { (it.startUTF16 until it.endUTF16) to it.reading }
            "ja" -> JapaneseReadings.read(text).pieces.map { (it.start until it.end) to it.value }
            "ko" -> KoreanReadings.resolve(text).pieces.map { (it.startUTF16 until it.endUTF16) to it.rendered }
            else -> {
                val iterator = android.icu.text.BreakIterator.getWordInstance(java.util.Locale.forLanguageTag(language))
                iterator.setText(text)
                buildList {
                    var start = iterator.first()
                    var end = iterator.next()
                    while (end != android.icu.text.BreakIterator.DONE) {
                        val fragment = text.substring(start, end)
                        add((start until end) to (read(context, fragment, language).text ?: fragment))
                        start = end
                        end = iterator.next()
                    }
                }
            }
        }
        val result = mutableListOf<PlayingWord>()
        var cursor = 0
        for ((source, spelling) in pieces) {
            if (spelling.isEmpty()) continue
            while (!displayed.startsWith(spelling, cursor) && cursor < displayed.length &&
                (displayed[cursor] == ' ' || displayed[cursor] == '\'')) cursor++
            if (!displayed.startsWith(spelling, cursor)) return emptyList()
            result += PlayingWord(source, cursor until cursor + spelling.length)
            cursor += spelling.length
        }
        return if (cursor == displayed.length) result else emptyList()
    }
    fun read(context: Context, text: String, language: String): FullMessageReading {
        val protected = protectedRanges(text)
        if (!needsReading(text, protected)) return FullMessageReading.notNeeded()
        if (!supports(language)) return FullMessageReading.unavailable(FullMessageReadingFailure.UNSUPPORTED)
        if (text.length > FullReadingLimits.MAX_TEXT_UTF16) return FullMessageReading.unavailable(FullMessageReadingFailure.INPUT_LIMIT)
        return try {
            when (language) {
                "ja" -> {
                    val result = JapaneseReadings.read(text)
                    when {
                        JapaneseReadings.Issue.INPUT_LIMIT in result.issues -> FullMessageReading.unavailable(FullMessageReadingFailure.INPUT_LIMIT)
                        JapaneseReadings.Issue.OUTPUT_LIMIT in result.issues -> FullMessageReading.unavailable(FullMessageReadingFailure.OUTPUT_LIMIT)
                        JapaneseReadings.Issue.UNSUPPORTED_API in result.issues -> FullMessageReading.unavailable(FullMessageReadingFailure.UNSUPPORTED)
                        result.issues.isNotEmpty() -> FullMessageReading.unavailable(FullMessageReadingFailure.UNRESOLVED)
                        else -> complete(result.reading)
                    }
                }
                "ko" -> {
                    val result = KoreanReadings.resolve(text)
                    when {
                        "input_length" in result.issues -> FullMessageReading.unavailable(FullMessageReadingFailure.INPUT_LIMIT)
                        "output_length" in result.issues -> FullMessageReading.unavailable(FullMessageReadingFailure.OUTPUT_LIMIT)
                        result.issues.isNotEmpty() -> FullMessageReading.unavailable(FullMessageReadingFailure.UNRESOLVED)
                        else -> complete(result.reading)
                    }
                }
                "zh" -> complete(chinese(context)?.resolve(text)?.reading ?: platform(text, "Han-Latin", protected))
                else -> complete(platform(text, "Arabic-Latin", protected))
            }
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { FullMessageReading.unavailable(FullMessageReadingFailure.PRODUCER_FAILURE) }
    }
}
