package co.fallsoft.vipi

import com.google.mlkit.nl.languageid.LanguageIdentification
import com.google.mlkit.nl.languageid.LanguageIdentificationOptions
import kotlinx.coroutines.tasks.await

/** Bundled local classifier: no download and no message text leaves the device. */
internal class MessageLanguage : AutoCloseable {
    private val client = LanguageIdentification.getClient(LanguageIdentificationOptions.Builder().setConfidenceThreshold(0.01f).build())
    suspend fun identify(text: String): String? {
        if (text.count(Char::isLetter) < 4) return null
        val ranked = client.identifyPossibleLanguages(text).await().sortedByDescending { it.confidence }
        val first = ranked.firstOrNull() ?: return null
        // The decoder expects the written language, not an inferred romanized
        // input. Short/ambiguous messages retain their original with an override.
        if (first.languageTag == "und" || first.languageTag.endsWith("-Latn") ||
            first.confidence < 0.85f || (ranked.getOrNull(1)?.confidence ?: 0f) > 0.10f) return null
        return first.languageTag
    }
    override fun close() { client.close() }
}
