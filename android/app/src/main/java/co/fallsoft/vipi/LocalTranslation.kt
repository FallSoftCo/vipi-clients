package co.fallsoft.vipi

import com.google.mlkit.common.model.DownloadConditions
import com.google.mlkit.nl.translate.TranslateLanguage
import com.google.mlkit.nl.translate.Translation
import com.google.mlkit.nl.translate.Translator
import com.google.mlkit.nl.translate.TranslatorOptions
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** No server fallback. Translation calls never trigger a download implicitly. */
class LocalTranslation : AutoCloseable {
    private val mutex = Mutex()
    private var client: Translator? = null
    private var direction: Pair<String, String>? = null
    private fun client(source: String, target: String): Translator {
        require(source != target)
        require(source in TranslateLanguage.getAllLanguages() && target in TranslateLanguage.getAllLanguages())
        if (direction != source to target) {
            close()
            client = Translation.getClient(TranslatorOptions.Builder().setSourceLanguage(source).setTargetLanguage(target).build())
            direction = source to target
        }
        return checkNotNull(client)
    }
    suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = mutex.withLock {
        val conditions = DownloadConditions.Builder().apply { if (!cellularAllowed) requireWifi() }.build()
        client(source, target).downloadModelIfNeeded(conditions).await()
    }
    suspend fun translate(text: String, source: String, target: String): String = mutex.withLock {
        require(text.length <= 16_384)
        client(source, target).translate(text).await()
    }
    override fun close() { client?.close(); client = null; direction = null }
}
