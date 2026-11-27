package co.fallsoft.vipi

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.google.mlkit.nl.languageid.LanguageIdentification
import com.google.mlkit.nl.languageid.LanguageIdentificationOptions
import com.google.mlkit.nl.translate.TranslateLanguage
import java.security.MessageDigest
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.async
import kotlinx.coroutines.cancel
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.coroutines.yield
import org.json.JSONObject

/**
 * Immutable mixed-message snapshot. Raw original is never rewritten by the display or persisted in
 * place of the authenticated message. Word snapshots record only complete native equivalents at
 * exact source ranges.
 */
enum class ImmersionMode {
    NEW_WORD,
    FULL_MESSAGES,
}

internal data class FullMessageTranslation(
    val original: String,
    val practiceText: String,
    val meaningText: String,
    val inputLanguage: String,
    val practiceLanguage: String,
    val meaningLanguage: String,
    val practiceReading: String? = null,
    val readingPolicy: String? = null,
    val readingStatus: FullMessageReadingStatus? = null,
    val readingFailure: FullMessageReadingFailure? = null,
    val words: List<WordReplacement>? = null,
    val mode: ImmersionMode = ImmersionMode.NEW_WORD,
) {
    fun json() =
        JSONObject()
            .put("original", original)
            .put("practice", practiceText)
            .put("meaning", meaningText)
            .put("input_language", inputLanguage)
            .put("practice_language", practiceLanguage)
            .put("meaning_language", meaningLanguage)
            .put("reading", practiceReading ?: JSONObject.NULL)
            .put("reading_policy", readingPolicy ?: JSONObject.NULL)
            .put(
                "words",
                words?.let { list ->
                    org.json.JSONArray().apply { list.forEach { put(it.json()) } }
                } ?: JSONObject.NULL,
            )
            .put("reading_status", readingStatus?.name ?: JSONObject.NULL)
            .put("reading_failure", readingFailure?.name ?: JSONObject.NULL)
            .put("mode", mode.name)
            .put("policy", if (mode == ImmersionMode.FULL_MESSAGES) FULL_POLICY else POLICY)

    companion object {
        const val POLICY = "incremental-word-growth-1"
        const val FULL_POLICY = "full-message-original-hold-1"

        fun parse(value: JSONObject): FullMessageTranslation {
            val mode = ImmersionMode.valueOf(value.optString("mode", ImmersionMode.NEW_WORD.name))
            require(
                value.getString("policy") ==
                    if (mode == ImmersionMode.FULL_MESSAGES) FULL_POLICY else POLICY
            )
            val guide = value.opt("reading") as? String
            val failure =
                FullMessageReadingFailure.entries.firstOrNull {
                    it.name == value.optString("reading_failure")
                }
            val status =
                FullMessageReadingStatus.entries
                    .firstOrNull { it.name == value.optString("reading_status") }
                    ?.takeIf {
                        when (it) {
                            FullMessageReadingStatus.NOT_NEEDED -> guide == null && failure == null
                            FullMessageReadingStatus.AVAILABLE ->
                                !guide.isNullOrBlank() &&
                                    guide != value.getString("practice") &&
                                    failure == null
                            FullMessageReadingStatus.UNAVAILABLE -> guide == null && failure != null
                        }
                    }
            // Unknown/invalid reading metadata needs a reading-only migration;
            // it must not invalidate an otherwise complete model translation.
            return FullMessageTranslation(
                    value.getString("original"),
                    value.getString("practice"),
                    value.getString("meaning"),
                    value.getString("input_language"),
                    value.getString("practice_language"),
                    value.getString("meaning_language"),
                    guide,
                    value.opt("reading_policy") as? String,
                    status,
                    failure.takeIf { status != null },
                    (value.opt("words") as? org.json.JSONArray)?.let { WordReplacement.parse(it) },
                    mode,
                )
                .also {
                    require(it.practiceText.isNotBlank() && it.meaningText == it.original)
                    require(it.mode != ImmersionMode.FULL_MESSAGES || it.words == null)
                    if (it.words != null)
                        require(
                            WordReplacement.compose(it.original, it.words, reading = false) ==
                                it.practiceText
                        )
                    else
                        require(
                            it.mode == ImmersionMode.FULL_MESSAGES ||
                                (it.inputLanguage == it.practiceLanguage &&
                                    it.practiceText == it.original)
                        )
                }
        }

        fun key(
            id: String,
            original: String,
            source: String,
            target: String,
            mode: ImmersionMode = ImmersionMode.NEW_WORD,
        ): String =
            MessageDigest.getInstance("SHA-256")
                .digest(
                    listOf(
                            if (mode == ImmersionMode.FULL_MESSAGES) FULL_POLICY else POLICY,
                            id,
                            original,
                            source,
                            target,
                        )
                        .joinToString("\u0000")
                        .toByteArray(Charsets.UTF_8)
                )
                .joinToString("") { "%02x".format(it) }
    }
}

/**
 * Derived text uses the same encrypted, account-owned store as its message. No source text or model
 * output is placed in preferences/public caches.
 */
internal class FullMessageTranslationStore(private val vault: MessageVault) {
    fun vocabulary() = IntroducedWords(vault)

    /**
     * History backups carry originals, not vocabulary/index keys. Imported history can reuse words
     * already learned here but never manufacture new progress. A collision/corrupt import must fail
     * before model selection.
     */
    fun mayIntroduce(id: String, text: String): Boolean {
        val uuid = runCatching { java.util.UUID.fromString(id) }.getOrNull() ?: return true
        require(uuid.toString() == id)
        return vault.transaction {
            val bytes = vault.get("imported", id) ?: return@transaction true
            val row = JSONObject(bytes.toString(Charsets.UTF_8))
            require(row.getString("id") == id && row.getString("text") == text) {
                "Imported history identity conflicts with message"
            }
            false
        }
    }

    fun plan(key: String): WordMessagePlan? = vault.transaction {
        vault.get("word-message-plan", key)?.let {
            WordMessagePlan.parse(JSONObject(it.toString(Charsets.UTF_8)))
        }
    }

    fun commit(
        key: String,
        planKey: String,
        value: FullMessageTranslation,
        marker: WordMessagePlan,
        addition: IntroducedWord?,
        words: IntroducedWords,
    ) = vault.transaction {
        check(vault.get("word-message-plan", planKey) == null) {
            "Immutable progression plan already committed"
        }
        if (addition != null) words.commit(addition)
        vault.put(
            "word-message-plan",
            planKey,
            marker.json().toString().toByteArray(Charsets.UTF_8),
        )
        vault.put("incremental-message", key, value.json().toString().toByteArray(Charsets.UTF_8))
    }

    fun read(key: String, mode: ImmersionMode = ImmersionMode.NEW_WORD): FullMessageTranslation? =
        vault.transaction {
            vault
                .get(
                    if (mode == ImmersionMode.FULL_MESSAGES) "full-message-review"
                    else "incremental-message",
                    key,
                )
                ?.let { FullMessageTranslation.parse(JSONObject(it.toString(Charsets.UTF_8))) }
        }

    fun write(key: String, value: FullMessageTranslation) = vault.transaction {
        vault.put(
            if (value.mode == ImmersionMode.FULL_MESSAGES) "full-message-review"
            else "incremental-message",
            key,
            value.json().toString().toByteArray(Charsets.UTF_8),
        )
    }
}

internal enum class MessageTranslationPhase {
    PREPARING,
    TRANSLATING,
    READY,
    FAILED,
}

internal data class MessageTranslationState(
    val phase: MessageTranslationPhase,
    val value: FullMessageTranslation? = null,
    val failure: String? = null,
)

/**
 * Identity/direction are advisory; every message reaches the translator even when language
 * identification is uncertain, short, or unsupported.
 */
internal interface MessageTranslationLanguage : AutoCloseable {
    suspend fun identify(text: String): String?
}

private class NativeMessageTranslationLanguage : MessageTranslationLanguage {
    private val client =
        LanguageIdentification.getClient(
            LanguageIdentificationOptions.Builder().setConfidenceThreshold(.8f).build()
        )

    override suspend fun identify(text: String): String? {
        val code = client.identifyLanguage(text).await()
        return translationCode(code)
    }

    override fun close() = client.close()
}

/**
 * Session-owned single-flight local translation; view disappearance does not duplicate work.
 * Closing/replacing the account or pair cancels pending work. One successful new source word is
 * committed with its immutable message plan; previously introduced words reuse encrypted native
 * equivalents.
 */
internal class ConversationTranslation(
    context: Context,
    val source: String,
    val target: String,
    private val store: FullMessageTranslationStore? = null,
    private val translator: LanguageTranslation = LocalTranslation(),
    private val language: MessageTranslationLanguage = NativeMessageTranslationLanguage(),
    private val reading: suspend (String, String) -> FullMessageReading = { text, code ->
        FullMessageReadings.read(context.applicationContext, text, code)
    },
    private val cacheByteLimit: Long = 8L * 1024 * 1024,
    val mode: ImmersionMode = ImmersionMode.NEW_WORD,
) : AutoCloseable {
    private val lock = Any()
    private val readingPolicy = FullMessageReadings.policy(target)
    private val vocabulary = store?.vocabulary() ?: IntroducedWords(null)
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val preparation = Mutex()
    private val modelExecution = Mutex()
    private val durablePending = linkedMapOf<String, () -> String?>()
    private var durableJob: Job? = null
    private var durableGeneration = 0L
    private var durableInFlight: String? = null
    internal val durableActive: Boolean
        get() =
            synchronized(lock) { durableJob?.let { !it.isCompleted && !it.isCancelled } == true }

    internal val pendingDurableCount: Int
        get() = synchronized(lock) { durablePending.size }

    internal val activeTaskCount: Int
        get() = synchronized(lock) { tasks.size }

    private val prepared = mutableSetOf<Set<String>>()
    private val tasks = mutableMapOf<String, Deferred<FullMessageTranslation>>()
    private val completed = linkedMapOf<String, FullMessageTranslation>()
    private var completedBytes = 0L

    private fun retainedBytes(value: FullMessageTranslation): Long =
        256L +
            2L *
                (value.original.length.toLong() +
                    value.practiceText.length +
                    value.meaningText.length +
                    (value.practiceReading?.length ?: 0) +
                    (value.readingPolicy?.length ?: 0) +
                    (value.readingStatus?.name?.length ?: 0) +
                    (value.readingFailure?.name?.length ?: 0) +
                    value.inputLanguage.length +
                    value.practiceLanguage.length +
                    value.meaningLanguage.length) +
            (value.words?.sumOf {
                96L + 2L * (it.source.length + it.target.length + (it.reading?.length ?: 0))
            } ?: 0L)

    val cachedBytes: Long
        get() = synchronized(lock) { completedBytes }

    val states = mutableStateMapOf<String, MessageTranslationState>()
    private var closed = false
    private val stateOrder = linkedSetOf<String>()
    private val visible = mutableMapOf<String, Int>()
    private val foreground = mutableMapOf<String, Int>()
    private var replayJob: Job? = null
    private var replayRevision = 0L
    private var replayGeneration = 0L
    private var replaySource: (() -> Sequence<SavedMessage>)? = null

    data class SavedMessage(val id: String, val text: String)

    val replayActive: Boolean
        get() = synchronized(lock) { replayJob?.let { !it.isCompleted && !it.isCancelled } == true }

    var replayFailure by mutableStateOf<String?>(null)
        private set

    private fun observed(key: String) = (visible[key] ?: 0) > 0 || (foreground[key] ?: 0) > 0

    private fun trimStates() {
        // READY values outside the128-entry cache survive only while actually
        // observed. Failure metadata stays bounded separately and contains no
        // translated paragraph; a visible failed row keeps its retry state.
        for (key in
            stateOrder.filter {
                !observed(it) && it !in tasks && it !in completed && states[it]?.value != null
            }) {
            states.remove(key)
            stateOrder.remove(key)
        }
        val failures = stateOrder.filter {
            !observed(it) && it !in tasks && states[it]?.phase == MessageTranslationPhase.FAILED
        }
        for (key in failures.take((failures.size - 128).coerceAtLeast(0))) {
            states.remove(key)
            stateOrder.remove(key)
        }
    }

    private fun recordState(key: String, state: MessageTranslationState) {
        states[key] = state
        stateOrder.remove(key)
        stateOrder.add(key)
    }

    private fun publish(key: String, state: MessageTranslationState) =
        synchronized(lock) {
            if (!closed && (observed(key) || states.containsKey(key))) recordState(key, state)
        }

    fun retain(id: String, text: String) =
        synchronized(lock) {
            val key = key(id, text)
            if (closed) return@synchronized
            visible[key] = (visible[key] ?: 0) + 1
            completed[key]?.let {
                recordState(key, MessageTranslationState(MessageTranslationPhase.READY, it))
            }
        }

    fun release(id: String, text: String) =
        synchronized(lock) {
            val key = key(id, text)
            if ((visible[key] ?: 0) <= 1) visible.remove(key)
            else visible[key] = visible.getValue(key) - 1
            trimStates()
        }

    /**
     * Disk-backed warming: one old record in flight, no eager per-history coroutine queue.
     * Visible/live requests preempt the next old record. A restarted scan replaces its iterator
     * after the current record finishes.
     */
    fun replaySaved(source: () -> Sequence<SavedMessage>) {
        val job =
            synchronized(lock) {
                if (closed) return
                replaySource = source
                replayRevision++
                replayFailure = null
                if (replayJob?.let { !it.isCompleted && !it.isCancelled } == true) return
                val generation = ++replayGeneration
                scope
                    .launch(start = CoroutineStart.LAZY) {
                        try {
                            while (true) {
                                val (revision, input) =
                                    synchronized(lock) {
                                        replayRevision to requireNotNull(replaySource)
                                    }
                                val iterator = input().iterator()
                                while (true) {
                                    currentCoroutineContext().ensureActive()
                                    if (synchronized(lock) { revision != replayRevision }) break
                                    if (!iterator.hasNext()) break
                                    val message = iterator.next()
                                    while (synchronized(lock) { foreground.isNotEmpty() }) delay(10)
                                    try {
                                        resolveObserved(
                                            message.id,
                                            message.text,
                                            retry = false,
                                            foregroundRequest = false,
                                        )
                                    } catch (cancelled: CancellationException) {
                                        throw cancelled
                                    } catch (_: Exception) {
                                        /* A visible request exposes its own failure/retry state. */
                                    }
                                    yield()
                                }
                                val finished =
                                    synchronized(lock) {
                                        if (revision == replayRevision) {
                                            replayJob = null
                                            true
                                        } else false
                                    }
                                if (finished) return@launch
                            }
                        } catch (cancelled: CancellationException) {
                            throw cancelled
                        } catch (failure: Exception) {
                            synchronized(lock) {
                                if (!closed) replayFailure = failure.javaClass.simpleName
                            }
                        } finally {
                            synchronized(lock) {
                                if (generation == replayGeneration) replayJob = null
                            }
                        }
                    }
                    .also { replayJob = it }
            }
        job.start()
    }

    var preparationFailed by mutableStateOf(false)
        private set

    init {
        require(cacheByteLimit > 0)
        require(
            source != target &&
                source in TranslateLanguage.getAllLanguages() &&
                target in TranslateLanguage.getAllLanguages()
        )
        preparePair()
    }

    fun key(id: String, text: String) = FullMessageTranslation.key(id, text, source, target, mode)

    fun state(id: String, text: String): MessageTranslationState? {
        val key = key(id, text)
        val state = states[key]
        if (state?.value != null) return state
        // A canceled/disposed observer does not cancel the account-owned model
        // task. Its genuine cached completion remains observable without adding
        // every replayed paragraph to Compose state.
        return synchronized(lock) {
            completed[key]?.let { MessageTranslationState(MessageTranslationPhase.READY, it) }
        } ?: state
    }

    fun preparePair() {
        scope.launch {
            try {
                modelExecution.withLock { prepare(source, target) }
                preparationFailed = false
            } catch (_: TimeoutCancellationException) {
                preparationFailed = true
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                preparationFailed = true
            }
        }
    }

    private suspend fun prepare(from: String, to: String) = preparation.withLock {
        val pair = setOf(from, to)
        if (pair !in prepared) {
            withTimeout(120_000) { translator.prepare(from, to, cellularAllowed = true) }
            currentCoroutineContext().ensureActive()
            synchronized(lock) {
                check(!closed)
                prepared += pair
            }
        }
    }

    /**
     * Catch-up retains opaque committed IDs and weak journal loaders, never one text-bearing
     * coroutine per inbox item. At most one durable record is loaded here; visible/manual requests
     * run before the next queued record.
     */
    fun enqueueStored(id: String, load: () -> String?) {
        val job =
            synchronized(lock) {
                if (closed || id == durableInFlight || id in durablePending) return
                durablePending[id] = load
                if (durableJob?.let { !it.isCompleted && !it.isCancelled } == true) return
                val generation = ++durableGeneration
                scope
                    .launch(start = CoroutineStart.LAZY) {
                        try {
                            while (true) {
                                currentCoroutineContext().ensureActive()
                                while (synchronized(lock) { foreground.isNotEmpty() }) delay(10)
                                val next =
                                    synchronized(lock) {
                                        durablePending.entries.firstOrNull()?.let { (id, loader) ->
                                            durablePending.remove(id)
                                            durableInFlight = id
                                            id to loader
                                        }
                                            ?: run {
                                                durableJob = null
                                                null
                                            }
                                    } ?: break
                                try {
                                    val text = withContext(Dispatchers.IO) { next.second() }
                                    if (text != null)
                                        resolveObserved(
                                            next.first,
                                            text,
                                            retry = false,
                                            foregroundRequest = false,
                                        )
                                } catch (cancelled: CancellationException) {
                                    throw cancelled
                                } catch (_: Exception) {
                                    /* Existing visible state exposes retry; no auto replay. */
                                } finally {
                                    synchronized(lock) {
                                        if (generation == durableGeneration) durableInFlight = null
                                    }
                                }
                                yield()
                            }
                        } finally {
                            synchronized(lock) {
                                if (generation == durableGeneration) {
                                    durableJob = null
                                    durableInFlight = null
                                }
                            }
                        }
                    }
                    .also { durableJob = it }
            }
        job.start()
    }

    fun enqueue(id: String, text: String, retry: Boolean = false) {
        scope.launch {
            try {
                resolve(id, text, retry)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                /* State records the visible failure. */
            }
        }
    }

    suspend fun resolve(id: String, text: String, retry: Boolean = false): FullMessageTranslation =
        resolveObserved(id, text, retry, foregroundRequest = true)

    private suspend fun resolveObserved(
        id: String,
        text: String,
        retry: Boolean,
        foregroundRequest: Boolean,
    ): FullMessageTranslation {
        val key = key(id, text)
        if (foregroundRequest) synchronized(lock) { foreground[key] = (foreground[key] ?: 0) + 1 }
        try {
            return resolveTask(id, text, retry)
        } finally {
            if (foregroundRequest)
                synchronized(lock) {
                    if ((foreground[key] ?: 0) <= 1) foreground.remove(key)
                    else foreground[key] = foreground.getValue(key) - 1
                    trimStates()
                }
        }
    }

    private suspend fun resolveTask(
        id: String,
        text: String,
        retry: Boolean,
    ): FullMessageTranslation {
        val key = key(id, text)
        val planKey = vocabulary.planKey(id, text, source, target)
        val task =
            synchronized(lock) {
                if (closed) throw CancellationException("Translation owner closed")
                val resident = completed[key] ?: states[key]?.value
                resident?.let {
                    if (!(retry && it.readingStatus == FullMessageReadingStatus.UNAVAILABLE)) {
                        if (observed(key))
                            recordState(
                                key,
                                MessageTranslationState(MessageTranslationPhase.READY, it),
                            )
                        return it
                    }
                }
                tasks[key]
                    ?: run {
                        if (!retry && states[key]?.phase == MessageTranslationPhase.FAILED)
                            throw IllegalStateException("Explicit retry required")
                        scope
                            .async(start = CoroutineStart.LAZY) {
                                try {
                                    if (resident == null)
                                        publish(
                                            key,
                                            MessageTranslationState(
                                                MessageTranslationPhase.PREPARING
                                            ),
                                        )
                                    // This is derived cache, never authenticated source.
                                    // A damaged/old entry is replaced by fresh model output;
                                    // retry must not loop forever on the same bad cache row.
                                    val translated =
                                        if (mode == ImmersionMode.FULL_MESSAGES) {
                                            val cached =
                                                resident
                                                    ?: try {
                                                        store?.let {
                                                            withContext(Dispatchers.IO) {
                                                                it.read(key, mode)
                                                            }
                                                        }
                                                    } catch (cancelled: CancellationException) {
                                                        throw cancelled
                                                    } catch (_: Exception) {
                                                        null
                                                    }
                                            cached?.also {
                                                require(
                                                    it.mode == mode &&
                                                        it.original == text &&
                                                        it.practiceLanguage == target &&
                                                        it.meaningLanguage == source
                                                )
                                            }
                                                ?: modelExecution.withLock {
                                                    withTimeout(60_000) { fullMessage(text, key) }
                                                }
                                        } else {
                                            val marker =
                                                store?.let {
                                                    withContext(Dispatchers.IO) { it.plan(planKey) }
                                                } ?: vocabulary.transientPlan(planKey)
                                            val markerWords = marker?.let {
                                                withContext(Dispatchers.IO) {
                                                    referencedWords(text, it)
                                                }
                                            }
                                            val cached =
                                                resident
                                                    ?: try {
                                                        store
                                                            ?.let {
                                                                withContext(Dispatchers.IO) {
                                                                    it.read(key)
                                                                }
                                                            }
                                                            ?.also { value ->
                                                                require(
                                                                    value.original == text &&
                                                                        value.practiceLanguage ==
                                                                            target &&
                                                                        value.meaningLanguage ==
                                                                            source
                                                                )
                                                                if (marker != null) {
                                                                    require(
                                                                        value.inputLanguage ==
                                                                            marker.input
                                                                    )
                                                                    require(
                                                                        value.words?.map {
                                                                            Triple(
                                                                                it.start,
                                                                                it.length,
                                                                                it.target,
                                                                            )
                                                                        } ==
                                                                            markerWords?.map {
                                                                                Triple(
                                                                                    it.start,
                                                                                    it.length,
                                                                                    it.target,
                                                                                )
                                                                            }
                                                                    )
                                                                }
                                                            }
                                                    } catch (cancelled: CancellationException) {
                                                        throw cancelled
                                                    } catch (failure: Exception) {
                                                        if (marker == null) throw failure else null
                                                    }
                                            currentCoroutineContext().ensureActive()
                                            if (cached != null && marker != null) cached
                                            else
                                                vocabulary.progression.withLock {
                                                    modelExecution.withLock {
                                                        currentCoroutineContext().ensureActive()
                                                        // A cache may disappear; the immutable
                                                        // progression
                                                        // snapshot is authoritative and never
                                                        // allocates twice.
                                                        val prior =
                                                            store?.plan(planKey)
                                                                ?: vocabulary.transientPlan(planKey)
                                                        if (prior != null)
                                                            restoreWordPlan(text, prior)
                                                        else {
                                                            check(cached == null) {
                                                                "Derived word cache has no authoritative plan"
                                                            }
                                                            val mayIntroduce =
                                                                store?.mayIntroduce(id, text)
                                                                    ?: true
                                                            val result =
                                                                withTimeout(60_000) {
                                                                    incrementalMessage(
                                                                        id,
                                                                        text,
                                                                        key,
                                                                        mayIntroduce,
                                                                    )
                                                                }
                                                            val snapshot =
                                                                markerFor(
                                                                    result.first,
                                                                    result.second,
                                                                )
                                                            currentCoroutineContext().ensureActive()
                                                            withContext(Dispatchers.IO) {
                                                                synchronized(lock) {
                                                                    if (closed)
                                                                        throw CancellationException(
                                                                            "Translation owner closed"
                                                                        )
                                                                    if (store != null)
                                                                        store.commit(
                                                                            key,
                                                                            planKey,
                                                                            result.first,
                                                                            snapshot,
                                                                            result.second,
                                                                            vocabulary,
                                                                        )
                                                                    else {
                                                                        result.second?.let(
                                                                            vocabulary::commit
                                                                        )
                                                                        vocabulary
                                                                            .commitTransientPlan(
                                                                                planKey,
                                                                                snapshot,
                                                                            )
                                                                    }
                                                                }
                                                            }
                                                            result.first
                                                        }
                                                    }
                                                }
                                        }
                                    // Old translation output remains valid when a reading
                                    // producer changes. Regenerate only this derived face,
                                    // never the authenticated source or model translation.
                                    val retryReading =
                                        retry &&
                                            translated.readingStatus ==
                                                FullMessageReadingStatus.UNAVAILABLE
                                    val value =
                                        if (
                                            translated.readingPolicy == readingPolicy &&
                                                translated.readingStatus != null &&
                                                !retryReading
                                        )
                                            translated
                                        else {
                                            if (translated.words != null)
                                                refreshWordReading(translated)
                                            else {
                                                val current = safeReading(translated.practiceText)
                                                translated.copy(
                                                    practiceReading = current.text,
                                                    readingPolicy = readingPolicy,
                                                    readingStatus = current.status,
                                                    readingFailure = current.failure,
                                                )
                                            }
                                        }
                                    currentCoroutineContext().ensureActive()
                                    withContext(Dispatchers.IO) {
                                        synchronized(lock) {
                                            if (closed)
                                                throw CancellationException(
                                                    "Translation owner closed"
                                                )
                                            if (resident == null || resident != value)
                                                store?.write(key, value)
                                            completed.remove(key)?.let {
                                                completedBytes -= retainedBytes(it)
                                            }
                                            completed[key] = value
                                            completedBytes += retainedBytes(value)
                                            while (
                                                completed.size > 128 ||
                                                    completedBytes > cacheByteLimit
                                            ) {
                                                completed.remove(completed.keys.first())?.let {
                                                    completedBytes -= retainedBytes(it)
                                                }
                                            }
                                            if (observed(key) || states.containsKey(key))
                                                recordState(
                                                    key,
                                                    MessageTranslationState(
                                                        MessageTranslationPhase.READY,
                                                        value,
                                                    ),
                                                )
                                            trimStates()
                                        }
                                    }
                                    value
                                } catch (timeout: TimeoutCancellationException) {
                                    val failure =
                                        java.io.IOException("Local translation timed out", timeout)
                                    publish(
                                        key,
                                        MessageTranslationState(
                                            MessageTranslationPhase.FAILED,
                                            failure = failure.javaClass.simpleName,
                                        ),
                                    )
                                    throw failure
                                } catch (error: Exception) {
                                    if (error !is CancellationException)
                                        synchronized(lock) {
                                            publish(
                                                key,
                                                MessageTranslationState(
                                                    MessageTranslationPhase.FAILED,
                                                    failure = error.javaClass.simpleName,
                                                ),
                                            )
                                        }
                                    throw error
                                } finally {
                                    synchronized(lock) {
                                        tasks.remove(key)
                                        trimStates()
                                    }
                                }
                            }
                            .also { tasks[key] = it }
                    }
            }
        task.start()
        return task.await()
    }

    private suspend fun safeReading(text: String): FullMessageReading =
        try {
            reading(text, target)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            FullMessageReading.unavailable(FullMessageReadingFailure.PRODUCER_FAILURE)
        }

    private suspend fun refreshWordReading(value: FullMessageTranslation): FullMessageTranslation {
        val results = mutableMapOf<String, FullMessageReading>()
        val words =
            requireNotNull(value.words).map { word ->
                val guide =
                    results[word.target]
                        ?: safeReading(word.target).also { results[word.target] = it }
                word.copy(reading = guide.text)
            }
        val failure =
            results.values
                .firstOrNull { it.status == FullMessageReadingStatus.UNAVAILABLE }
                ?.failure
        val hasGuide = words.any { it.reading != null }
        return value.copy(
            words = words,
            practiceReading =
                if (failure == null && hasGuide)
                    WordReplacement.compose(value.original, words, reading = true)
                else null,
            readingPolicy = readingPolicy,
            readingStatus =
                if (failure != null) FullMessageReadingStatus.UNAVAILABLE
                else if (hasGuide) FullMessageReadingStatus.AVAILABLE
                else FullMessageReadingStatus.NOT_NEEDED,
            readingFailure = failure,
        )
    }

    private fun markerFor(
        value: FullMessageTranslation,
        addition: IntroducedWord?,
    ): WordMessagePlan =
        WordMessagePlan(
            WordMessagePlan.hash(value.original),
            value.inputLanguage,
            target,
            source,
            value.words?.map { word ->
                WordPlanReference(
                    word.start,
                    word.length,
                    vocabulary.reference(
                        value.inputLanguage,
                        target,
                        IncrementalWords.normalized(word.source, value.inputLanguage),
                    ),
                )
            },
            addition?.let { vocabulary.reference(it.source, it.target, it.key) },
        )

    private fun referencedWords(text: String, plan: WordMessagePlan): List<WordReplacement>? {
        require(
            plan.originalHash == WordMessagePlan.hash(text) &&
                plan.target == target &&
                plan.meaningLanguage == source
        )
        if (plan.words == null) {
            require(plan.input == target && plan.introducedID == null)
            return null
        }
        var end = 0
        val spans =
            plan.words.map { ref ->
                require(ref.start >= end && ref.length > 0 && ref.start + ref.length <= text.length)
                val original = text.substring(ref.start, ref.start + ref.length)
                val word = vocabulary.referenced(ref.wordID, plan.input, target)
                require(word.key == IncrementalWords.normalized(original, plan.input))
                end = ref.start + ref.length
                WordReplacement(ref.start, ref.length, original, word.translation, word.reading)
            }
        if (plan.introducedID != null) require(plan.words.any { it.wordID == plan.introducedID })
        return spans
    }

    private suspend fun restoreWordPlan(
        text: String,
        plan: WordMessagePlan,
    ): FullMessageTranslation {
        val spans =
            referencedWords(text, plan)
                ?: return FullMessageTranslation(text, text, text, target, target, source)
        return refreshWordReading(
            FullMessageTranslation(
                text,
                WordReplacement.compose(text, spans, false),
                text,
                plan.input,
                target,
                source,
                words = spans,
            )
        )
    }

    /**
     * Reuses the pre-incremental local whole-message route, with exact authored original as the
     * held face. No vocabulary selection/commit.
     */
    private suspend fun fullMessage(text: String, key: String): FullMessageTranslation {
        val detected =
            try {
                withTimeoutOrNull(2_000) { language.identify(text) }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                null
            }
        currentCoroutineContext().ensureActive()
        val input = detected?.takeIf { it in TranslateLanguage.getAllLanguages() } ?: source
        val practice =
            if (input == target) text
            else {
                if (input == source) prepare(source, target)
                else
                    check(translator.isReady(input, target)) {
                        "Detected language models are not prepared"
                    }
                publish(key, MessageTranslationState(MessageTranslationPhase.TRANSLATING))
                translator.translate(text, input, target)
            }
        currentCoroutineContext().ensureActive()
        require(practice.isNotBlank()) { "Empty local translation" }
        return FullMessageTranslation(
            text,
            practice,
            text,
            input,
            target,
            source,
            mode = ImmersionMode.FULL_MESSAGES,
        )
    }

    private suspend fun incrementalMessage(
        id: String,
        text: String,
        key: String,
        mayIntroduce: Boolean,
    ): Pair<FullMessageTranslation, IntroducedWord?> {
        val configured = IncrementalWords.tokens(text, source)
        val detected =
            if (configured.size >= 3)
                try {
                    withTimeoutOrNull(2_000) { language.identify(text) }
                } catch (cancelled: CancellationException) {
                    throw cancelled
                } catch (_: Exception) {
                    null
                }
            else null
        currentCoroutineContext().ensureActive()
        val input = detected?.takeIf { it in TranslateLanguage.getAllLanguages() } ?: source
        if (input == target)
            return FullMessageTranslation(text, text, text, input, target, source) to null
        val tokens = IncrementalWords.tokens(text, input)
        val known = mutableMapOf<String, IntroducedWord>()
        var targetCharacters = 0L
        var guideCharacters = 0L
        for (token in tokens) if (token.key !in known)
            vocabulary.word(input, target, token.key)?.let {
                targetCharacters += it.translation.length
                guideCharacters += (it.reading ?: it.translation).length
                check(targetCharacters <= 2_097_152L && guideCharacters <= 2_097_152L) {
                    "Word snapshot exceeds message record capacity"
                }
                known[token.key] = it
            }
        var addition: IntroducedWord? = null
        // ICU supplies lexical boundaries, not POS. Randomize only the
        // unfamiliar, literal-safe distinct candidates; old plans bypass this.
        val candidates = tokens.distinctBy { it.key }.filterNot { it.key in known }
        val start =
            if (candidates.isEmpty()) 0 else IncrementalWords.candidateStart(id, candidates.size)
        for (offset in candidates.indices) {
            if (!mayIntroduce) break
            val token = candidates[(start + offset) % candidates.size]
            if (input == source) prepare(source, target)
            else
                check(translator.isReady(input, target)) {
                    "Detected language models are not prepared; no download fallback"
                }
            publish(key, MessageTranslationState(MessageTranslationPhase.TRANSLATING))
            val translated = translator.translate(token.text, input, target).trim()
            currentCoroutineContext().ensureActive()
            require(translated.toByteArray(Charsets.UTF_8).size <= 2_097_152) {
                "Word equivalent exceeds record capacity"
            }
            if (translated.isBlank() || IncrementalWords.normalized(translated, input) == token.key)
                continue
            val guide = safeReading(translated)
            check(guide.status != FullMessageReadingStatus.UNAVAILABLE) {
                "Required word reading unavailable"
            }
            val word =
                IntroducedWord(input, target, token.key, translated, guide.text, readingPolicy)
            known[token.key] = word
            addition = word
            break
        }
        val spans = tokens.mapNotNull { token ->
            known[token.key]?.let { word ->
                WordReplacement(
                    token.start,
                    token.end - token.start,
                    token.text,
                    word.translation,
                    word.reading,
                )
            }
        }
        var value =
            FullMessageTranslation(
                text,
                WordReplacement.compose(text, spans, reading = false),
                text,
                input,
                target,
                source,
                words = spans,
            )
        // Only inserted practice text is transliterated; source words and all
        // punctuation remain exactly authored. A policy refresh cannot add words.
        value = refreshWordReading(value)
        check(value.readingStatus != FullMessageReadingStatus.UNAVAILABLE) {
            "Required word reading unavailable"
        }
        return value to addition
    }

    override fun close() {
        synchronized(lock) {
            if (closed) return
            closed = true
            tasks.clear()
            completed.clear()
            completedBytes = 0
            states.clear()
            stateOrder.clear()
            visible.clear()
            foreground.clear()
            replaySource = null
            durablePending.clear()
            durableInFlight = null
            durableGeneration++
        }
        scope.cancel()
        translator.close()
        language.close()
        vocabulary.close()
    }
}
