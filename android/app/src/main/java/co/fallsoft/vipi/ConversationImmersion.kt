package co.fallsoft.vipi

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.ui.unit.dp
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import co.fallsoft.vipi.core.ImmersionResult
import co.fallsoft.vipi.core.TranslationIntegrity
import com.google.mlkit.common.model.RemoteModelManager
import com.google.mlkit.nl.translate.TranslateRemoteModel
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import kotlin.coroutines.coroutineContext

/** Public app-signed assets; no QA signing keys and no stored message text. */
internal class BundledImmersionCatalog(private val context: Context) {
    private val verified = mutableMapOf<String, File>()
    private val index by lazy {
        JSONObject(context.assets.open("immersion/catalog.json").bufferedReader().use { it.readText() }).also {
            require(it.getString("schema") == "vipi-bundled-frames-1")
        }
    }
    private val references by lazy {
        val values = index.getJSONArray("references")
        val result = mutableMapOf<String, MutableMap<String, String>>()
        for (offset in 0 until values.length()) {
            val value = values.getJSONObject(offset)
            check(result.getOrPut(value.getString("pair")) { mutableMapOf() }
                .put(value.getString("original"), value.getString("translation")) == null)
        }
        result
    }
    fun reference(original: String, source: String, target: String): String? {
        val values = references["$source-$target"] ?: return null
        values[original]?.let { return it }
        val sentences = LocalImmersion.sentences(original, source)
        if (sentences.isEmpty()) return null
        var end = 0
        val output = StringBuilder()
        for (range in sentences) {
            val gap = original.substring(end, range.first)
            if (!gap.all(Char::isWhitespace)) return null
            val value = values[original.substring(range)] ?: return null
            output.append(gap).append(value); end = range.last+1
        }
        val tail = original.substring(end)
        return if (tail.all(Char::isWhitespace)) output.append(tail).toString() else null
    }
    fun result(original: String, translated: String, source: String, target: String, density: Double,
        supplementalEntries: List<co.fallsoft.vipi.core.VocabularyEntry> = emptyList()): ImmersionResult {
        require(source in initialLanguages.map { it.code } && target in initialLanguages.map { it.code } && source != target)
        val id = "$source-$target"
        val packs = index.getJSONArray("packs")
        val pack = (0 until packs.length()).map { packs.getJSONObject(it) }.single { it.getString("id") == id }
        val entries = database(pack, "").use { ReviewedFrameLookup.entries(it, original, translated, source, target) }.toMutableList()
        val contexts = index.optJSONArray("contexts")
        if (contexts != null) {
            val contextual = (0 until contexts.length()).map { contexts.getJSONObject(it) }.singleOrNull { it.getString("id") == id }
            if (contextual != null) database(contextual, "-contexts").use { entries += ReviewedContextLookup.entries(it, original, source, target) }
        }
        return LocalImmersion.align(original, translated, entries, density, source, target, supplementalEntries)
    }
    private fun database(pack: JSONObject, suffix: String): SQLiteDatabase {
        val id = pack.getString("id") + suffix
        val path = verified.getOrPut(id) {
            val bytes = context.assets.open("immersion/$id.sqlite").use { it.readBytes() }
            val hash = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
            require(bytes.size == pack.getInt("bytes") && hash == pack.getString("sha256"))
            val root = File(context.noBackupFilesDir, "immersion-public").apply { mkdirs() }
            val file = File(root, "$id-$hash.sqlite")
            // Atomic replacement also repairs a partial/changed local copy.
            val temporary = File.createTempFile("pack-", ".sqlite", root)
            try { temporary.writeBytes(bytes); check(temporary.renameTo(file)) } finally { temporary.delete() }
            val ownRevision = Regex(Regex.escape(id)+"-[a-f0-9]{64}\\.sqlite")
            root.listFiles()?.filter { it.name.matches(ownRevision) && it != file }?.forEach { it.delete() }
            file
        }
        return SQLiteDatabase.openDatabase(path.path, null, SQLiteDatabase.OPEN_READONLY or SQLiteDatabase.NO_LOCALIZED_COLLATORS)
    }
}

/** Per conversation, serial work and bounded memory. ChatItem is immutable. */
internal class ConversationImmersion(context: Context, val source: String, val target: String, private val density: Double) : AutoCloseable {
    private val translator = LocalTranslation()
    private val language = MessageLanguage()
    private val catalog = BundledImmersionCatalog(context.applicationContext)
    private val readings = SentenceReadings(context.applicationContext)
    private val mutex = Mutex()
    private val cache = linkedMapOf<String, ImmersionResult>()
    private val inputLanguages = mutableStateMapOf<String, String>()
    private var closed = false
    var ready by mutableStateOf<Boolean?>(null)
        private set
    fun inputLanguage(id: String): String? = inputLanguages[id]
    fun selectInputLanguage(id: String, language: String?) {
        if (closed || (language != null && language !in listOf(source, target))) return
        if (language == null) inputLanguages.remove(id) else inputLanguages[id] = language
    }
    fun cached(text: String, messageID: String? = null): ImmersionResult? =
        if (closed) null else cache["${messageID?.let { inputLanguages[it] } ?: "auto"}:$text"]
    fun reading(text: String): String? = readings.reading(text, target)

    suspend fun checkDownloads() {
        try {
            val manager = RemoteModelManager.getInstance()
            val installed = listOf(source, target).all { code ->
                code == "en" || manager.isModelDownloaded(TranslateRemoteModel.Builder(code).build()).await()
            }
            if (!closed) ready = installed
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { if (!closed) ready = false }
    }
    suspend fun result(text: String, inputLanguage: String? = null): ImmersionResult? = mutex.withLock {
        if (closed || text.isBlank() || text.length > 16_384) return@withLock null
        if (inputLanguage != null && inputLanguage !in listOf(source, target)) return@withLock null
        val key = (inputLanguage ?: "auto") + ":" + text
        cache[key]?.let { return@withLock it }
        try {
            val forward = if (inputLanguage != target) withContext(Dispatchers.Default) { catalog.reference(text, source, target) } else null
            val reverse = if (forward == null && inputLanguage != source) withContext(Dispatchers.Default) { catalog.reference(text, target, source) } else null
            val detected = when {
                forward != null -> source
                reverse != null -> target
                inputLanguage != null -> inputLanguage
                else -> language.identify(text)
            }
            if (closed || detected !in listOf(source, target) || (forward == null && reverse == null && ready != true)) return@withLock null
            val reversed = detected == target
            val translated = forward ?: reverse ?: translator.translate(text, if (reversed) target else source, if (reversed) source else target)
            coroutineContext.ensureActive()
            if (closed || !TranslationIntegrity.preservesIdentifiers(text, translated)) return@withLock null
            val result = withContext(Dispatchers.Default) {
                catalog.result(if (reversed) translated else text, if (reversed) text else translated, source, target, density)
            }
            if (closed) return@withLock null
            cache[key] = result
            while (cache.size > 128) cache.remove(cache.keys.first())
            result
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { null }
    }
    override fun close() { closed = true; cache.clear(); inputLanguages.clear(); translator.close(); language.close() }
}

@Composable internal fun ConversationImmersionText(text: String, id: String, immersion: ConversationImmersion,
    speech: SpeechPlayback, paused: Boolean, onVoiceHelp: () -> Unit, metadata: @Composable () -> Unit) {
    // Recycled rows must start from the already prepared layout. Briefly
    // showing plain text before an asynchronous cache hit moves page anchors.
    var result by remember(id, text, immersion) { mutableStateOf(immersion.cached(text, id)) }
    var waiting by remember(text, immersion) { mutableStateOf<ImmersionResult?>(null) }
    var hasWaiting by remember(text, immersion) { mutableStateOf(false) }
    val currentlyPaused by rememberUpdatedState(paused)
    var mode by remember(text, immersion) { mutableStateOf(ReadingMode.IMMERSED) }
    val inputLanguage = immersion.inputLanguage(id)
    LaunchedEffect(text, immersion, immersion.ready, inputLanguage) {
        val value = immersion.result(text, inputLanguage)
        if (currentlyPaused) { waiting = value; hasWaiting = true } else { result = value; hasWaiting = false }
    }
    LaunchedEffect(paused) { if (!paused && hasWaiting) { result = waiting; waiting = null; hasWaiting = false } }
    val current = result
    if (current == null) Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
        SelectionContainer { Text(text) }
        UntranslatedMessageActions(text, immersion.source, immersion.target, inputLanguage, onLanguage = { immersion.selectInputLanguage(id, it) }, metadata = metadata)
    }
    else ImmersionBubble(current, mode, speech, immersion.source, immersion.target, id, paused,
        fullReading = remember(current, immersion) { immersion.reading(current.translation) },
        embedded = true, onModeChange = { mode = it }, metadata = metadata, onVoiceHelp = onVoiceHelp,
        originalMessage = text, inputLanguage = inputLanguage, onInputLanguage = { immersion.selectInputLanguage(id, it) })
}
