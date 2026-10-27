package co.fallsoft.vipi

import androidx.compose.runtime.*
import com.google.mlkit.common.model.RemoteModelManager
import com.google.mlkit.nl.translate.TranslateRemoteModel
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.tasks.await

internal data class DownloadPair(val source: String, val target: String) {
    val valid: Boolean get() = source != target && listOf(source, target).all { code -> initialLanguages.any { it.code == code } }
    val models: Set<String> get() = setOf(source, target) - "en" // English is built into ML Kit.
}

/** Native model state, independent of transient messages or cached translations. */
internal interface LanguageDownloadStore : AutoCloseable {
    suspend fun installed(pair: DownloadPair): Set<String>
    suspend fun download(pair: DownloadPair, cellular: Boolean)
    suspend fun remove(pair: DownloadPair)
}

internal class NativeLanguageDownloadStore : LanguageDownloadStore {
    private val manager = RemoteModelManager.getInstance()
    private val translator = LocalTranslation()
    override suspend fun installed(pair: DownloadPair): Set<String> {
        require(pair.valid)
        return pair.models.filter { manager.isModelDownloaded(TranslateRemoteModel.Builder(it).build()).await() }.toSet()
    }
    override suspend fun download(pair: DownloadPair, cellular: Boolean) {
        require(pair.valid); translator.prepare(pair.source, pair.target, cellular)
    }
    override suspend fun remove(pair: DownloadPair) {
        require(pair.valid); translator.close()
        for (code in installed(pair)) manager.deleteDownloadedModel(TranslateRemoteModel.Builder(code).build()).await()
    }
    override fun close() = translator.close()
}

/** Every async completion is tied to the exact visit and pair that requested it. */
internal class LanguageDownloads(private val store: LanguageDownloadStore = NativeLanguageDownloadStore()) : AutoCloseable {
    var pair by mutableStateOf<DownloadPair?>(null); private set
    var installed by mutableStateOf<Set<String>?>(null); private set
    var checking by mutableStateOf(false); private set
    var operation by mutableStateOf<String?>(null); private set
    var message by mutableStateOf<String?>(null); private set
    val busy: Boolean get() = operation != null
    val ready: Boolean get() = pair?.models?.let { installed?.containsAll(it) } == true
    private var epoch = 0L
    private var closed = false
    private fun current(token: Long) = !closed && token == epoch
    suspend fun refresh(value: DownloadPair) {
        if (closed || busy) return
        val token = ++epoch; pair = value; installed = null; checking = true; message = null
        try {
            require(value.valid)
            val observed = store.installed(value)
            require(value.models.containsAll(observed))
            if (current(token)) installed = observed
        } catch (error: CancellationException) { throw error }
        catch (_: Exception) { if (current(token)) message = "Your downloads couldn’t be checked. Please try again." }
        finally { if (current(token)) checking = false }
    }
    suspend fun download(cellular: Boolean) {
        val value = pair ?: return
        if (closed || busy || checking || !value.valid || ready || installed == null) return
        perform(value, "Downloading languages…", "The download couldn’t finish. Check your connection and try again.") {
            store.download(value, cellular)
        }
    }
    suspend fun remove() {
        val value = pair ?: return
        if (closed || busy || checking || !value.valid || installed.isNullOrEmpty()) return
        perform(value, "Removing downloads…", "Some downloads couldn’t be removed. Please try again.") { store.remove(value) }
    }
    private suspend fun perform(value: DownloadPair, label: String, failure: String, action: suspend () -> Unit) {
        val token = ++epoch; operation = label; message = null
        try {
            action()
            val observed = store.installed(value)
            require(value.models.containsAll(observed))
            if (current(token)) installed = observed
        } catch (error: CancellationException) { throw error }
        catch (_: Exception) {
            if (current(token)) {
                // A failed operation can still have partially changed native storage.
                installed = null; message = failure
                try {
                    val observed = store.installed(value)
                    require(value.models.containsAll(observed))
                    if (current(token)) installed = observed
                } catch (error: CancellationException) { throw error }
                catch (_: Exception) { /* Check again remains available. */ }
            }
        } finally { if (current(token)) operation = null }
    }
    fun invalidate() { epoch++; checking = false; operation = null; installed = null; message = null }
    override fun close() { invalidate(); closed = true; store.close() }
}
