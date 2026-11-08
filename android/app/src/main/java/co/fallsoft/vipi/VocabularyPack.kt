package co.fallsoft.vipi

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.util.Base64
import android.system.Os
import android.system.OsConstants
import co.fallsoft.vipi.core.VocabularyEntry
import co.fallsoft.vipi.core.ImmersionEngine
import co.fallsoft.vipi.core.ContextMappingMatcher
import co.fallsoft.vipi.core.VocabularySourceScope
import org.json.JSONObject
import java.io.File
import java.security.KeyFactory
import java.security.MessageDigest
import java.security.Signature
import java.security.spec.X509EncodedKeySpec
import java.text.Normalizer
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap

/** Public vocabulary only. Trust keys are supplied by the app, never by the download. */
enum class VocabularyPackKind { VOCABULARY, REVIEWED_CONTEXT, REVIEWED_FRAME }
enum class VocabularyPackState { ABSENT, ACTIVE, INACTIVE, REINSTALL_REQUIRED }
data class VocabularyPackStatus(val state: VocabularyPackState, val revision: Int? = null,
                                val hash: String? = null, val cleanupPending: Boolean = false)
class VocabularyPackReinstallRequired : IllegalStateException("Verified pack reinstall required")
internal enum class PackActivationCheckpoint { STAGED, BEFORE_COMMIT, AFTER_COMMIT, BEFORE_DELETE }
class VocabularyPackStore(context: Context, private val trustedKeys: Map<String, ByteArray>,
                          private val kind: VocabularyPackKind = VocabularyPackKind.VOCABULARY) {
    private val isContext = kind == VocabularyPackKind.REVIEWED_CONTEXT
    private val isFrame = kind == VocabularyPackKind.REVIEWED_FRAME
    private val isReviewed = isContext || isFrame
    private val reviewedSchemas = if (isFrame) setOf(6,7,8) else setOf(5)
    private fun reviewedPolicy(schema:Int) = if (isFrame) when(schema) {
        8 -> "reviewed-bidirectional-side-unit-3"
        7 -> "reviewed-bidirectional-phrase-and-unit-2"
        else -> "reviewed-bidirectional-phrase-1"
    } else "reviewed-finite-context-1"
    private val reviewedFile = if (isFrame) "frames.sqlite" else "contexts.sqlite"
    private fun reviewedMetadata(schema:Int) = if (isFrame) when(schema) {
        8 -> "vipi-reviewed-frame-3"
        7 -> "vipi-reviewed-frame-2"
        else -> "vipi-reviewed-frame-1"
    } else "vipi-reviewed-context-1"
    private val reviewedIndexes = if (isFrame) listOf("source_inputs", "target_inputs") else listOf("context_inputs")
    private val root = File(context.filesDir, when {isFrame -> "language-packs/reviewed-frames"; isContext -> "language-packs/reviewed-contexts"; else -> "language-packs"}).apply { mkdirs() }
    private val receiptPrefix = when {isFrame -> "frame-pack-"; isContext -> "context-pack-"; else -> "pack-"}
    private val records = PrivateRecords(context)
    // Every handle for this namespace shares one commit/reader boundary.
    private val lock = locks.getOrPut(root.canonicalPath) { Any() }
    internal var qualificationCheckpoint: ((PackActivationCheckpoint) -> Unit)? = null
        set(value) { check(BuildConfig.DEBUG); field = value }
    internal var qualificationRecordWrite: ((PrivateRecordWriteCheckpoint, java.io.FileDescriptor?) -> Unit)?
        get() = records.qualificationWriteCheckpoint
        set(value) { records.qualificationWriteCheckpoint = value }
    private fun checkpoint(value: PackActivationCheckpoint) { qualificationCheckpoint?.invoke(value) }
    companion object { private val locks = ConcurrentHashMap<String, Any>() }
    private fun fileHash(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(65_536)
            while (true) { val count = input.read(buffer); if (count < 0) break; digest.update(buffer, 0, count) }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
    private fun syncDirectory() {
        check(root.isDirectory)
        val descriptor = Os.open(root.path, OsConstants.O_RDONLY, 0)
        try { Os.fsync(descriptor) } finally { Os.close(descriptor) }
    }
    private fun record(id: String): JSONObject? = records.read(receiptPrefix + id)?.also {
        require(it.getInt("revision") > 0 && it.getString("hash").matches(Regex("[0-9a-f]{64}")))
        if (it.has("activation_version")) require(it.getInt("activation_version") == 1 && it.has("active"))
    }
    private data class Active(val file: File, val manifest: JSONObject)
    private fun active(id: String, record: JSONObject): Active? {
        if (!record.has("activation_version")) throw VocabularyPackReinstallRequired()
        if (record.isNull("active")) return null
        val value = record.getJSONObject("active")
        val original = Base64.decode(value.getString("manifest_bytes"), Base64.NO_WRAP)
        val signature = Base64.decode(value.getString("signature"), Base64.NO_WRAP)
        require(original.size in 1..16_384 && signature.size in 64..80)
        require(sha256(original) == value.getString("manifest_sha256"))
        val manifest = JSONObject(original.toString(Charsets.UTF_8))
        val key = trustedKeys[manifest.getString("key_id")] ?: throw VocabularyPackReinstallRequired()
        require(manifest.getString("signature_algorithm") == "ECDSA-P256-SHA256")
        require(Signature.getInstance("SHA256withECDSA").run {
            initVerify(KeyFactory.getInstance("EC").generatePublic(X509EncodedKeySpec(key))); update(original); verify(signature)
        })
        require(manifest.getString("pack_id") == id && manifest.getInt("revision") == record.getInt("revision") &&
            manifest.getString("sha256") == record.getString("hash"))
        require(value.getString("file") == "$id-${record.getInt("revision")}-${record.getString("hash")}.sqlite")
        val file = File(root, value.getString("file"))
        if (!file.isFile || file.length() != manifest.getLong("bytes") || file.length() !in 512L..67_108_864L ||
            fileHash(file) != record.getString("hash")) throw VocabularyPackReinstallRequired()
        return Active(file, manifest)
    }
    private fun obsolete(id: String, keep: File?): List<File> = root.listFiles()?.filter {
        (it.name.matches(Regex("$id-[1-9][0-9]*-[0-9a-f]{64}\\.sqlite")) && it != keep) ||
            it.name in setOf("$id.json", "$id.json.new", "$id.json.bak")
    }.orEmpty()
    private fun cleanup(id: String, keep: File?) {
        for (file in obsolete(id, keep)) { checkpoint(PackActivationCheckpoint.BEFORE_DELETE); check(file.delete() || !file.exists()) }
    }
    /** State is authoritative even if obsolete-file deletion could not reclaim space. */
    fun status(id: String): VocabularyPackStatus = synchronized(lock) {
        require(validID(id))
        val accepted = record(id) ?: return@synchronized VocabularyPackStatus(VocabularyPackState.ABSENT,
            cleanupPending = obsolete(id, null).isNotEmpty())
        val selected = try { active(id, accepted) } catch (_: VocabularyPackReinstallRequired) {
            return@synchronized VocabularyPackStatus(VocabularyPackState.REINSTALL_REQUIRED,
                accepted.getInt("revision"), accepted.getString("hash"), obsolete(id, null).isNotEmpty())
        }
        VocabularyPackStatus(if (selected == null) VocabularyPackState.INACTIVE else VocabularyPackState.ACTIVE,
            accepted.getInt("revision"), accepted.getString("hash"), obsolete(id, selected?.file).isNotEmpty())
    }
    private fun validID(id: String) = id.matches(Regex("[a-z]{2,3}-[a-z]{2,3}"))
    private fun sha256(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    fun install(manifestBytes: ByteArray, signature: ByteArray, database: ByteArray,
                checkCancellation: () -> Unit = {}): String = synchronized(lock) {
        checkCancellation()
        require(manifestBytes.size in 1..16_384 && signature.size in 64..80 && database.size in 512..67_108_864)
        val originalManifest = manifestBytes.copyOf()
        val originalSignature = signature.copyOf()
        val manifest = JSONObject(originalManifest.toString(Charsets.UTF_8))
        val key = requireNotNull(trustedKeys[manifest.getString("key_id")]) { "Unknown signing key" }
        require(manifest.getString("signature_algorithm") == "ECDSA-P256-SHA256")
        require(Signature.getInstance("SHA256withECDSA").run {
            initVerify(KeyFactory.getInstance("EC").generatePublic(X509EncodedKeySpec(key))); update(originalManifest); verify(originalSignature)
        }) { "Invalid pack signature" }
        val id = manifest.getString("pack_id")
        val revision = manifest.getInt("revision")
        val hash = manifest.getString("sha256")
        val schema = manifest.getInt("schema_version")
        require(validID(id) && revision > 0 && hash.matches(Regex("[0-9a-f]{64}")) && if (isReviewed) schema in reviewedSchemas else schema in setOf(1, 3, 4))
        require(id == manifest.getString("source_language") + "-" + manifest.getString("target_language"))
        val normalization = manifest.getString("normalization")
        require(if (isReviewed) normalization == "exact-utf16" && manifest.getString("file") == reviewedFile
            else (normalization == "unicode-nfc-lower" || (schema >= 3 && normalization == "unicode-nfc-lower-arabic-harakat-v1")) && manifest.getString("file") == "vocabulary.sqlite")
        require(if (isReviewed) manifest.optString("context_policy") == reviewedPolicy(schema)
            else if (schema == 4) manifest.optString("context_policy") in setOf("all-source-senses-veto-3","all-source-senses-native-guards-veto-4") else manifest.optString("context_policy") in setOf("", "cross-sense-label-veto-2"))
        require((manifest.optString("context_policy")=="all-source-senses-native-guards-veto-4")==manifest.has("native_source_guard_policy"))
        require(manifest.getLong("bytes") == database.size.toLong() && sha256(database) == hash)
        require(database.copyOfRange(0, 16).contentEquals("SQLite format 3\u0000".toByteArray()))
        val previous = record(id)
        if (previous != null) require(revision > previous.getInt("revision") || (revision == previous.getInt("revision") && hash == previous.getString("hash"))) { "Pack rollback or revision conflict" }
        val destination = File(root, "$id-$revision-$hash.sqlite")
        val temp = File.createTempFile("install-", ".sqlite", root)
        try {
            temp.outputStream().use { it.write(database); it.fd.sync() }
            require(fileHash(temp) == hash)
            checkpoint(PackActivationCheckpoint.STAGED); checkCancellation()
            SQLiteDatabase.openDatabase(temp.path, null, SQLiteDatabase.OPEN_READONLY or SQLiteDatabase.NO_LOCALIZED_COLLATORS).use { db ->
                db.rawQuery("PRAGMA application_id", null).use { require(it.moveToFirst() && it.getInt(0) == 1447645257) }
                db.rawQuery("PRAGMA user_version", null).use { require(it.moveToFirst() && it.getInt(0) == schema) }
                db.rawQuery("PRAGMA quick_check", null).use { require(it.moveToFirst() && it.getString(0) == "ok") }
                db.rawQuery("SELECT value FROM metadata WHERE key='pack_id'", null).use { require(it.moveToFirst() && it.getString(0) == id) }
                if (isReviewed) {
                    db.rawQuery("SELECT value FROM metadata WHERE key='schema'",null).use { require(it.moveToFirst() && it.getString(0)==reviewedMetadata(schema)) }
                    db.rawQuery("SELECT value FROM metadata WHERE key='context_policy'",null).use { require(it.moveToFirst() && it.getString(0)==reviewedPolicy(schema)) }
                    db.rawQuery("SELECT id FROM mappings LIMIT 1",null).use { require(it.moveToFirst()) }
                    db.rawQuery("SELECT count(*) FROM mappings WHERE length(CAST(payload AS BLOB))>32768",null).use { require(it.moveToFirst() && it.getInt(0)==0) }
                    for(index in reviewedIndexes) {
                        db.rawQuery("SELECT count(*) FROM (SELECT input FROM $index GROUP BY input HAVING count(*)>256)",null).use { require(it.moveToFirst() && it.getInt(0)==0) }
                        db.rawQuery("SELECT count(*) FROM mappings m WHERE NOT EXISTS (SELECT 1 FROM $index i WHERE i.mapping_id=m.id)",null).use {require(it.moveToFirst() && it.getInt(0)==0)}
                    }
                    db.rawQuery("PRAGMA foreign_key_check",null).use { require(!it.moveToFirst()) }
                    return@use
                }
                db.rawQuery("SELECT source,target FROM vocabulary LIMIT 1", null).use { require(it.moveToFirst()) }
                if(manifest.has("native_source_guard_policy")) {
                    require(schema==4 && manifest.getString("source_language")=="zh" &&
                        manifest.getString("native_source_guard_policy")=="attested-native-han-lexeme-and-polysemy-veto-1")
                    for(field in listOf("native_source_guard_policy","native_source_guard_sha256"))
                        db.rawQuery("SELECT value FROM metadata WHERE key=?",arrayOf(field)).use { require(it.moveToFirst() && it.getString(0)==manifest.getString(field)) }
                    db.rawQuery("SELECT count(*) FROM source_guards WHERE length(source)<1 OR length(source)>32 OR protect_inner NOT IN (0,1) OR ambiguous NOT IN (0,1)",null).use {require(it.moveToFirst() && it.getInt(0)==0)}
                }
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
            syncDirectory()
            val selected = JSONObject().put("file", destination.name)
                .put("manifest_bytes", Base64.encodeToString(originalManifest, Base64.NO_WRAP))
                .put("manifest_sha256", sha256(originalManifest))
                .put("signature", Base64.encodeToString(originalSignature, Base64.NO_WRAP))
            val next = JSONObject().put("activation_version", 1).put("revision", revision).put("hash", hash).put("active", selected)
            require(next.toString().toByteArray(Charsets.UTF_8).size <= 65_507) // PrivateRecords envelope adds 29 bytes.
            checkpoint(PackActivationCheckpoint.BEFORE_COMMIT); checkCancellation()
            records.write(receiptPrefix + id, next)
        } finally { temp.delete() }
        // Activation is committed. Cleanup failure/cancellation cannot undo it or
        // imply failure to the caller; status() exposes remaining owned files.
        runCatching { checkpoint(PackActivationCheckpoint.AFTER_COMMIT); cleanup(id, destination) }
        id
    }

    fun entries(id: String, text: String, translation: String? = null): List<VocabularyEntry> = synchronized(lock) {
        require(validID(id) && text.length <= 16_384)
        val accepted = record(id) ?: return@synchronized emptyList()
        val selected = active(id, accepted) ?: return@synchronized emptyList()
        val manifest = selected.manifest
        val filename = selected.file.name
        if (isFrame) {
            require(manifest.getInt("schema_version") in reviewedSchemas && manifest.getString("context_policy")==reviewedPolicy(manifest.getInt("schema_version")))
            if(translation.isNullOrEmpty() || translation.length>32768)return@synchronized emptyList()
            return@synchronized SQLiteDatabase.openDatabase(File(root,filename).path,null,SQLiteDatabase.OPEN_READONLY or SQLiteDatabase.NO_LOCALIZED_COLLATORS).use {db ->
                ReviewedFrameLookup.entries(db,text,translation,manifest.getString("source_language"),manifest.getString("target_language"))
            }
        }
        if (isContext) {
            require(manifest.getInt("schema_version")==5)
            val source=manifest.getString("source_language");val target=manifest.getString("target_language")
            SQLiteDatabase.openDatabase(File(root,filename).path,null,SQLiteDatabase.OPEN_READONLY or SQLiteDatabase.NO_LOCALIZED_COLLATORS).use { db ->
                return@synchronized ReviewedContextLookup.entries(db, text, source, target)
            }
        }
        val rawTerms = candidateTerms(text, manifest.getString("source_language"))
        val terms = if (manifest.getString("normalization") == "unicode-nfc-lower-arabic-harakat-v1") rawTerms.map(ImmersionEngine::lookupKey).distinct() else rawTerms
        if (terms.isEmpty()) return@synchronized emptyList()
        data class LookupKey(val source: String, val sense: String)
        data class Group(val targets: MutableSet<String> = linkedSetOf(), val readings: MutableMap<String, MutableSet<String>> = linkedMapOf(), val hints: MutableSet<String> = linkedSetOf())
        val grouped = linkedMapOf<LookupKey, Group>()
        val meanings = mutableMapOf<String, MutableSet<String>>()
        val nativeGuards=mutableListOf<VocabularyEntry>()
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
                if(manifest.optString("native_source_guard_policy")=="attested-native-han-lexeme-and-polysemy-veto-1") {
                    db.rawQuery("SELECT source,protect_inner,ambiguous FROM source_guards WHERE source IN ($placeholders)",batch.toTypedArray()).use { cursor ->
                        while(cursor.moveToNext())nativeGuards+=VocabularyEntry(cursor.getString(0),emptyList(),
                            protectInner=cursor.getInt(1)==1,unresolvedNativeSenses=cursor.getInt(2)==1)
                    }
                }
            }
        }
        grouped.entries.sortedWith(compareBy({ it.key.source }, { it.key.sense })).map {
            VocabularyEntry(it.key.source, it.value.targets.sorted(), it.value.readings.mapValues { row -> row.value.sorted() }, it.value.hints.sorted(), (meanings[it.key.source]?.size ?: 0) > 1)
        }+nativeGuards
    }

    fun remove(id: String, checkCancellation: () -> Unit = {}): VocabularyPackStatus = synchronized(lock) {
        require(validID(id)); checkCancellation()
        val accepted = record(id)
        if (accepted != null) {
            if (!accepted.has("activation_version")) throw VocabularyPackReinstallRequired()
            val inactive = JSONObject().put("activation_version", 1).put("revision", accepted.getInt("revision"))
                .put("hash", accepted.getString("hash")).put("active", JSONObject.NULL)
            checkpoint(PackActivationCheckpoint.BEFORE_COMMIT); checkCancellation()
            records.write(receiptPrefix + id, inactive)
        }
        runCatching { checkpoint(PackActivationCheckpoint.AFTER_COMMIT); cleanup(id, null) }
        status(id)
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
