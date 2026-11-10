package co.fallsoft.vipi

import co.fallsoft.vipi.core.TranslationIntegrity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** Bundled local classifier: no downloads or network calls. */
internal class MessageLanguage : AutoCloseable {
    private val lock = Any()
    private var closed = false
    suspend fun identify(text: String): String? = withContext(Dispatchers.Default) {
        synchronized(lock) {
            if (closed || text.length > 16_384) return@synchronized null
            val masked = mask(text)
            if (masked.count(Char::isLetter) < 4) return@synchronized null
            val bytes = masked.toByteArray(Charsets.UTF_8)
            if (bytes.size > 65_536) return@synchronized null
            val result = LocalLanguageDetector.detect(bytes) ?: return@synchronized null
            if (result[0] != "1") return@synchronized null
            val code = if (result[1] == "zh-Hant") "zh" else result[1]
            code.takeIf { it in supported }
        }
    }
    override fun close() { synchronized(lock) { closed = true } }
    companion object {
        private val supported = setOf("en", "es", "fr", "de", "it", "pt", "ar", "zh", "ja", "ko", "sw")
        internal fun mask(text: String): String = StringBuilder(text).apply {
            TranslationIntegrity.protectedLiteralRanges(text).asReversed().forEach {
                replace(it.first, it.last + 1, " ")
            }
        }.toString()
    }
}

internal object LocalLanguageDetector {
    init { System.loadLibrary("vipi_language") }
    // Standard UTF-8 bytes, never JNI's modified UTF-8 string representation.
    external fun detect(bytes: ByteArray): Array<String>?
}
