package co.fallsoft.vipi

import co.fallsoft.vipi.core.TranslationIntegrity
import java.text.Normalizer

/**
 * Dormant renderer for explicitly vocalized Arabic. Never supplies missing short vowels; no
 * diacritizer/model is enabled by this component.
 */
internal object ArabicVocalizedReadings {
    const val POLICY = "vocalized-arabic-conventional-latin-candidate-1"

    data class Piece(
        val startUTF16: Int,
        val endUTF16: Int,
        val source: String,
        val reading: String?,
        val protected: Boolean,
    )

    data class Result(val reading: String?, val pieces: List<Piece>, val unresolved: List<IntRange>)

    private val consonants =
        mapOf(
            'ء' to "'",
            'أ' to "'",
            'إ' to "'",
            'ؤ' to "'",
            'ئ' to "'",
            'ب' to "b",
            'ت' to "t",
            'ث' to "th",
            'ج' to "j",
            'ح' to "ḥ",
            'خ' to "kh",
            'د' to "d",
            'ذ' to "dh",
            'ر' to "r",
            'ز' to "z",
            'س' to "s",
            'ش' to "sh",
            'ص' to "ṣ",
            'ض' to "ḍ",
            'ط' to "ṭ",
            'ظ' to "ẓ",
            'ع' to "'",
            'غ' to "gh",
            'ف' to "f",
            'ق' to "q",
            'ك' to "k",
            'ل' to "l",
            'م' to "m",
            'ن' to "n",
            'ه' to "h",
            'و' to "w",
            'ي' to "y",
            'ة' to "t",
        )
    private val sun = "تثدذرزسشصضطظلن".toSet()
    // Omitted orthographic long alif only; supplied short vowels stay authoritative.
    private val longAlif =
        mapOf(
            "هذا" to setOf(0),
            "هذه" to setOf(0),
            "ذلك" to setOf(0),
            "هؤلاء" to setOf(0),
            "أولئك" to setOf(2),
            "لكن" to setOf(0),
            "الله" to setOf(2),
            "الرحمن" to setOf(4),
            "رحمن" to setOf(2),
            "إله" to setOf(1),
            "الإله" to setOf(3),
        )
    private val vowels =
        mapOf('َ' to "a", 'ُ' to "u", 'ِ' to "i", 'ً' to "an", 'ٌ' to "un", 'ٍ' to "in", 'ْ' to "")

    private fun mark(c: Char) =
        Character.getType(c) in
            setOf(
                Character.NON_SPACING_MARK.toInt(),
                Character.COMBINING_SPACING_MARK.toInt(),
                Character.ENCLOSING_MARK.toInt(),
            )

    private fun arabicLetter(c: Char) =
        Character.isLetter(c) &&
            Character.UnicodeScript.of(c.code) == Character.UnicodeScript.ARABIC

    private data class Node(val base: Char, val marks: Set<Char>)

    private fun nodes(word: String): List<Node>? {
        val normalized = Normalizer.normalize(word, Normalizer.Form.NFC)
        val result = mutableListOf<Node>()
        var i = 0
        while (i < normalized.length) {
            val base = normalized[i++]
            if (base == 'ـ') continue
            if (!arabicLetter(base)) return null
            val marks = mutableSetOf<Char>()
            while (i < normalized.length && mark(normalized[i])) marks += normalized[i++]
            if (marks.any { it !in vowels && it != 'ّ' && it != 'ٰ' }) return null
            if (marks.count { it in vowels } > 1) return null
            result += Node(base, marks)
        }
        return result.takeIf { it.isNotEmpty() }
    }

    private fun short(node: Node) = node.marks.firstNotNullOfOrNull { vowels[it] }

    private fun word(text: String): String? {
        val n = nodes(text) ?: return null
        val bare = n.map { it.base }.joinToString("")
        val boost = mutableSetOf<Int>()
        longAlif[bare]?.let { boost += it }
        if (n.size > 1 && n[0].base in "وفبك" && short(n[0]) in listOf("a", "i"))
            longAlif[bare.drop(1)]?.forEach { boost += it + 1 }
        var start = 0
        var prefix = ""
        var suppressDouble = -1
        var article = if (n.size > 2 && n[0].base in "اٱ" && n[1].base == 'ل') 0 else -1
        if (
            article < 0 &&
                n.size > 3 &&
                n[0].base in "وفبك" &&
                short(n[0]) in listOf("a", "i") &&
                n[1].base in "اٱ" &&
                n[2].base == 'ل'
        ) {
            prefix = consonants.getValue(n[0].base) + short(n[0]) + "-"
            article = 1
        }
        if (article >= 0) {
            start = article + 2
            val next = n[start].base
            if (next in sun) {
                prefix += (if (article == 0) "a" else "") + consonants.getValue(next) + "-"
                suppressDouble = start
            } else prefix += (if (article == 0) "al-" else "l-")
            if (bare.drop(article) == "الله")
                prefix = if (article == 0) "al" else prefix.removeSuffix("l-") + "l"
        } else if (
            n.size > 2 &&
                n[0].base == 'ل' &&
                short(n[0]) == "i" &&
                n[1].base == 'ل' &&
                'ْ' in n[1].marks
        ) {
            prefix = "li-l-"
            start = 2
        }
        val out = StringBuilder(prefix)
        var i = start
        while (i < n.size) {
            val node = n[i]
            val c = node.base
            val next = n.getOrNull(i + 1)
            if (c == 'آ') {
                out.append(if (i == 0) "ā" else "'ā")
                i++
                continue
            }
            if (
                c == 'ا' &&
                    i == n.lastIndex &&
                    i > 0 &&
                    n[i - 1].base == 'و' &&
                    node.marks.isEmpty()
            ) {
                i++
                continue
            }
            var consonant =
                when {
                    c in "اٱ" -> ""
                    c == 'ة' && short(node) == null -> "h"
                    i == 0 && c in "أإ" -> ""
                    else -> consonants[c] ?: return null
                }
            var vowel = short(node)
            if ('ٰ' in node.marks) {
                if (vowel != null && vowel != "a") return null
                vowel = "ā"
            }
            if (i in boost && vowel == "a") vowel = "ā"
            if (vowel == null) {
                if (c == 'ة' && i == n.lastIndex) {
                    out.append("h")
                    i++
                    continue
                }
                if ('ّ' in node.marks && i == n.lastIndex) vowel = "" else return null
            }
            if ('ّ' in node.marks && i != suppressDouble) consonant += consonant
            var consumed = 1
            if (next != null && next.marks.isEmpty()) {
                if (
                    (vowel == "a" && next.base in "اى") ||
                        (vowel == "u" && next.base == 'و') ||
                        (vowel == "i" && next.base == 'ي')
                ) {
                    vowel =
                        when (vowel) {
                            "a" -> "ā"
                            "u" -> "ū"
                            else -> "ī"
                        }
                    consumed = 2
                } else if (vowel == "an" && next.base == 'ا') consumed = 2
            }
            out.append(consonant).append(vowel)
            i += consumed
        }
        return out.toString()
    }

    fun resolve(text: String): Result {
        if (text.length !in 1..16_384 || text.codePoints().anyMatch { it in 0xD800..0xDFFF })
            return Result(null, emptyList(), emptyList())
        val mask = BooleanArray(text.length)
        for (range in TranslationIntegrity.protectedLiteralRanges(text)) for (i in range) mask[i] =
            true
        for (match in
            Regex("[\\p{IsLatin}][\\p{IsLatin}\\p{M}]*(?:[’'._-][\\p{IsLatin}\\p{M}]+)*")
                .findAll(text)) for (i in match.range) mask[i] = true
        val pieces = mutableListOf<Piece>()
        val unresolved = mutableListOf<IntRange>()
        val output = StringBuilder()
        var i = 0
        var any = false
        while (i < text.length) {
            val start = i
            val protected = mask[i]
            val kind =
                when {
                    protected -> 0
                    arabicLetter(text[i]) || mark(text[i]) || text[i] == 'ـ' -> 1
                    else -> 2
                }
            i++
            while (
                i < text.length &&
                    when (kind) {
                        0 -> mask[i]
                        1 -> !mask[i] && (arabicLetter(text[i]) || mark(text[i]) || text[i] == 'ـ')
                        else ->
                            !mask[i] && !arabicLetter(text[i]) && !mark(text[i]) && text[i] != 'ـ'
                    }
            ) i++
            val source = text.substring(start, i)
            val value = if (kind == 1) word(source) else source
            if (kind == 1) {
                any = true
                if (value == null) unresolved += start until i
            }
            if (
                kind == 2 &&
                    source.codePoints().anyMatch {
                        Character.isLetter(it) &&
                            Character.UnicodeScript.of(it) != Character.UnicodeScript.LATIN
                    }
            )
                unresolved += start until i
            pieces += Piece(start, i, source, value, protected)
            output.append(value ?: source)
        }
        check(pieces.joinToString("") { it.source } == text)
        return Result(
            output.toString().takeIf { any && unresolved.isEmpty() && it.length <= 65_536 },
            pieces,
            unresolved,
        )
    }
}
