package co.fallsoft.vipi

import org.json.JSONObject
import java.security.MessageDigest

/** Native display-only port of pinned pinyin-pro 3.29.5 ordinary data and its
 * probability/tie selection. MIT, copyright 2022-present zh-lx. Original script
 * remains audio/copy authority; exact provenance lives in data/readings. */
internal class ChineseReadings(data: ByteArray) {
    companion object {
        const val DATA_SHA256 = "ec2f31077ea4aa2f531e0711366bb3d07af495c8ab53f144f32a5b231ed3f35c"
        const val POLICY = "pinyin-pro-3.29.5-marked-native-2"
        private val opaque = listOf(
            Regex("```[\\s\\S]*?```"), Regex("`[^`\\r\\n]+`"),
            Regex("(?i)(?:https?://|www\\.)[^\\s<>\"“”‘’，。！？；、]+"),
            Regex("[\\p{IsLatin}\\p{M}\\p{N}._%+\\-]+@[\\p{IsLatin}\\p{M}\\p{N}.\\-]+\\.[\\p{IsLatin}\\p{M}]{2,}"),
            Regex("[\\p{IsLatin}\\p{M}\\p{N}]++(?:[\\-_'’./:][\\p{IsLatin}\\p{M}\\p{N}]++)*+")
        )
        private fun mark(point: Int) = Character.getType(point) in setOf(
            Character.NON_SPACING_MARK.toInt(), Character.COMBINING_SPACING_MARK.toInt(), Character.ENCLOSING_MARK.toInt())
        private fun number(point: Int) = Character.getType(point) in setOf(
            Character.DECIMAL_DIGIT_NUMBER.toInt(), Character.LETTER_NUMBER.toInt(), Character.OTHER_NUMBER.toInt())
        private fun alphanumeric(point: Int) = Character.isLetter(point) || mark(point) || number(point)
        private fun emailLocal(point: Int) = Character.UnicodeScript.of(point) == Character.UnicodeScript.LATIN ||
            mark(point) || number(point) || point in "._%+-".map(Char::code)
        private fun emails(text: String): Sequence<MatchResult> = sequence {
            // Same matching set as the upstream ordered expression; anchor at
            // actual @ signs to avoid quadratic unsuccessful Java regex starts.
            for (at in text.indices) if (text[at] == '@') {
                var start = at
                while (start > 0) { val cp = text.codePointBefore(start); if (!emailLocal(cp)) break; start -= Character.charCount(cp) }
                if (start < at) opaque[3].matchAt(text, start)?.let { yield(it) }
            }
        }
    }
    data class Piece(val startUTF16: Int, val endUTF16: Int, val source: String,
                     val reading: String, val converted: Boolean, val protected: Boolean)
    data class Result(val reading: String?, val pieces: List<Piece>, val unresolved: List<IntRange>)
    private data class Pattern(val source: IntArray, val readings: List<String>, val probability: Double)
    private data class Word(val source: IntArray, val readings: List<String>, val capitalized: Boolean)
    private val words: List<Word>
    private data class Node(val children: MutableMap<Int, Int> = mutableMapOf(), var pattern: Int? = null)
    private data class State(var probability: Double, var decimal: Int, val next: Int, val pattern: Int?) {
        fun scale() { if (probability < 1e-300) { probability *= 1e300; decimal++ } }
    }
    private val characters: Map<Int, List<String>>
    private val patterns: List<Pattern>
    private val nodes: List<Node>
    init {
        require(data.size == 813_708)
        require(MessageDigest.getInstance("SHA-256").digest(data).joinToString("") { "%02x".format(it) } == DATA_SHA256)
        val table = JSONObject(data.toString(Charsets.UTF_8)); require(table.getString("schema") == "vipi-pinyin-pro-marked-2")
        val chars = table.getJSONArray("characters"); val entries = table.getJSONArray("patterns")
        require(chars.length() == 21_132 && entries.length() == 4_198)
        val characterMap = mutableMapOf<Int, List<String>>()
        for (i in 0 until chars.length()) {
            val item = chars.getJSONArray(i); require(item.length() == 2); val points = item.getString(0).codePoints().toArray()
            val values = item.getJSONArray(1); val readings = (0 until values.length()).map { values.getString(it) }
            require(points.size == 1 && readings.isNotEmpty() && readings.all { it.isNotEmpty() })
            require(characterMap.put(points[0], readings) == null)
        }
        val allPatterns = mutableListOf<Pattern>(); val trie = mutableListOf(Node())
        for (i in 0 until entries.length()) {
            val item = entries.getJSONObject(i); val points = item.getString("source").codePoints().toArray()
            val values = item.getJSONArray("readings"); val readings = (0 until values.length()).map { values.getString(it) }
            val probability = item.getDouble("probability")
            require(points.size in 2..5 && points.size == readings.size && item.getInt("priority") == 1 && item.getInt("order") == i)
            require(probability.isFinite() && probability > 0)
            allPatterns += Pattern(points, readings, probability)
            var node = 0
            for (point in points) {
                val next = trie[node].children[point] ?: trie.size.also { trie += Node(); trie[node].children[point] = it }
                node = next
            }
            val old = trie[node].pattern
            if (old == null || allPatterns[old].probability <= probability) trie[node].pattern = i
        }
        val wordRows = table.getJSONArray("words")
        words = (0 until wordRows.length()).map { i ->
            val row = wordRows.getJSONObject(i); val readings = row.getJSONArray("readings")
            Word(row.getString("source").codePoints().toArray(), (0 until readings.length()).map { readings.getString(it) }, row.getBoolean("capitalized"))
        }.sortedByDescending { it.source.size }
        require(words.size == 35 && words.all { it.source.size in 2..5 && it.source.size == it.readings.size })
        characters = characterMap; patterns = allPatterns; nodes = trie
    }
    private fun best(a: State?, b: State): State {
        if (a == null) return b
        if (a.decimal != b.decimal) return if (a.decimal < b.decimal) a else b
        return if (a.probability > b.probability) a else b // incoming wins exact ties
    }
    private fun selected(points: IntArray, protected: BooleanArray): Map<Int, Int> {
        val n = points.size; val ending = Array(n) { mutableListOf<Pair<Int, Int>>() }
        for (start in 0 until n) if (!protected[start]) {
            var node = 0
            for (end in start until minOf(n, start + 5)) {
                if (protected[end]) break
                val next = nodes[node].children[points[end]] ?: break; node = next
                nodes[node].pattern?.let { ending[end] += start to it }
            }
        }
        val dp = arrayOfNulls<State>(n); val terminal = State(1.0, 0, n, null)
        for (end in n - 1 downTo 0) {
            val suffix = if (end + 1 == n) terminal else checkNotNull(dp[end + 1])
            val next = if (suffix.pattern == null) suffix.next else end + 1
            for ((start, pattern) in ending[end].asReversed()) {
                val state = State(patterns[pattern].probability * suffix.probability, suffix.decimal, next, pattern)
                state.scale(); dp[start] = best(dp[start], state)
            }
            // Upstream fallback explicitly resets decimal to zero. Preserve
            // this numeric behavior rather than silently changing selection.
            val unknown = State(1e-13 * suffix.probability, 0, next, null); unknown.scale(); dp[end] = best(dp[end], unknown)
        }
        val chosen = mutableMapOf<Int, Int>(); var index = 0
        while (index < n) { val state = checkNotNull(dp[index]); state.pattern?.let { chosen[index] = it }; index = state.next }
        return chosen
    }
    fun resolve(text: String, preserveOpaque: Boolean = true): Result {
        require(text.length in 1..FullReadingLimits.MAX_TEXT_UTF16)
        val points = text.codePoints().toArray(); val offsets = IntArray(points.size + 1)
        for (i in points.indices) offsets[i + 1] = offsets[i] + Character.charCount(points[i])
        val mask = BooleanArray(text.length)
        if (preserveOpaque) for ((i, pattern) in opaque.withIndex()) for (match in if (i == 3) emails(text) else pattern.findAll(text)) {
            if (match.range.any { mask[it] }) continue
            for (index in match.range) mask[index] = true
        }
        val protected = BooleanArray(points.size) { i -> (offsets[i] until offsets[i + 1]).all { mask[it] } }
        val chosen = selected(points, protected)
        val values = points.indices.map { i ->
            val point = points[i]; val previous = if (i == 0) null else characters[points[i - 1]]
            when {
                protected[i] -> String(Character.toChars(point))
                point == '了'.code && previous == null -> "liǎo"
                point == '々'.code -> previous?.first() ?: "tóng"
                else -> characters[point]?.first() ?: String(Character.toChars(point))
            }
        }.toMutableList()
        for ((start, pattern) in chosen) for ((offset, reading) in patterns[pattern].readings.withIndex()) values[start + offset] = reading
        // Join only attested words whose contextual selected syllables agree.
        // This changes display spacing, never the source ranges or speech text.
        val joined = arrayOfNulls<String>(points.size)
        var wordStart = 0
        while (wordStart < points.size) {
            val start = wordStart
            val word = words.firstOrNull { w -> start + w.source.size <= points.size && w.source.indices.all { j ->
                !protected[start + j] && points[start + j] == w.source[j] && values[start + j] == w.readings[j]
            } }
            if (word == null) { wordStart++; continue }
            for (j in 1 until word.source.size) joined[start + j] = if (values[start + j].firstOrNull() in listOf('a', 'ā', 'á', 'ǎ', 'à', 'e', 'ē', 'é', 'ě', 'è', 'o', 'ō', 'ó', 'ǒ', 'ò')) "'" else ""
            if (word.capitalized) values[start] = values[start].replaceFirstChar { it.uppercaseChar() }
            wordStart += word.source.size
        }
        val pieces = mutableListOf<Piece>(); val unresolved = mutableListOf<IntRange>(); val output = StringBuilder(); var previousConverted = false
        for (i in points.indices) {
            val source = text.substring(offsets[i], offsets[i + 1]); val reading = values[i]
            val converted = source != reading && !protected[i]
            if (!protected[i] && !converted && Character.isLetter(points[i]) &&
                Character.UnicodeScript.of(points[i]) != Character.UnicodeScript.LATIN) unresolved += offsets[i] until offsets[i + 1]
            if (joined[i] != null) output.append(joined[i])
            else if ((previousConverted || converted) && output.isNotEmpty() && reading.isNotEmpty() &&
                alphanumeric(output.codePointBefore(output.length)) && alphanumeric(reading.codePointAt(0))) output.append(' ')
            output.append(reading); previousConverted = converted
            pieces += Piece(offsets[i], offsets[i + 1], source, reading, converted, protected[i])
        }
        return Result(if (unresolved.isEmpty()) output.toString() else null, pieces, unresolved)
    }
}
