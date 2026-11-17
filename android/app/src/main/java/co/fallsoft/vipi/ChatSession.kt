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
    var familiarity: VocabularyFamiliarityStore? = null; private set
    var profile by mutableStateOf<ChatProfile?>(null); private set
    var needsProfile by mutableStateOf(false); private set
    var busy by mutableStateOf(false); private set
    var syncing by mutableStateOf(false); private set
    var ready by mutableStateOf(false); private set
    var threads by mutableStateOf<List<ChatThread>>(emptyList()); private set
    var contacts by mutableStateOf<Map<UUID, ChatProfile>>(emptyMap()); private set
    var blockedPeers by mutableStateOf<Set<UUID>>(emptySet()); private set
    var peersNeedingRecovery by mutableStateOf<Set<UUID>>(emptySet()); private set
    var revision by mutableStateOf(0); private set
    var notice by mutableStateOf<String?>(null)
    var needsPlan by mutableStateOf(false); private set
    var needsReauthentication by mutableStateOf(false); private set
    var needsDeviceRecovery by mutableStateOf(false); private set
    var recoveryNeedsSignIn by mutableStateOf(false); private set
    private var syncAgain = false
    var lastSyncComplete = false; private set
    private var syncDone: kotlinx.coroutines.CompletableDeferred<Unit>? = null
    @Volatile private var closed = false
    private var historyBusy = false
    private var historyDone: kotlinx.coroutines.CompletableDeferred<Unit>? = null
    private var importedNames = emptyMap<UUID, String>()
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
            familiarity = VocabularyFamiliarityStore(store)
            ready = store.transaction { store.get("local", "registered-device")?.toString(Charsets.UTF_8) == core!!.device.id.toString() }
            contacts = store.transaction { store.ids("contact").associate { key ->
                val contact = ChatProfile.parse(JSONObject(requireNotNull(store.get("contact", key)).toString(Charsets.UTF_8)))
                contact.id to contact
            } }
            blockedPeers = store.transaction { store.ids("blocked").map(UUID::fromString).toSet() }
            peersNeedingRecovery = store.transaction { store.ids("peer-recovery-needed").map(UUID::fromString).toSet() }
        }
        profile = value; needsProfile = false; records.write(cacheKey, value.json()); reload()
    }
    private fun reload() {
        threads = history?.threads() ?: emptyList()
        importedNames = vault?.let { store -> store.transaction { store.ids("imported-peer").mapNotNull { id ->
            val row = JSONObject(requireNotNull(store.get("imported-peer", id)).toString(Charsets.UTF_8))
            if (row.isNull("display_name")) null else UUID.fromString(id) to row.getString("display_name")
        }.toMap() } } ?: emptyMap()
        revision++
    }
    private suspend fun <T> historyOperation(block: (HistoryBackupStore, () -> Unit) -> T): T =
        kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main.immediate) {
            ensureOpen(); check(!historyBusy && !busy) { "Please wait for message delivery to finish and try again" }
            val store = requireNotNull(vault); historyBusy = true
            historyDone = kotlinx.coroutines.CompletableDeferred()
            val job = currentCoroutineContext()[kotlinx.coroutines.Job]
            try {
                // Returning from the system file picker also resumes foreground inbox sync.
                // Reserve this operation, then await that sync before opening the history.
                syncDone?.await(); ensureOpen()
                kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
                block(HistoryBackupStore(store)) { job?.ensureActive(); check(!closed) }
            } } finally {
                historyBusy = false; historyDone?.complete(Unit); historyDone = null
                if (!closed) reload()
            }
        }
    suspend fun exportHistory(file: java.io.File, password: String) = historyOperation { store, check -> store.export(file, password, check) }
    suspend fun inspectHistory(file: java.io.File, password: String) = historyOperation { store, check -> store.validate(file, password, check) }
    suspend fun importHistory(file: java.io.File, password: String, confirmed: HistoryBackupCodec.Inspection) = historyOperation { store, check -> store.merge(file, password, confirmed, check) }
    suspend fun start() {
        if (busy || closed) return
        busy = true; notice = null; recoveryNeedsSignIn = false
        try {
            val currentProfile = ChatProfile.parse(request("GET", "/v1/me"))
            needsReauthentication = false
            open(currentProfile); provision()
        }
        catch (error: CancellationException) { throw error }
        catch (error: ServiceFailure) { if (error.code == "profile_required") needsProfile = true else notice = explanation(context, error) }
        catch (error: Exception) { notice = explanation(context, error) }
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
        catch (error: Exception) { notice = explanation(context, error) }
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
    suspend fun confirmDeviceReplacement() {
        if (closed || busy || !needsDeviceRecovery) return
        busy = true; ready = false; notice = null; recoveryNeedsSignIn = false
        try {
            syncDone?.await()
            while (historyBusy) { historyDone?.await(); ensureOpen() }
            val old = requireNotNull(core); val store = requireNotNull(vault)
            PrivateSpeechCache.erase(context)
            val next = DeviceRecovery.candidate(store, old.device)
            val result = request("POST", "/v1/devices", JSONObject().put("device_id", next.id).put("secret", next.secret).put("replace_active", true))
            check(result.getBoolean("active") && UUID.fromString(result.getString("id")) == next.id)
            DeviceRecovery.commit(store, old.device, next)
            core = MessagingCore(store); ready = true; needsDeviceRecovery = false
            provision(); reload()
            notice = context.getString(R.string.ui_ea1029db5e5d)
        } catch (error: CancellationException) { throw error }
        catch (error: Exception) {
            if (error is Authentication.SignInRequired || error is ServiceFailure && error.code in setOf("recent_sign_in_required", "sign_in_required")) recoveryNeedsSignIn = true
            if (error is ServiceFailure && error.code == "device_revoked") {
                // The pending candidate was displaced after an uncertain earlier success.
                // A further takeover needs another explicit user confirmation with a new candidate.
                vault?.transaction { vault?.remove("local", "replacement-device") }
            }
            notice = explanation(context, error)
        } finally { busy = false }
        if (ready) synchronize()
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
    fun name(peer: UUID) = contacts[peer]?.displayName ?: importedNames[peer] ?: "New conversation"
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
    suspend fun previewPeerRecovery(peer: UUID): SignalKeys.RecoveryPreview {
        val core = core ?: throw ServiceFailure(0, "device_not_ready")
        val store = requireNotNull(vault); check(ready && peer !in blockedPeers)
        while (historyBusy) { historyDone?.await(); ensureOpen() }
        val id = store.transaction {
            store.get("pending-recovery", peer.toString())?.let { UUID.fromString(it.toString(Charsets.UTF_8)) }
                ?: UUID.randomUUID().also { store.put("pending-recovery", peer.toString(), it.toString().toByteArray()) }
        }
        try {
            val response = request("POST", "/v1/people/$peer/keys", JSONObject().put("request_id", id), core.device)
            return core.keys.previewRecovery(peer, id, response)
        } catch (error: ServiceFailure) {
            if (error.status == 410 || error.code == "recipient_identity_changed")
                store.transaction { store.remove("pending-recovery", peer.toString()) }
            throw error
        }
    }
    suspend fun confirmPeerRecovery(compared: SignalKeys.RecoveryPreview) {
        val core = core ?: throw ServiceFailure(0, "device_not_ready")
        check(ready && compared.peer !in blockedPeers)
        // Same claim replay checks that this is still the active directory device.
        val response = request("POST", "/v1/people/${compared.peer}/keys", JSONObject().put("request_id", compared.requestID), core.device)
        while (historyBusy) { historyDone?.await(); ensureOpen() }
        require(vault!!.transaction { vault!!.get("pending-recovery", compared.peer.toString())?.toString(Charsets.UTF_8) } == compared.requestID.toString())
        core.keys.confirmRecovery(compared, response)
        peersNeedingRecovery = peersNeedingRecovery - compared.peer
        notice = context.getString(R.string.ui_5f0f1b251f45)
        reload(); synchronize()
    }
    fun markRead(peer: UUID) { if (threads.any { it.peer == peer && it.unread > 0 }) { history?.markRead(peer); reload() } }
    fun compose(peer: UUID) = history?.composeDraft(peer) ?: ""
    fun saveCompose(text: String, peer: UUID) { history?.saveComposeDraft(text, peer) }
    fun reportReason(item: ChatItem): String? = vault?.transaction {
        vault!!.get("human-report", item.id.toString())?.let { JSONObject(it.toString(Charsets.UTF_8)).getJSONObject("request").getString("reason") }
    }
    suspend fun report(item: ChatItem, reason: String) {
        val store = requireNotNull(vault); val core = requireNotNull(core)
        require(!item.outgoing && item.state != "imported" && reason in setOf("spam", "harassment", "harmful", "other"))
        val report = store.transaction {
            val original = StoredChat.parse(requireNotNull(store.get("incoming", item.id.toString())))
            require(original.envelope.sender == item.peer && original.text == item.text && item.text.toByteArray(Charsets.UTF_8).size <= 32768)
            store.get("human-report", item.id.toString())?.let { JSONObject(it.toString(Charsets.UTF_8)) }
                ?: JSONObject().put("state", "pending").put("request", JSONObject()
                    .put("report_id", UUID.randomUUID().toString()).put("reported_user_id", item.peer.toString())
                    .put("message_id", item.id.toString()).put("reason", reason).put("selected_text", original.text)
                    .put("consent_version", "report-v1")).also { store.put("human-report", item.id.toString(), it.toString().toByteArray(Charsets.UTF_8)) }
        }
        if (report.getString("state") == "reported") return
        val body = report.getJSONObject("request"); require(body.getString("reason") == reason)
        val result = request("POST", "/v1/reports", body, core.device)
        check(result.getBoolean("reported") && result.getString("report_id") == body.getString("report_id"))
        store.transaction { store.put("human-report", item.id.toString(), report.put("state", "reported").toString().toByteArray(Charsets.UTF_8)) }
    }
    fun send(text: String, peer: UUID) {
        val core = core
        if (!ready || core == null) throw ServiceFailure(0, "device_not_ready")
        val now = System.currentTimeMillis()
        if (peer in blockedPeers) throw ServiceFailure(0, "contact_blocked")
        if (peer in peersNeedingRecovery) throw PeerIdentityChanged(peer)
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
        if (!ready || needsReauthentication) return
        while (historyBusy) { historyDone?.await(); ensureOpen() }
        if (syncing) { syncAgain = true; syncDone?.await(); return }
        syncing = true
        lastSyncComplete = false
        var completed = true
        syncDone = kotlinx.coroutines.CompletableDeferred()
        try {
            do {
                syncAgain = false; currentCoroutineContext().ensureActive()
                var cursor: String? = null
                val seenCursors = mutableSetOf<String>()
                val unknownSenders = linkedSetOf<UUID>()
                // Queue capacity is 10,000; restart at its beginning next sync
                // so transient decryption failures can recover.
                for (page in 0 until 100) {
                    currentCoroutineContext().ensureActive()
                    val result = request("GET", "/v1/messages/pending", device = core.device, query = cursor?.let { mapOf("after" to it) } ?: emptyMap())
                    val inbox = result.getJSONArray("messages")
                    repeat(inbox.length()) { index ->
                        try {
                            val item = RoutedMessage.received(inbox.getJSONObject(index), profile!!.id)
                            if (item.envelope.sender !in blockedPeers) {
                                core.receive(item, System.currentTimeMillis())
                                if (item.envelope.sender !in contacts && unknownSenders.size < 20) unknownSenders.add(item.envelope.sender)
                            }
                        }
                        catch (error: Exception) {
                            if (error is CancellationException) throw error
                            if (error is RetiredPeerMessage) return@repeat // Never acknowledge unread ciphertext from an explicitly retired device.
                            if (error is PeerIdentityChanged) markPeerRecovery(error.peer)
                            completed = false; notice = if (error is PeerIdentityChanged) explanation(context, error) else "A message couldn’t be opened securely. Your existing conversations are saved."
                        }
                    }
                    if (!result.has("next_cursor") || result.isNull("next_cursor")) break
                    val next = result.getString("next_cursor")
                    if (!seenCursors.add(next)) throw ServiceFailure(0, "invalid_inbox_cursor")
                    cursor = next
                }
                // Names are presentation metadata, never evidence of Signal identity trust.
                for (peer in unknownSenders) {
                    try {
                        val value = ChatProfile.parse(request("GET", "/v1/people/by-id/$peer", device = core.device))
                        require(value.id == peer)
                        vault!!.transaction { vault!!.put("contact", peer.toString(), value.json().toString().toByteArray(Charsets.UTF_8)) }
                        contacts = contacts + (peer to value)
                    } catch (error: CancellationException) { throw error }
                    catch (_: Exception) { /* Keep the securely received message even when its profile is unavailable. */ }
                }
                for (id in core.journal.pendingReceipts()) {
                    try {
                        val state = request("POST", "/v1/messages/$id/receipt", device = core.device).getString("state")
                        if (state in setOf("delivered", "expired", "unavailable", "identity_changed")) core.journal.receiptAccepted(id)
                    } catch (error: ServiceFailure) {
                        if (error.status == 404 && error.code == "message_not_found") core.journal.receiptAccepted(id)
                        else if (error.status == 429) { completed = false; break }
                        else throw error
                    }
                }
                for (draft in core.journal.pendingDrafts(System.currentTimeMillis()).sortedBy { it.createdAt }) {
                    try {
                        if (draft.recipient in blockedPeers || draft.recipient in peersNeedingRecovery) continue
                        establish(draft.recipient)
                        if (draft.recipient in blockedPeers) continue
                        core.queue(draft.id, draft.recipient, draft.text, draft.createdAt, System.currentTimeMillis())
                    } catch (error: CancellationException) { throw error }
                    catch (error: Exception) { if (error is PeerIdentityChanged) markPeerRecovery(error.peer); completed = false; notice = explanation(context, error) }
                }
                for (envelope in core.journal.pending(System.currentTimeMillis())) {
                    if (envelope.recipient in blockedPeers) continue
                    try {
                        val routed = core.queue(envelope.id, envelope.recipient, requireNotNull(core.journal.outgoing(envelope.id)).text, envelope.createdAt, System.currentTimeMillis())
                        val state = request("POST", "/v1/messages", routed.sendJSON(), core.device).getString("state")
                        if (state == "identity_changed") markPeerRecovery(envelope.recipient)
                        core.journal.applyStatus(envelope.id, if (state in setOf("unavailable", "identity_changed")) "failed" else state)
                    } catch (error: ServiceFailure) {
                        if (error.code == "recipient_identity_changed") markPeerRecovery(envelope.recipient)
                        val state = terminalSendState(error)
                        if (state != null) core.journal.applyStatus(envelope.id, state)
                        else if (error.code != "recipient_queue_full") throw error
                        else completed = false
                        notice = explanation(context, error)
                    }
                }
            } while (syncAgain)
            lastSyncComplete = completed
        } catch (error: CancellationException) { throw error }
        catch (error: Exception) { notice = explanation(context, error) }
        finally {
            syncing = false
            try { reload() } catch (_: Exception) { lastSyncComplete = false; notice = context.getString(R.string.ui_efd4b5d37081) }
            syncDone?.complete(Unit); syncDone = null
        }
    }
    suspend fun registerPush(token: String) {
        require(token.length in 1..4096 && token.none(Char::isISOControl))
        val core = core ?: return
        if (!ready) return
        request("PUT", "/v1/devices/push", JSONObject().put("provider", "fcm").put("token", token).put("environment", "production"), core.device)
    }
    internal fun eventDevice(): DeviceCredential? = if (ready && !closed && !needsReauthentication) core?.device else null
    private fun markPeerRecovery(peer: UUID) {
        vault?.transaction { vault?.put("peer-recovery-needed", peer.toString(), byteArrayOf(1)) }
        peersNeedingRecovery = peersNeedingRecovery + peer
    }
    internal fun noteDeviceRevoked() {
        if (closed) return
        ready = false; needsDeviceRecovery = true; needsReauthentication = false
        notice = context.getString(R.string.ui_54a04d4e9955)
    }
    override fun close() {
        closed = true; ready = false; needsProfile = false; syncAgain = false
        syncDone?.cancel(); syncDone = null
        historyDone?.cancel(); historyDone = null
        vault?.close(); vault = null; core = null; history = null
        profile = null; threads = emptyList(); contacts = emptyMap(); blockedPeers = emptySet(); peersNeedingRecovery = emptySet()
    }
    private fun ensureOpen() { if (closed) throw CancellationException("Chat session closed") }
    private suspend fun request(method: String, path: String, body: JSONObject? = null,
                                device: DeviceCredential? = null, query: Map<String, String> = emptyMap()): JSONObject {
        ensureOpen(); currentCoroutineContext().ensureActive()
        return try {
            val result = api.request(method, path, body, device, query)
            if (method == "POST" && path == "/v1/messages") { needsPlan = false; notice = null }
            ensureOpen(); currentCoroutineContext().ensureActive(); result
        } catch (error: Exception) {
            if (error is ServiceFailure && error.code == "base_subscription_required") needsPlan = true
            if (error is ServiceFailure && error.code in setOf("device_revoked", "device_replacement_confirmation_required")) {
                needsDeviceRecovery = true; needsReauthentication = false; ready = false
            }
            if (error is Authentication.SignInRequired || error is ServiceFailure && error.code in setOf("sign_in_required", "recent_sign_in_required")) {
                if (needsDeviceRecovery) recoveryNeedsSignIn = true else needsReauthentication = true
            }
            ensureOpen(); throw error
        }
    }
    companion object {
        private fun terminalSendState(error: ServiceFailure): String? = when {
            error.status == 410 && error.code == "message_expired" -> "expired"
            error.status == 404 && error.code == "recipient_unavailable" -> "failed"
            error.status == 409 && error.code in setOf("recipient_identity_changed", "message_id_conflict") -> "failed"
            error.status == 400 && error.code in setOf("invalid_ciphertext", "invalid_ciphertext_size", "invalid_cipher_type") -> "failed"
            else -> null
        }
        fun explanation(context: Context, error: Exception): String {
            if (error is PeerIdentityChanged) return context.getString(R.string.ui_2e03fab81b5f)
            if (error is ServiceFailure) {
                when (error.code) {
                    "username_unavailable" -> return context.getString(R.string.ui_5cd3939d3b90)
                    "person_not_found" -> return context.getString(R.string.ui_eb7c5193d2ac)
                    "invalid_username" -> return context.getString(R.string.ui_5394002806ab)
                    "own_username" -> return context.getString(R.string.ui_901dc3311d68)
                    "service_not_available" -> return context.getString(R.string.ui_e1e68ee1cefa)
                    "base_subscription_required" -> return context.getString(R.string.ui_f1af503686b6)
                    "device_replacement_confirmation_required" -> return context.getString(R.string.ui_0fac2fda13a5)
                    "recent_sign_in_required", "sign_in_required", "device_revoked" -> return context.getString(R.string.ui_77d4347c1125)
                    "recipient_keys_unavailable" -> return context.getString(R.string.ui_965e47e6fb9e)
                    "device_not_ready" -> return context.getString(R.string.ui_20b395d8ee06)
                    "contact_blocked" -> return context.getString(R.string.ui_13dff14c70d6)
                    "message_expired" -> return context.getString(R.string.ui_6315acd44d88)
                    "recipient_unavailable", "recipient_identity_changed", "message_id_conflict", "invalid_ciphertext", "invalid_ciphertext_size", "invalid_cipher_type" -> return context.getString(R.string.ui_9e36cb35d1a0)
                }
                if (error.status == 429) return context.getString(R.string.ui_4a144bcc83d9)
            }
            return context.getString(R.string.ui_fc3360ba8336)
        }
    }
}
