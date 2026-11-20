package co.fallsoft.vipi

import android.app.Activity
import android.app.Application
import android.app.Instrumentation
import android.content.Context
import android.content.Intent
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.core.view.WindowInsetsCompat
import androidx.test.uiautomator.By
import androidx.test.uiautomator.BySelector
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import okhttp3.Request
import okhttp3.Response
import okhttp3.Protocol
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.security.KeyStore
import java.time.Instant
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

/** Real MainActivity + navigation + model + encrypted sessions. Only the external
 * service, WebSocket, billing and share boundaries are controlled. */
internal class JourneyServices(profileRequired: Boolean, private val seedBotMessages: Int = 0,
    private val expectedBotPosts: Int = 1, private val expectedFriendPosts: Int = 1,
    private val cardlessAccess: Boolean = false,
    private val deletionService: DeletionTransport? = null,
    private val emptyPriceCatalog: Boolean = false,
    private val accountDisplayName: String = "Journey Tester",
    private val peerDisplayName: String = "Journey Friend",
    private val botReplyText: String = "The local lifecycle reply arrived.",
    private val cardlessStartedAt: Instant? = null,
    private val holdPriceCatalog: Boolean = false,
    private val translationFactory: () -> LanguageTranslation = { NoJourneyModelTranslation }) : VipiWorkflowBoundary, AutoCloseable {
    val account = UUID.randomUUID()
    val peer = UUID.randomUUID()
    val subject = "user_journey_${UUID.randomUUID().toString().replace("-", "")}"
    val profileUnavailable = AtomicBoolean(false)
    val profileWrites = AtomicInteger()
    val deviceRegistrations = AtomicInteger()
    val friendPosts = AtomicInteger()
    val reportPosts = AtomicInteger()
    val baseExpired = AtomicBoolean(false)
    val baseRestored = AtomicBoolean(false)
    val refusedFriendIDs = mutableListOf<UUID>()
    val refusedFriendCiphertexts = mutableListOf<String>()
    val cardlessStarted: Instant = cardlessStartedAt ?: Instant.now().minusSeconds(29 * 86_400L)
    val cardlessEnds: Instant = cardlessStarted.plusSeconds(30 * 86_400L)
    val friendReplyReceipts = AtomicInteger()
    val inboxWakeups = AtomicInteger()
    val friendReply = "Thanks for your message — café ☕."
    var friendReplyId: UUID? = null
        private set
    var outgoingFriendId: UUID? = null
        private set
    private var pendingPeerReply: JSONObject? = null
    val generatedPeerReplies = linkedMapOf<UUID, String>()
    val botPosts = AtomicInteger()
    val botAllowanceGets = AtomicInteger()
    val cancelledBotPosts = AtomicInteger()
    val failNextEntitlement = AtomicBoolean(false)
    val failBotReply = AtomicBoolean(false)
    val botReplyGate = CompletableDeferred<Unit>()
    val botReply = botReplyText
    val botFollowupReply = "The new local reply is now fully reachable."
    val botRequestPrompts = mutableListOf<String>()
    val lookups = mutableListOf<String>()
    var peerReceived: String? = null
    private var created = !profileRequired
    private var remaining = 150
    private var registered: DeviceCredential? = null
    private var peerVault: MessageVault? = null
    private var peerCore: MessagingCore? = null
    private var peerPublication: JSONObject? = null
    val commerceRequests = AtomicInteger(0)
    private val sockets = mutableListOf<JourneySocket>()
    fun model(application: Application): VipiModel {
        PrivateRecords(application).write("session", IdentityAuthority.FALLSOFT_VIPI_PRODUCTION.tag(JSONObject()
            .put("userID", subject).put("accessToken", "synthetic-inert-access").put("refreshToken", "synthetic-inert-refresh")))
        if (seedBotMessages > 0) MessageVault(application, account).use { history ->
            history.transaction {
                history.put("bot-settings", "consent", "deepseek-v1".toByteArray())
                val start = System.currentTimeMillis() - 60_000
                repeat(seedBotMessages) { index ->
                    // Historical encrypted data remains part of account erasure
                    // coverage; it does not recreate a Bot runtime feature.
                    val id = "m%019d-seeded-%03d".format(java.util.Locale.ROOT, start + index, index)
                    val message = JSONObject().put("id", id).put("role", if (index % 2 == 0) "user" else "assistant")
                        .put("content", "Earlier historical message $index.").put("status", "confirmed").put("request_id", JSONObject.NULL)
                    history.put("bot-message", id, message.toString().toByteArray())
                }
            }
        }
        val vault = MessageVault(application, peer)
        peerVault = vault
        peerCore = MessagingCore(vault)
        peerPublication = requireNotNull(peerCore).keys.publication(System.currentTimeMillis(), 2)
        requireNotNull(peerCore).keys.published(1)
        return VipiModel(application, translationFactory(), this)
    }
    override fun translationClient(): LanguageTranslation = translationFactory()
    override fun transport(authentication: Authentication, userID: String): ChatTransport {
        check(userID == subject)
        return object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject {
                if (path == "/v1/entitlements" || path.startsWith("/v1/billing/") || path.startsWith("/v1/bot/")) {
                    commerceRequests.incrementAndGet()
                    error("Removed commerce/Bot endpoint requested by free friend chat")
                }
                if (method == "POST" && path in setOf("/v1/reports", "/v1/bot/reports")) {
                    reportPosts.incrementAndGet()
                    error("No report submit is authorized in the cancel journey")
                }
                return when {
                    method == "GET" && path == "/v1/me" -> {
                        if (profileUnavailable.get()) throw java.io.IOException("Controlled profile service unavailable")
                        if (!created) throw ServiceFailure(404, "profile_required")
                        ChatProfile(account, "journey_tester", accountDisplayName).json()
                    }
                    method == "PUT" && path == "/v1/me" -> {
                        val fields = requireNotNull(body)
                        check(!created && fields.getString("username") == "journey_tester")
                        check(fields.getString("display_name") == "Journey Tester")
                        created = true; profileWrites.incrementAndGet()
                        ChatProfile(account, "journey_tester", accountDisplayName).json()
                    }
                    method == "POST" && path == "/v1/devices" -> {
                        check(deviceRegistrations.incrementAndGet() == 1)
                        check(body?.optBoolean("replace_active") != true)
                        val fields = requireNotNull(body)
                        registered = DeviceCredential(UUID.fromString(fields.getString("device_id")), fields.getString("secret"))
                        JSONObject().put("id", registered!!.id).put("active", true)
                    }
                    method == "GET" && path == "/v1/keys" -> JSONObject().put("revision", 1).put("remaining", 20)
                    method == "GET" && path == "/v1/messages/pending" -> {
                        check(device == registered)
                        JSONObject().put("messages", JSONArray().apply { pendingPeerReply?.let { put(JSONObject(it.toString())) } })
                            .put("next_cursor", JSONObject.NULL)
                    }
                    method == "POST" && pendingPeerReply != null && path == "/v1/messages/${pendingPeerReply!!.getString("id")}/receipt" -> {
                        check(device == registered && pendingPeerReply != null)
                        check(friendReplyReceipts.incrementAndGet() <= generatedPeerReplies.size)
                        pendingPeerReply = null
                        JSONObject().put("state", "delivered")
                    }
                    method == "GET" && path.startsWith("/v1/blocks/") -> JSONObject().put("blocked", false)
                    method == "GET" && path.startsWith("/v1/people/") -> {
                        val name = path.substringAfterLast('/')
                        lookups += name
                        if (name == "missing_friend") throw ServiceFailure(404, "person_not_found")
                        check(name == "journey_friend")
                        ChatProfile(peer, "journey_friend", peerDisplayName).json()
                    }
                    method == "POST" && path == "/v1/people/$peer/keys" -> {
                        val publication = requireNotNull(peerPublication)
                        JSONObject().put("request_id", requireNotNull(body).getString("request_id"))
                            .put("user_id", peer).put("device_id", requireNotNull(peerCore).device.id).put("signal_device_id", 1)
                            .put("registration_id", publication.getInt("registration_id")).put("identity_key", publication.getString("identity_key"))
                            .put("signed", publication.getJSONObject("signed")).put("one_time", publication.getJSONArray("one_time").getJSONObject(0))
                    }
                    method == "POST" && path == "/v1/messages" -> {
                        check(device == registered)
                        val encrypted = JSONObject(requireNotNull(body).toString())
                        check(!encrypted.toString().contains("I am reading a book now."))
                        if (cardlessAccess && baseExpired.get() && !baseRestored.get()) {
                            check(refusedFriendIDs.size < 8) { "Unexpected unbounded retry of expired send" }
                            refusedFriendIDs += UUID.fromString(encrypted.getString("id"))
                            refusedFriendCiphertexts += encrypted.toString()
                            throw ServiceFailure(402, "base_subscription_required")
                        }
                        check(friendPosts.incrementAndGet() <= expectedFriendPosts)
                        outgoingFriendId = UUID.fromString(encrypted.getString("id"))
                        encrypted.put("sender_id", account).put("sender_device_id", requireNotNull(registered).id)
                        peerReceived = requireNotNull(peerCore).receive(RoutedMessage.received(encrypted, peer), System.currentTimeMillis()).text
                        JSONObject().put("state", "delivered")
                    }
                    method == "GET" && path == "/v1/entitlements" -> {
                        if (failNextEntitlement.getAndSet(false)) throw java.io.IOException("Synthetic entitlement unavailable")
                        if (cardlessAccess) {
                            val expired = baseExpired.get()
                            val restored = baseRestored.get()
                            val now = if (expired) cardlessEnds.plusSeconds(1) else Instant.now()
                            val base = JSONObject().put("active", !expired || restored)
                                .put("expires_at", if (restored) now.plusSeconds(365 * 86_400L).toString() else cardlessEnds.toString())
                                .put("trial_ends_at", if (!expired) cardlessEnds.toString() else JSONObject.NULL)
                                .put("review_access", false)
                                .put("access_source", if (restored) "google_play" else if (!expired) "cardless_trial" else JSONObject.NULL)
                                .put("cardless_trial", JSONObject().put("started_at", cardlessStarted.toString())
                                    .put("ends_at", cardlessEnds.toString()).put("active", !expired))
                            val bot = JSONObject().put("active", false).put("available", true)
                                .put("expires_at", JSONObject.NULL).put("trial_ends_at", JSONObject.NULL)
                            return JSONObject().put("base", base).put("bot_mini", bot)
                                .put("billing_account_id", "c".repeat(64)).put("server_time", now.toString())
                                .put("purchases_ready", JSONObject().put("google", true))
                        }
                        fun plan() = JSONObject().put("active", true).put("expires_at", JSONObject.NULL).put("trial_ends_at", JSONObject.NULL)
                            .put("review_access", true).put("access_source", "review_complimentary")
                        JSONObject().put("base", plan()).put("bot_mini", plan().put("available", true))
                            .put("billing_account_id", "c".repeat(64)).put("server_time", Instant.now().toString())
                    }
                    method == "GET" && path == "/v1/bot/allowance" -> { botAllowanceGets.incrementAndGet(); allowance() }
                    method == "POST" && path == "/v1/bot/messages" -> {
                        check(device == registered)
                        val post = botPosts.incrementAndGet()
                        check(post <= expectedBotPosts)
                        val sent = requireNotNull(body)
                        check(sent.getString("consent_version") == "deepseek-v1")
                        val context = sent.getJSONArray("messages")
                        val expectedContextSize = if (seedBotMessages == 0) minOf(post * 2 - 1, 11) else 11
                        check(context.length() == expectedContextSize) { "POST $post must retain exactly $expectedContextSize confirmed turns plus the new prompt" }
                        check(context.getJSONObject(context.length() - 1).getString("role") == "user")
                        if (post > 1) {
                            check(context.getJSONObject(context.length() - 3).getString("content") == botRequestPrompts.last())
                            check(context.getJSONObject(context.length() - 3).getString("role") == "user")
                            check(context.getJSONObject(context.length() - 2).getString("content") == if (post == 2) botReply else botFollowupReply)
                            check(context.getJSONObject(context.length() - 2).getString("role") == "assistant")
                        }
                        botRequestPrompts += context.getJSONObject(context.length() - 1).getString("content")
                        try { botReplyGate.await() }
                        catch (cancelled: kotlinx.coroutines.CancellationException) {
                            cancelledBotPosts.incrementAndGet(); throw cancelled
                        }
                        if (failBotReply.get()) throw java.io.IOException("Synthetic uncertain provider outcome")
                        remaining = 150 - post
                        JSONObject().put("request_id", sent.getString("request_id")).put("reply", if (post == 1) botReply else botFollowupReply).put("allowance", allowance())
                    }
                    else -> error("Unexpected journey service boundary request: $method $path")
                }
            }
        }
    }
    fun queuePeerReplyAndSignalInbox() {
        check(friendReplyId == null)
        friendReplyId = queueAdditionalPeerReplyAndSignalInbox(friendReply)
    }
    fun queueAdditionalPeerReplyAndSignalInbox(text: String): UUID {
        check(android.os.Looper.myLooper() == android.os.Looper.getMainLooper())
        check(friendPosts.get() in 1..expectedFriendPosts && peerReceived != null && pendingPeerReply == null)
        val socket = requireNotNull(sockets.lastOrNull { it.active }) { "The actual foreground inbox event connection must be open" }
        val core = requireNotNull(peerCore)
        val id = UUID.randomUUID(); val now = System.currentTimeMillis()
        val encrypted = core.queue(id, account, text, now, now)
        check(encrypted.recipientDevice == requireNotNull(registered).id)
        val wire = encrypted.sendJSON().put("sender_id", peer).put("sender_device_id", core.device.id)
        check(!wire.toString().contains(text))
        generatedPeerReplies[id] = text; pendingPeerReply = wire
        inboxWakeups.incrementAndGet()
        socket.inboxChanged()
        return id
    }
    private fun allowance() = JSONObject().put("available", true).put("service_ready", true)
        .put("remaining_replies", remaining).put("monthly_replies", 150).put("period", "2098-12")
        .put("resets_at", "2099-01-01T00:00:00Z").put("max_context_bytes", 8192)
    override fun requestPush(context: Context, registration: Boolean) = Unit
    override fun cancelPush(context: Context) = Unit
    override fun deletionTransport(authentication: Authentication) = deletionService
    override fun foregroundEvents(scope: CoroutineScope, authentication: Authentication, chat: ChatSession): ForegroundInboxEvents =
        ForegroundInboxEvents(scope, { "synthetic-inert-access" }, chat::eventDevice, { chat.synchronize() },
            sockets = WebSocket.Factory { request, listener -> JourneySocket(request, listener).also { sockets += it; it.open() } })
    /** HTTP boundary only; absence of Billing SDK is checked in package proof. */
    fun assertNoPurchase() { assertEquals(0, commerceRequests.get()) }
    override fun close() {
        sockets.forEach { it.cancel() }
        peerVault?.close()
        // These are isolated random fixture accounts, never a retained reviewer account.
        KeyStore.getInstance("AndroidKeyStore").apply {
            load(null); deleteEntry("co.fallsoft.vipi.messages.$account"); deleteEntry("co.fallsoft.vipi.messages.$peer")
        }
    }
    private class JourneySocket(private val request: Request, private val listener: WebSocketListener) : WebSocket {
        var active = true
            private set
        override fun request() = request
        override fun queueSize() = 0L
        override fun send(text: String) = error("No application content may use the fake event socket")
        override fun send(bytes: ByteString) = error("No application content may use the fake event socket")
        override fun close(code: Int, reason: String?): Boolean { active = false; return true }
        override fun cancel() { active = false }
        fun inboxChanged() { check(active); listener.onMessage(this, "{\"event\":\"inbox_changed\"}") }
        fun open() = listener.onOpen(this, Response.Builder().request(request).protocol(Protocol.HTTP_1_1).code(101).message("Switching Protocols").build())
    }
}
