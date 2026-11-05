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
import co.fallsoft.vipi.core.ImmersionPresentation
import co.fallsoft.vipi.core.PartialImmersionResult
import co.fallsoft.vipi.core.SourceReferenceUnit
import co.fallsoft.vipi.core.SourceReferencePresentation
import co.fallsoft.vipi.core.ReferenceComposition
import co.fallsoft.vipi.core.LookupFirst
import co.fallsoft.vipi.core.LookupFirstRequest
import co.fallsoft.vipi.core.LookupFirstOutcome
import co.fallsoft.vipi.core.ImmersionOrigin
import co.fallsoft.vipi.core.ImmersionStatus
import co.fallsoft.vipi.core.ImmersionPresentationState
import co.fallsoft.vipi.core.ImmersionPresentationRequest
import co.fallsoft.vipi.core.BoundedImmersionCache
import co.fallsoft.vipi.core.TranslationIntegrity
import com.google.mlkit.common.model.RemoteModelManager
import com.google.mlkit.nl.translate.TranslateRemoteModel
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.isActive
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
    private val catalogBytes by lazy { context.assets.open("immersion/catalog.json").use { it.readBytes() } }
    private val catalogSha256 by lazy { MessageDigest.getInstance("SHA-256").digest(catalogBytes).joinToString("") { "%02x".format(it) } }
    private val index by lazy {
        JSONObject(catalogBytes.toString(Charsets.UTF_8)).also {
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
        return ReferenceComposition.compose(original, LocalImmersion.sentences(original, source), target, values::get)
    }
    fun partial(original: String, source: String, target: String, density: Double,
                readings: SentenceReadings): PartialImmersionResult? {
        val values = references["$source-$target"] ?: return null
        val nativeSourceWords = LocalImmersion.words(original, source)
        val units = LocalImmersion.sentences(original, source).mapNotNull { range ->
            val text = original.substring(range)
            if (nativeSourceWords.any { it.first <= range.last && it.last >= range.first &&
                    (it.first < range.first || it.last > range.last) }) return@mapNotNull null
            val translated = values[text] ?: return@mapNotNull null
            if (text.length > 128 || translated.length > 128) return@mapNotNull null
            val unitTokens = nativeSourceWords.count { it.first >= range.first && it.last <= range.last }
            if (unitTokens <= 0) return@mapNotNull null
            val id = MessageDigest.getInstance("SHA-256").digest((source + "\u0000" + target + "\u0000" + text + "\u0000" + translated).toByteArray())
                .joinToString("") { "%02x".format(it) }
            SourceReferenceUnit(range.first, range.last + 1, text, translated,
                readings.reading(translated, target), "catalog-reference-sha256:$id", catalogSha256,
                nativeSourceTokens = unitTokens)
        }
        return SourceReferencePresentation.create(original, target, units, density, nativeSourceWords.size)
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
    private val lexical = BundledLexicalCatalog(context.applicationContext)
    private val readings = SentenceReadings(context.applicationContext)
    private val mutex = Mutex()
    private val cache = BoundedImmersionCache<LookupFirstOutcome>(128)
    private val inputLanguages = mutableStateMapOf<String, String>()
    private var closed = false
    private var generation = 0L
    internal var lastOutcome: LookupFirstOutcome? = null
        private set
    internal var lexicalPreparation: String = "unmeasured"
        private set
    var ready by mutableStateOf<Boolean?>(null)
        private set
    fun inputLanguage(id: String): String? = inputLanguages[id]
    fun selectInputLanguage(id: String, language: String?) {
        if (closed || (language != null && language !in listOf(source, target))) return
        if (inputLanguages[id] != language) generation++
        if (language == null) inputLanguages.remove(id) else inputLanguages[id] = language
    }
    fun cachedPresentation(text: String, messageID: String? = null): ImmersionPresentation? =
        if (closed) null else cache["${messageID?.let { inputLanguages[it] } ?: "auto"}:$text"]?.result
    fun cached(text: String, messageID: String? = null): ImmersionResult? = cachedPresentation(text, messageID) as? ImmersionResult
    fun reading(text: String): String? = readings.reading(text, target)

    suspend fun checkDownloads() {
        try {
            // Status checking must not eagerly expand lexical databases before lookup.
            // Lexical preparation/failure is recorded independently at actual alignment.
            val manager = RemoteModelManager.getInstance()
            val installed = listOf(source, target).all { code ->
                code == "en" || manager.isModelDownloaded(TranslateRemoteModel.Builder(code).build()).await()
            }
            if (!closed) ready = installed
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { if (!closed) ready = false }
    }
    // Compatibility for existing complete-result consumers; the live UI uses presentation().
    suspend fun result(text: String, inputLanguage: String? = null): ImmersionResult? =
        presentation(text, inputLanguage) as? ImmersionResult

    suspend fun presentation(text: String, inputLanguage: String? = null, messageID: String? = null,
                             onPartial: (PartialImmersionResult) -> Unit = {}): ImmersionPresentation? = mutex.withLock {
        lastOutcome = null // cancellation/early rejection must not expose prior-invocation telemetry
        val revision = generation
        val requestContext = coroutineContext
        fun valid() = !closed && revision == generation && requestContext.isActive &&
            (messageID == null || inputLanguages[messageID] == inputLanguage)
        if (!valid()) return@withLock null
        val key = (inputLanguage ?: "auto") + ":" + text
        cache[key]?.takeIf { it.result?.translation != null }?.let {
            lastOutcome = it.cachedInvocation()
            return@withLock it.result
        }
        val outcome = LookupFirst.resolve(LookupFirstRequest(text, source, target, inputLanguage), ::valid,
            reference = { original, from, to -> withContext(Dispatchers.Default) { catalog.reference(original, from, to) } },
            identify = { language.identify(it) }, modelsReady = { ready == true },
            translate = { original, from, to -> translator.translate(original, from, to) },
            align = { original, targetText -> withContext(Dispatchers.IO) {
                val supplemental = try {
                    lexical.entries(original, targetText, source, target).also { lexicalPreparation = "ready" }
                } catch (cancelled: CancellationException) { throw cancelled }
                catch (_: Exception) { lexicalPreparation = "failed"; emptyList() }
                coroutineContext.ensureActive()
                catalog.result(original, targetText, source, target, density, supplementalEntries = supplemental)
            } },
            partialReference = { original, from, to -> withContext(Dispatchers.Default) {
                catalog.partial(original, from, to, density, readings)
            } },
            onPartial = { partial -> if (valid()) { cache[key] = LookupFirstOutcome(partial, ImmersionOrigin.SOURCE_REFERENCE_PARTIAL, ImmersionStatus.PARTIAL, 0)
                    onPartial(partial) } })
        lastOutcome = outcome
        if (!valid()) return@withLock null
        if (outcome.result != null) cache[key] = outcome
        outcome.result
    }
    override fun close() { generation++; closed = true; cache.clear(); inputLanguages.clear(); translator.close(); language.close() }
}

@Composable internal fun ConversationImmersionText(text: String, id: String, immersion: ConversationImmersion,
    speech: SpeechPlayback, paused: Boolean, onVoiceHelp: () -> Unit, metadata: @Composable () -> Unit) {
    val inputLanguage = immersion.inputLanguage(id)
    val request = remember(id, text, immersion, inputLanguage) {
        ImmersionPresentationRequest(id, text, immersion.source, immersion.target, inputLanguage, immersion)
    }
    val latestRequest by rememberUpdatedState(request)
    var state by remember(request) {
        mutableStateOf(ImmersionPresentationState(request, immersion.cachedPresentation(text, id)))
    }
    val currentlyPaused by rememberUpdatedState(paused)
    var mode by remember(request) { mutableStateOf(ReadingMode.IMMERSED) }
    LaunchedEffect(request, immersion.ready) {
        fun accept(value: ImmersionPresentation?) {
            if (latestRequest == request) state = state.accept(request, value, currentlyPaused)
        }
        val value = immersion.presentation(text, inputLanguage, id) { accept(it) }
        accept(value)
    }
    LaunchedEffect(paused, request) {
        if (!paused && latestRequest == request) state = state.resume(request)
    }
    // Re-keying immediately clears stale visible/waiting values and full-target actions.
    val current = state.takeIf { it.request == request }?.visible
    if (current == null) Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
        SelectionContainer { Text(text) }
        UntranslatedMessageActions(text, immersion.source, immersion.target, inputLanguage, onLanguage = { immersion.selectInputLanguage(id, it) }, metadata = metadata)
    }
    else ImmersionBubble(current, mode, speech, immersion.source, immersion.target, id, paused,
        fullReading = remember(current, immersion) { current.translation?.let { immersion.reading(it) } },
        embedded = true, onModeChange = { mode = it }, metadata = metadata, onVoiceHelp = onVoiceHelp,
        originalMessage = text, inputLanguage = inputLanguage, onInputLanguage = { immersion.selectInputLanguage(id, it) })
}
