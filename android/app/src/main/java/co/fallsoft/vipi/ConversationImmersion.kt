package co.fallsoft.vipi

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.ui.unit.dp
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import co.fallsoft.vipi.core.ImmersionResult
import co.fallsoft.vipi.core.ImmersionPresentation
import co.fallsoft.vipi.core.PartialImmersionResult
import co.fallsoft.vipi.core.SourceReferenceUnit
import co.fallsoft.vipi.core.SourceReferencePresentation
import co.fallsoft.vipi.core.SourceLookupEvidence
import co.fallsoft.vipi.core.ReferenceComposition
import co.fallsoft.vipi.core.LookupFirst
import co.fallsoft.vipi.core.LookupFirstRequest
import co.fallsoft.vipi.core.LookupFirstOutcome
import co.fallsoft.vipi.core.ImmersionIntent
import co.fallsoft.vipi.core.ImmersionTranslationTimeout
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
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.TimeoutCancellationException
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
        supplementalEntries: List<co.fallsoft.vipi.core.VocabularyEntry> = emptyList(),
        sourceEvidence: SourceLookupEvidence? = null): ImmersionResult {
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
        return LocalImmersion.align(original, translated, entries, density, source, target, supplementalEntries, sourceEvidence)
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

/** An explicitly injected qualification policy. Release builds cannot enable it. */
internal interface SourceUnitQaPolicy {
    val cacheIdentity: String
    fun partial(original: String, source: String, target: String, density: Double): PartialImmersionResult?
}
/** Optional trusted source catalog seam; no provider is installed by default.
 * Identity includes the catalog/policy and immutable known-concept snapshot.
 * Replace the conversation engine when that identity changes.
 */
internal interface SourceLookupProvider {
    val cacheIdentity: String
    suspend fun lookup(original: String, source: String, target: String, density: Double): SourceLookupEvidence
}
internal data class ImmersionInvocationCounters(val readiness: Int = 0, val heavyAlignment: Int = 0,
    val partialPresentation: Int = 0, val qaSourceLookup: Int = 0, val sourceRecognition: Int = 0)

/** Per conversation, keyed request work and bounded memory. ChatItem is immutable. */
internal class ConversationImmersion(context: Context, val source: String, val target: String, private val density: Double,
    private val translator: LanguageTranslation = LocalTranslation(),
    private val qaSourceUnits: SourceUnitQaPolicy? = null,
    qaReadingProducer: (suspend (String, String) -> FullReading?)? = null,
    private val qaModelsReady: Boolean? = null,
    sourceKnownConceptIDs: Set<String> = emptySet(),
    private val sourceLookup: SourceLookupProvider? = JapaneseStarterLookup.bundledIfPromoted(context, sourceKnownConceptIDs)) : AutoCloseable {
    private val sourceLookupIdentity = sourceLookup?.cacheIdentity
    init {
        require(qaSourceUnits == null || BuildConfig.DEBUG)
        require(qaReadingProducer == null || BuildConfig.DEBUG)
        require(qaModelsReady == null || BuildConfig.DEBUG)
        require(qaSourceUnits == null || qaSourceUnits.cacheIdentity.matches(Regex("[A-Za-z0-9._:-]{1,160}")))
        require(sourceLookupIdentity == null || sourceLookupIdentity.matches(Regex("[A-Za-z0-9._:-]{1,160}")))
    }
    private fun sourceLookupIsCurrent() = sourceLookup?.cacheIdentity == sourceLookupIdentity
    private fun cacheKey(text: String, inputLanguage: String?) =
        (sourceLookupIdentity ?: "no-source-provider") + ":" +
            (qaSourceUnits?.cacheIdentity ?: "accepted") + ":" + (inputLanguage ?: "auto") + ":" + text
    private val language = MessageLanguage()
    private val catalog = BundledImmersionCatalog(context.applicationContext)
    private val lexical = BundledLexicalCatalog(context.applicationContext)
    private val applicationContext = context.applicationContext
    private val readings by lazy { SentenceReadings(applicationContext) }
    private val fullReadings = FullReadingCache(NativeFullReadings.POLICY, producer = qaReadingProducer ?: { text, language ->
        NativeFullReadings.resolve(text, language, readings, applicationContext)
    })
    // Waiting for inference must not stall a different row's local source lookup.
    private val stateLock = Any()
    private val catalogMutex = Mutex()
    private val providerMutex = Mutex()
    private data class RequestKey(val generation: Long, val inputLanguage: String?, val text: String)
    private class RequestGate(val mutex: Mutex = Mutex(), var users: Int = 0)
    private val requestGates = mutableMapOf<RequestKey, RequestGate>()
    private suspend fun <T> withRequestGate(key: RequestKey, block: suspend (Long) -> T): T {
        val gate = synchronized(stateLock) { requestGates.getOrPut(key) { RequestGate() }.also { it.users++ } }
        try { return gate.mutex.withLock { block(key.generation) } }
        finally { synchronized(stateLock) { if (--gate.users == 0) requestGates.remove(key) } }
    }
    private data class CachedOutcome(val outcome: LookupFirstOutcome, val generation: Long, val modelRevision: Long)
    private fun LookupFirstOutcome.deterministicRejection() = result == null && status == ImmersionStatus.INVALID_RESULT &&
        origin == ImmersionOrigin.LOCAL_FULL_CONTEXT && localTranslationCalls > 0
    private fun reusable(value: LookupFirstOutcome, intent: ImmersionIntent) =
        if (value.result != null) intent == ImmersionIntent.AUTOMATIC_IMMERSION || value.result?.translation != null
        else intent == ImmersionIntent.AUTOMATIC_IMMERSION && value.deterministicRejection()
    private fun cachedOutcome(key: String) = synchronized(stateLock) {
        cache[key]?.takeUnless { it.outcome.deterministicRejection() &&
            (it.generation != generation || it.modelRevision != modelRevision) }?.outcome
    }
    private fun cacheOutcome(key: String, value: LookupFirstOutcome, requestGeneration: Long? = null,
        readinessRevision: Long? = null) = synchronized(stateLock) {
        if (!value.deterministicRejection() || cache[key]?.outcome?.result == null)
            cache[key] = CachedOutcome(value, requestGeneration ?: generation, readinessRevision ?: modelRevision)
    }
    private val cache = BoundedImmersionCache<CachedOutcome>(128)
    private val inputLanguages = mutableStateMapOf<String, String>()
    @Volatile private var closed = false
    @Volatile private var generation = 0L
    private var modelRevision = 0L
    private data class FullAttempt(val generation: Long, val messageID: String?, val inputLanguage: String?,
                                   val text: String, val epoch: Long)
    private val fullAttempts = linkedMapOf<FullAttempt, LookupFirstOutcome>()
    private val fullEpoch = java.util.concurrent.atomic.AtomicLong()
    fun newFullTranslationEpoch(): Long = fullEpoch.incrementAndGet().also { check(it > 0) }
    private fun rememberAttempt(key: FullAttempt?, outcome: LookupFirstOutcome) {
        synchronized(stateLock) {
            if (key == null || closed || key.generation != generation) return
            fullAttempts[key] = outcome
            while (fullAttempts.size > 32) fullAttempts.remove(fullAttempts.keys.first())
        }
    }
    internal var lastOutcome: LookupFirstOutcome? = null
        private set
    internal var lastInvocation = ImmersionInvocationCounters()
        private set
    internal var lexicalPreparation: String = "unmeasured"
        private set
    var ready by mutableStateOf<Boolean?>(null)
        private set
    private fun updateReadiness(value: Boolean) = synchronized(stateLock) {
        if (!closed && ready != value) { modelRevision++; ready = value }
    }
    fun inputLanguage(id: String): String? = inputLanguages[id]
    fun selectInputLanguage(id: String, language: String?) {
        if (closed || (language != null && language !in listOf(source, target))) return
        if (inputLanguages[id] != language) synchronized(stateLock) { generation++; fullAttempts.clear() }
        if (language == null) inputLanguages.remove(id) else inputLanguages[id] = language
    }
    fun cachedPresentation(text: String, messageID: String? = null): ImmersionPresentation? =
        if (closed || !sourceLookupIsCurrent()) null else cachedOutcome(cacheKey(text, messageID?.let { inputLanguages[it] }))?.result
    fun cached(text: String, messageID: String? = null): ImmersionResult? = cachedPresentation(text, messageID) as? ImmersionResult
    fun cachedReading(text: String): FullReading? = fullReadings.cached(text, target)
    suspend fun reading(text: String): FullReading? = fullReadings.resolve(text, target)

    suspend fun checkDownloads() {
        qaModelsReady?.let { updateReadiness(it); return }
        try {
            // Status checking must not eagerly expand lexical databases before lookup.
            // Lexical preparation/failure is recorded independently at actual alignment.
            val manager = RemoteModelManager.getInstance()
            val installed = listOf(source, target).all { code ->
                code == "en" || manager.isModelDownloaded(TranslateRemoteModel.Builder(code).build()).await()
            }
            updateReadiness(installed)
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { updateReadiness(false) }
    }
    // Compatibility for existing complete-result consumers; the live UI uses presentation().
    suspend fun result(text: String, inputLanguage: String? = null): ImmersionResult? =
        presentation(text, inputLanguage) as? ImmersionResult

    suspend fun presentation(text: String, inputLanguage: String? = null, messageID: String? = null,
                             onPartial: (PartialImmersionResult) -> Unit = {}): ImmersionPresentation? =
        resolve(text, inputLanguage, messageID, ImmersionIntent.AUTOMATIC_IMMERSION, null, onPartial).result

    /** One explicit attempt; simultaneous callers with the same epoch share its outcome, including failure. */
    suspend fun fullTranslation(text: String, inputLanguage: String?, messageID: String?,
                                requestEpoch: Long): LookupFirstOutcome {
        require(requestEpoch > 0)
        return resolve(text, inputLanguage, messageID, ImmersionIntent.FULL_TRANSLATION, requestEpoch) {}
    }

    private suspend fun resolve(text: String, inputLanguage: String?, messageID: String?, intent: ImmersionIntent,
                                requestEpoch: Long?, onPartial: (PartialImmersionResult) -> Unit): LookupFirstOutcome {
        val submittedRevision = generation
        // A row re-entering the viewport can use its already approved partial
        // even while the same message's explicit reference request is pending.
        val cached = synchronized(stateLock) {
            if (!closed && (messageID == null || inputLanguages[messageID] == inputLanguage))
                cachedOutcome(cacheKey(text, inputLanguage)) else null
        }
        if (coroutineContext.isActive && sourceLookupIsCurrent() && submittedRevision == generation && cached != null && reusable(cached, intent))
            return cached.cachedInvocation().also { lastOutcome = it; lastInvocation = ImmersionInvocationCounters() }
        return withRequestGate(RequestKey(submittedRevision, inputLanguage, text)) { revision ->
        lastOutcome = null
        var readinessCalls = 0; var alignmentCalls = 0; var partialCalls = 0; var qaCalls = 0; var recognitionCalls = 0
        val readinessRevision = synchronized(stateLock) { modelRevision }
        val requestContext = coroutineContext
        fun valid() = !closed && sourceLookupIsCurrent() && revision == generation && requestContext.isActive &&
            (messageID == null || inputLanguages[messageID] == inputLanguage)
        fun finish(value: LookupFirstOutcome): LookupFirstOutcome {
            lastOutcome = value
            lastInvocation = ImmersionInvocationCounters(readinessCalls, alignmentCalls, partialCalls, qaCalls, recognitionCalls)
            return value
        }
        fun stale() = LookupFirstOutcome(null, null, ImmersionStatus.STALE, 0)
        if (!valid()) return@withRequestGate finish(stale())
        val key = cacheKey(text, inputLanguage)
        cachedOutcome(key)?.takeIf { reusable(it, intent) }?.let {
            return@withRequestGate finish(it.cachedInvocation())
        }
        val attempt = requestEpoch?.let { FullAttempt(revision, messageID, inputLanguage, text, it) }
        attempt?.let { synchronized(stateLock) { fullAttempts[it] } }?.let { return@withRequestGate finish(it.cachedInvocation()) }
        val outcome = try {
            LookupFirst.resolve(LookupFirstRequest(text, source, target, inputLanguage, intent), ::valid,
                reference = { original, from, to -> catalogMutex.withLock { withContext(Dispatchers.Default) { catalog.reference(original, from, to) } } },
                identify = { language.identify(it) }, modelsReady = { readinessCalls++; ready == true },
                translate = { original, from, to ->
                    if (intent == ImmersionIntent.FULL_TRANSLATION) {
                        try { withTimeout(30_000) { providerMutex.withLock { translator.translate(original, from, to) } } }
                        catch (_: TimeoutCancellationException) { requestContext.ensureActive(); throw ImmersionTranslationTimeout() }
                    } else providerMutex.withLock { translator.translate(original, from, to) }
                },
                align = { original, targetText, evidence -> catalogMutex.withLock { withContext(Dispatchers.IO) {
                    alignmentCalls++
                    val supplemental = try {
                        lexical.entries(original, targetText, source, target).also { lexicalPreparation = "ready" }
                    } catch (cancelled: CancellationException) { throw cancelled }
                    catch (_: Exception) { lexicalPreparation = "failed"; emptyList() }
                    coroutineContext.ensureActive()
                    catalog.result(original, targetText, source, target, density, supplementalEntries = supplemental, sourceEvidence = evidence)
                } } },
                partialReference = { original, from, to -> catalogMutex.withLock { withContext(Dispatchers.Default) {
                    partialCalls++
                    catalog.partial(original, from, to, density, readings) ?: qaSourceUnits?.let {
                        qaCalls++; it.partial(original, from, to, density)
                    }
                } } },
                sourceEvidenceIdentity = sourceLookupIdentity,
                sourceEvidence = sourceLookup?.let { provider -> { original, from, to ->
                    recognitionCalls++
                    withContext(Dispatchers.Default) { provider.lookup(original, from, to, density) }
                } },
                onPartial = { partial -> if (valid()) {
                    cacheOutcome(key, LookupFirstOutcome(partial, ImmersionOrigin.SOURCE_REFERENCE_PARTIAL, ImmersionStatus.PARTIAL, 0))
                    onPartial(partial)
                } })
        } catch (cancelled: CancellationException) {
            // A queued duplicate of this canceled attempt must not start another
            // inference. A deliberate retry receives a new row-owned epoch.
            rememberAttempt(attempt, stale())
            throw cancelled
        }
        if (!valid()) return@withRequestGate finish(stale())
        // Deterministic rejected translations may be reused only automatically.
        // Explicit full requests bypass them; transient errors/cancellation do not enter this cache.
        if (outcome.result != null || outcome.deterministicRejection()) cacheOutcome(key, outcome, revision, readinessRevision)
        rememberAttempt(attempt, outcome)
        finish(outcome)
        }
    }
    override fun close() {
        synchronized(stateLock) { generation++; closed = true; cache.clear(); fullAttempts.clear() }
        fullReadings.close(); inputLanguages.clear(); translator.close(); language.close()
    }
}

private data class OriginalOnlyPresentation(override val original: String) : ImmersionPresentation {
    override val translation: String? = null
    override val spans = emptyList<co.fallsoft.vipi.core.ImmersionSpan>()
}

@Composable internal fun ConversationImmersionText(text: String, id: String, immersion: ConversationImmersion,
    speech: SpeechPlayback, paused: Boolean, onVoiceHelp: () -> Unit, onReport: (() -> Unit)? = null,
    onTranslationSetup: (() -> Unit)? = null, contextualActions: Boolean = false, metadata: @Composable () -> Unit) {
    val inputLanguage = immersion.inputLanguage(id)
    val request = remember(id, text, immersion, inputLanguage) {
        ImmersionPresentationRequest(id, text, immersion.source, immersion.target, inputLanguage, immersion)
    }
    val latestRequest by rememberUpdatedState(request)
    var state by remember(request) {
        mutableStateOf(ImmersionPresentationState(request, immersion.cachedPresentation(text, id)))
    }
    var interacting by remember(request) { mutableStateOf(false) }
    val currentlyPaused by rememberUpdatedState(paused || interacting)
    var mode by remember(request) { mutableStateOf(ReadingMode.IMMERSED) }
    var fullLoading by remember(request) { mutableStateOf(false) }
    var modeBeforeFullRequest by remember(request) { mutableStateOf(ReadingMode.IMMERSED) }
    var fullError by remember(request) { mutableStateOf<ImmersionStatus?>(null) }
    var fullEpoch by remember(request) { mutableLongStateOf(0) }
    var fullJob by remember(request) { mutableStateOf<Job?>(null) }
    val scope = rememberCoroutineScope()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    fun cancelFull(restoreMode: Boolean = false) {
        fullEpoch = immersion.newFullTranslationEpoch()
        fullJob?.cancel(); fullJob = null; fullLoading = false; fullError = null
        if (restoreMode) mode = modeBeforeFullRequest
    }
    fun requestFull() {
        if (fullLoading) return
        val epoch = immersion.newFullTranslationEpoch(); fullEpoch = epoch
        modeBeforeFullRequest = mode; fullLoading = true; fullError = null
        fullJob = scope.launch {
            try {
                val outcome = immersion.fullTranslation(text, inputLanguage, id, epoch)
                coroutineContext.ensureActive()
                if (latestRequest == request && fullEpoch == epoch) {
                    outcome.result?.let { state = state.accept(request, it, currentlyPaused) }
                    if (outcome.result?.translation != null) { fullError = null; mode = ReadingMode.TRANSLATION }
                    else fullError = outcome.fallbackStatus ?: outcome.status
                }
            } catch (cancelled: CancellationException) { throw cancelled }
            finally { if (latestRequest == request && fullEpoch == epoch) { fullLoading = false; fullJob = null } }
        }
    }
    DisposableEffect(request, lifecycle) {
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_STOP) cancelFull() }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer); fullJob?.cancel() }
    }
    LaunchedEffect(request, immersion.ready) {
        fun accept(value: ImmersionPresentation?) {
            if (latestRequest == request) state = state.accept(request, value, currentlyPaused)
        }
        val value = immersion.presentation(text, inputLanguage, id) { accept(it) }
        accept(value)
    }
    LaunchedEffect(paused, interacting, request) {
        if (!paused && !interacting && latestRequest == request) state = state.resume(request)
    }
    val current = state.takeIf { it.request == request }?.visible
    val reference = current?.translation
    var fullReading by remember(request, reference) { mutableStateOf(reference?.let(immersion::cachedReading)) }
    LaunchedEffect(request, reference) {
        if (reference != null) {
            val value = immersion.reading(reference)
            coroutineContext.ensureActive()
            if (latestRequest == request) fullReading = value
        }
    }
    ImmersionBubble(current ?: remember(text) { OriginalOnlyPresentation(text) }, mode, speech, immersion.source, immersion.target, id, paused,
        fullReading = fullReading?.text,
        embedded = true, onModeChange = { value -> cancelFull(); mode = value }, metadata = metadata, onVoiceHelp = onVoiceHelp,
        originalMessage = text, inputLanguage = inputLanguage, onInputLanguage = { cancelFull(); immersion.selectInputLanguage(id, it) },
        onInteractionChange = { interacting = it }, onReport = onReport,
        onFullTranslation = ::requestFull, fullTranslationLoading = fullLoading, fullTranslationError = fullError,
        onCancelFullTranslation = { cancelFull(restoreMode = true) }, onTranslationSetup = onTranslationSetup,
        contextualActions = contextualActions)
}
