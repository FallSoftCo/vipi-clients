package co.fallsoft.vipi

import co.fallsoft.vipi.core.ImmersionSpan
import co.fallsoft.vipi.core.VocabularyFamiliarity
import java.security.SecureRandom
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec
import java.util.Locale
import org.json.JSONObject

/** Account-local encrypted counters, not message text or a mastery score. */
internal class VocabularyFamiliarityStore(private val vault: MessageVault) {
    private val cached = mutableMapOf<String, VocabularyFamiliarity>()
    private var idKey: ByteArray? = null
    @Volatile var sourceHistoryRevision: Long = 0L
        private set
    private fun key(span: ImmersionSpan, source: String, target: String): String {
        val secret = idKey ?: vault.transaction {
            vault.get("immersion-metadata", "id-key-v1")?.also { require(it.size == 32) }
                ?: ByteArray(32).also { SecureRandom().nextBytes(it); vault.put("immersion-metadata", "id-key-v1", it) }
        }.also { idKey = it }
        // A keyed identifier prevents dictionary guessing from SQLite metadata.
        return Mac.getInstance("HmacSHA256").apply { init(SecretKeySpec(secret, "HmacSHA256")) }
            .doFinal(listOf("v1", source, target, span.original.lowercase(Locale.ROOT), span.translated)
                .joinToString("\u0000").toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
    }
    private fun sourceUnitKey(unit: co.fallsoft.vipi.core.SourceReferenceUnit, source: String, target: String): String? {
        // Only reviewed frame identity is stable evidence; legacy/ambiguous candidates remain unseen.
        val identity = unit.learningIdentity ?: return null
        if (identity.patternId.isBlank() || identity.meaning.isBlank() || identity.reading != (unit.reading ?: "") ||
            unit.referenceId != "frame:${unit.catalogSha256}:${identity.patternId}") return null
        val secret = idKey ?: vault.transaction {
            vault.get("immersion-metadata", "id-key-v1")?.also { require(it.size == 32) }
                ?: ByteArray(32).also { SecureRandom().nextBytes(it); vault.put("immersion-metadata", "id-key-v1", it) }
        }.also { idKey = it }
        val fields = listOf("v2-frame-sense-1", source, target, identity.patternId, unit.original, unit.translated, identity.meaning, identity.reading)
        val encoded = encodeFrameIdentity(fields)
        return Mac.getInstance("HmacSHA256").apply { init(SecretKeySpec(secret, "HmacSHA256")) }
            .doFinal(encoded).joinToString("") { "%02x".format(it) }
    }
    @Synchronized fun sourceSeenBatch(units: List<co.fallsoft.vipi.core.SourceReferenceUnit>, source: String, target: String, day: Int): Map<co.fallsoft.vipi.core.SourceReferenceUnit, co.fallsoft.vipi.core.AdditiveExposureSelection.Seen> {
        val unknown = co.fallsoft.vipi.core.AdditiveExposureSelection.Seen(false, available = false)
        val unseen = co.fallsoft.vipi.core.AdditiveExposureSelection.Seen(false)
        return try {
            val ids = units.associateWith { sourceUnitKey(it, source, target) }
            vault.transaction { ids.mapValues { (_, id) ->
                if (id == null) unseen else try {
                    val bytes = vault.get("immersion-frame-exposure-next", id)
                    if (bytes == null) unseen else {
                        val record = JSONObject(bytes.toString(Charsets.UTF_8)); val last = record.getInt("lastDay"); val days = record.getInt("exposureDays")
                        require(last in 0..3_000_000 && days in 1..3650)
                        val interval = when (days) { 1 -> 1; 2 -> 2; 3 -> 4; 4 -> 7; else -> 14 }
                        co.fallsoft.vipi.core.AdditiveExposureSelection.Seen(true, day.toLong() - last >= interval)
                    }
                } catch (_: Exception) { unknown }
            } }
        } catch (_: Exception) { units.associateWith { unknown } }
    }
    @Synchronized fun sourceSeen(unit: co.fallsoft.vipi.core.SourceReferenceUnit, source: String, target: String, day: Int) =
        sourceSeenBatch(listOf(unit), source, target, day).getValue(unit)
    @Synchronized fun observeSourceUnits(units: List<co.fallsoft.vipi.core.SourceReferenceUnit>, source: String, target: String, day: Int): Boolean {
        if (day !in 0..3_000_000 || units.isEmpty()) return false
        return try {
            val ids = units.mapNotNull { sourceUnitKey(it, source, target) }.toSet()
            val updates = mutableMapOf<String, Int>()
            vault.transaction { ids.forEach { id ->
                val old = vault.get("immersion-frame-exposure-next", id)?.let { JSONObject(it.toString(Charsets.UTF_8)) }
                val last = old?.getInt("lastDay") ?: -1; val count = old?.getInt("exposureDays") ?: 0
                require(last in -1..3_000_000 && count in 0..3650)
                if (day > last) { vault.put("immersion-frame-exposure-next", id, JSONObject().put("lastDay",day).put("exposureDays",(count+1).coerceAtMost(3650)).toString().toByteArray(Charsets.UTF_8)); updates[id] = day }
            } }
            if (updates.isNotEmpty()) sourceHistoryRevision++
            updates.isNotEmpty()
        } catch (_: Exception) { false }
    }
    private fun read(key: String): VocabularyFamiliarity {
        val data = vault.get("immersion-exposure", key) ?: return VocabularyFamiliarity()
        val value = JSONObject(data.toString(Charsets.UTF_8))
        val day = value.getInt("lastDay"); require(day in -1..3_000_000)
        return VocabularyFamiliarity(value.getInt("exposureDays"), day)
    }
    @Synchronized fun targetMilliseconds(spans: List<ImmersionSpan>, source: String, target: String, day: Int): Long {
        if (spans.isEmpty()) return 4500
        return try {
            val ids = spans.map { key(it, source, target) }
            if (ids.all { it in cached }) return ids.minOf { cached.getValue(it).targetMilliseconds(day) }
            vault.transaction {
            ids.minOf { id ->
                val record = cached[id] ?: read(id).also { if (cached.size < 4096) cached[id] = it }
                record.targetMilliseconds(day)
            }
        } } catch (_: Exception) { 4500L }
    }
    /** Only a complete visible target dwell earns exposure; same-day flips don't accumulate. */
    @Synchronized fun observe(spans: List<ImmersionSpan>, source: String, target: String, day: Int): Boolean {
        if (day !in 0..3_000_000 || spans.isEmpty()) return false
        return try {
            val ids = spans.map { key(it, source, target) }.toSet().filter { cached[it]?.lastDay != day }
            if (ids.isEmpty()) return true
            val saved = vault.transaction {
                ids.associateWith { id ->
                    val old = read(id); val value = old.observe(day)
                    if (value != old) vault.put("immersion-exposure", id, JSONObject()
                        .put("exposureDays", value.exposureDays).put("lastDay", value.lastDay).toString().toByteArray(Charsets.UTF_8))
                    value
                }
            }
            if (cached.size + saved.size > 4096) cached.clear()
            cached.putAll(saved); true
        } catch (_: Exception) { false }
    }
}

/** Shared exact UTF-8 framing; callers establish reviewed provenance separately. */
internal fun encodeFrameIdentity(fields: List<String>): ByteArray {
    require(fields.size == 8)
    val bytes = java.io.ByteArrayOutputStream()
    java.io.DataOutputStream(bytes).use { out -> fields.forEach { field ->
        val utf8 = field.toByteArray(Charsets.UTF_8); out.writeInt(utf8.size); out.write(utf8)
    } }
    return bytes.toByteArray()
}
