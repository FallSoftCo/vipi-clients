// Generated from the pinned Unicode CLDR data. See adjacent LICENSE/upstream.json.
package co.fallsoft.vipi
internal object KoreanLetterRules {
    const val policy = "cldr-f692579-orthographic-1"
    private val letters =
        mapOf(
            4352 to "g",
            4353 to "kk",
            4354 to "n",
            4355 to "d",
            4356 to "tt",
            4357 to "l",
            4358 to "m",
            4359 to "b",
            4360 to "pp",
            4361 to "s",
            4362 to "ss",
            4363 to "",
            4364 to "j",
            4365 to "jj",
            4366 to "ch",
            4367 to "k",
            4368 to "t",
            4369 to "p",
            4370 to "h",
            4449 to "a",
            4450 to "ae",
            4451 to "ya",
            4452 to "yae",
            4453 to "eo",
            4454 to "e",
            4455 to "yeo",
            4456 to "ye",
            4457 to "o",
            4458 to "wa",
            4459 to "wae",
            4460 to "oe",
            4461 to "yo",
            4462 to "u",
            4463 to "wo",
            4464 to "we",
            4465 to "wi",
            4466 to "yu",
            4467 to "eu",
            4468 to "ui",
            4469 to "i",
            4520 to "g",
            4521 to "kk",
            4522 to "gs",
            4523 to "n",
            4524 to "nj",
            4525 to "nh",
            4526 to "d",
            4527 to "l",
            4528 to "lg",
            4529 to "lm",
            4530 to "lb",
            4531 to "ls",
            4532 to "lt",
            4533 to "lp",
            4534 to "lh",
            4535 to "m",
            4536 to "b",
            4537 to "bs",
            4538 to "s",
            4539 to "ss",
            4540 to "ng",
            4541 to "j",
            4542 to "ch",
            4543 to "k",
            4544 to "t",
            4545 to "p",
            4546 to "h",
        )

    private data class Rule(val before: Regex, val after: Regex)

    private val rules =
        listOf(
            Rule(Regex("[aeiou]s\$"), Regex("^ᄊ")),
            Rule(Regex("a\$"), Regex("^[ᅦᅥᅳ]")),
            Rule(Regex("[^aow]e\$"), Regex("^[ᅩᅬ]")),
            Rule(Regex("[^aowy]e\$"), Regex("^[ᅮᅴ]")),
            Rule(Regex("[^ey]o\$"), Regex("^[ᅦᅥᅳ]")),
            Rule(Regex("[^y]u\$"), Regex("^[ᅵ]")),
            Rule(Regex("[^aeiouwy][y]e\$"), Regex("^ᄋ[ᅩᅬ]")),
            Rule(Regex("[^aeiouwy]e\$"), Regex("^ᄋ[ᅩᅬᅮ]")),
            Rule(Regex("[^aeiouwy][oa]\$"), Regex("^ᄋ[ᅦᅥᅳ]")),
            Rule(Regex("[^aeiouwy][wy]a\$"), Regex("^ᄋ[ᅦᅥᅳ]")),
            Rule(Regex("[aeiou]b\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]d\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]g\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]h\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]j\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]k\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]m\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]n\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]p\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]s\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]t\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]l\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]bs\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]kk\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]gs\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]lb\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]lg\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]lh\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]lm\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]lp\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]ls\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]lt\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]ng\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]nh\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]nj\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]ss\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]ch\$"), Regex("^ᄋ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]j\$"), Regex("^ᄌ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]k\$"), Regex("^ᄏ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]s\$"), Regex("^ᄉ[ᅡ-ᅵ]")),
            Rule(Regex("[aeiou]bs\$"), Regex("^[ᄉᄊ]")),
            Rule(Regex("[aeiou]gs\$"), Regex("^[ᄉᄊ]")),
            Rule(Regex("[aeiou]lb\$"), Regex("^[ᄇ]")),
            Rule(Regex("[aeiou]lg\$"), Regex("^[ᄀ]")),
            Rule(Regex("[aeiou]ls\$"), Regex("^[ᄉᄊ]")),
            Rule(Regex("[aeiou]ng\$"), Regex("^[ᄀ]")),
            Rule(Regex("[aeiou]nj\$"), Regex("^[ᄌᄍ]")),
            Rule(Regex("[aeiou]lp\$"), Regex("^[ᄑ]")),
            Rule(Regex("[aeiou]lt\$"), Regex("^[ᄐ]")),
            Rule(Regex("[aeiou]k\$"), Regex("^[ᄁᄏ]")),
            Rule(Regex("[aeiou]p\$"), Regex("^ᄑ")),
            Rule(Regex("[aeiou]t\$"), Regex("^ᄐ")),
            Rule(Regex("[aeiou]c\$"), Regex("^[ᄒ]")),
        )
    // A fixed dispatch table avoids scanning irrelevant rules per letter.
    private val byFirst =
        letters.keys.associateWith { code ->
            rules.filter { rule ->
                (0x1161..0x1175).any { vowel ->
                    rule.after.containsMatchIn(code.toChar().toString() + vowel.toChar())
                }
            }
        }

    fun romanize(source: String): String {
        require(source.isNotEmpty() && source.all { it.code in 0xAC00..0xD7A3 })
        val jamo = StringBuilder(source.length * 3)
        for (syllable in source) {
            val index = syllable.code - 0xAC00
            jamo.append((0x1100 + index / 588).toChar())
            jamo.append((0x1161 + index % 588 / 28).toChar())
            if (index % 28 != 0) jamo.append((0x11A7 + index % 28).toChar())
        }
        val output = StringBuilder()
        for (index in jamo.indices) {
            val candidates = byFirst[jamo[index].code].orEmpty()
            if (candidates.isNotEmpty()) {
                // ICU negated context classes include the start boundary.
                val before =
                    if (output.length < 6) "\uFFFF" + output.toString()
                    else output.substring(output.length - 6)
                val after = jamo.substring(index, minOf(jamo.length, index + 2))
                if (
                    candidates.any {
                        it.before.containsMatchIn(before) && it.after.containsMatchIn(after)
                    }
                )
                    output.append('-')
            }
            output.append(letters.getValue(jamo[index].code))
        }
        return output.toString()
    }
}
