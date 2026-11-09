package co.fallsoft.vipi

import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.util.regex.Pattern
import java.util.Collections
import co.fallsoft.vipi.FrozenContextTokenizer.Range

/** Disabled evidence API. No masks, approvals, selection budget or display output. */
internal class FrozenContextPackReader(
    pack: File,
    expectedSHA256: String,
    expectedMetadata: Map<String, String>,
    dictionaries: Map<String, File>,
    private val tokenizer: FrozenContextTokenizer
) {
    data class Rule(val id: String, val sourceKey: String, val tokens: List<String>,
        val focusOffset: Int, val target: String, val ratio: Double?, val components: Int,
        val weight: Double, val recordSHA256: String, val headIDs: List<String>)
    data class Head(val id: String, val contextID: String, val sourceKey: String,
        val tokens: List<String>, val focusStart: Int, val focusEnd: Int, val target: String,
        val readingsJSON: String, val posJSON: String, val fixed: Boolean,
        val trainRank: Int, val recordSHA256: String)
    data class Match(val rule: Rule, val contextRange: Range, val tokenStart: Int,
        val contextGeometryCompatible: Boolean)
    data class Assessment(val winner: Match?, val rawMatches: List<Match>)
    val candidateClassifier:FrozenCandidateClassifier
    val tupleEvidence:FrozenContextTupleEvidence
    val contentSHA256: String
    val metadata: Map<String, String>
    val rules: List<Rule>
    val heads: Map<String, Head>
    private val byKey: Map<String, List<Rule>>

    init {
        require(expectedSHA256.matches(HASH) && dictionaries.keys == setOf("en", "es"))
        require(digest(pack, 16L shl 20) == expectedSHA256)
        lateinit var classifier:FrozenCandidateClassifier
        lateinit var tuples:FrozenContextTupleEvidence
        val headMap = linkedMapOf<String, Head>(); val loaded = mutableListOf<Rule>()
        val meta = open(pack).use { db ->
            require(pragma(db, "application_id") == 1447645257 && pragma(db, "user_version") == 1)
            val actual = metadata(db)
            val required = mapOf("kind" to "vipi.frozen-context-research", "schema" to "1",
                "source" to "en", "target" to "es", "permission" to "disabled_research_only",
                "normalization" to "NFC+Unicode-casefold+whitespace-collapse; offsets never normalized",
                "tokenizer_sha256" to "d1f41157ec44e95e25420a7d65b37bcfe40b174592dfce812248e49955aeeb5f")
            require(required.all { actual[it.key] == it.value })
            require(listOf("policy_sha256", "input_manifest_sha256").all { expectedMetadata[it]?.matches(HASH) == true })
            require(expectedMetadata.all { actual[it.key] == it.value })
            for (language in listOf("en", "es")) {
                val file = dictionaries.getValue(language); val sha = actual.getValue("dictionary_${language}_sha256")
                require(digest(file, 512L shl 20) == sha)
                val dictionaryMeta = open(file).use { metadata(it) }
                val encoded = JSONObject(actual.getValue("dictionary_${language}_metadata_json"))
                val expected = encoded.keys().asSequence().associateWith { encoded.getString(it) }
                require(dictionaryMeta == expected && dictionaryMeta.containsKey("release_id") && dictionaryMeta.containsKey("source_inventory_sha256"))
                require(digest(file, 512L shl 20) == sha)
            }
            var integrity = false
            rows(db, "PRAGMA integrity_check(1)", 1) { integrity = text(it, 0) == "ok" }
            require(integrity)
            rows(db, "PRAGMA foreign_key_check", 1) { error("Foreign key failure") }
            rows(db, "SELECT id,context_id,source_key,tokens_json,focus_json,target,readings_json,pos_json,fixed,train_rank,source_record_sha256,permission FROM heads ORDER BY id", 4096) { c ->
                val id = text(c, 0); val tokens = strings(text(c, 3)); val focus = JSONArray(text(c, 4))
                require(tokens.isNotEmpty() && tokens.size <= 128 && focus.length() == 2)
                val a = focus.getInt(0); val b = focus.getInt(1); val fixed = integer(c, 8); val rank = integer(c, 9)
                require(a >= 0 && b > a && b <= tokens.size && fixed in 0..1 && rank >= 0)
                require(text(c, 11) == "conditional_source_name_only" && !headMap.containsKey(id))
                val sha = text(c, 10); require(sha.matches(HASH))
                headMap[id] = Head(id, text(c, 1), text(c, 2), tokens, a, b, text(c, 5),
                    text(c, 6), text(c, 7), fixed == 1, rank, sha)
            }
            val edges = mutableMapOf<String, MutableList<String>>()
            rows(db, "SELECT rule_id,head_id,support_components FROM rule_heads ORDER BY rule_id,head_id", 32768) { c ->
                val id = text(c, 0); val head = text(c, 1)
                require(headMap.containsKey(head) && integer(c, 2) >= 2)
                val list = edges.getOrPut(id) { mutableListOf() }; require(head !in list); list += head
            }
            rows(db, "SELECT id,source_key,tokens_json,focus_offset,length,target,ratio,winner_components,winner_weight,source_record_sha256,permission FROM rules ORDER BY id", 4096) { c ->
                val id = text(c, 0); val tokens = strings(text(c, 2)); val focus = integer(c, 3)
                val length = integer(c, 4); val target = text(c, 5)
                val ratio = if (c.isNull(6)) null else number(c, 6)
                val support = integer(c, 7); val weight = number(c, 8); val sha = text(c, 9)
                require(length in 2..8 && tokens.size == length && focus in tokens.indices && support >= 2)
                require((ratio == null || ratio > 1.5) && weight > 0 && sha.matches(HASH))
                require(text(c, 10) == "conditional_research_only")
                val ids = Collections.unmodifiableList(edges[id].orEmpty().toList()); require(ids.all { headMap.getValue(it).target == target })
                loaded += Rule(id, text(c, 1), tokens, focus, target, ratio, support, weight, sha, ids)
            }
            require(headMap.size == 453 && edges.values.sumOf { it.size } == 2091)
            require(loaded.size == 1157 && loaded.map { it.id }.toSet().size == loaded.size)
            require(edges.keys.all { key -> loaded.any { it.id == key } })
            require(loaded.count { it.headIDs.isEmpty() } == 23)
            classifier=FrozenCandidateClassifier(db)
            tuples=FrozenContextTupleEvidence(db,loaded,headMap)
            actual
        }
        require(digest(pack, 16L shl 20) == expectedSHA256)
        candidateClassifier=classifier
        tupleEvidence=tuples
        contentSHA256 = expectedSHA256; metadata = Collections.unmodifiableMap(meta.toMap())
        rules = Collections.unmodifiableList(loaded.toList()); heads = Collections.unmodifiableMap(headMap.toMap()); byKey = rules.groupBy { it.sourceKey }
    }

    fun assess(original: String, nativeWords: List<Range>, focus: Range, sourceKeys: List<String>): Assessment {
        require(original.length <= 16384 && nativeWords.size <= 16384 && sourceKeys.size <= 256)
        require(sourceKeys.all { it.toByteArray(Charsets.UTF_8).size <= 4096 })
        val boundaries = mutableSetOf(0)
        val matcher = Pattern.compile("\\X").matcher(original)
        while (matcher.find()) boundaries += matcher.end()
        var end = 0
        for (range in nativeWords) {
            require(range.start >= end && range.end > range.start && range.end <= original.length)
            require(range.start in boundaries && range.end in boundaries); end = range.end
        }
        require(focus in nativeWords)
        val tokens = tokenizer.tokenize(original); val position = tokens.indexOfFirst { it.range == focus }
        if (position < 0) return Assessment(null, emptyList())
        val native = nativeWords.toSet(); val matches = mutableListOf<Match>()
        for (key in sourceKeys.distinct().sorted()) {
            val parts = JSONArray(key); require(parts.length() > 0 && parts.get(0) is String)
            require(parts.getString(0) == tokens[position].normalized)
            for (rule in byKey[key].orEmpty()) {
                val start = position - rule.focusOffset; val after = start + rule.tokens.size
                if (start < 0 || after > tokens.size) continue
                val window = tokens.subList(start, after)
                if (!window.all { it.hasAlphabeticScalar } || window.map { it.normalized } != rule.tokens) continue
                matches += Match(rule, Range(window.first().range.start, window.last().range.end), start,
                    window.all { it.range in native })
            }
        }
        val ranked = matches.sortedWith(compareByDescending<Match> { it.rule.tokens.size }
            .thenByDescending { it.rule.ratio ?: Double.POSITIVE_INFINITY }
            .thenByDescending { it.rule.components }.thenByDescending { it.rule.weight }
            .thenBy { it.tokenStart }.thenBy { it.rule.id })
        return Assessment(ranked.firstOrNull { it.contextGeometryCompatible }, Collections.unmodifiableList(ranked))
    }

    private companion object {
        val HASH = Regex("[0-9a-f]{64}")
        fun sidecars(file: File) { require(listOf("-wal", "-shm", "-journal").none { File(file.path + it).exists() }) }
        fun digest(file: File, max: Long): String {
            sidecars(file); require(file.isFile && file.length() <= max)
            val digest = MessageDigest.getInstance("SHA-256"); var total = 0L
            file.inputStream().use { input ->
                val buffer = ByteArray(1 shl 20)
                while (true) {
                    val n = input.read(buffer); if (n < 0) break
                    total += n; require(total <= max); digest.update(buffer, 0, n)
                }
            }
            sidecars(file)
            return digest.digest().joinToString("") { "%02x".format(it.toInt() and 255) }
        }
        fun open(file: File): SQLiteDatabase {
            sidecars(file)
            val db = SQLiteDatabase.openDatabase(file.path, null, SQLiteDatabase.OPEN_READONLY or SQLiteDatabase.NO_LOCALIZED_COLLATORS)
            try {
                db.execSQL("PRAGMA query_only=ON")
                db.execSQL("PRAGMA trusted_schema=OFF")
                db.rawQuery("PRAGMA busy_timeout=100", null).use { while (it.moveToNext()) {} }
                return db
            } catch (error: Throwable) { db.close(); throw error }
        }
        fun rows(db: SQLiteDatabase, sql: String, limit: Int, body: (Cursor) -> Unit) {
            db.rawQuery(sql, null).use { c ->
                var count = 0
                while (c.moveToNext()) { require(++count <= limit); body(c) }
            }
        }
        fun text(c: Cursor, i: Int): String {
            require(c.getType(i) == Cursor.FIELD_TYPE_STRING)
            return c.getString(i).also { require(!it.contains('\u0000') && it.toByteArray(Charsets.UTF_8).size <= 1048576) }
        }
        fun integer(c: Cursor, i: Int): Int {
            require(c.getType(i) == Cursor.FIELD_TYPE_INTEGER)
            return c.getLong(i).also { require(it in Int.MIN_VALUE.toLong()..Int.MAX_VALUE.toLong()) }.toInt()
        }
        fun number(c: Cursor, i: Int): Double {
            require(c.getType(i) in setOf(Cursor.FIELD_TYPE_FLOAT, Cursor.FIELD_TYPE_INTEGER))
            return c.getDouble(i).also { require(it.isFinite()) }
        }
        fun strings(value: String): List<String> {
            val array = JSONArray(value)
            require(array.length() <= 128)
            return Collections.unmodifiableList((0 until array.length()).map { require(array.get(it) is String); array.getString(it) })
        }
        fun metadata(db: SQLiteDatabase): Map<String, String> {
            val values = mutableMapOf<String, String>()
            rows(db, "SELECT key,value FROM metadata ORDER BY key", 512) { c ->
                val key = text(c, 0); require(!values.containsKey(key)); values[key] = text(c, 1)
            }
            return values.toMap()
        }
        fun pragma(db: SQLiteDatabase, key: String): Int {
            var value: Int? = null
            rows(db, "PRAGMA $key", 1) { value = integer(it, 0) }
            return requireNotNull(value)
        }
    }
}
