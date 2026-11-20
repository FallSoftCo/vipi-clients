package co.fallsoft.vipi

import android.icu.text.BreakIterator
import org.json.JSONArray
import org.json.JSONObject
import java.text.Normalizer
import java.util.Locale

/** Native lexical boundaries only: no phrase dictionary, morphology model or
 * product vocabulary quota. Original UTF-16 ranges preserve punctuation. */
internal object IncrementalWords {
    data class Token(val start: Int, val end: Int, val text: String, val key: String)
    fun normalized(word: String, language: String): String =
        Normalizer.normalize(word, Normalizer.Form.NFC).lowercase(Locale.forLanguageTag(language))
    private val protectedLiterals = Regex(
        "```[\\s\\S]*?(?:```|$)|`[^`\\r\\n]*(?:`|$)|(?i:https?://|www\\.)[^\\s<>]+|" +
            "[\\p{L}\\p{N}\\p{M}_.+%-]+@[\\p{L}\\p{N}\\p{M}_.-]+\\.[\\p{L}\\p{M}]{2,}|" +
            "[@#][\\p{L}\\p{N}_]+|\\S*\\p{N}\\S*")
    fun tokens(text: String, language: String): List<Token> {
        val literals = protectedLiterals.findAll(text).map { it.range }.toList()
        val iterator = BreakIterator.getWordInstance(Locale.forLanguageTag(language))
        iterator.setText(text)
        val result = mutableListOf<Token>()
        var start = iterator.first()
        var end = iterator.next()
        while (end != BreakIterator.DONE) {
            val word = text.substring(start, end)
            if (word.codePoints().anyMatch { Character.isLetter(it) } &&
                literals.none { start <= it.last && end > it.first }) {
                result += Token(start, end, word, normalized(word, language))
            }
            start = end; end = iterator.next()
        }
        return result
    }
}

/** A complete native SDK equivalent may contain several target words. It is
 * one introduced SOURCE lexical unit, never a truncated target translation. */
internal data class IntroducedWord(val source: String, val target: String, val key: String,
    val translation: String, val reading: String?, val readingPolicy: String) {
    fun json() = JSONObject().put("source", source).put("target", target).put("key", key)
        .put("translation", translation).put("reading", reading ?: JSONObject.NULL).put("reading_policy", readingPolicy)
    companion object {
        fun parse(value: JSONObject) = IntroducedWord(value.getString("source"), value.getString("target"),
            value.getString("key"), value.getString("translation"), value.opt("reading") as? String,
            value.getString("reading_policy")).also { require(it.translation.isNotBlank()) }
    }
}

internal data class WordReplacement(val start: Int, val length: Int, val source: String,
    val target: String, val reading: String? = null) {
    fun json() = JSONObject().put("start", start).put("length", length).put("source", source)
        .put("target", target).put("reading", reading ?: JSONObject.NULL)
    companion object {
        fun parse(value: JSONObject) = WordReplacement(value.getInt("start"), value.getInt("length"),
            value.getString("source"), value.getString("target"), value.opt("reading") as? String)
        fun parse(values: JSONArray): List<WordReplacement> = (0 until values.length()).map { parse(values.getJSONObject(it)) }
        fun compose(original: String, words: List<WordReplacement>, reading: Boolean): String {
            // A larger face cannot fit the existing 2 MiB encrypted-record
            // bound. Reject before materializing repeated large equivalents;
            // this is storage safety, never a vocabulary/word-count limit.
            val projected = original.length.toLong() + words.sumOf {
                (if (reading) it.reading ?: it.target else it.target).length.toLong() - it.length
            }
            require(projected in 0..2_097_152L) { "Word display exceeds message record capacity" }
            var end = 0
            val result = StringBuilder(projected.toInt())
            for (word in words) {
                require(word.start >= end && word.length > 0 && word.start + word.length <= original.length)
                require(original.substring(word.start, word.start + word.length) == word.source)
                result.append(original, end, word.start).append(if (reading) word.reading ?: word.target else word.target)
                end = word.start + word.length
            }
            return result.append(original, end, original.length).toString()
        }
        fun ranges(words: List<WordReplacement>, reading: Boolean): List<IntRange> {
            var shift = 0
            return words.map { word ->
                val inserted = if (reading) word.reading ?: word.target else word.target
                val start = word.start + shift
                shift += inserted.length - word.length
                start until start + inserted.length
            }
        }
    }
}

/** Authoritative progression snapshot independent of reading/cache policy.
 * It keeps no paragraph: exact ranges reference immutable encrypted vocabulary. */
internal data class WordPlanReference(val start: Int, val length: Int, val wordID: String) {
    fun json() = JSONObject().put("start", start).put("length", length).put("word_id", wordID)
}
internal data class WordMessagePlan(val originalHash: String, val input: String, val target: String,
    val meaningLanguage: String, val words: List<WordPlanReference>?, val introducedID: String?) {
    fun json() = JSONObject().put("policy", "word-message-plan-v1").put("original_hash", originalHash)
        .put("input", input).put("target", target).put("meaning_language", meaningLanguage)
        .put("words", words?.let { list -> JSONArray().apply { list.forEach { put(it.json()) } } } ?: JSONObject.NULL)
        .put("introduced_id", introducedID ?: JSONObject.NULL)
    companion object {
        fun hash(text: String) = java.security.MessageDigest.getInstance("SHA-256").digest(text.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
        fun parse(value: JSONObject): WordMessagePlan {
            require(value.getString("policy") == "word-message-plan-v1")
            val words = (value.opt("words") as? JSONArray)?.let { list -> (0 until list.length()).map { index ->
                val item = list.getJSONObject(index)
                WordPlanReference(item.getInt("start"), item.getInt("length"), item.getString("word_id"))
            } }
            return WordMessagePlan(value.getString("original_hash"), value.getString("input"), value.getString("target"),
                value.getString("meaning_language"), words, value.opt("introduced_id") as? String)
        }
    }
}
