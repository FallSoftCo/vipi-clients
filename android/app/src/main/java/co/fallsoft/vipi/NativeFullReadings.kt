package co.fallsoft.vipi

/** Display-only metadata. The original script remains the source for speech,
 * copying and message storage. Unsupported input keeps that script visible. */
internal object NativeFullReadings {
    const val POLICY = "authored-first-ja-kana-ko-cldr-v1"

    fun resolve(text: String, language: String, authored: SentenceReadings): FullReading? {
        if (text.length !in 1..16_384) return null
        authored.reading(text, language)?.let { return FullReading(it, FullReading.Provenance.AUTHORED) }
        val reading = when (language) {
            "ja" -> JapaneseReadings.read(text).reading
            "ko" -> KoreanReadings.resolve(text).reading
            else -> null
        }
        return reading?.takeIf { it.length in 1..65_536 }?.let {
            FullReading(it, FullReading.Provenance.LOCAL_TRANSLITERATION)
        }
    }
}
