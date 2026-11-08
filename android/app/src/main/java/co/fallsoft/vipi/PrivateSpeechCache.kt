package co.fallsoft.vipi

import android.content.Context
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.currentCoroutineContext
import java.io.File
import java.util.UUID

/** Disposable message audio has a shorter lifetime than reusable public voice data. */
internal object PrivateSpeechCache {
    private val gate = Any()
    private val leases = mutableSetOf<Lease>()

    class Lease internal constructor(internal val base: File, internal val root: File?, private val invalidate: () -> Unit) : AutoCloseable {
        private var closed = false
        private val jobs = mutableSetOf<Job>()
        fun <T> access(block: (File) -> T): T = synchronized(gate) {
            if (closed) throw CancellationException("Speech account ended")
            block(requireNotNull(root))
        }
        suspend fun <T> track(block: suspend () -> T): T = coroutineScope {
            val job = requireNotNull(currentCoroutineContext()[Job])
            synchronized(gate) {
                if (closed) throw CancellationException("Speech account ended")
                jobs += job
            }
            try { block() } finally { synchronized(gate) { jobs -= job } }
        }
        override fun close() = synchronized(gate) {
            if (!closed) {
                closed = true; leases -= this
                jobs.toList().forEach { it.cancel(CancellationException("Speech account ended")) }; jobs.clear()
                invalidate()
                root?.let { check(!it.exists() || it.deleteRecursively()) { "Private speech cleanup incomplete" } }
            }
        }
    }

    fun register(context: Context, files: Boolean, invalidate: () -> Unit): Lease = synchronized(gate) {
        val base = File(context.cacheDir, "vipi-speech")
        // A unique directory prevents a late native writer from entering a new account's cache.
        val root = if (files) File(base, UUID.randomUUID().toString()).apply {
            check(mkdirs()) { "Private speech cache unavailable" }
        } else null
        Lease(base, root, invalidate).also { leases += it }
    }

    fun erase(context: Context) = synchronized(gate) {
        val root = File(context.cacheDir, "vipi-speech")
        leases.filter { it.base == root }.toList().forEach { it.close() }
        // Includes legacy flat-cache audio and abandoned files from a previous process.
        check(!root.exists() || root.deleteRecursively()) { "Private speech cleanup incomplete" }
    }
}
