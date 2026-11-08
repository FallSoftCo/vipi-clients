package co.fallsoft.vipi

import android.content.Context

/** Display-only metadata. The original script remains the source for speech,
 * copying and message storage. Unsupported input keeps that script visible. */
internal object NativeFullReadings {
    const val POLICY = "authored-first-ja-kana-ko-cldr-zh-pinyin-v1"
    private var chineseLoaded = false
    private var chineseReader: ChineseReadings? = null

    @Synchronized private fun chinese(context: Context): ChineseReadings? {
        if (!chineseLoaded) {
            chineseReader = try {
                ChineseReadings(context.assets.open("readings/chinese-ordinary.json").use { it.readBytes() })
            } catch (_: Exception) { null }
            chineseLoaded = true
        }
        return chineseReader
    }

    fun resolve(text: String, language: String, authored: SentenceReadings, context: Context): FullReading? {
        if (text.length !in 1..16_384) return null
        authored.reading(text, language)?.let { return FullReading(it, FullReading.Provenance.AUTHORED) }
        val reading = when (language) {
            "ja" -> JapaneseReadings.read(text).reading
            "ko" -> KoreanReadings.resolve(text).reading
            "zh" -> chinese(context)?.resolve(text)?.reading
            else -> null
        }
        return reading?.takeIf { it.length in 1..65_536 }?.let {
            FullReading(it, FullReading.Provenance.LOCAL_TRANSLITERATION)
        }
    }
}
