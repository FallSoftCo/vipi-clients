package co.fallsoft.vipi.contextqa

import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest
import java.text.Normalizer

/** Isolated, uncompiled preparation. Original offsets are half-open UTF16. */
internal class FrozenContextTokenizer(tableBytes: ByteArray) {
    data class Range(val start: Int, val end: Int)
    data class Token(val original: String, val normalized: String, val range: Range, val hasAlphabeticScalar: Boolean)
    private val table: JSONObject
    private val assigned: List<IntRange>
    private val alnum: List<IntRange>
    private val alpha: List<IntRange>
    private val space: List<IntRange>
    private val folds: Map<Int, IntArray>

    init {
        require(tableBytes.size == 51278 && sha256(tableBytes) == TABLE_SHA)
        table = JSONObject(tableBytes.toString(Charsets.UTF_8))
        require(table.getString("unicode_version") == "15.0.0")
        assigned = ranges("assigned"); alnum = ranges("alnum")
        alpha = ranges("alpha"); space = ranges("space")
        val values = table.getJSONArray("casefold")
        val map = mutableMapOf<Int, IntArray>()
        for (i in 0 until values.length()) {
            val row = values.getJSONArray(i)
            require(row.length() == 2)
            val key = row.getInt(0); val sequence = row.getJSONArray(1)
            require(!map.containsKey(key))
            map[key] = IntArray(sequence.length()) { sequence.getInt(it) }
        }
        folds = map.toMap()
    }
    private fun ranges(key: String): List<IntRange> {
        val rows = table.getJSONArray(key)
        var end = -1
        return (0 until rows.length()).map {
            val row = rows.getJSONArray(it)
            require(row.length() == 2)
            val a = row.getInt(0); val b = row.getInt(1)
            require(a > end && a <= b && b <= 0x10ffff)
            end = b; a..b
        }
    }
    private fun contains(value: Int, rows: List<IntRange>): Boolean {
        var low = 0; var high = rows.size
        while (low < high) {
            val mid = low + (high - low) / 2
            if (rows[mid].last < value) low = mid + 1 else high = mid
        }
        return low < rows.size && rows[low].first <= value
    }
    private fun scalars(text: String): IntArray {
        require(text.length <= 16384)
        val values = text.codePoints().toArray()
        require(values.all { it !in 0xd800..0xdfff && contains(it, assigned) })
        return values
    }
    fun normalize(text: String): String {
        scalars(text)
        val nfc = scalars(Normalizer.normalize(text, Normalizer.Form.NFC))
        val result = StringBuilder(); var pendingSpace = false
        for (value in nfc) for (fold in folds[value] ?: intArrayOf(value)) {
            if (contains(fold, space)) {
                if (result.isNotEmpty()) pendingSpace = true
            } else {
                if (pendingSpace) result.append(' ')
                pendingSpace = false; result.appendCodePoint(fold)
            }
        }
        return result.toString()
    }
    fun tokenize(source: String): List<Token> {
        val values = scalars(source)
        val offsets = IntArray(values.size + 1)
        for (i in values.indices) offsets[i + 1] = offsets[i] + Character.charCount(values[i])
        val result = mutableListOf<Token>(); var i = 0
        while (i < values.size) {
            val start = i; val value = values[i]
            if (contains(value, alnum)) {
                i++
                while (i < values.size && contains(values[i], alnum)) i++
                while (i + 1 < values.size && values[i] in setOf(39, 0x2019) && contains(values[i + 1], alnum)) {
                    i += 2
                    while (i < values.size && contains(values[i], alnum)) i++
                }
            } else if (value == 95 || contains(value, space)) { i++; continue }
            else i++
            val original = source.substring(offsets[start], offsets[i])
            val normalized = normalize(original)
            result += Token(original, normalized, Range(offsets[start], offsets[i]),
                normalized.codePoints().toArray().any { contains(it, alpha) })
        }
        return result.toList()
    }
    companion object {
        const val TABLE_SHA = "930b68ddf7c328233125eeb56a68b6863a9b97942a7a5023128e6ad34b489879"
        fun sha256(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(bytes)
            .joinToString("") { "%02x".format(it.toInt() and 255) }
    }
}
