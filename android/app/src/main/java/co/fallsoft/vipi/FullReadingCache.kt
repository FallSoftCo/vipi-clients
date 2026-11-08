package co.fallsoft.vipi

import kotlinx.coroutines.*
import kotlin.coroutines.coroutineContext

/** Display metadata only. Original messages and speech never use this text. */
internal data class FullReading(val text: String, val provenance: Provenance) {
    enum class Provenance { AUTHORED, LOCAL_TRANSLITERATION }
}

/** One conversation/configuration owns this memory-only cache. Rendering reads
 * state; producers run on the worker dispatcher, outside the short entry lock. */
internal class FullReadingCache(
    private val policy: String,
    dispatcher: CoroutineDispatcher = Dispatchers.Default,
    private val producer: suspend (String, String) -> FullReading?
) : AutoCloseable {
    // Kotlin String equality preserves exact UTF16 spelling (no Unicode canonical
    // equivalence). Valid Unicode therefore has the same identity as exact UTF8;
    // malformed surrogate strings cannot collide through replacement encoding.
    private data class Key(val text: String, val language: String, val policy: String)
    private data class Entry(val value: FullReading?)
    private data class Pending(val token: Any, val generation: Long, val task: Deferred<FullReading?>)
    private val lock = Any()
    private val scope = CoroutineScope(SupervisorJob() + dispatcher)
    private val values = linkedMapOf<Key, Entry>()
    private val pending = mutableMapOf<Key, Pending>()
    private var generation = 0L
    private var closed = false
    init { require(policy.isNotEmpty()) }
    val count: Int get() = synchronized(lock) { values.size }
    fun hasResolved(text: String, language: String): Boolean = synchronized(lock) {
        !closed && values.containsKey(Key(text, language, policy))
    }
    fun cached(text: String, language: String): FullReading? = synchronized(lock) {
        if (closed) null else values[Key(text, language, policy)]?.value
    }
    suspend fun resolve(text: String, language: String): FullReading? {
        coroutineContext.ensureActive()
        if (text.length !in 1..16_384 || language !in setOf("ar", "zh", "ja", "ko")) return null
        val key = Key(text, language, policy)
        val entry = synchronized(lock) {
            if (closed) return null
            values[key]?.let { return it.value }
            pending[key] ?: run {
                if (pending.size >= 128) return null
                val epoch = generation; val token = Any()
                val task = scope.async(start = CoroutineStart.LAZY) {
                    try {
                        val result = try { producer(text, language)?.takeIf { it.text.length in 1..65_536 } }
                        catch (cancelled: CancellationException) { throw cancelled }
                        catch (_: Exception) { null }
                        coroutineContext.ensureActive()
                        synchronized(lock) {
                            if (!closed && generation == epoch && pending[key]?.token === token) {
                                pending.remove(key); values[key] = Entry(result)
                                while (values.size > 128) values.remove(values.keys.first())
                            }
                        }
                        result
                    } finally {
                        synchronized(lock) { if (pending[key]?.token === token) pending.remove(key) }
                    }
                }
                Pending(token, epoch, task).also { pending[key] = it }
            }
        }
        entry.task.start()
        val value = entry.task.await() // Cancelling this waiter does not cancel shared work.
        coroutineContext.ensureActive()
        return synchronized(lock) { if (!closed && generation == entry.generation) value else null }
    }
    fun removeAll() {
        val tasks = synchronized(lock) {
            generation++; values.clear(); pending.values.map { it.task }.also { pending.clear() }
        }
        tasks.forEach { it.cancel() }
    }
    override fun close() {
        synchronized(lock) { closed = true }
        removeAll(); scope.cancel()
    }
}
