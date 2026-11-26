package co.fallsoft.vipi

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

internal enum class FeedbackPrompt { SURVEY, REVIEW }
internal enum class FundingChoice(val wire: String) { YES("yes"), MAYBE("maybe"), NO("no"), SKIP("skip") }

/** Per-account encrypted records. No text, recipient, or usage counters leave the device. */
internal class LaunchFeedback(private val vault: MessageVault) {
    companion object {
        const val PATH = "/v1/me/surveys/private-chat-usd1-v1"
        private const val DAY = 86_400_000L
        private const val KEY = "private-chat-usd1-v1"
        private val successful = setOf("accepted", "delivered", "read")

        fun directAccepted(vault: MessageVault, id: String, authoredAt: Long) = record(vault, "d/$id", authoredAt)
        fun groupAccepted(vault: MessageVault, id: String, authoredAt: Long) = record(vault, "g/$id", authoredAt)

        private fun record(vault: MessageVault, id: String, authoredAt: Long) {
            // The first forty distinct messages suffice even when the fourteenth day arrives later.
            if (vault.get("local", "chat-usage-complete") != null) return
            val bytes = vault.get("local", "chat-usage")
            val usage = bytes?.let { JSONObject(it.toString(Charsets.UTF_8)) } ?: JSONObject()
            val ids = usage.optJSONArray("ids") ?: JSONArray()
            val days = usage.optJSONArray("days") ?: JSONArray()
            val day = Math.floorDiv(authoredAt, DAY)
            val newId = ids.length() < 40 && (0 until ids.length()).none { ids.getString(it) == id }
            val newDay = days.length() < 14 && (0 until days.length()).none { days.getLong(it) == day }
            if (!newId && !newDay) return
            if (newId) ids.put(id)
            if (newDay) days.put(day)
            if (ids.length() == 40 && days.length() == 14) {
                vault.put("local", "chat-usage-complete", byteArrayOf(1))
                vault.remove("local", "chat-usage")
            } else vault.put("local", "chat-usage", usage.put("ids", ids).put("days", days).toString().toByteArray())
        }
    }

    /** Bounded pages release the messaging database between reads. Fresh receipts use the same deduplication. */
    suspend fun includeEarlierMessages() = withContext(Dispatchers.IO) {
        for (kind in listOf("outgoing", "group-message")) {
            val cursorKey = "feedback-history-$kind"
            while (true) {
                currentCoroutineContext().ensureActive()
                val more = vault.transaction {
                    val cursor = vault.get("local", cursorKey)?.toString(Charsets.UTF_8)
                    if (cursor == "" || vault.get("local", "chat-usage-complete") != null) return@transaction false
                    val ids = vault.pageIDs(kind, "", before = cursor, limit = 40)
                    for (id in ids) {
                        val raw = vault.get(kind, id) ?: continue
                        val data = JSONObject(raw.toString(Charsets.UTF_8))
                        if (data.optJSONObject("chat_features")?.has("reaction") == true) continue
                        if (kind == "outgoing" && data.optString("state") in successful) {
                            val envelope = data.getJSONObject("envelope")
                            if (envelope.getString("sender") == vault.account.toString())
                                directAccepted(vault, id, envelope.getLong("createdAt"))
                        } else if (kind == "group-message" && data.optString("sender") == vault.account.toString() &&
                            data.optString("delivery") == GroupDelivery.ACCEPTED.name) {
                            groupAccepted(vault, data.getString("id"), data.getLong("createdAt"))
                        }
                    }
                    vault.put("local", cursorKey, (if (ids.size < 40) "" else ids.last()).toByteArray())
                    ids.size == 40
                }
                if (!more) break
                kotlinx.coroutines.yield()
            }
        }
    }

    private fun state() = vault.get("local", KEY)?.let { JSONObject(it.toString(Charsets.UTF_8)) } ?: JSONObject()
    private fun save(s: JSONObject) = vault.put("local", KEY, s.toString().toByteArray())

    fun eligible(kind: FeedbackPrompt, session: String, now: Long) = vault.transaction { eligibleInTransaction(kind, session, now) }
    private fun eligibleInTransaction(kind: FeedbackPrompt, session: String, now: Long): Boolean {
        val s = state()
        if (s.has(kind.name) || s.optString("session") == session) return false
        val previous = maxOf(s.optLong("SURVEY", 0), s.optLong("REVIEW", 0))
        if (previous > 0 && now - previous < 7 * DAY) return false
        if (vault.get("local", "chat-usage-complete") != null) return true
        val u = vault.get("local", "chat-usage")?.let { JSONObject(it.toString(Charsets.UTF_8)) } ?: return false
        return kind == FeedbackPrompt.SURVEY && u.getJSONArray("ids").length() >= 20 && u.getJSONArray("days").length() >= 7
    }
    fun claim(kind: FeedbackPrompt, session: String, now: Long) = vault.transaction {
        if (!eligibleInTransaction(kind, session, now)) false
        else { save(state().put(kind.name, now).put("session", session)); true }
    }
    fun queue(choice: FundingChoice) = vault.transaction {
        val s = state()
        if (s.has("SURVEY") && !s.has("decision")) save(s.put("decision", true).put("pending", choice.wire))
    }
    fun pending(): String? = vault.transaction { state().optString("pending").ifEmpty { null } }
    fun submitted(choice: String) = vault.transaction {
        val s = state()
        if (s.optString("pending") == choice) { s.remove("pending"); save(s) }
    }
}
