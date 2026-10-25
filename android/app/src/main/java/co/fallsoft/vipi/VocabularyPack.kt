package co.fallsoft.vipi

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.util.AtomicFile
import co.fallsoft.vipi.core.VocabularyEntry
import co.fallsoft.vipi.core.ImmersionEngine
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
        val schema = manifest.getInt("schema_version")
        require(validID(id) && revision > 0 && schema in setOf(1, 3, 4))
        require(id == manifest.getString("source_language") + "-" + manifest.getString("target_language"))
        val normalization = manifest.getString("normalization")
        require((normalization == "unicode-nfc-lower" || (schema >= 3 && normalization == "unicode-nfc-lower-arabic-harakat-v1")) && manifest.getString("file") == "vocabulary.sqlite")
        require(if (schema == 4) manifest.optString("context_policy") == "all-source-senses-veto-3" else manifest.optString("context_policy") in setOf("", "cross-sense-label-veto-2"))
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
                db.rawQuery("PRAGMA user_version", null).use { require(it.moveToFirst() && it.getInt(0) == schema) }
                db.rawQuery("PRAGMA quick_check", null).use { require(it.moveToFirst() && it.getString(0) == "ok") }
                db.rawQuery("SELECT value FROM metadata WHERE key='pack_id'", null).use { require(it.moveToFirst() && it.getString(0) == id) }
                db.rawQuery("SELECT source,target FROM vocabulary LIMIT 1", null).use { require(it.moveToFirst()) }
                if (schema >= 3) {
                    db.rawQuery("SELECT value FROM metadata WHERE key='schema'", null).use { require(it.moveToFirst() && it.getString(0) == "vipi-bilingual-$schema") }
                    db.rawQuery("SELECT source_url FROM senses LIMIT 1", null).use { require(it.moveToFirst()) }
                    db.rawQuery("SELECT reading FROM vocabulary LIMIT 1", null).use { require(it.moveToFirst()) }
                    db.rawQuery("PRAGMA foreign_key_check", null).use { require(!it.moveToFirst()) }
                    if (manifest.has("context_policy")) {
                        db.rawQuery("SELECT value FROM metadata WHERE key='context_policy'", null).use { require(it.moveToFirst() && it.getString(0) == manifest.getString("context_policy")) }
                        db.rawQuery("SELECT count(*) FROM sense_context WHERE length(hints)>4096", null).use { require(it.moveToFirst() && it.getInt(0) == 0) }
                    }
                    if (schema == 4) {
                        db.rawQuery("SELECT count(*) FROM source_senses", null).use { require(it.moveToFirst() && it.getInt(0) > 0) }
                        db.rawQuery("SELECT count(*) FROM vocabulary v WHERE NOT EXISTS (SELECT 1 FROM source_senses s WHERE s.source=v.source AND s.sense_id=v.sense_id)", null).use { require(it.moveToFirst() && it.getInt(0) == 0) }
                    }
                }
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
        val rawTerms = candidateTerms(text, manifest.getString("source_language"))
        val terms = if (manifest.getString("normalization") == "unicode-nfc-lower-arabic-harakat-v1") rawTerms.map(ImmersionEngine::lookupKey).distinct() else rawTerms
        if (terms.isEmpty()) return emptyList()
        data class LookupKey(val source: String, val sense: String)
        data class Group(val targets: MutableSet<String> = linkedSetOf(), val readings: MutableMap<String, MutableSet<String>> = linkedMapOf(), val hints: MutableSet<String> = linkedSetOf())
        val grouped = linkedMapOf<LookupKey, Group>()
        val meanings = mutableMapOf<String, MutableSet<String>>()
        SQLiteDatabase.openDatabase(File(root, filename).path, null, SQLiteDatabase.OPEN_READONLY or SQLiteDatabase.NO_LOCALIZED_COLLATORS).use { db ->
            for (batch in terms.chunked(200)) {
                val placeholders = batch.joinToString(",") { "?" }
                val sql = if (manifest.getInt("schema_version") == 4) {
                    "SELECT s.source,s.sense_id,v.target,v.reading,COALESCE(c.hints,'') FROM source_senses s LEFT JOIN vocabulary v ON v.source=s.source AND v.sense_id=s.sense_id LEFT JOIN sense_context c ON c.sense_id=s.sense_id WHERE s.source IN ($placeholders) ORDER BY s.source,s.sense_id,v.target,v.reading"
                } else {
                    var columns = if (manifest.getInt("schema_version") == 3) "source,sense_id,target,reading" else "source,'' AS sense_id,target,'' AS reading"
                    columns += if (manifest.optString("context_policy") == "cross-sense-label-veto-2") ",COALESCE((SELECT hints FROM sense_context WHERE sense_context.sense_id=vocabulary.sense_id),'') AS hints" else ",'' AS hints"
                    "SELECT DISTINCT $columns FROM vocabulary WHERE source IN ($placeholders) ORDER BY source,sense_id,target,reading"
                }
                db.rawQuery(sql, batch.toTypedArray()).use { cursor ->
                    while (cursor.moveToNext()) {
                        val group = grouped.getOrPut(LookupKey(cursor.getString(0), cursor.getString(1))) { Group() }
                        if (!cursor.isNull(2) && !cursor.isNull(3)) {
                            val target = cursor.getString(2)
                            group.targets.add(target)
                            group.readings.getOrPut(target) { linkedSetOf() }.add(cursor.getString(3))
                        }
                        group.hints.addAll(cursor.getString(4).split('\u001f').filter { it.isNotEmpty() })
                        meanings.getOrPut(cursor.getString(0)) { linkedSetOf() }.add(cursor.getString(1))
                    }
                }
            }
        }
        return grouped.entries.sortedWith(compareBy({ it.key.source }, { it.key.sense })).map {
            VocabularyEntry(it.key.source, it.value.targets.sorted(), it.value.readings.mapValues { row -> row.value.sorted() }, it.value.hints.sorted(), (meanings[it.key.source]?.size ?: 0) > 1)
        }
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
