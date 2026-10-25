package co.fallsoft.vipi

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import org.json.JSONObject
import java.io.Closeable
import java.security.MessageDigest
import java.util.UUID

internal data class ChatProfile(val id: UUID, val username: String, val displayName: String) {
    fun json() = JSONObject().put("id", id).put("username", username).put("display_name", displayName)
    companion object { fun parse(value: JSONObject) = ChatProfile(UUID.fromString(value.getString("id")), value.getString("username"), value.getString("display_name")) }
}

/** Main-thread coordinator; transport events, lifecycle and explicit refresh
 * share one synchronization. Durable journal commits always precede receipts. */
internal class ChatSession(private val context: Context, authentication: Authentication, val userID: String) : Closeable {
    private val api = ServiceClient(authentication, userID)
    private val records = PrivateRecords(context)
    private var vault: MessageVault? = null
    private var core: MessagingCore? = null
    private var history: ConversationHistory? = null
    var profile by mutableStateOf<ChatProfile?>(null); private set
    var needsProfile by mutableStateOf(false); private set
    var busy by mutableStateOf(false); private set
    var syncing by mutableStateOf(false); private set
    var ready by mutableStateOf(false); private set
    var threads by mutableStateOf<List<ChatThread>>(emptyList()); private set
    var contacts by mutableStateOf<Map<UUID, ChatProfile>>(emptyMap()); private set
    var revision by mutableStateOf(0); private set
    var notice by mutableStateOf<String?>(null)
    private var syncAgain = false
    private val cacheKey get() = "profile-" + MessageDigest.getInstance("SHA-256").digest(userID.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
    init { records.read(cacheKey)?.let { open(ChatProfile.parse(it)) } }
    private fun open(value: ChatProfile) {
        check(profile == null || profile!!.id == value.id) { "Account changed" }
        if (vault == null) {
            val store = MessageVault(context, value.id); vault = store
            core = MessagingCore(store); history = ConversationHistory(store)
            ready = store.transaction { store.get("local", "registered-device")?.toString(Charsets.UTF_8) == core!!.device.id.toString() }
            contacts = store.transaction { store.ids("contact").associate { key ->
                val contact = ChatProfile.parse(JSONObject(requireNotNull(store.get("contact", key)).toString(Charsets.UTF_8)))
                contact.id to contact
            } }
        }
        profile = value; needsProfile = false; records.write(cacheKey, value.json()); reload()
    }
    private fun reload() { threads = history?.threads() ?: emptyList(); revision++ }
    suspend fun start() {
        if (busy) return
        busy = true; notice = null
        try { open(ChatProfile.parse(api.request("GET", "/v1/me"))); provision() }
        catch (error: CancellationException) { throw error }
        catch (error: ServiceFailure) { if (error.code == "profile_required") needsProfile = true else notice = explanation(error) }
        catch (error: Exception) { notice = explanation(error) }
        finally { busy = false }
        if (ready) synchronize()
    }
    suspend fun createProfile(username: String, name: String) {
        if (busy) return
        busy = true; notice = null
        try {
            open(ChatProfile.parse(api.request("PUT", "/v1/me", JSONObject().put("username", username.trim().lowercase()).put("display_name", name))))
            provision()
        } catch (error: CancellationException) { throw error }
        catch (error: Exception) { notice = explanation(error) }
        finally { busy = false }
        if (ready) synchronize()
    }
    private suspend fun provision() {
        val core = core ?: return; val vault = vault ?: return
        if (!ready) {
            val result = api.request("POST", "/v1/devices", JSONObject().put("device_id", core.device.id).put("secret", core.device.secret))
            check(result.getBoolean("active") && UUID.fromString(result.getString("id")) == core.device.id)
            vault.transaction { vault.put("local", "registered-device", core.device.id.toString().toByteArray(Charsets.UTF_8)) }
            ready = true
        }
        val inventory = api.request("GET", "/v1/keys", device = core.device)
        val hasPending = vault.transaction { vault.get("key-directory", "pending") != null }
        if (hasPending || inventory.getInt("remaining") < 10) {
            val publication = core.keys.publication(System.currentTimeMillis())
            val result = api.request("PUT", "/v1/keys", publication, core.device)
            core.keys.published(result.getInt("revision"))
        }
    }
    suspend fun find(input: String): ChatProfile {
        val core = core; val vault = vault
        if (!ready || core == null || vault == null) throw ServiceFailure(0, "device_not_ready")
        val username = input.trim().lowercase()
        if (!username.matches(Regex("[a-z][a-z0-9_]{2,23}"))) throw ServiceFailure(0, "invalid_username")
        val value = ChatProfile.parse(api.request("GET", "/v1/people/$username", device = core.device))
        if (value.id == profile?.id) throw ServiceFailure(0, "own_username")
        vault.transaction { vault.put("contact", value.id.toString(), value.json().toString().toByteArray(Charsets.UTF_8)) }
        contacts = contacts + (value.id to value); return value
    }
    fun name(peer: UUID) = contacts[peer]?.displayName ?: "New conversation"
    fun messages(peer: UUID, before: String? = null) = history?.messages(peer, before) ?: emptyList()
    fun markRead(peer: UUID) { if (threads.any { it.peer == peer && it.unread > 0 }) { history?.markRead(peer); reload() } }
    fun compose(peer: UUID) = history?.composeDraft(peer) ?: ""
    fun saveCompose(text: String, peer: UUID) { history?.saveComposeDraft(text, peer) }
    fun send(text: String, peer: UUID) {
        val core = core
        if (!ready || core == null) throw ServiceFailure(0, "device_not_ready")
        val now = System.currentTimeMillis()
        core.journal.saveDraft(UUID.randomUUID(), peer, text, now, now, consumeCompose = true); reload()
    }
    private suspend fun establish(peer: UUID) {
        val core = core ?: return; val vault = vault ?: return
        if (core.hasSession(peer)) return
        val requestID = vault.transaction {
            vault.get("pending-claim", peer.toString())?.let { UUID.fromString(it.toString(Charsets.UTF_8)) }
                ?: UUID.randomUUID().also { vault.put("pending-claim", peer.toString(), it.toString().toByteArray(Charsets.UTF_8)) }
        }
        try {
            val response = api.request("POST", "/v1/people/$peer/keys", JSONObject().put("request_id", requestID), core.device)
            core.keys.establish(peer, requestID, response)
            vault.transaction { vault.remove("pending-claim", peer.toString()) }
        } catch (error: ServiceFailure) {
            if (error.status == 410) vault.transaction { vault.remove("pending-claim", peer.toString()) }
            throw error
        }
    }
    suspend fun synchronize() {
        val core = core ?: return
        if (!ready) return
        if (syncing) { syncAgain = true; return }
        syncing = true
        try {
            do {
                syncAgain = false; currentCoroutineContext().ensureActive()
                val inbox = api.request("GET", "/v1/messages/pending", device = core.device).getJSONArray("messages")
                repeat(inbox.length()) { index ->
                    try { core.receive(RoutedMessage.received(inbox.getJSONObject(index), profile!!.id), System.currentTimeMillis()) }
                    catch (_: Exception) { notice = "A message couldn’t be opened securely. Your existing conversations are saved." }
                }
                for (id in core.journal.pendingReceipts()) {
                    val state = api.request("POST", "/v1/messages/$id/receipt", device = core.device).getString("state")
                    if (state in setOf("delivered", "expired", "unavailable", "identity_changed")) core.journal.receiptAccepted(id)
                }
                for (draft in core.journal.pendingDrafts(System.currentTimeMillis()).sortedBy { it.createdAt }) {
                    try {
                        establish(draft.recipient)
                        core.queue(draft.id, draft.recipient, draft.text, draft.createdAt, System.currentTimeMillis())
                    } catch (error: CancellationException) { throw error }
                    catch (error: Exception) { notice = explanation(error) }
                }
                for (envelope in core.journal.pending(System.currentTimeMillis())) {
                    val routed = core.queue(envelope.id, envelope.recipient, requireNotNull(core.journal.outgoing(envelope.id)).text, envelope.createdAt, System.currentTimeMillis())
                    val state = api.request("POST", "/v1/messages", routed.sendJSON(), core.device).getString("state")
                    core.journal.applyStatus(envelope.id, if (state in setOf("unavailable", "identity_changed")) "failed" else state)
                }
            } while (syncAgain)
        } catch (error: CancellationException) { throw error }
        catch (error: Exception) { notice = explanation(error) }
        finally {
            syncing = false
            try { reload() } catch (_: Exception) { notice = "Your saved conversations couldn’t be opened. Please try again." }
        }
    }
    override fun close() { vault?.close() }
    companion object {
        fun explanation(error: Exception): String {
            if (error is ServiceFailure) {
                when (error.code) {
                    "username_unavailable" -> return "That username isn’t available. Try another."
                    "person_not_found" -> return "No one was found with that username. Check the spelling with your friend."
                    "invalid_username" -> return "Use 3–24 letters, numbers or underscores, starting with a letter."
                    "own_username" -> return "That’s your username. Enter your friend’s username to start a conversation."
                    "service_not_available" -> return "Vipi is being prepared for launch. This account isn’t in the preview yet."
                    "device_replacement_confirmation_required" -> return "This account is already active on another device. Moving your account needs a separate confirmation."
                    "recent_sign_in_required", "sign_in_required", "device_revoked" -> return "Please sign in again to reconnect your account. Your saved conversations are still on this device."
                    "recipient_keys_unavailable" -> return "Your friend needs to open Vipi before this first message can be sent. Your message is saved."
                    "device_not_ready" -> return "Connect once to finish setting up this device."
                }
                if (error.status == 429) return "Please wait a moment before trying again. Your messages are saved."
            }
            return "We couldn’t connect. Your messages are saved on this device. Try again when you’re online."
        }
    }
}
