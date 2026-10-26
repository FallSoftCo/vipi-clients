package co.fallsoft.vipi

import android.content.Context
import org.json.JSONObject

/** Exact authored sentence readings, never a generic script conversion. */
internal class SentenceReadings(context: Context) {
    private val index: Map<String, Map<String, String>> = try {
        val root = JSONObject(context.assets.open("sentence-readings.json").bufferedReader().use { it.readText() })
        require(root.getString("schema") == "vipi-sentence-readings-1")
        val rows = root.getJSONArray("entries")
        val languages = mutableMapOf<String, MutableMap<String, String>>()
        for (i in 0 until rows.length()) {
            val row = rows.getJSONObject(i)
            val language = row.getString("language"); val text = row.getString("text"); val latin = row.getString("latin")
            require(language in listOf("ar", "zh", "ja", "ko") && text.isNotEmpty() && latin.isNotEmpty())
            check(languages.getOrPut(language) { mutableMapOf() }.put(text, latin) == null)
        }
        languages
    } catch (_: Exception) { emptyMap() }
    fun reading(text: String, language: String): String? {
        if (text.length > 16_384) return null
        val values = index[language] ?: return null
        values[text]?.let { return it }
        val ranges = LocalImmersion.sentences(text, language)
        if (ranges.isEmpty()) return null
        val result = StringBuilder(); var end = 0
        for (range in ranges) {
            val gap = text.substring(end, range.first)
            if (!gap.all(Char::isWhitespace)) return null
            val reading = values[text.substring(range)] ?: return null
            result.append(if (gap.isEmpty() && result.isNotEmpty()) " " else gap).append(reading)
            end = range.last + 1
        }
        val tail = text.substring(end)
        return if (tail.all(Char::isWhitespace)) result.append(tail).toString() else null
    }
}
