package co.fallsoft.vipi

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.io.Closeable
import java.io.File
import java.security.KeyStore
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** One native transaction owns protocol state and its inbox/outbox records.
 * Values are authenticated/encrypted; record types and opaque IDs remain SQLite metadata.
 * Never suspend or perform network work inside transaction(). */
internal class MessageVault(context: Context, val account: UUID) : Closeable {
    val file = File(context.noBackupFilesDir, "messages/$account/messages.sqlite")
    private val key: SecretKey
    private val database: SQLiteDatabase
    init {
        synchronized(keyLock) {
            val alias = "co.fallsoft.vipi.messages.$account"
            val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
            key = (store.getKey(alias, null) as? SecretKey) ?: run {
                check(!file.exists()) { "Message storage key is unavailable; recovery is required" }
                KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
                    init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                        .setKeySize(256).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                        .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
                }.generateKey()
            }
            check(file.parentFile!!.isDirectory || file.parentFile!!.mkdirs())
            database = SQLiteDatabase.openOrCreateDatabase(file, null)
            database.enableWriteAheadLogging()
            database.execSQL("PRAGMA synchronous=FULL")
            database.execSQL("CREATE TABLE IF NOT EXISTS records (kind TEXT NOT NULL, id TEXT NOT NULL, value BLOB NOT NULL, PRIMARY KEY(kind,id))")
        }
        try { transaction {
            val version = get("metadata", "schema")
            if (version == null) {
                put("metadata", "schema", byteArrayOf(1))
                // A new local account store can preview newly delivered messages.
                // Existing stores with an absent consent token stay private.
                put("local", "notification-previews", UUID.randomUUID().toString().toByteArray())
            }
            else check(version.contentEquals(byteArrayOf(1))) { "Unsupported message storage version" }
        } } catch (error: Exception) { database.close(); throw error }
    }
    @Synchronized fun <T> transaction(block: () -> T): T {
        check(!database.inTransaction()) { "Nested message transaction" }
        database.beginTransaction()
        try {
            val result = block()
            database.setTransactionSuccessful()
            return result
        } finally { database.endTransaction() }
    }
    private fun address(kind: String, id: String): ByteArray {
        check(database.inTransaction()) { "Message records require an atomic transaction" }
        require(kind.matches(Regex("[a-z-]{1,48}")) && id.length in 1..512 && '\u0000' !in id)
        return "vipi.messages.v1\u0000$account\u0000$kind\u0000$id".toByteArray(Charsets.UTF_8)
    }
    fun get(kind: String, id: String): ByteArray? {
        val aad = address(kind, id)
        return database.rawQuery("SELECT value FROM records WHERE kind=? AND id=?", arrayOf(kind, id)).use { cursor ->
            if (!cursor.moveToFirst()) null else {
                val bytes = cursor.getBlob(0)
                require(bytes.size in 29..2_097_181 && bytes[0] == 1.toByte())
                Cipher.getInstance("AES/GCM/NoPadding").run {
                    init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(128, bytes.copyOfRange(1, 13)))
                    updateAAD(aad); doFinal(bytes.copyOfRange(13, bytes.size))
                }
            }
        }
    }
    fun put(kind: String, id: String, value: ByteArray) {
        val aad = address(kind, id)
        require(value.size <= 2_097_152)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key); updateAAD(aad) }
        val bytes = byteArrayOf(1) + cipher.iv + cipher.doFinal(value)
        val values = ContentValues().apply { put("kind", kind); put("id", id); put("value", bytes) }
        check(database.insertWithOnConflict("records", null, values, SQLiteDatabase.CONFLICT_REPLACE) != -1L)
    }
    fun remove(kind: String, id: String) { address(kind, id); database.delete("records", "kind=? AND id=?", arrayOf(kind, id)) }
    fun ids(kind: String): List<String> {
        address(kind, "enumerate")
        return database.rawQuery("SELECT id FROM records WHERE kind=? ORDER BY id", arrayOf(kind)).use { cursor ->
            buildList { while (cursor.moveToNext()) add(cursor.getString(0)) }
        }
    }
    fun pageIDs(kind: String, prefix: String, before: String? = null, limit: Int = 50): List<String> {
        address(kind, prefix.ifEmpty { "enumerate" }); require(limit in 1..100)
        val upper = prefix + '\uFFFF'
        return database.rawQuery("SELECT id FROM records WHERE kind=? AND id>=? AND id<? AND id<? ORDER BY id DESC LIMIT ?",
            arrayOf(kind, prefix, upper, before ?: upper, limit.toString())).use { cursor ->
            buildList { while (cursor.moveToNext()) add(cursor.getString(0)) }
        }
    }
    @Synchronized override fun close() { database.close() }
    companion object { private val keyLock = Any() }
}
