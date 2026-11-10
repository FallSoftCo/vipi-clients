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
