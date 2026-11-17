package co.fallsoft.vipi

import co.fallsoft.vipi.core.TranslationIntegrity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.tasks.await

/** Bundled on-device classification; confidence routes lookup, never authorizes a translation. */
internal class MessageLanguage : AutoCloseable {
    private val lock = Any()
    private val client = com.google.mlkit.nl.languageid.LanguageIdentification.getClient()
    private var closed = false
    suspend fun identify(text: String, requireTwoWords: Boolean = true): String? = withContext(Dispatchers.Default) {
        if (text.length > 16_384) return@withContext null
        val masked = mask(text)
        if (masked.count(Char::isLetter) < 4 || masked.toByteArray(Charsets.UTF_8).size > 65_536 || (requireTwoWords && !hasTwoWords(masked))) return@withContext null
        val task = synchronized(lock) { if (closed) return@withContext null; client.identifyLanguage(masked) }
        val result = task.await()
        synchronized(lock) {
            if (closed) return@synchronized null
            val code = if (result == "zh-Hant") "zh" else result
            code.takeIf { it in supported }
        }
    }
    override fun close() { synchronized(lock) { if (!closed) { closed = true; client.close() } } }
    companion object {
        private val supported = setOf("en", "es", "fr", "de", "it", "pt", "ar", "zh", "ja", "ko", "sw")
        internal fun mask(text: String): String = StringBuilder(text).apply {
            TranslationIntegrity.protectedLiteralRanges(text).asReversed().forEach {
                replace(it.first, it.last + 1, " ")
            }
        }.toString()
        internal fun hasTwoWords(text: String): Boolean {
            val iterator = java.text.BreakIterator.getWordInstance(java.util.Locale.ROOT)
            iterator.setText(text)
            var start = iterator.first(); var count = 0
            while (true) {
                val end = iterator.next()
                if (end == java.text.BreakIterator.DONE) break
                if (text.substring(start, end).any(Char::isLetter) && ++count >= 2) return true
                start = end
            }
            return false
        }
    }
}

internal object LocalLanguageDetector {
    init { System.loadLibrary("vipi_language") }
    // Standard UTF-8 bytes, never JNI's modified UTF-8 string representation.
    external fun detect(bytes: ByteArray): Array<String>?
}
