package co.fallsoft.vipi

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.system.Os
import android.system.OsConstants
import android.util.AtomicFile
import java.io.File
import java.io.FileDescriptor
import java.io.IOException
import java.nio.file.Files
import java.nio.file.LinkOption.NOFOLLOW_LINKS
import java.security.KeyStore
import java.util.concurrent.ConcurrentHashMap
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import org.json.JSONObject

internal enum class PrivateRecordCommitState { NOT_COMMITTED, COMMITTED_DURABILITY_UNCERTAIN, UNKNOWN }
internal class PrivateRecordWriteFailure(val commitState: PrivateRecordCommitState, cause: Exception) :
    IOException("Private record write could not be confirmed: $commitState", cause)
internal enum class PrivateRecordWriteCheckpoint { BEFORE_FILE_SYNC, BEFORE_FINISH, AFTER_FINISH, BEFORE_DIRECTORY_SYNC }

/** Authenticated local records. Success requires explicit sync and exact ciphertext readback.
 * The wrapping key never leaves Android Keystore. */
internal class PrivateRecords(context: Context) {
    private val directory = File(context.noBackupFilesDir, "private-records").apply { mkdirs() }
    private val alias = "co.fallsoft.vipi.private.v1"
    private val recordLock = locks.getOrPut(directory.canonicalPath) { Any() }
    companion object { private val locks = ConcurrentHashMap<String, Any>() }
    internal var qualificationWriteCheckpoint: ((PrivateRecordWriteCheckpoint, FileDescriptor?) -> Unit)? = null
        set(value) { check(BuildConfig.DEBUG); field = value }
    private fun currentBytes(target: AtomicFile): ByteArray? {
        if (!target.baseFile.exists()) return null
        require(target.baseFile.length() <= 65_536)
        return target.baseFile.readBytes()
    }
    private fun syncDirectory() {
        val descriptor = Os.open(directory.path, OsConstants.O_RDONLY, 0)
        try {
            qualificationWriteCheckpoint?.invoke(PrivateRecordWriteCheckpoint.BEFORE_DIRECTORY_SYNC, descriptor)
            Os.fsync(descriptor)
        } catch (failure: Exception) {
            runCatching { Os.close(descriptor) }.exceptionOrNull()?.let(failure::addSuppressed)
            throw failure
        }
        Os.close(descriptor)
    }
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setKeySize(256).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        }.generateKey()
    }
    private fun file(name: String): AtomicFile {
        require(name.matches(Regex("[a-z0-9-]{1,80}")))
        return AtomicFile(File(directory, name))
    }
    fun write(name: String, value: JSONObject): Unit = synchronized(recordLock) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()); updateAAD(name.toByteArray()) }
        val bytes = byteArrayOf(1) + cipher.iv + cipher.doFinal(value.toString().toByteArray(Charsets.UTF_8))
        require(bytes.size in 30..65_536)
        val target = file(name)
        val previous = currentBytes(target)
        var stream: java.io.FileOutputStream? = null
        var finishStarted = false
        try {
            stream = target.startWrite()
            stream.write(bytes)
            qualificationWriteCheckpoint?.invoke(PrivateRecordWriteCheckpoint.BEFORE_FILE_SYNC, stream.fd)
            // AtomicFile.finishWrite logs sync/rename failures rather than throwing.
            // Our explicit sync must succeed before it may attempt activation.
            stream.fd.sync()
            qualificationWriteCheckpoint?.invoke(PrivateRecordWriteCheckpoint.BEFORE_FINISH, stream.fd)
            finishStarted = true
            target.finishWrite(stream)
            qualificationWriteCheckpoint?.invoke(PrivateRecordWriteCheckpoint.AFTER_FINISH, null)
            syncDirectory()
            check(currentBytes(target)?.contentEquals(bytes) == true) { "Private record activation readback failed" }
        } catch (failure: Exception) {
            if (!finishStarted && stream != null) runCatching { target.failWrite(stream) }
            val observation = runCatching { currentBytes(target) }
            val current = observation.getOrNull()
            val state = when {
                observation.isFailure -> PrivateRecordCommitState.UNKNOWN
                current?.contentEquals(bytes) == true -> PrivateRecordCommitState.COMMITTED_DURABILITY_UNCERTAIN
                (current == null && previous == null) || (current != null && previous != null && current.contentEquals(previous)) -> PrivateRecordCommitState.NOT_COMMITTED
                else -> PrivateRecordCommitState.UNKNOWN
            }
            throw PrivateRecordWriteFailure(state, failure)
        }
    }
    fun read(name: String): JSONObject? = synchronized(recordLock) {
        val target = file(name)
        if (!target.baseFile.exists()) return@synchronized null
        val bytes = target.readFully()
        require(bytes.size in 30..65_536 && bytes[0] == 1.toByte())
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply {
            init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes.copyOfRange(1, 13)))
            updateAAD(name.toByteArray())
        }
        JSONObject(cipher.doFinal(bytes.copyOfRange(13, bytes.size)).toString(Charsets.UTF_8))
    }
    fun remove(name: String): Unit = synchronized(recordLock) {
        val base = file(name).baseFile
        // A failed sidecar deletion must leave the authoritative record available
        // to a newly opened account-deletion coordinator so it can retry.
        val paths = listOf(File(base.path + ".new"), File(base.path + ".bak"), base).map { it.toPath() }
        for (path in paths) {
            Files.deleteIfExists(path)
            check(!Files.exists(path, NOFOLLOW_LINKS)) { "Private record could not be removed" }
        }
        syncDirectory()
        check(paths.none { Files.exists(it, NOFOLLOW_LINKS) }) { "Private record removal could not be confirmed" }
    }
}
