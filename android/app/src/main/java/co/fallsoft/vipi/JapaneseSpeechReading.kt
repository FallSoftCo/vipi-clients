package co.fallsoft.vipi

/** The bundled Japanese voice accepts kana, not kanji. Never change the displayed text. */
internal object JapaneseSpeechReading {
    fun convert(original: String): String = pronunciation(original).first

    fun pronunciation(original: String): Pair<String, SpeechProjection> {
        val offsets = mutableListOf<PlayingWord>()
        val result = StringBuilder()
        var cursor = 0
        for (token in NativeJapaneseTokenizer.tokens(original)) {
            val start = token.position
            val end = start + token.surface.length
            check(start >= cursor && end <= original.length && original.substring(start, end) == token.surface)
            if (start > cursor) offsets += PlayingWord(result.length until result.length + start - cursor, cursor until start)
            result.append(original.substring(cursor, start))
            val pronunciation = sequenceOf(token.pronunciation, token.reading).firstOrNull { value ->
                !value.isNullOrBlank() && value.codePoints().allMatch { code ->
                    code == 0x30fc || Character.UnicodeScript.of(code) in setOf(
                        Character.UnicodeScript.HIRAGANA, Character.UnicodeScript.KATAKANA)
                }
            }
            val spoken = pronunciation ?: token.surface
            offsets += PlayingWord(result.length until result.length + spoken.length, start until end)
            result.append(spoken)
            cursor = end
        }
        if (cursor < original.length) offsets += PlayingWord(result.length until result.length + original.length - cursor, cursor until original.length)
        result.append(original.substring(cursor))
        // Unknown names/characters have no reliable reading. Do not speak their code points.
        if (result.codePoints().anyMatch { Character.UnicodeScript.of(it) == Character.UnicodeScript.HAN }) {
            throw OfflineVoiceUnavailable("ja")
        }
        return result.toString() to SpeechProjection(false, offsets)
    }
}
