package co.fallsoft.vipi

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.google.mlkit.nl.languageid.LanguageIdentification
import com.google.mlkit.nl.translate.TranslateLanguage
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.yield
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.async
import kotlinx.coroutines.cancel
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONObject
import java.security.MessageDigest

/** Actual complete local model output. Raw original is never rewritten by the
 * display or persisted in place of the authenticated message. No word mappings.
 */
internal data class FullMessageTranslation(
    val original: String, val practiceText: String, val meaningText: String,
    val inputLanguage: String, val practiceLanguage: String, val meaningLanguage: String,
    val practiceReading: String? = null, val readingPolicy: String? = null,
    val readingStatus: FullMessageReadingStatus? = null, val readingFailure: FullMessageReadingFailure? = null
) {
    fun json() = JSONObject().put("original", original).put("practice", practiceText).put("meaning", meaningText)
        .put("input_language", inputLanguage).put("practice_language", practiceLanguage).put("meaning_language", meaningLanguage)
        .put("reading", practiceReading ?: JSONObject.NULL).put("reading_policy", readingPolicy ?: JSONObject.NULL)
        .put("reading_status", readingStatus?.name ?: JSONObject.NULL).put("reading_failure", readingFailure?.name ?: JSONObject.NULL).put("policy", POLICY)
    companion object {
        const val POLICY = "full-local-message-gesture-1"
        fun parse(value: JSONObject): FullMessageTranslation {
            require(value.getString("policy") == POLICY)
            val guide = value.opt("reading") as? String
            val failure = FullMessageReadingFailure.entries.firstOrNull { it.name == value.optString("reading_failure") }
            val status = FullMessageReadingStatus.entries.firstOrNull { it.name == value.optString("reading_status") }?.takeIf {
                when (it) {
                    FullMessageReadingStatus.NOT_NEEDED -> guide == null && failure == null
                    FullMessageReadingStatus.AVAILABLE -> !guide.isNullOrBlank() && guide != value.getString("practice") && failure == null
                    FullMessageReadingStatus.UNAVAILABLE -> guide == null && failure != null
                }
            }
            // Unknown/invalid reading metadata needs a reading-only migration;
            // it must not invalidate an otherwise complete model translation.
            return FullMessageTranslation(value.getString("original"), value.getString("practice"), value.getString("meaning"),
                value.getString("input_language"), value.getString("practice_language"), value.getString("meaning_language"),
                guide, value.opt("reading_policy") as? String, status, failure.takeIf { status != null })
                .also { require(it.practiceText.isNotBlank() && it.meaningText.isNotBlank()) }
        }
        fun key(id: String, original: String, source: String, target: String): String =
            MessageDigest.getInstance("SHA-256").digest(listOf(POLICY, id, original, source, target)
                .joinToString("\u0000").toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
    }
}

/** Derived text uses the same encrypted, account-owned store as its message.
 * No source text or model output is placed in preferences/public caches.
 */
internal class FullMessageTranslationStore(private val vault: MessageVault) {
    fun read(key: String): FullMessageTranslation? = vault.transaction {
        vault.get("full-message-translation", key)?.let { FullMessageTranslation.parse(JSONObject(it.toString(Charsets.UTF_8))) }
    }
    fun write(key: String, value: FullMessageTranslation) = vault.transaction {
        vault.put("full-message-translation", key, value.json().toString().toByteArray(Charsets.UTF_8))
    }
}

internal enum class MessageTranslationPhase { PREPARING, TRANSLATING, READY, FAILED }
internal data class MessageTranslationState(val phase: MessageTranslationPhase,
    val value: FullMessageTranslation? = null, val failure: String? = null)

/** Identity/direction are advisory; every message reaches the translator even
 * when language identification is uncertain, short, or unsupported.
 */
internal interface MessageTranslationLanguage : AutoCloseable {
    suspend fun identify(text: String): String?
}
private class NativeMessageTranslationLanguage : MessageTranslationLanguage {
    private val client = LanguageIdentification.getClient()
    override suspend fun identify(text: String): String? {
        val code = client.identifyLanguage(text).await()
        return TranslateLanguage.fromLanguageTag(code)
    }
    override fun close() = client.close()
}

/** Session-owned single-flight local translation; view disappearance does not
 * duplicate work. Closing/replacing the account or pair cancels pending work.
 * Cache contains only complete practice+meaning output, never lookup partials.
 */
internal class ConversationTranslation(
    context: Context, val source: String, val target: String,
    private val store: FullMessageTranslationStore? = null,
    private val translator: LanguageTranslation = LocalTranslation(),
    private val language: MessageTranslationLanguage = NativeMessageTranslationLanguage(),
    private val reading: suspend (String, String) -> FullMessageReading = { text, code -> FullMessageReadings.read(context.applicationContext, text, code) },
    private val cacheByteLimit: Long = 8L * 1024 * 1024
) : AutoCloseable {
    private val lock = Any()
    private val readingPolicy = FullMessageReadings.policy(target)
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val preparation = Mutex()
    private val modelExecution = Mutex()
    private val durablePending = linkedMapOf<String, () -> String?>()
    private var durableJob: Job? = null
    private var durableGeneration = 0L
    private var durableInFlight: String? = null
    internal val durableActive: Boolean get() = synchronized(lock) { durableJob?.let { !it.isCompleted && !it.isCancelled } == true }
    internal val pendingDurableCount: Int get() = synchronized(lock) { durablePending.size }
    internal val activeTaskCount: Int get() = synchronized(lock) { tasks.size }
    private val prepared = mutableSetOf<Set<String>>()
    private val tasks = mutableMapOf<String, Deferred<FullMessageTranslation>>()
    private val completed = linkedMapOf<String, FullMessageTranslation>()
    private var completedBytes = 0L
    private fun retainedBytes(value: FullMessageTranslation): Long = 256L + 2L *
        (value.original.length.toLong() + value.practiceText.length + value.meaningText.length +
            (value.practiceReading?.length ?: 0) + (value.readingPolicy?.length ?: 0) +
            (value.readingStatus?.name?.length ?: 0) + (value.readingFailure?.name?.length ?: 0) +
            value.inputLanguage.length + value.practiceLanguage.length + value.meaningLanguage.length)
    val cachedBytes: Long get() = synchronized(lock) { completedBytes }
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
    val replayActive: Boolean get() = synchronized(lock) { replayJob?.let { !it.isCompleted && !it.isCancelled } == true }
    var replayFailure by mutableStateOf<String?>(null); private set
    private fun observed(key: String) = (visible[key] ?: 0) > 0 || (foreground[key] ?: 0) > 0
    private fun trimStates() {
        // READY values outside the128-entry cache survive only while actually
        // observed. Failure metadata stays bounded separately and contains no
        // translated paragraph; a visible failed row keeps its retry state.
        for (key in stateOrder.filter { !observed(it) && it !in tasks && it !in completed && states[it]?.value != null }) {
            states.remove(key); stateOrder.remove(key)
        }
        val failures = stateOrder.filter { !observed(it) && it !in tasks && states[it]?.phase == MessageTranslationPhase.FAILED }
        for (key in failures.take((failures.size - 128).coerceAtLeast(0))) {
            states.remove(key); stateOrder.remove(key)
        }
    }
    private fun recordState(key: String, state: MessageTranslationState) {
        states[key] = state; stateOrder.remove(key); stateOrder.add(key)
    }
    private fun publish(key: String, state: MessageTranslationState) = synchronized(lock) {
        if (!closed && (observed(key) || states.containsKey(key))) recordState(key, state)
    }
    fun retain(id: String, text: String) = synchronized(lock) {
        val key = key(id, text); if (closed) return@synchronized
        visible[key] = (visible[key] ?: 0) + 1
        completed[key]?.let { recordState(key, MessageTranslationState(MessageTranslationPhase.READY, it)) }
    }
    fun release(id: String, text: String) = synchronized(lock) {
        val key = key(id, text)
        if ((visible[key] ?: 0) <= 1) visible.remove(key) else visible[key] = visible.getValue(key) - 1
        trimStates()
    }
    /** Disk-backed warming: one old record in flight, no eager per-history
     * coroutine queue. Visible/live requests preempt the next old record.
     * A restarted scan replaces its iterator after the current record finishes. */
    fun replaySaved(source: () -> Sequence<SavedMessage>) {
        val job = synchronized(lock) {
            if (closed) return
            replaySource = source; replayRevision++; replayFailure = null
            if (replayJob?.let { !it.isCompleted && !it.isCancelled } == true) return
            val generation = ++replayGeneration
            scope.launch(start = CoroutineStart.LAZY) {
                try {
                    while (true) {
                        val (revision, input) = synchronized(lock) { replayRevision to requireNotNull(replaySource) }
                        val iterator = input().iterator()
                        while (true) {
                            currentCoroutineContext().ensureActive()
                            if (synchronized(lock) { revision != replayRevision }) break
                            if (!iterator.hasNext()) break
                            val message = iterator.next()
                            while (synchronized(lock) { foreground.isNotEmpty() }) delay(10)
                            try { resolveObserved(message.id, message.text, retry = false, foregroundRequest = false) }
                            catch (cancelled: CancellationException) { throw cancelled }
                            catch (_: Exception) { /* A visible request exposes its own failure/retry state. */ }
                            yield()
                        }
                        val finished = synchronized(lock) {
                            if (revision == replayRevision) { replayJob = null; true } else false
                        }
                        if (finished) return@launch
                    }
                } catch (cancelled: CancellationException) { throw cancelled }
                catch (failure: Exception) { synchronized(lock) { if (!closed) replayFailure = failure.javaClass.simpleName } }
                finally { synchronized(lock) { if (generation == replayGeneration) replayJob = null } }
            }.also { replayJob = it }
        }
        job.start()
    }
    var preparationFailed by mutableStateOf(false); private set
    init {
        require(cacheByteLimit > 0)
        require(source != target && source in TranslateLanguage.getAllLanguages() && target in TranslateLanguage.getAllLanguages())
        preparePair()
    }
    fun key(id: String, text: String) = FullMessageTranslation.key(id, text, source, target)
    fun state(id: String, text: String): MessageTranslationState? {
        val key = key(id, text)
        val state = states[key]
        if (state?.value != null) return state
        // A canceled/disposed observer does not cancel the account-owned model
        // task. Its genuine cached completion remains observable without adding
        // every replayed paragraph to Compose state.
        return synchronized(lock) { completed[key]?.let { MessageTranslationState(MessageTranslationPhase.READY, it) } } ?: state
    }
    fun preparePair() { scope.launch {
        try { modelExecution.withLock { prepare(source, target) }; preparationFailed = false }
        catch (_: TimeoutCancellationException) { preparationFailed = true }
        catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { preparationFailed = true }
    } }
    private suspend fun prepare(from: String, to: String) = preparation.withLock {
        val pair = setOf(from, to)
        if (pair !in prepared) {
            withTimeout(120_000) { translator.prepare(from, to, cellularAllowed = true) }
            currentCoroutineContext().ensureActive()
            synchronized(lock) { check(!closed); prepared += pair }
        }
    }
    /** Catch-up retains opaque committed IDs and weak journal loaders, never
     * one text-bearing coroutine per inbox item. At most one durable record is
     * loaded here; visible/manual requests run before the next queued record. */
    fun enqueueStored(id: String, load: () -> String?) {
        val job = synchronized(lock) {
            if (closed || id == durableInFlight || id in durablePending) return
            durablePending[id] = load
            if (durableJob?.let { !it.isCompleted && !it.isCancelled } == true) return
            val generation = ++durableGeneration
            scope.launch(start = CoroutineStart.LAZY) {
                try {
                    while (true) {
                        currentCoroutineContext().ensureActive()
                        while (synchronized(lock) { foreground.isNotEmpty() }) delay(10)
                        val next = synchronized(lock) {
                            durablePending.entries.firstOrNull()?.let { (id, loader) ->
                                durablePending.remove(id); durableInFlight = id; id to loader
                            } ?: run { durableJob = null; null }
                        } ?: break
                        try {
                            val text = withContext(Dispatchers.IO) { next.second() }
                            if (text != null) resolveObserved(next.first, text, retry = false, foregroundRequest = false)
                        } catch (cancelled: CancellationException) { throw cancelled }
                        catch (_: Exception) { /* Existing visible state exposes retry; no auto replay. */ }
                        finally { synchronized(lock) { if (generation == durableGeneration) durableInFlight = null } }
                        yield()
                    }
                } finally { synchronized(lock) { if (generation == durableGeneration) { durableJob = null; durableInFlight = null } } }
            }.also { durableJob = it }
        }
        job.start()
    }
    fun enqueue(id: String, text: String, retry: Boolean = false) {
        scope.launch { try { resolve(id, text, retry) } catch (cancelled: CancellationException) { throw cancelled } catch (_: Exception) { /* State records the visible failure. */ } }
    }
    suspend fun resolve(id: String, text: String, retry: Boolean = false): FullMessageTranslation =
        resolveObserved(id, text, retry, foregroundRequest = true)
    private suspend fun resolveObserved(id: String, text: String, retry: Boolean, foregroundRequest: Boolean): FullMessageTranslation {
        val key = key(id, text)
        if (foregroundRequest) synchronized(lock) { foreground[key] = (foreground[key] ?: 0) + 1 }
        try { return resolveTask(id, text, retry) }
        finally { if (foregroundRequest) synchronized(lock) {
            if ((foreground[key] ?: 0) <= 1) foreground.remove(key) else foreground[key] = foreground.getValue(key) - 1
            trimStates()
        } }
    }
    private suspend fun resolveTask(id: String, text: String, retry: Boolean): FullMessageTranslation {
        val key = key(id, text)
        val task = synchronized(lock) {
            if (closed) throw CancellationException("Translation owner closed")
            val resident = completed[key] ?: states[key]?.value
            resident?.let {
                if (!(retry && it.readingStatus == FullMessageReadingStatus.UNAVAILABLE)) {
                    if (observed(key)) recordState(key, MessageTranslationState(MessageTranslationPhase.READY, it))
                    return it
                }
            }
            tasks[key] ?: run {
                if (!retry && states[key]?.phase == MessageTranslationPhase.FAILED) throw IllegalStateException("Explicit retry required")
                scope.async(start = CoroutineStart.LAZY) {
                    try {
                        if (resident == null) publish(key, MessageTranslationState(MessageTranslationPhase.PREPARING))
                        // This is derived cache, never authenticated source.
                        // A damaged/old entry is replaced by fresh model output;
                        // retry must not loop forever on the same bad cache row.
                        val cached = resident ?: try { store?.let { withContext(Dispatchers.IO) { it.read(key) } }
                            ?.takeIf { it.original == text && it.practiceLanguage == target && it.meaningLanguage == source } }
                        catch (cancelled: CancellationException) { throw cancelled }
                        catch (_: Exception) { null }
                        currentCoroutineContext().ensureActive()
                        val translated = if (cached != null) cached else modelExecution.withLock {
                            currentCoroutineContext().ensureActive()
                            val detected = try { withTimeoutOrNull(2_000) { language.identify(text) } } catch (cancelled: CancellationException) { throw cancelled } catch (_: Exception) { null }
                            val input = detected?.takeIf { it in TranslateLanguage.getAllLanguages() } ?: source
                            val practice = if (input == target) text else {
                                prepare(input, target)
                                publish(key, MessageTranslationState(MessageTranslationPhase.TRANSLATING))
                                withTimeout(60_000) { translator.translate(text, input, target) }
                            }
                            val meaning = if (input == source) text else {
                                prepare(input, source)
                                publish(key, MessageTranslationState(MessageTranslationPhase.TRANSLATING))
                                withTimeout(60_000) { translator.translate(text, input, source) }
                            }
                            require(practice.isNotBlank() && meaning.isNotBlank()) { "Empty local translation" }
                            FullMessageTranslation(text, practice, meaning, input, target, source)
                        }
                        // Old translation output remains valid when a reading
                        // producer changes. Regenerate only this derived face,
                        // never the authenticated source or model translation.
                        val retryReading = retry && translated.readingStatus == FullMessageReadingStatus.UNAVAILABLE
                        val value = if (translated.readingPolicy == readingPolicy && translated.readingStatus != null && !retryReading) translated else {
                            val current = try { reading(translated.practiceText, target) }
                            catch (cancelled: CancellationException) { throw cancelled }
                            catch (_: Exception) { FullMessageReading.unavailable(FullMessageReadingFailure.PRODUCER_FAILURE) }
                            translated.copy(practiceReading = current.text, readingPolicy = readingPolicy,
                                readingStatus = current.status, readingFailure = current.failure)
                        }
                        currentCoroutineContext().ensureActive()
                        withContext(Dispatchers.IO) { synchronized(lock) {
                            if (closed) throw CancellationException("Translation owner closed")
                            if (cached == null || cached != value) store?.write(key, value)
                            completed.remove(key)?.let { completedBytes -= retainedBytes(it) }
                            completed[key] = value; completedBytes += retainedBytes(value)
                            while (completed.size > 128 || completedBytes > cacheByteLimit) {
                                completed.remove(completed.keys.first())?.let { completedBytes -= retainedBytes(it) }
                            }
                            if (observed(key) || states.containsKey(key)) recordState(key, MessageTranslationState(MessageTranslationPhase.READY, value))
                            trimStates()
                        } }
                        value
                    } catch (timeout: TimeoutCancellationException) {
                        val failure = java.io.IOException("Local translation timed out", timeout)
                        publish(key, MessageTranslationState(MessageTranslationPhase.FAILED, failure = failure.javaClass.simpleName))
                        throw failure
                    } catch (error: Exception) {
                        if (error !is CancellationException) synchronized(lock) {
                            publish(key, MessageTranslationState(MessageTranslationPhase.FAILED, failure = error.javaClass.simpleName))
                        }
                        throw error
                    } finally { synchronized(lock) { tasks.remove(key); trimStates() } }
                }.also { tasks[key] = it }
            }
        }
        task.start()
        return task.await()
    }
    override fun close() {
        synchronized(lock) { if (closed) return; closed = true; tasks.clear(); completed.clear(); completedBytes = 0; states.clear(); stateOrder.clear(); visible.clear(); foreground.clear(); replaySource = null; durablePending.clear(); durableInFlight = null; durableGeneration++ }
        scope.cancel()
        translator.close(); language.close()
    }
}
