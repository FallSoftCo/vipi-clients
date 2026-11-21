package co.fallsoft.vipi

import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
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

/** A displayed @ prefix is accepted for lookup only; the stored username stays canonical. */
internal fun normalizeLookupUsername(input: String): String {
    val normalized = input.trim().lowercase().removePrefix("@")
    if (!normalized.matches(Regex("[a-z][a-z0-9_]{2,23}"))) throw ServiceFailure(0, "invalid_username")
    return normalized
}

/** Main-thread coordinator; transport events, lifecycle and explicit refresh
 * share one synchronization. Durable journal commits always precede receipts. */
internal class ChatSession(private val context: Context, private val api: ChatTransport, val userID: String,
                           private val mediaTransport: CiphertextTransport? = (api as? ServiceClient)?.media) : Closeable {
    constructor(context: Context, authentication: Authentication, userID: String) : this(context, ServiceClient(authentication, userID), userID)
    private val records = PrivateRecords(context)
    private var vault: MessageVault? = null
    private val mediaScope = kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.SupervisorJob() + kotlinx.coroutines.Dispatchers.Main.immediate)
    private var registeredMediaDevice: UUID? = null
    private var registeringMedia = false
    fun avatar(peer: UUID): ProfileAvatar? = vault?.let { it.transaction { it.avatar(peer) } }
    fun setOwnAvatar(jpeg: ByteArray?) {
        val store = requireNotNull(vault)
        store.transaction {
            val previous = store.avatar(store.account)?.revision ?: 0
            store.storeAvatar(store.account, ProfileAvatar(maxOf(previous + 1, System.currentTimeMillis()), jpeg))
        }
        revision++
    }
    private fun registerMedia() {
        val device = eventDevice() ?: return
        if (mediaTransport == null || registeringMedia || registeredMediaDevice == device.id) return
        registeringMedia = true
        mediaScope.launch {
            try {
                val result = request("PUT", "/v1/media/capability", JSONObject().put("version", 1), device)
                if (result.optInt("version") == 1 && eventDevice() == device) registeredMediaDevice = device.id
            } catch (cancel: CancellationException) { throw cancel }
            catch (_: Exception) { /* Older services support text. Retry on the next session start. */ }
            finally { registeringMedia = false }
        }
    }
    suspend fun requirePeerMedia(peer: UUID) {
        val device = eventDevice() ?: throw ServiceFailure(0, "device_not_ready")
        val store = requireNotNull(vault)
        val known = store.transaction { store.get("peer-device", peer.toString())?.toString(Charsets.UTF_8) }
        val result = try { request("GET", "/v1/media/capability/$peer", device = device) }
        catch (cancel: CancellationException) { throw cancel }
        catch (failure: java.io.IOException) {
            if (failure is ServiceFailure && failure.status == 404) {
                store.transaction { store.remove("peer-media-device", peer.toString()) }
                throw ServiceFailure(0, "media_peer_unavailable")
            }
            // Only a previously observed capability for this exact Signal device can qualify an offline draft.
            val transient = failure !is ServiceFailure || failure.status >= 500
            val cached = store.transaction { store.get("peer-media-device", peer.toString())?.toString(Charsets.UTF_8) }
            if (transient && known != null && known == cached && eventDevice() == device && peer !in peersNeedingRecovery && peer !in blockedPeers) return
            throw failure
        }
        check(device == eventDevice() && !closed && peer !in blockedPeers && peer !in peersNeedingRecovery)
        if (result.optInt("version") != 1 || result.isNull("device_id")) {
            store.transaction { store.remove("peer-media-device", peer.toString()) }
            throw ServiceFailure(0, "media_peer_unavailable")
        }
        val target = UUID.fromString(result.getString("device_id"))
        if (known != null && known != target.toString()) throw PeerIdentityChanged(peer)
        store.transaction { store.put("peer-media-device", peer.toString(), target.toString().toByteArray()) }
    }
    suspend fun openMedia(peer: UUID, attachment: AttachmentManifest, repository: AttachmentRepository): java.io.File {
        val device = eventDevice() ?: throw ServiceFailure(0, "device_not_ready")
        fun valid() = profile?.id == repository.account && device == eventDevice() && peer !in blockedPeers && peer !in peersNeedingRecovery
        check(valid())
        val file = repository.open(attachment, false, requireNotNull(mediaTransport), device)
        if (!valid()) { file.delete(); throw CancellationException("Chat changed") }
        return file
    }
    var holdEducation: HoldEducation? = null
        private set
    var feedback: LaunchFeedback? = null
        private set
    var visitedConversation = false
    fun takeFeedbackReturn(): Boolean = visitedConversation.also { visitedConversation = false }
    private var checkedSurveySession: String? = null
    suspend fun fundingSurveyAvailable(session: String): Boolean {
        if (checkedSurveySession == session) return false
        checkedSurveySession = session
        return try {
            eventDevice()?.let { request("GET", LaunchFeedback.PATH, device = it).get("available") == true } ?: false
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { false }
    }
    suspend fun retryFundingChoice() {
        val ledger = feedback ?: return
        val choice = ledger.pending() ?: return
        val device = eventDevice() ?: return
        try {
            request("PUT", LaunchFeedback.PATH, JSONObject().put("choice", choice), device)
            ledger.submitted(choice)
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { /* The encrypted pending answer survives offline and process death. */ }
    }
    private var core: MessagingCore? = null
    private var history: ConversationHistory? = null
    private var activity: ChatActivityEvents? = null
    fun isPeerTyping(peer: UUID) = activity?.isTyping(peer) == true
    fun composerActivity(peer: UUID, active: Boolean) { activity?.composer(peer, active) }
    fun visibleMessages(peer: UUID, incoming: List<UUID>, outgoing: List<UUID>) {
        activity?.visible(peer, incoming, outgoing)
    }
    internal fun peerTypingEvent(peer: UUID, active: Boolean) { activity?.remoteTyping(peer, active) }
    internal fun receiptEvent(peer: UUID) { activity?.receiptsChanged(peer) }
    internal fun eventConnected() { activity?.reconnected() }
    var translations by mutableStateOf<ConversationTranslation?>(null); private set
    private var translationMode = ImmersionMode.NEW_WORD
    private var translationPair: Pair<String, String>? = null
    private var translationFactory: (() -> LanguageTranslation)? = null
    private val newMessageObservers = mutableMapOf<Any, Pair<UUID, (String, String) -> Unit>>()
    internal fun observeNewMessages(owner: Any, peer: UUID, action: (String, String) -> Unit) {
        newMessageObservers[owner] = peer to action
        MessageAudioQualification.emit("observer_attached", fields = arrayOf("observers" to newMessageObservers.size))
    }
    internal fun removeNewMessageObserver(owner: Any) {
        newMessageObservers.remove(owner)
        MessageAudioQualification.emit("observer_detached", fields = arrayOf("observers" to newMessageObservers.size))
    }
    private fun newMessage(peer: UUID, id: String, text: String) {
        val matches = newMessageObservers.values.toList().filter { it.first == peer }
        MessageAudioQualification.emit("durable_message", id, "observer_matches" to matches.size)
        matches.forEach { runCatching { it.second(id, text) }.onFailure {
            MessageAudioQualification.emit("observer_failure", id, "failure" to it.javaClass.name)
        } }
    }
    var notificationPreviews by mutableStateOf(false)
        private set

    fun changeNotificationPreviews(enabled: Boolean) {
        val store = vault ?: return
        store.transaction {
            if (enabled) store.put("local", "notification-previews", UUID.randomUUID().toString().toByteArray())
            else store.remove("local", "notification-previews")
        }
        notificationPreviews = enabled
        if (!enabled) PushDelivery.clearPosted(context)
    }

    data class NotificationDelivery(val id: String, val pending: Boolean, val preview: String?)

    fun notificationDelivery(peer: UUID, protectedStorageAvailable: Boolean): NotificationDelivery? {
        if (!ready || closed || needsReauthentication || needsDeviceRecovery ||
            peer in blockedPeers || peer in peersNeedingRecovery) return null
        val store = vault ?: return null
        return store.transaction {
            val thread = store.get("thread", peer.toString()) ?: return@transaction null
            val summary = JSONObject(thread.toString(Charsets.UTF_8))
            // Old receipts predate dismissal tracking. Wait for a genuine new
            // arrival instead of reconstructing an alert on upgrade.
            if (summary.optInt("unread") <= 0 || !summary.optBoolean("notificationDeliveryTracked")) return@transaction null
            val id = summary.optString("notificationMessage").takeIf { it.isNotEmpty() } ?: return@transaction null
            val pending = store.get("posted-notification", peer.toString())?.toString(Charsets.UTF_8) != id
            if (!protectedStorageAvailable) return@transaction NotificationDelivery(id, pending, null)
            val message = store.get("incoming", id)?.let(StoredChat::parse) ?: return@transaction null
            if (message.seen || message.state != "delivered" || message.envelope.sender != peer ||
                message.envelope.recipient != store.account || message.envelope.id.toString() != id) return@transaction null
            val consent = store.get("local", "notification-previews")?.toString(Charsets.UTF_8)
            val preview = if (notificationPreviews && consent != null && consent == summary.optString("notificationConsent"))
                PushDelivery.previewLine(message.text) else null
            NotificationDelivery(id, pending, preview)
        }
    }
    fun notificationPosted(deliveries: Map<UUID, String>) { history?.notificationPosted(deliveries) }

    var groups by mutableStateOf<GroupsSession?>(null); private set
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
            feedback = LaunchFeedback(store)
            holdEducation = HoldEducation(store)
            core = MessagingCore(store); history = ConversationHistory(store)
            groups = groupSession(value.id, store, requireNotNull(core))
            notificationPreviews = store.transaction { store.get("local", "notification-previews") != null }
            activity = ChatActivityEvents(store, requireNotNull(core).journal,
                { peer -> ready && !closed && !needsReauthentication && peer !in blockedPeers && peer !in peersNeedingRecovery },
                { peer, action, value -> request("POST", "/v1/conversations/$peer/$action", value, requireNotNull(core).device) },
                ::reload)

            translationPair?.let { (source, target) ->
                translations = ConversationTranslation(context, source, target, FullMessageTranslationStore(store),
                    translator = translationFactory?.invoke() ?: LocalTranslation(), mode = translationMode)
            }
            ready = store.transaction { store.get("local", "registered-device")?.toString(Charsets.UTF_8) == core!!.device.id.toString() }
            contacts = store.transaction { store.ids("contact").associate { key ->
                val contact = ChatProfile.parse(JSONObject(requireNotNull(store.get("contact", key)).toString(Charsets.UTF_8)))
                contact.id to contact
            } }
            blockedPeers = store.transaction { store.ids("blocked").map(UUID::fromString).toSet() }
            peersNeedingRecovery = store.transaction { store.ids("peer-recovery-needed").map(UUID::fromString).toSet() }
        }
        profile = value; needsProfile = false; records.write(cacheKey, value.json()); reload(); replaySavedTranslations()
    }
    private var groupProtocolChecked = false

    private fun applyServerProfile(response: JSONObject) {
        val account = ChatProfile.parse(response)
        open(account)
        groupProtocolChecked = true
        // A cached contact/profile or a lenient JSON string conversion cannot negotiate the wire protocol.
        val protocol = response.opt("group_protocol_version")
        requireNotNull(groups).remoteAvailable = protocol == 1 || protocol == 1L
    }

    private fun groupSession(account: UUID, store: MessageVault, currentCore: MessagingCore): GroupsSession {
        val local = GroupsStore(store)
        val transport = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject {
                check(groups?.remoteAvailable == true)
                return this@ChatSession.request(method, path, body, device, query)
            }
        }
        return GroupsSession(account, GroupsAPI(transport, currentCore.device), local, GroupsCrypto(store, currentCore, local),
            preparePeer = { peer -> ensureOpen(); check(ready && peer !in blockedPeers && peer !in peersNeedingRecovery); establish(peer) },
            needsIdentityReview = { it in peersNeedingRecovery }, committed = { message -> translateDurable(message.renderID) })
    }

    internal suspend fun checkInboxProtocol() {
        if (groupProtocolChecked || !ready || closed) return
        try {
            applyServerProfile(request("GET", "/v1/me"))
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (error: java.io.IOException) {
            if (needsReauthentication || needsDeviceRecovery) throw error
            // An unavailable capability read still permits a direct-only inbox fetch.
        }
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
    suspend fun importHistory(file: java.io.File, password: String, confirmed: HistoryBackupCodec.Inspection) =
        historyOperation { store, check -> store.merge(file, password, confirmed, check) }.also { replaySavedTranslations() }
    suspend fun start() {
        if (busy || closed) return
        busy = true; notice = null; recoveryNeedsSignIn = false
        try {
            val currentProfile = request("GET", "/v1/me")
            needsReauthentication = false
            applyServerProfile(currentProfile); provision()
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
            applyServerProfile(request("PUT", "/v1/me", JSONObject().put("username", username.trim().lowercase()).put("display_name", name)))
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
        registerMedia()
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
            groups?.close(); groups = null; groupProtocolChecked = false
            feedback = LaunchFeedback(store)
            holdEducation = HoldEducation(store)
            core = MessagingCore(store); groups = groupSession(store.account, store, requireNotNull(core)); ready = true; needsDeviceRecovery = false
            checkInboxProtocol()
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
        val username = normalizeLookupUsername(input)
        val value = ChatProfile.parse(request("GET", "/v1/people/$username", device = core.device))
        if (value.id == profile?.id) throw ServiceFailure(0, "own_username")
        vault.transaction { vault.put("contact", value.id.toString(), value.json().toString().toByteArray(Charsets.UTF_8)) }
        contacts = contacts + (value.id to value); return value
    }
    fun savedFriends(): List<SavedFriend> {
        val own = profile?.id ?: return emptyList()
        val recents = threads.map { it.peer }
        val ids = recents + contacts.values.sortedWith(compareBy(String.CASE_INSENSITIVE_ORDER) { it.displayName }).map { it.id }
        return ids.distinct().filter { it != own && it !in blockedPeers }.map { id ->
            val known = contacts[id]
            SavedFriend(id, known?.displayName?.ifBlank { known.username } ?: name(id), known?.username)
        }
    }
    fun name(peer: UUID) = contacts[peer]?.displayName ?: importedNames[peer] ?: context.getString(R.string.nav_new_chat)
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
        if (blocked) PushDelivery.clearPeer(context, userID, peer)
        blockedPeers = if (blocked) blockedPeers + peer else blockedPeers - peer
        reload()
    }
    internal fun configureTranslations(source: String, target: String, factory: (() -> LanguageTranslation)? = null,
        mode: ImmersionMode = translationMode) {
        if (translationPair == source to target && translationMode == mode && translations != null) return
        translations?.close(); translations = null
        translationPair = source to target; translationFactory = factory; translationMode = mode
        vault?.let { store ->
            translations = ConversationTranslation(context, source, target, FullMessageTranslationStore(store),
                translator = factory?.invoke() ?: LocalTranslation(), mode = mode)
            replaySavedTranslations()
        }
    }
    internal fun messageOriginal(id: String): String? {
        if (closed) return null
        val store = vault ?: return null
        if (id.startsWith("group:")) {
            val parts = id.split(':'); if (parts.size != 3) return null
            return runCatching { groups?.messageOriginal(UUID.fromString(parts[1]), UUID.fromString(parts[2])) }.getOrNull()
        }
        return store.transaction {
            store.get("incoming", id)?.let { StoredChat.parse(it).text }
                ?: store.get("outgoing", id)?.let { StoredChat.parse(it).text }
                ?: store.get("draft", id)?.let { DraftChat.parse(it).text }
        }
    }
    private fun translateDurable(id: String) {
        val owner = java.lang.ref.WeakReference(this)
        translations?.enqueueStored(id) { owner.get()?.messageOriginal(id) }
    }
    fun messages(peer: UUID, before: String? = null) = history?.messages(peer, before) ?: emptyList()
    private fun replaySavedTranslations() {
        val index = history ?: return
        val peers = threads.map { it.peer }
        translations?.replaySaved { sequence {
            // Newest page of each thread first; only16 decrypted records are
            // retained per page, and only one old model call runs at a time.
            val cursors = peers.associateWith { null as String? }.toMutableMap()
            while (cursors.isNotEmpty()) {
                for (peer in peers) {
                    if (peer !in cursors) continue
                    val page = index.messages(peer, cursors[peer], limit = 16)
                    if (page.size < 16) cursors.remove(peer) else cursors[peer] = page.last().cursor
                    for (message in page) yield(ConversationTranslation.SavedMessage(message.id.toString(), message.text))
                }
            }
            for (message in groups?.historyForImmersion().orEmpty()) yield(ConversationTranslation.SavedMessage(message.renderID, message.text))
        } }
    }
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
    fun markRead(peer: UUID) { if (threads.any { it.peer == peer && it.unread > 0 }) { history?.markRead(peer); PushDelivery.clearPeer(context, userID, peer); reload() } }
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
    fun send(text: String, peer: UUID) { enqueue(text, peer, emptyList()) }
    /** Prepared originals are already private durable ciphertext. Persist their
     * manifests before any network operation; lifecycle sync owns all retries. */
    fun sendAttachments(text: String, peer: UUID, attachments: List<AttachmentManifest>, onCommitted: () -> Unit = {}): UUID {
        require(attachments.isNotEmpty())
        if (mediaTransport == null) throw ServiceFailure(0, "media_not_enabled")
        return enqueue(text, peer, attachments, onCommitted)
    }
    private fun enqueue(text: String, peer: UUID, attachments: List<AttachmentManifest>, onCommitted: () -> Unit = {}): UUID {
        ensureOpen()
        val core = core
        if (!ready || core == null) throw ServiceFailure(0, "device_not_ready")
        val now = System.currentTimeMillis()
        if (peer in blockedPeers) throw ServiceFailure(0, "contact_blocked")
        if (peer in peersNeedingRecovery) throw PeerIdentityChanged(peer)
        val id = UUID.randomUUID()
        core.journal.saveDraft(id, peer, text, now, now, consumeCompose = true, attachments = attachments)
        onCommitted()
        translateDurable(id.toString())
        newMessage(peer, id.toString(), text)
        reload()
        return id
    }
    suspend fun viewPhoto(peer: UUID, manifest: AttachmentManifest, repository: AttachmentRepository): android.graphics.Bitmap {
        fun currentDevice(): DeviceCredential {
            ensureOpen()
            require(profile?.id == repository.account && peer !in blockedPeers && peer !in peersNeedingRecovery)
            return eventDevice() ?: throw ServiceFailure(0, "device_not_ready")
        }
        val device = currentDevice()
        val image = repository.viewPhoto(manifest, mediaTransport ?: throw ServiceFailure(0, "media_not_enabled"), device)
        check(currentDevice() == device)
        return image
    }

    private suspend fun uploadAttachments(core: MessagingCore, attachments: List<AttachmentManifest>) {
        if (attachments.isEmpty()) return
        ensureOpen()
        val bytes = mediaTransport ?: throw ServiceFailure(0, "media_not_enabled")
        val repository = AttachmentRepository(context, requireNotNull(profile).id)
        for (manifest in attachments) {
            repository.ensureUploaded(manifest, api, bytes, core.device)
            ensureOpen()
            if (this.core !== core) throw CancellationException("Account changed")
        }
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
                            val raw = inbox.getJSONObject(index)
                            if (GroupIncoming.hasContext(raw)) {
                                // A group packet never falls through to the direct journal.
                                groups?.takeIf { it.remoteAvailable }?.let { controller ->
                                    val incoming = GroupIncoming.parse(raw, profile!!.id)
                                    require(incoming.kind in setOf("message", "control"))
                                    val sender = incoming.routed.envelope.sender
                                    val changedRoute = requireNotNull(vault).transaction { requireNotNull(vault).get("identity", "$sender/1") != null && requireNotNull(vault).get("peer-device", sender.toString())?.toString(Charsets.UTF_8) != incoming.routed.senderDevice.toString() }
                                    if (changedRoute) markPeerRecovery(sender)
                                    if (incoming.kind == "control") controller.receiveControl(incoming) else controller.receive(incoming)
                                    if (sender !in contacts && unknownSenders.size < 20) unknownSenders.add(sender)
                                }
                                return@repeat
                            }
                            val item = RoutedMessage.received(raw, profile!!.id)
                            if (item.envelope.sender !in blockedPeers) {
                                val duplicate = vault!!.transaction { vault!!.get("incoming", item.envelope.id.toString()) != null }
                                val received = core.receive(item, System.currentTimeMillis())
                                if (!duplicate) activity?.remoteTyping(item.envelope.sender, false)
                                if (!duplicate) translateDurable(received.envelope.id.toString())
                                if (!duplicate) newMessage(item.envelope.sender, received.envelope.id.toString(), received.text)
                                if (item.envelope.sender !in contacts && unknownSenders.size < 20) unknownSenders.add(item.envelope.sender)
                            }
                        }
                        catch (error: Exception) {
                            if (error is CancellationException) throw error
                            if (error is RetiredPeerMessage) return@repeat // Never acknowledge unread ciphertext from an explicitly retired device.
                            if (error is PeerIdentityChanged) markPeerRecovery(error.peer)
                            completed = false; notice = if (error is PeerIdentityChanged) explanation(context, error) else context.getString(R.string.message_secure_open_failed)
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
                        uploadAttachments(core, draft.attachments)
                        if (draft.recipient in blockedPeers || draft.recipient in peersNeedingRecovery) continue
                        establish(draft.recipient)
                        if (draft.recipient in blockedPeers) continue
                        core.queue(draft.id, draft.recipient, draft.text, draft.createdAt, System.currentTimeMillis(), draft.attachments)
                    } catch (error: CancellationException) { throw error }
                    catch (error: Exception) { if (error is PeerIdentityChanged) markPeerRecovery(error.peer); completed = false; notice = explanation(context, error) }
                }
                for (envelope in core.journal.pending(System.currentTimeMillis())) {
                    if (envelope.recipient in blockedPeers) continue
                    try {
                        val saved = requireNotNull(core.journal.outgoing(envelope.id))
                        if (saved.state == "queued") uploadAttachments(core, saved.attachments)
                        if (envelope.recipient in blockedPeers || envelope.recipient in peersNeedingRecovery) continue
                        val routed = core.queue(envelope.id, envelope.recipient, saved.text, envelope.createdAt, System.currentTimeMillis(), saved.attachments)
                        val state = request("POST", "/v1/messages", routed.sendJSON(), core.device).getString("state")
                        if (state == "identity_changed") markPeerRecovery(envelope.recipient)
                        core.journal.applyStatus(envelope.id, if (state in setOf("unavailable", "identity_changed")) "failed" else state)
                        if (saved.state !in setOf("accepted", "delivered", "read") && state in setOf("accepted", "delivered")) {
                            activity?.outgoingAccepted(envelope.id, envelope.recipient)
                        }
                    } catch (error: ServiceFailure) {
                        if (error.code == "recipient_identity_changed") markPeerRecovery(envelope.recipient)
                        val state = terminalSendState(error)
                        if (state != null) core.journal.applyStatus(envelope.id, state)
                        else if (error.code != "recipient_queue_full") throw error
                        else completed = false
                        notice = explanation(context, error)
                    }
                }
                groups?.takeIf { it.remoteAvailable }?.let { controller ->
                    controller.synchronize()
                    for (id in controller.pendingReceipts()) {
                        try {
                            val state = request("POST", "/v1/messages/$id/receipt", device = core.device).getString("state")
                            if (state in setOf("delivered", "expired", "unavailable", "identity_changed")) controller.receiptAccepted(id)
                        } catch (failure: ServiceFailure) {
                            if (failure.status == 404 && failure.code == "message_not_found") controller.receiptAccepted(id) else if (failure.status == 429) break else throw failure
                        }
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
        PushDelivery.clearPeer(context, userID, peer)
        peersNeedingRecovery = peersNeedingRecovery + peer
    }
    internal fun noteDeviceRevoked() {
        if (closed) return
        PushDelivery.clearPosted(context)
        ready = false; needsDeviceRecovery = true; needsReauthentication = false
        notice = context.getString(R.string.ui_54a04d4e9955)
    }
    override fun close() {
        mediaScope.cancel()
        activity?.close(); activity = null
        newMessageObservers.clear()
        translations?.close(); translations = null
        closed = true; ready = false; needsProfile = false; syncAgain = false
        syncDone?.cancel(); syncDone = null
        historyDone?.cancel(); historyDone = null
        groups?.close(); groups = null
        feedback = null; holdEducation = null; visitedConversation = false
        vault?.close(); vault = null; core = null; history = null
        profile = null; threads = emptyList(); contacts = emptyMap(); blockedPeers = emptySet(); peersNeedingRecovery = emptySet()
    }
    private fun ensureOpen() { if (closed) throw CancellationException("Chat session closed") }
    private suspend fun request(method: String, path: String, body: JSONObject? = null,
                                device: DeviceCredential? = null, query: Map<String, String> = emptyMap()): JSONObject {
        ensureOpen(); currentCoroutineContext().ensureActive()
        return try {
            val result = if (groups?.remoteAvailable == true && device != null && GroupInboxProtocol.supports(method, path)) {
                api.groupInboxRequest(method, path, body, device, query)
            } else api.request(method, path, body, device, query)
            if (method == "POST" && path == "/v1/messages") notice = null
            ensureOpen(); currentCoroutineContext().ensureActive(); result
        } catch (error: Exception) {
            if (error is ServiceFailure && error.code in setOf("device_revoked", "device_replacement_confirmation_required")) {
                PushDelivery.clearPosted(context)
                needsDeviceRecovery = true; needsReauthentication = false; ready = false
            }
            if (error is Authentication.SignInRequired || error is ServiceFailure && error.code in setOf("sign_in_required", "recent_sign_in_required")) {
                PushDelivery.clearPosted(context)
                groupProtocolChecked = false; groups?.remoteAvailable = false
                if (needsDeviceRecovery) recoveryNeedsSignIn = true else needsReauthentication = true
            }
            ensureOpen(); throw error
        }
    }
    companion object {
        private fun terminalSendState(error: ServiceFailure): String? = when {
            error.status == 410 && error.code == "message_expired" -> "expired"
            error.status == 404 && error.code == "recipient_unavailable" -> "failed"
            error.status == 409 && error.code in setOf("recipient_identity_changed", "message_id_conflict", "recipient_media_unsupported") -> "failed"
            error.status == 400 && error.code in setOf("invalid_ciphertext", "invalid_ciphertext_size", "invalid_cipher_type") -> "failed"
            else -> null
        }
        fun explanation(context: Context, error: Exception): String {
            if (error is ServiceFailure && error.code in setOf("media_peer_unavailable", "media_not_enabled", "recipient_media_unsupported")) return context.getString(R.string.media_peer_unavailable)
            if (error is MediaActionFailure) return context.getString(error.label)
            if (error is PhotoTooLarge) return context.getString(R.string.photo_too_large)
            if (error is PeerIdentityChanged) return context.getString(R.string.ui_2e03fab81b5f)
            if (error is ServiceFailure) {
                when (error.code) {
                    "username_unavailable" -> return context.getString(R.string.ui_5cd3939d3b90)
                    "person_not_found" -> return context.getString(R.string.ui_eb7c5193d2ac)
                    "invalid_username" -> return context.getString(R.string.ui_5394002806ab)
                    "own_username" -> return context.getString(R.string.ui_901dc3311d68)
                    "service_not_available" -> return context.getString(R.string.ui_e1e68ee1cefa)
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
