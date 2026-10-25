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
internal class ChatSession(private val context: Context, private val api: ChatTransport, val userID: String) : Closeable {
    constructor(context: Context, authentication: Authentication, userID: String) : this(context, ServiceClient(authentication, userID), userID)
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
    var blockedPeers by mutableStateOf<Set<UUID>>(emptySet()); private set
    var revision by mutableStateOf(0); private set
    var notice by mutableStateOf<String?>(null)
    private var syncAgain = false
    private var closed = false
    private val blockVersions = mutableMapOf<UUID, Int>()
    private val changingBlocks = mutableSetOf<UUID>()
    private val cacheKey get() = "profile-" + MessageDigest.getInstance("SHA-256").digest(userID.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
    init { records.read(cacheKey)?.let { open(ChatProfile.parse(it)) } }
    private fun open(value: ChatProfile) {
        ensureOpen()
        check(profile == null || profile!!.id == value.id) { "Account changed" }
        if (vault == null) {
            val store = MessageVault(context, value.id); vault = store
            core = MessagingCore(store); history = ConversationHistory(store)
            ready = store.transaction { store.get("local", "registered-device")?.toString(Charsets.UTF_8) == core!!.device.id.toString() }
            contacts = store.transaction { store.ids("contact").associate { key ->
                val contact = ChatProfile.parse(JSONObject(requireNotNull(store.get("contact", key)).toString(Charsets.UTF_8)))
                contact.id to contact
            } }
            blockedPeers = store.transaction { store.ids("blocked").map(UUID::fromString).toSet() }
        }
        profile = value; needsProfile = false; records.write(cacheKey, value.json()); reload()
    }
    private fun reload() { threads = history?.threads() ?: emptyList(); revision++ }
    suspend fun start() {
        if (busy || closed) return
        busy = true; notice = null
        try { open(ChatProfile.parse(request("GET", "/v1/me"))); provision() }
        catch (error: CancellationException) { throw error }
        catch (error: ServiceFailure) { if (error.code == "profile_required") needsProfile = true else notice = explanation(error) }
        catch (error: Exception) { notice = explanation(error) }
        finally { busy = false }
        if (ready) synchronize()
    }
    suspend fun createProfile(username: String, name: String) {
        if (busy || closed) return
        busy = true; notice = null
        try {
            open(ChatProfile.parse(request("PUT", "/v1/me", JSONObject().put("username", username.trim().lowercase()).put("display_name", name))))
            provision()
        } catch (error: CancellationException) { throw error }
        catch (error: Exception) { notice = explanation(error) }
        finally { busy = false }
        if (ready) synchronize()
    }
    private suspend fun provision() {
        val core = core ?: return; val vault = vault ?: return
        if (!ready) {
            val result = request("POST", "/v1/devices", JSONObject().put("device_id", core.device.id).put("secret", core.device.secret))
            check(result.getBoolean("active") && UUID.fromString(result.getString("id")) == core.device.id)
            vault.transaction { vault.put("local", "registered-device", core.device.id.toString().toByteArray(Charsets.UTF_8)) }
            ready = true
        }
        val inventory = request("GET", "/v1/keys", device = core.device)
        val hasPending = vault.transaction { vault.get("key-directory", "pending") != null }
        if (hasPending || inventory.getInt("remaining") < 10) {
            val publication = core.keys.publication(System.currentTimeMillis())
            val result = request("PUT", "/v1/keys", publication, core.device)
            core.keys.published(result.getInt("revision"))
        }
    }
    suspend fun find(input: String): ChatProfile {
        val core = core; val vault = vault
        if (!ready || core == null || vault == null) throw ServiceFailure(0, "device_not_ready")
        val username = input.trim().lowercase()
        if (!username.matches(Regex("[a-z][a-z0-9_]{2,23}"))) throw ServiceFailure(0, "invalid_username")
        val value = ChatProfile.parse(request("GET", "/v1/people/$username", device = core.device))
        if (value.id == profile?.id) throw ServiceFailure(0, "own_username")
        vault.transaction { vault.put("contact", value.id.toString(), value.json().toString().toByteArray(Charsets.UTF_8)) }
        contacts = contacts + (value.id to value); return value
    }
    fun name(peer: UUID) = contacts[peer]?.displayName ?: "New conversation"
    suspend fun refreshBlock(peer: UUID) {
        val core = core ?: throw ServiceFailure(0, "device_not_ready")
        if (peer in changingBlocks) return
        val version = blockVersions[peer] ?: 0
        val blocked = request("GET", "/v1/blocks/$peer", device = core.device).getBoolean("blocked")
        if (version == (blockVersions[peer] ?: 0) && peer !in changingBlocks) recordBlock(blocked, peer)
    }
    suspend fun setBlocked(blocked: Boolean, peer: UUID) {
        val core = core
        if (!ready || core == null) throw ServiceFailure(0, "device_not_ready")
        if (!changingBlocks.add(peer)) throw ServiceFailure(0, "block_in_progress")
        blockVersions[peer] = (blockVersions[peer] ?: 0) + 1
        try {
            val value = request("PUT", "/v1/blocks/$peer", JSONObject().put("blocked", blocked), core.device)
            check(value.getBoolean("blocked") == blocked)
            recordBlock(blocked, peer)
        } finally { changingBlocks.remove(peer) }
    }
    private fun recordBlock(blocked: Boolean, peer: UUID) {
        val core = core ?: return
        core.journal.setBlocked(blocked, peer)
        blockedPeers = if (blocked) blockedPeers + peer else blockedPeers - peer
        reload()
    }
    fun messages(peer: UUID, before: String? = null) = history?.messages(peer, before) ?: emptyList()
    fun securityNumber(peer: UUID): SecurityNumber? = (core ?: throw ServiceFailure(0, "device_not_ready")).securityNumber(peer)
    fun setIdentityVerified(verified: Boolean, peer: UUID, compared: SecurityNumber) {
        (core ?: throw ServiceFailure(0, "device_not_ready")).setIdentityVerified(verified, peer, compared); revision++
    }
    fun markRead(peer: UUID) { if (threads.any { it.peer == peer && it.unread > 0 }) { history?.markRead(peer); reload() } }
    fun compose(peer: UUID) = history?.composeDraft(peer) ?: ""
    fun saveCompose(text: String, peer: UUID) { history?.saveComposeDraft(text, peer) }
    fun send(text: String, peer: UUID) {
        val core = core
        if (!ready || core == null) throw ServiceFailure(0, "device_not_ready")
        val now = System.currentTimeMillis()
        if (peer in blockedPeers) throw ServiceFailure(0, "contact_blocked")
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
            val response = request("POST", "/v1/people/$peer/keys", JSONObject().put("request_id", requestID), core.device)
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
                var cursor: String? = null
                val seenCursors = mutableSetOf<String>()
                // Queue capacity is 10,000; restart at its beginning next sync
                // so transient decryption failures can recover.
                for (page in 0 until 100) {
                    currentCoroutineContext().ensureActive()
                    val result = request("GET", "/v1/messages/pending", device = core.device, query = cursor?.let { mapOf("after" to it) } ?: emptyMap())
                    val inbox = result.getJSONArray("messages")
                    repeat(inbox.length()) { index ->
                        try {
                            val item = RoutedMessage.received(inbox.getJSONObject(index), profile!!.id)
                            if (item.envelope.sender !in blockedPeers) core.receive(item, System.currentTimeMillis())
                        }
                        catch (_: Exception) { notice = "A message couldn’t be opened securely. Your existing conversations are saved." }
                    }
                    if (!result.has("next_cursor") || result.isNull("next_cursor")) break
                    val next = result.getString("next_cursor")
                    if (!seenCursors.add(next)) throw ServiceFailure(0, "invalid_inbox_cursor")
                    cursor = next
                }
                for (id in core.journal.pendingReceipts()) {
                    try {
                        val state = request("POST", "/v1/messages/$id/receipt", device = core.device).getString("state")
                        if (state in setOf("delivered", "expired", "unavailable", "identity_changed")) core.journal.receiptAccepted(id)
                    } catch (error: ServiceFailure) {
                        if (error.status == 404 && error.code == "message_not_found") core.journal.receiptAccepted(id)
                        else if (error.status == 429) break
                        else throw error
                    }
                }
                for (draft in core.journal.pendingDrafts(System.currentTimeMillis()).sortedBy { it.createdAt }) {
                    try {
                        if (draft.recipient in blockedPeers) continue
                        establish(draft.recipient)
                        if (draft.recipient in blockedPeers) continue
                        core.queue(draft.id, draft.recipient, draft.text, draft.createdAt, System.currentTimeMillis())
                    } catch (error: CancellationException) { throw error }
                    catch (error: Exception) { notice = explanation(error) }
                }
                for (envelope in core.journal.pending(System.currentTimeMillis())) {
                    if (envelope.recipient in blockedPeers) continue
                    try {
                        val routed = core.queue(envelope.id, envelope.recipient, requireNotNull(core.journal.outgoing(envelope.id)).text, envelope.createdAt, System.currentTimeMillis())
                        val state = request("POST", "/v1/messages", routed.sendJSON(), core.device).getString("state")
                        core.journal.applyStatus(envelope.id, if (state in setOf("unavailable", "identity_changed")) "failed" else state)
                    } catch (error: ServiceFailure) {
                        val state = terminalSendState(error)
                        if (state != null) core.journal.applyStatus(envelope.id, state)
                        else if (error.code != "recipient_queue_full") throw error
                        notice = explanation(error)
                    }
                }
            } while (syncAgain)
        } catch (error: CancellationException) { throw error }
        catch (error: Exception) { notice = explanation(error) }
        finally {
            syncing = false
            try { reload() } catch (_: Exception) { notice = "Your saved conversations couldn’t be opened. Please try again." }
        }
    }
    override fun close() {
        closed = true; ready = false; needsProfile = false; syncAgain = false
        vault?.close(); vault = null; core = null; history = null
        profile = null; threads = emptyList(); contacts = emptyMap(); blockedPeers = emptySet()
    }
    private fun ensureOpen() { if (closed) throw CancellationException("Chat session closed") }
    private suspend fun request(method: String, path: String, body: JSONObject? = null,
                                device: DeviceCredential? = null, query: Map<String, String> = emptyMap()): JSONObject {
        ensureOpen(); currentCoroutineContext().ensureActive()
        return try {
            val result = api.request(method, path, body, device, query)
            ensureOpen(); currentCoroutineContext().ensureActive(); result
        } catch (error: Exception) { ensureOpen(); throw error }
    }
    companion object {
        private fun terminalSendState(error: ServiceFailure): String? = when {
            error.status == 410 && error.code == "message_expired" -> "expired"
            error.status == 404 && error.code == "recipient_unavailable" -> "failed"
            error.status == 409 && error.code in setOf("recipient_identity_changed", "message_id_conflict") -> "failed"
            error.status == 400 && error.code in setOf("invalid_ciphertext", "invalid_ciphertext_size", "invalid_cipher_type") -> "failed"
            else -> null
        }
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
                    "contact_blocked" -> return "Unblock this person to send a new message."
                    "message_expired" -> return "This message expired before delivery. You can send it again."
                    "recipient_unavailable", "recipient_identity_changed", "message_id_conflict", "invalid_ciphertext", "invalid_ciphertext_size", "invalid_cipher_type" -> return "A message couldn’t be delivered. Your other conversations can continue."
                }
                if (error.status == 429) return "Please wait a moment before trying again. Your messages are saved."
            }
            return "Can’t connect. Messages are saved here."
        }
    }
}
