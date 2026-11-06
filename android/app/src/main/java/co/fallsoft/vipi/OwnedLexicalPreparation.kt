package co.fallsoft.vipi

import android.system.Os
import android.system.OsConstants
import org.json.JSONObject
import java.io.File
import java.io.FileDescriptor
import java.io.FileOutputStream
import java.io.IOException
import java.nio.channels.OverlappingFileLockException
import java.nio.file.Files
import java.nio.file.LinkOption.NOFOLLOW_LINKS
import java.nio.file.StandardCopyOption.ATOMIC_MOVE
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.CancellationException

/** Cooperative public-cache protocol, NOT isolation from hostile same-UID code.
 * Every v1 writer holds the same root lock from recovery through publication.
 * Legacy/unrecorded files are NEVER recovery candidates. Small intent/outcome
 * receipts are retained; their eventual retention policy is a separate concern.
 */
internal class OwnedLexicalPreparation(private val root: File, private val operations: Operations = Operations()) {
    enum class Point { INTENT_SYNCED, TEMP_CREATED, CHUNK_WRITTEN, BEFORE_DATA_SYNC, BEFORE_PUBLISH }
    internal open class Operations {
        open fun checkpoint(point: Point) = Unit
        open fun syncData(output: FileOutputStream) { output.fd.sync() }
        open fun publish(temporary: File, destination: File): Boolean = temporary.renameTo(destination)
    }
    companion object {
        private val localMonitor = Any()
        internal const val DIRECTORY = ".lexical-prepare-v1"
        internal const val LOCK = ".lexical-prepare-v1.lock"
        private const val INTENT = "vipi-owned-lexical-attempt-1"
        private const val OUTCOME = "vipi-owned-lexical-outcome-1"
        private const val PRODUCER = "BundledLexicalCatalog/owned-prepare-1"
        private const val LIMIT = 536_870_912L
    }
    private data class Attempt(val directory: File, val token: String, val id: String,
                               val hash: String, val bytes: Long) {
        val payload: File get() = File(directory, "payload.sqlite")
    }
    private val area: File get() = File(root, DIRECTORY)
    private val pending: File get() = File(area, "pending")
    private val receipts: File get() = File(area, "receipts")
    private fun rootId() = MessageDigest.getInstance("SHA-256")
        .digest(root.canonicalPath.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
    private fun exists(file: File) = Files.exists(file.toPath(), NOFOLLOW_LINKS)
    private fun regular(file: File) = Files.isRegularFile(file.toPath(), NOFOLLOW_LINKS)
    private fun directory(file: File) = Files.isDirectory(file.toPath(), NOFOLLOW_LINKS)
    // Android streams constructed from an existing fd do NOT own it.
    private inline fun <T> withDescriptor(fd: FileDescriptor, body: (FileDescriptor) -> T): T {
        var failure: Throwable? = null
        try { return body(fd) } catch (error: Throwable) { failure = error; throw error }
        finally {
            try { Os.close(fd) }
            catch (closing: Throwable) { failure?.addSuppressed(closing) ?: throw closing }
        }
    }
    private fun syncDirectory(file: File) {
        withDescriptor(Os.open(file.path, OsConstants.O_RDONLY or OsConstants.O_NOFOLLOW or
            OsConstants.O_NONBLOCK or OsConstants.O_CLOEXEC, 0)) {
            // O_DIRECTORY is not exported by the public Android SDK. Verify the opened inode instead.
            if (!OsConstants.S_ISDIR(Os.fstat(it).st_mode)) throw IOException("Expected public preparation directory")
            Os.fsync(it)
        }
    }
    private fun ensureDirectory(file: File) {
        if (!exists(file)) {
            Files.createDirectory(file.toPath())
            syncDirectory(requireNotNull(file.parentFile))
        }
        if (!directory(file)) throw IOException("Unexpected public preparation directory")
    }
    private fun writeReceipt(file: File, value: JSONObject) {
        val bytes = value.toString().toByteArray(Charsets.UTF_8)
        require(bytes.size <= 8192)
        val fd = Os.open(file.path, OsConstants.O_WRONLY or OsConstants.O_CREAT or OsConstants.O_EXCL or
            OsConstants.O_NOFOLLOW or OsConstants.O_CLOEXEC, 384) // new owner-only receipt, never truncate/replace
        withDescriptor(fd) { owned ->
            FileOutputStream(owned).use { output ->
                output.write(bytes)
                output.fd.sync()
            }
        }
        syncDirectory(requireNotNull(file.parentFile))
    }
    private fun readReceipt(file: File): JSONObject? = try {
        if (!regular(file) || file.length() !in 1L..8192L) null else JSONObject(file.readText(Charsets.UTF_8))
    } catch (_: Exception) { null } // Unknown/malformed records are held, never guessed.
    private fun keys(value: JSONObject) = value.keys().asSequence().toSet()
    private fun integer(value: JSONObject, key: String): Long? = when (val raw = value.opt(key)) {
        is Int -> raw.toLong()
        is Long -> raw
        else -> null
    }
    private fun recorded(file: File): Attempt? = try {
        if (!directory(file) || UUID.fromString(file.name).toString() != file.name) null else {
            val value = readReceipt(File(file, "intent.json"))
            if (value == null || keys(value) != setOf("schema", "producer", "root", "attempt", "id", "sha256", "bytes", "payload") ||
                value.getString("schema") != INTENT || value.getString("producer") != PRODUCER ||
                value.getString("root") != rootId() || value.getString("attempt") != file.name ||
                value.getString("payload") != "payload.sqlite" ||
                !value.getString("id").matches(Regex("(d-[a-z]{2,3}|w-[a-z]{2,3}-[a-z]{2,3})")) ||
                !value.getString("sha256").matches(Regex("[a-f0-9]{64}")) ||
                integer(value, "bytes")?.let { it in 512..LIMIT } != true) null
            else Attempt(file, file.name, value.getString("id"), value.getString("sha256"), value.getLong("bytes"))
        }
    } catch (_: Exception) { null }
    private fun allowedChildren(attempt: Attempt): Boolean = attempt.directory.listFiles()?.all {
        it.name in setOf("intent.json", "payload.sqlite", "outcome.json") && regular(it)
    } == true
    private fun terminal(attempt: Attempt): Boolean {
        val value = readReceipt(File(attempt.directory, "outcome.json")) ?: return false
        return try {
            keys(value) == setOf("schema", "root", "attempt", "state", "publication", "removed_bytes", "error_class") &&
                value.getString("schema") == OUTCOME && value.getString("root") == rootId() &&
                value.getString("attempt") == attempt.token &&
                value.getString("state") in setOf("published", "failed", "cancelled", "error_after_publish", "recovered_abandoned") &&
                value.getString("publication") in setOf("observed", "not_observed", "original_unknown") &&
                value.opt("error_class") is String &&
                integer(value, "removed_bytes")?.let { it in 0..attempt.bytes } == true
        } catch (_: Exception) { false }
    }
    private fun archive(attempt: Attempt) {
        check(terminal(attempt) && !exists(attempt.payload) && allowedChildren(attempt))
        val destination = File(receipts, attempt.token)
        if (exists(destination)) throw IOException("Preparation receipt collision; retained")
        Files.move(attempt.directory.toPath(), destination.toPath(), ATOMIC_MOVE)
        syncDirectory(pending); syncDirectory(receipts)
    }
    private fun finish(attempt: Attempt, state: String, publication: String, failure: Throwable?) {
        check(recorded(attempt.directory) == attempt && allowedChildren(attempt))
        var removed = 0L
        if (exists(attempt.payload)) {
            check(regular(attempt.payload) && attempt.payload.length() <= attempt.bytes)
            removed = attempt.payload.length()
            Files.delete(attempt.payload.toPath()) // ONLY this attributed payload, under the held root lease.
            syncDirectory(attempt.directory)
        }
        writeReceipt(File(attempt.directory, "outcome.json"), JSONObject()
            .put("schema", OUTCOME).put("root", rootId()).put("attempt", attempt.token)
            .put("state", state).put("publication", publication).put("removed_bytes", removed)
            .put("error_class", failure?.javaClass?.name ?: ""))
        archive(attempt)
    }
    private fun recover() {
        for (entry in pending.listFiles() ?: throw IOException("Cannot inventory public preparations")) {
            val attempt = recorded(entry) ?: continue
            if (!allowedChildren(attempt)) continue
            if (exists(File(entry, "outcome.json"))) {
                if (terminal(attempt) && !exists(attempt.payload)) archive(attempt)
                continue // An inconsistent terminal+payload combination is uncertain: hold it.
            }
            if (exists(attempt.payload) && (!regular(attempt.payload) || attempt.payload.length() > attempt.bytes)) continue
            // The lease excludes ALL cooperative v1 writers. PID/age/name alone is never used.
            // This does NOT assert whether the interrupted invocation published a final file.
            finish(attempt, "recovered_abandoned", "original_unknown", null)
        }
    }
    private fun begin(id: String, hash: String, bytes: Long): Attempt {
        val token = UUID.randomUUID().toString()
        val file = File(pending, token)
        Files.createDirectory(file.toPath()); syncDirectory(pending)
        val attempt = Attempt(file, token, id, hash, bytes)
        writeReceipt(File(file, "intent.json"), JSONObject().put("schema", INTENT).put("producer", PRODUCER)
            .put("root", rootId()).put("attempt", token).put("id", id).put("sha256", hash)
            .put("bytes", bytes).put("payload", "payload.sqlite"))
        return attempt
    }
    internal fun checkpoint(point: Point) = operations.checkpoint(point)
    internal fun syncData(output: FileOutputStream) {
        operations.checkpoint(Point.BEFORE_DATA_SYNC)
        operations.syncData(output)
    }
    fun materialize(id: String, hash: String, bytes: Long, accepted: (File) -> Boolean,
                    writeAndValidate: (File) -> Unit): File = synchronized(localMonitor) {
        if (Thread.currentThread().isInterrupted) throw InterruptedException()
        require(id.matches(Regex("(d-[a-z]{2,3}|w-[a-z]{2,3}-[a-z]{2,3})")) && hash.matches(Regex("[a-f0-9]{64}")) && bytes in 512..LIMIT)
        check(root.isDirectory || root.mkdirs())
        if (!directory(root)) throw IOException("Unexpected public cache root")
        // Never unlink/replace this lock inode, including after failure or recovery.
        val lockFile = File(root, LOCK)
        if (exists(lockFile) && !regular(lockFile)) throw IOException("Unexpected preparation lock entry; retained")
        val lockFd = Os.open(lockFile.path, OsConstants.O_RDWR or OsConstants.O_CREAT or
            OsConstants.O_NOFOLLOW or OsConstants.O_CLOEXEC, 384) // deliberately NO O_TRUNC
        withDescriptor(lockFd) { ownedLock -> FileOutputStream(ownedLock).use { lockStream ->
            val channel = lockStream.channel
            val lease = try { channel.tryLock() } catch (_: OverlappingFileLockException) { null }
                ?: throw IOException("Public preparation lease is active; no recovery performed")
            lease.use {
                if (Thread.currentThread().isInterrupted) throw InterruptedException()
                ensureDirectory(area); ensureDirectory(pending); ensureDirectory(receipts)
                recover()
                val destination = File(root, "$id-$hash.sqlite")
                if (exists(destination) && !regular(destination)) throw IOException("Unexpected public cache entry; retained")
                if (regular(destination) && accepted(destination)) return@synchronized destination
                if (Thread.currentThread().isInterrupted) throw InterruptedException()
                val attempt = begin(id, hash, bytes)
                var failure: Throwable? = null
                var published = false
                try {
                    operations.checkpoint(Point.INTENT_SYNCED) // durable attribution BEFORE payload creation/writing
                    Files.createFile(attempt.payload.toPath())
                    operations.checkpoint(Point.TEMP_CREATED)
                    writeAndValidate(attempt.payload) // caller MUST retain checksum/length/header verification
                    operations.checkpoint(Point.BEFORE_PUBLISH)
                    check(operations.publish(attempt.payload, destination))
                    check(regular(destination) && !exists(attempt.payload))
                    published = true
                    syncDirectory(root); syncDirectory(attempt.directory)
                    destination
                } catch (error: Throwable) {
                    failure = error
                    throw error
                } finally {
                    val state = if (published) { if (failure == null) "published" else "error_after_publish" }
                        else if (failure is InterruptedException || failure is CancellationException) "cancelled" else "failed"
                    try { finish(attempt, state, if (published) "observed" else "not_observed", failure) }
                    catch (cleanup: Throwable) { failure?.addSuppressed(cleanup) ?: throw cleanup }
                }
            }
        }}
    }
}
