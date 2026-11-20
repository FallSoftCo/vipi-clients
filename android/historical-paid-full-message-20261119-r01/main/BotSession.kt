package co.fallsoft.vipi

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CancellationException
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.util.UUID
import java.util.Locale

internal data class BotAllowance(val available: Boolean, val remaining: Int, val monthly: Int, val resetsAt: Instant, val serviceReady: Boolean) {
    companion object {
        fun parse(value: JSONObject, available: Boolean = value.optBoolean("available", false)): BotAllowance {
            val remaining = value.getInt("remaining_replies"); val monthly = value.getInt("monthly_replies")
            require(monthly >= 0 && remaining in 0..monthly)
            require(value.getString("period").matches(Regex("[0-9]{4}-[0-9]{2}")))
            return BotAllowance(available, remaining, monthly, Instant.parse(value.getString("resets_at")), value.optBoolean("service_ready", false))
        }
    }
}

internal data class BotMessage(val id: String, val role: String, val text: String, val status: String, val requestID: String? = null) {
    fun json() = JSONObject().put("id", id).put("role", role).put("content", text).put("status", status).put("request_id", requestID ?: JSONObject.NULL)
    companion object {
        fun parse(value: JSONObject) = BotMessage(value.getString("id"), value.getString("role"), value.getString("content"), value.getString("status"),
            if (value.isNull("request_id")) null else UUID.fromString(value.getString("request_id")).toString())
    }
}

/** Local bot history shares the account's encrypted vault but no friend-message query path.
 * A request is recorded before network work and never retried automatically. */
internal class BotSession(context: Context, account: UUID, private val api: ChatTransport,
    private val nowMillis: () -> Long = System::currentTimeMillis) : AutoCloseable {
    private val appContext = context.applicationContext
    private val vault = MessageVault(context, account)
    var translations by mutableStateOf<ConversationTranslation?>(null); private set
    private var translationPair: Pair<String, String>? = null
    private val newMessageObservers = mutableMapOf<Any, (String, String) -> Unit>()
    internal fun observeNewMessages(owner: Any, action: (String, String) -> Unit) { newMessageObservers[owner] = action }
    internal fun removeNewMessageObserver(owner: Any) { newMessageObservers.remove(owner) }
    private fun newMessage(id: String, text: String) { newMessageObservers.values.toList().forEach { runCatching { it(id, text) } } }
    internal fun configureTranslations(source: String, target: String, factory: (() -> LanguageTranslation)? = null) {
        if (translationPair == source to target && translations != null) return
        translations?.close()
        translationPair = source to target
        translations = ConversationTranslation(appContext, source, target, FullMessageTranslationStore(vault), translator = factory?.invoke() ?: LocalTranslation())
        replaySavedTranslations()
    }
    internal fun messageOriginal(id: String): String? {
        if (closed) return null
        return vault.transaction { vault.get("bot-message", id)?.let { BotMessage.parse(JSONObject(it.toString(Charsets.UTF_8))).text } }
    }
    private fun translateDurable(id: String) {
        val owner = java.lang.ref.WeakReference(this)
        translations?.enqueueStored(id) { owner.get()?.messageOriginal(id) }
    }
    private fun replaySavedTranslations() {
        translations?.replaySaved { sequence {
            var before: String? = null
            while (true) {
                val page = vault.transaction {
                    vault.pageIDs("bot-message", "m", before = before, limit = 16).map { id ->
                        BotMessage.parse(JSONObject(requireNotNull(vault.get("bot-message", id)).toString(Charsets.UTF_8)))
                    }
                }
                for (message in page) yield(ConversationTranslation.SavedMessage(message.id, message.text))
                if (page.size < 16) break
                before = page.last().id
            }
        } }
    }
    private var closed = false
    private var allowanceRevision = 0L
    var messages by mutableStateOf<List<BotMessage>>(emptyList()); private set
    var earlierAvailable by mutableStateOf(false); private set
    var draft by mutableStateOf(""); private set
    var consent by mutableStateOf(false); private set
    var busy by mutableStateOf(false); private set
    var reporting by mutableStateOf(false); private set
    var notice by mutableStateOf<String?>(null); private set
    var allowance by mutableStateOf<BotAllowance?>(null); private set
    init {
        vault.transaction {
            consent = vault.get("bot-settings", "consent")?.toString(Charsets.UTF_8) == "deepseek-v1"
            draft = vault.get("bot-settings", "draft")?.toString(Charsets.UTF_8).orEmpty()
            val ids = vault.pageIDs("bot-message", "m", limit = 50)
            messages = ids.reversed().map { BotMessage.parse(JSONObject(requireNotNull(vault.get("bot-message", it)).toString(Charsets.UTF_8))) }
            earlierAvailable = ids.size == 50
        }
    }
    fun acceptConsent() { check(!closed); vault.transaction { vault.put("bot-settings", "consent", "deepseek-v1".toByteArray()) }; consent = true }
    fun saveDraft(value: String) { check(!closed); require(value.toByteArray(Charsets.UTF_8).size <= ConversationHistory.MAX_DRAFT_BYTES); vault.transaction { vault.put("bot-settings", "draft", value.toByteArray()) }; draft = value }
    fun earlier() {
        check(!closed)
        vault.transaction {
            val ids = vault.pageIDs("bot-message", "m", before = messages.firstOrNull()?.id, limit = 50)
            messages = ids.reversed().map { BotMessage.parse(JSONObject(requireNotNull(vault.get("bot-message", it)).toString(Charsets.UTF_8))) } + messages
            earlierAvailable = ids.size == 50
        }
    }
    suspend fun refreshAllowance() {
        if (closed) return
        val revision = ++allowanceRevision
        try {
            val response = api.request("GET", "/v1/bot/allowance")
            require(response.getInt("max_context_bytes") == 8192)
            val value = BotAllowance.parse(response)
            if (!closed && revision == allowanceRevision) allowance = value
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { if (!closed && revision == allowanceRevision) { allowance = null; notice = appContext.getString(R.string.bot_allowance_check_failed) } }
    }
    suspend fun send() {
        if (closed || busy || !consent || draft.isBlank() || allowance?.let { it.available && it.remaining > 0 && it.resetsAt.isAfter(Instant.now()) } != true) return
        busy = true; notice = null
        ++allowanceRevision // An earlier quota read cannot authorize another send after this request.
        val requestID = UUID.randomUUID().toString()
        val user = BotMessage("m%019d-%s".format(Locale.ROOT, nextMessageMillis(), requestID), "user", draft.trim(), "unconfirmed", requestID)
        var recorded = false
        try {
            val device = DeviceCredential.registered(vault) ?: run {
                notice = appContext.getString(R.string.bot_device_not_ready)
                return
            }
            val context = contextFor(messages, user)
            vault.transaction { vault.put("bot-message", user.id, user.json().toString().toByteArray()); vault.remove("bot-settings", "draft") }
            recorded = true; messages = messages + user; draft = ""
            translateDurable(user.id)
            newMessage(user.id, user.text)
            val response = api.request("POST", "/v1/bot/messages", JSONObject().put("request_id", requestID).put("consent_version", "deepseek-v1").put("messages", context), device)
            if (closed) return
            require(response.getString("request_id") == requestID)
            val reply = response.getString("reply"); require(reply.isNotBlank() && reply.toByteArray().size <= 65_536)
            val confirmed = user.copy(status = "confirmed")
            val answer = BotMessage("m%019d-%s".format(Locale.ROOT, nowMillis().coerceAtLeast(user.id.substring(1, 20).toLong() + 1), UUID.randomUUID()), "assistant", reply, "confirmed", requestID)
            val updatedAllowance = BotAllowance.parse(response.getJSONObject("allowance"))
            vault.transaction {
                vault.put("bot-message", user.id, confirmed.json().toString().toByteArray())
                vault.put("bot-message", answer.id, answer.json().toString().toByteArray())
            }
            messages = messages.map { if (it.id == user.id) confirmed else it } + answer
            translateDurable(answer.id)
            newMessage(answer.id, answer.text)
            ++allowanceRevision
            allowance = updatedAllowance
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) {
            val deviceRejected = recorded && failure is ServiceFailure && failure.code == "device_revoked"
            if (!closed && deviceRejected) {
                val rejected = user.copy(status = "rejected")
                vault.transaction { vault.put("bot-message", user.id, rejected.json().toString().toByteArray()) }
                messages = messages.map { if (it.id == user.id) rejected else it }
            }
            if (!closed) notice = when {
                deviceRejected -> appContext.getString(R.string.bot_device_unauthorized)
                failure is ServiceFailure && failure.code == "monthly_allowance_reached" -> appContext.getString(R.string.bot_allowance_exhausted)
                recorded -> appContext.getString(R.string.bot_reply_unconfirmed)
                else -> appContext.getString(R.string.bot_message_not_saved)
            }
            if (!closed && recorded) { ++allowanceRevision; allowance = null }
        } finally { if (!closed) busy = false }
    }
    suspend fun report(message: BotMessage, reason: String, selected: String): Boolean {
        if (closed || reporting) return false
        require(message.role == "assistant" && message.requestID != null && messages.contains(message))
        require(reason in setOf("harmful", "inaccurate", "other") && selected.isNotBlank() && message.text.contains(selected) && selected.toByteArray(Charsets.UTF_8).size <= 4000)
        reporting = true
        try {
            val reply = api.request("POST", "/v1/bot/reports", JSONObject().put("request_id", message.requestID).put("reason", reason).put("selected_reply", selected), requireNotNull(DeviceCredential.registered(vault)))
            check(reply.getBoolean("reported"))
            if (closed) return false
            vault.transaction { vault.put("bot-reported", message.requestID, byteArrayOf(1)) }
            notice = appContext.getString(R.string.bot_report_received); return true
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { if (!closed) notice = appContext.getString(R.string.bot_report_unconfirmed); return false }
        finally { if (!closed) reporting = false }
    }
    private fun nextMessageMillis(): Long = nowMillis().coerceAtLeast(
        (messages.lastOrNull()?.id?.substring(1, 20)?.toLongOrNull() ?: -1L) + 1)
    override fun close() { closed = true; ++allowanceRevision; newMessageObservers.clear(); translations?.close(); translations = null; vault.close() }
    companion object {
        fun contextFor(history: List<BotMessage>, latest: BotMessage): JSONArray {
            require(latest.role == "user" && latest.text.isNotBlank() && latest.text.toByteArray(Charsets.UTF_8).size <= 8192)
            val selected = (history.filter { it.status == "confirmed" && it.role in setOf("user", "assistant") } + latest).takeLast(12).toMutableList()
            while (selected.sumOf { it.text.toByteArray(Charsets.UTF_8).size } > 8192) selected.removeAt(0)
            while (selected.first().role != "user") selected.removeAt(0)
            return JSONArray().apply { selected.forEach { put(JSONObject().put("role", it.role).put("content", it.text)) } }
        }
    }
}
