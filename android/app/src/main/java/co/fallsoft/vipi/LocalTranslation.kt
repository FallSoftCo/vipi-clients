package co.fallsoft.vipi

import com.google.mlkit.common.model.DownloadConditions
import com.google.mlkit.common.model.RemoteModelManager
import com.google.mlkit.nl.translate.TranslateRemoteModel
import com.google.mlkit.nl.translate.TranslateLanguage
import com.google.mlkit.nl.translate.Translation
import com.google.mlkit.nl.translate.Translator
import com.google.mlkit.nl.translate.TranslatorOptions
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** No server fallback. Translation calls never trigger a download implicitly. */
interface LanguageTranslation : AutoCloseable {
    suspend fun prepare(source: String, target: String, cellularAllowed: Boolean)
    suspend fun translate(text: String, source: String, target: String): String
    // Controlled boundaries must declare their readiness. A message itself
    // never authorizes downloading a newly detected third-language model.
    suspend fun isReady(source: String, target: String): Boolean = source == target
}

class LocalTranslation : LanguageTranslation {
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
    override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean): Unit = mutex.withLock {
        // A locally installed pair can translate offline without starting the
        // SDK download workflow or waiting for its remote configuration.
        if (isReady(source, target)) return@withLock
        val conditions = DownloadConditions.Builder().apply { if (!cellularAllowed) requireWifi() }.build()
        client(source, target).downloadModelIfNeeded(conditions).await()
    }
    override suspend fun isReady(source: String, target: String): Boolean {
        if (source == target) return true
        val installed = RemoteModelManager.getInstance().getDownloadedModels(TranslateRemoteModel::class.java).await().map { it.language }.toSet()
        return (source == "en" || source in installed) && (target == "en" || target in installed)
    }
    override suspend fun translate(text: String, source: String, target: String): String = mutex.withLock {
        // Callers pass complete selected lexical units. The SDK output is
        // preserved intact; no word/phrase dictionary or truncation is used.
        require(text.length <= 65_536)
        client(source, target).translate(text).await()
    }
    override fun close() { client?.close(); client = null; direction = null }
}
