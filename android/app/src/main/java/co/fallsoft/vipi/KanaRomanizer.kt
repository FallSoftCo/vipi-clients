package co.fallsoft.vipi

import java.text.Normalizer

/** Small deterministic kana layer, dormant with JapaneseReadings. No Android ICU API.
 * Factual correspondences: ALA-LC Japanese 2022 charts A/B, printed pp33-34.
 * https://loc.gov/catdir/cpso/romanization/japanese.pdf
 * Retains Vipi's existing wo/wi/we display spelling; not full ALA-LC catalog style.
 */
internal object KanaRomanizer {
    data class Normalized(val text: String, val sourceBoundaries: List<Int>) {
        fun sourceRange(start: Int, end: Int): IntRange? {
            if (start < 0 || end <= start || end >= sourceBoundaries.size) return null
            val a = sourceBoundaries[start]; val b = sourceBoundaries[end]
            return if (a >= 0 && b > a) a until b else null
        }
    }
    private fun base(code: Int) = code in 0x3041..0x3096 || code in 0x30a1..0x30fa || code in 0xff66..0xff9d
    private fun mark(code: Int) = code in setOf(0x3099, 0x309a, 0xff9e, 0xff9f)

    /** Normalize kana clusters only in an analysis copy. -1 marks an indivisible
     * cluster's internal boundary. Original spelling and UTF16 offsets survive. */
    fun normalizeKana(original: String): Normalized {
        val text = StringBuilder(); val boundaries = mutableListOf(0)
        var start = 0
        while (start < original.length) {
            val cp = original.codePointAt(start)
            var end = start + Character.charCount(cp)
            if (base(cp)) while (end < original.length && mark(original.codePointAt(end))) {
                end += Character.charCount(original.codePointAt(end))
            }
            val raw = original.substring(start, end)
            val normalized = if (base(cp)) Normalizer.normalize(raw, Normalizer.Form.NFKC) else raw
            text.append(normalized)
            for (i in normalized.indices) boundaries += if (i == normalized.lastIndex) end else -1
            start = end
        }
        return Normalized(text.toString(), boundaries.toList())
    }

    private val table: Map<String, String> = buildMap {
        fun row(kana: String, roman: String) {
            val values = roman.split(' '); check(kana.length == values.size)
            kana.forEachIndexed { i, c -> put(c.toString(), values[i]) }
        }
        row("アイウエオ", "a i u e o")
        row("カキクケコ", "ka ki ku ke ko"); row("サシスセソ", "sa shi su se so")
        row("タチツテト", "ta chi tsu te to"); row("ナニヌネノ", "na ni nu ne no")
        row("ハヒフヘホ", "ha hi fu he ho"); row("マミムメモ", "ma mi mu me mo")
        row("ヤユヨ", "ya yu yo"); row("ラリルレロ", "ra ri ru re ro")
        row("ワヰヱヲン", "wa wi we wo n")
        row("ガギグゲゴ", "ga gi gu ge go"); row("ザジズゼゾ", "za ji zu ze zo")
        row("ダヂヅデド", "da ji zu de do"); row("バビブベボ", "ba bi bu be bo")
        row("パピプペポ", "pa pi pu pe po"); row("ヴ", "vu")
        row("ァィゥェォャュョヮ", "a i u e o ya yu yo wa")
        for ((kana, consonant) in listOf('キ' to "k", 'ギ' to "g", 'ニ' to "n", 'ヒ' to "h",
            'ミ' to "m", 'リ' to "r", 'ビ' to "b", 'ピ' to "p")) {
            put("${kana}ャ", consonant + "ya"); put("${kana}ュ", consonant + "yu")
            put("${kana}ョ", consonant + "yo"); put("${kana}ェ", consonant + "ye")
            put("${kana}ィ", consonant + "ī")
        }
        for ((kana, consonant) in listOf('シ' to "sh", 'チ' to "ch", 'ジ' to "j", 'ヂ' to "j")) {
            put("${kana}ャ", consonant + "a"); put("${kana}ュ", consonant + "u")
            put("${kana}ョ", consonant + "o"); put("${kana}ェ", consonant + "e")
        }
        // Additional chart A spellings and chart B loanword combinations. Longest first.
        for (entry in ("キァ=kya ヒォ=hyo ビォ=byo ピォ=pyo イェ=ye " +
            "ウァ=wa ウィ=wi ウェ=we ウォ=wo クァ=kwa クィ=kwi クェ=kwe クォ=kwo " +
            "グァ=gwa グィ=gwi グェ=gwe グォ=gwo スィ=si スェ=swe ズィ=zi " +
            "ツァ=tsa ツィ=tsi ツェ=tse ツォ=tso ティ=ti トゥ=tu テュ=tyu " +
            "ファ=fa フィ=fi フェ=fe フォ=fo フュ=fyu フョ=fyo フィェ=fye " +
            "ヴァ=va ヴィ=vi ヴェ=ve ヴォ=vo ヴュ=vyu ディ=di ドゥ=du デュ=dyu").split(' ')) {
            val fields = entry.split('='); put(fields[0], fields[1])
        }
    }

    /** Receives kana only; literals/punctuation belong to the caller's exact pieces.
     * Unknown symbols and unresolved geminates fail closed, never disappear. */
    fun romanize(original: String): String? {
        if (original.isEmpty() || original.length > 16_384) return null
        val normalized = normalizeKana(original).text
        val kana = normalized.map { if (it in '\u3041'..'\u3096') (it.code + 0x60).toChar() else it }.joinToString("")
        val out = StringBuilder(); var i = 0
        fun syllable(at: Int): Pair<String, Int>? {
            for (length in 3 downTo 1) if (at + length <= kana.length) {
                table[kana.substring(at, at + length)]?.let { return it to length }
            }
            return null
        }
        while (i < kana.length) {
            if (kana[i] == 'ッ') {
                val next = syllable(i + 1)?.first ?: return null
                val initial = when {
                    next.startsWith("ch") -> 't'
                    next.first() in "bdfghjkpstvwz" -> next.first()
                    else -> return null
                }
                out.append(initial); i++; continue
            }
            if (kana[i] == 'ー') {
                val long = when (out.lastOrNull()) { 'a' -> 'ā'; 'i' -> 'ī'; 'u' -> 'ū'; 'e' -> 'ē'; 'o' -> 'ō'; else -> return null }
                out.setCharAt(out.lastIndex, long); i++; continue
            }
            val (roman, length) = syllable(i) ?: return null
            out.append(roman)
            if (kana[i] == 'ン') {
                val next = syllable(i + length)?.first
                if (next != null && next.first() in "aiueoy") out.append('\'')
            }
            i += length
        }
        return out.toString().takeIf(String::isNotEmpty)
    }
}
