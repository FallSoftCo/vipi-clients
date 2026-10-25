package co.fallsoft.vipi

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.util.AtomicFile
import co.fallsoft.vipi.core.VocabularyEntry
import org.json.JSONObject
import java.io.File
import java.security.KeyFactory
import java.security.MessageDigest
import java.security.Signature
import java.security.spec.X509EncodedKeySpec
import java.text.Normalizer
import java.util.Locale

/** Public vocabulary only. Trust keys are supplied by the app, never by the download. */
class VocabularyPackStore(context: Context, private val trustedKeys: Map<String, ByteArray>) {
    private val root = File(context.filesDir, "language-packs").apply { mkdirs() }
    private val records = PrivateRecords(context)
    private fun validID(id: String) = id.matches(Regex("[a-z]{2,3}-[a-z]{2,3}"))
    private fun sha256(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    @Synchronized fun install(manifestBytes: ByteArray, signature: ByteArray, database: ByteArray): String {
        require(manifestBytes.size in 1..16_384 && signature.size in 64..80 && database.size in 512..67_108_864)
        val manifest = JSONObject(manifestBytes.toString(Charsets.UTF_8))
        val key = requireNotNull(trustedKeys[manifest.getString("key_id")]) { "Unknown signing key" }
        require(manifest.getString("signature_algorithm") == "ECDSA-P256-SHA256")
        require(Signature.getInstance("SHA256withECDSA").run {
            initVerify(KeyFactory.getInstance("EC").generatePublic(X509EncodedKeySpec(key))); update(manifestBytes); verify(signature)
        }) { "Invalid pack signature" }
        val id = manifest.getString("pack_id")
        val revision = manifest.getInt("revision")
        val hash = manifest.getString("sha256")
        require(validID(id) && revision > 0 && manifest.getInt("schema_version") == 1)
        require(id == manifest.getString("source_language") + "-" + manifest.getString("target_language"))
        require(manifest.getString("normalization") == "unicode-nfc-lower" && manifest.getString("file") == "vocabulary.sqlite")
        require(manifest.getLong("bytes") == database.size.toLong() && sha256(database) == hash)
        require(database.copyOfRange(0, 16).contentEquals("SQLite format 3\u0000".toByteArray()))
        val previous = records.read("pack-" + id)
        if (previous != null) require(revision > previous.getInt("revision") || (revision == previous.getInt("revision") && hash == previous.getString("hash"))) { "Pack rollback or revision conflict" }
        val destination = File(root, "$id-$revision-$hash.sqlite")
        val temp = File.createTempFile("install-", ".sqlite", root)
        try {
            temp.outputStream().use { it.write(database); it.fd.sync() }
            SQLiteDatabase.openDatabase(temp.path, null, SQLiteDatabase.OPEN_READONLY or SQLiteDatabase.NO_LOCALIZED_COLLATORS).use { db ->
                db.rawQuery("PRAGMA application_id", null).use { require(it.moveToFirst() && it.getInt(0) == 1447645257) }
                db.rawQuery("PRAGMA user_version", null).use { require(it.moveToFirst() && it.getInt(0) == 1) }
                db.rawQuery("PRAGMA quick_check", null).use { require(it.moveToFirst() && it.getString(0) == "ok") }
                db.rawQuery("SELECT value FROM metadata WHERE key='pack_id'", null).use { require(it.moveToFirst() && it.getString(0) == id) }
                db.rawQuery("SELECT source,target FROM vocabulary LIMIT 1", null).use { require(it.moveToFirst()) }
            }
            // POSIX rename replaces atomically, including a damaged previous copy.
            require(temp.renameTo(destination))
            records.write("pack-" + id, JSONObject().put("revision", revision).put("hash", hash))
            val pointer = AtomicFile(File(root, "$id.json"))
            val stream = pointer.startWrite()
            try { stream.write(JSONObject().put("file", destination.name).put("manifest", manifest).toString().toByteArray()); pointer.finishWrite(stream) }
            catch (error: Exception) { pointer.failWrite(stream); throw error }
        } finally { temp.delete() }
        // Previous installed revisions have no live readers: all access uses this monitor.
        root.listFiles()?.filter { it.name.startsWith("$id-") && it.extension == "sqlite" && it != destination }?.forEach { it.delete() }
        return id
    }

    @Synchronized fun entries(id: String, text: String): List<VocabularyEntry> {
        require(validID(id) && text.length <= 16_384)
        val pointer = File(root, "$id.json")
        if (!pointer.exists()) return emptyList()
        val value = JSONObject(pointer.readText())
        val manifest = value.getJSONObject("manifest")
        val accepted = records.read("pack-" + id) ?: return emptyList()
        require(accepted.getInt("revision") == manifest.getInt("revision") && accepted.getString("hash") == manifest.getString("sha256"))
        val filename = value.getString("file")
        require(filename == "$id-${accepted.getInt("revision")}-${accepted.getString("hash")}.sqlite")
        val terms = candidateTerms(text, manifest.getString("source_language"))
        if (terms.isEmpty()) return emptyList()
        val grouped = linkedMapOf<String, MutableSet<String>>()
        SQLiteDatabase.openDatabase(File(root, filename).path, null, SQLiteDatabase.OPEN_READONLY or SQLiteDatabase.NO_LOCALIZED_COLLATORS).use { db ->
            for (batch in terms.chunked(200)) {
                val placeholders = batch.joinToString(",") { "?" }
                db.rawQuery("SELECT DISTINCT source,target FROM vocabulary WHERE source IN ($placeholders) ORDER BY source,target", batch.toTypedArray()).use { cursor ->
                    while (cursor.moveToNext()) grouped.getOrPut(cursor.getString(0)) { linkedSetOf() }.add(cursor.getString(1))
                }
            }
        }
        return grouped.map { VocabularyEntry(it.key, it.value.toList()) }
    }

    @Synchronized fun remove(id: String) {
        require(validID(id))
        File(root, "$id.json").delete()
        root.listFiles()?.filter { it.name.startsWith("$id-") && it.extension == "sqlite" }?.forEach { it.delete() }
        // Retain the accepted revision so deleting data cannot enable a rollback.
    }

    private fun candidateTerms(text: String, language: String): List<String> {
        val words = if (language in setOf("zh", "ja")) LocalImmersion.words(text, language)
            else Regex("[\\p{L}\\p{M}]+(?:['’-][\\p{L}\\p{M}]+)*").findAll(text).map { it.range }.toList()
        val terms = linkedSetOf<String>()
        for (start in words.indices) for (length in 1..minOf(5, words.size - start)) {
            val end = start + length - 1
            if ((start until end).any { text.substring(words[it].last + 1, words[it + 1].first).any { c -> !c.isWhitespace() } }) continue
            val surface = text.substring(words[start].first, words[end].last + 1).trim().split(Regex("\\s+")).joinToString(" ")
            terms += Normalizer.normalize(surface, Normalizer.Form.NFC).lowercase(Locale.ROOT)
        }
        return terms.toList()
    }
}
