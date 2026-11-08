package co.fallsoft.vipi

/** The bundled Japanese voice accepts kana, not kanji. Never change the displayed text. */
internal object JapaneseSpeechReading {
    fun convert(original: String): String {
        val result = StringBuilder()
        var cursor = 0
        for (token in LocalImmersion.japaneseTokens(original)) {
            val start = token.position
            val end = start + token.surface.length
            check(start >= cursor && end <= original.length && original.substring(start, end) == token.surface)
            result.append(original.substring(cursor, start))
            val pronunciation = sequenceOf(token.pronunciation, token.reading).firstOrNull { value ->
                !value.isNullOrBlank() && value.codePoints().allMatch { code ->
                    code == 0x30fc || Character.UnicodeScript.of(code) in setOf(
                        Character.UnicodeScript.HIRAGANA, Character.UnicodeScript.KATAKANA)
                }
            }
            result.append(pronunciation ?: token.surface)
            cursor = end
        }
        result.append(original.substring(cursor))
        // Unknown names/characters have no reliable reading. Do not speak their code points.
        if (result.codePoints().anyMatch { Character.UnicodeScript.of(it) == Character.UnicodeScript.HAN }) {
            throw OfflineVoiceUnavailable("ja")
        }
        return result.toString()
    }
}
