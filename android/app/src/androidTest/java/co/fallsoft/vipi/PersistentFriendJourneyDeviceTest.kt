package co.fallsoft.vipi

import android.app.Application
import android.content.Context
import android.os.Process
import android.util.AtomicFile
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.core.view.WindowInsetsCompat
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import okhttp3.*
import okio.ByteString
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.io.IOException
import java.security.KeyStore
import java.security.MessageDigest
import java.time.Duration
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** Host-orchestrated two-phase regression. Phase1 deliberately stays alive
 * after its durable ready marker; the host must force-stop ONLY the QA process.
 * A normal whole-class test invocation is not a substitute for that proof. */
class PersistentFriendJourneyDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()
    private fun token(): String {
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("vipiHostProcessDeath") == "true") { "Requires the dedicated host process-death controller" }
        return requireNotNull(args.getString("vipiPersistentJourneyToken")).also {
            require(it.matches(Regex("[a-f0-9]{32}")))
        }
    }
    private fun screen(f: MainActivityJourneyFixture, value: Screen) = compose.waitUntil(10_000) { f.model.screen == value }
    private fun ime(f: MainActivityJourneyFixture): Boolean {
        var visible = false
        f.instrumentation.runOnMainSync {
            visible = android.view.inspector.WindowInspector.getGlobalWindowViews().any { view ->
                view.rootWindowInsets?.let { WindowInsetsCompat.toWindowInsetsCompat(it).isVisible(WindowInsetsCompat.Type.ime()) } == true
            }
        }
        return visible
    }
    private fun editor(text: String) = compose.onNodeWithTag("message-input").assert(SemanticsMatcher("Exact durable plain-text draft") {
        val key = androidx.compose.ui.semantics.SemanticsProperties.EditableText
        it.config.contains(key) && it.config[key].text == text
    })

    @Test fun prepareOfflineQueueAndWaitForHostProcessKill() {
        val token = token()
        val services = PersistentJourneyRelay(token, create = true)
        val f = MainActivityJourneyFixture("process-death-prepare", services::model, retainedToken = token)
        // No use/finally closing the model before the host's abrupt kill.
        // Timeout/failure is never declared a successful process-death phase.
        f.launch(); screen(f, Screen.PROFILE)
        compose.onNodeWithTag("profile-name").performScrollTo().performTouchInput { click() }
        compose.onNodeWithTag("profile-name").performTextInput("Process Tester")
        compose.onNodeWithTag("profile-username").performScrollTo().performTouchInput { click() }
        compose.onNodeWithTag("profile-username").performTextInput("process_tester")
        compose.onNodeWithTag("profile-submit").performScrollTo().assertIsEnabled()
        compose.onNodeWithText(f.base.getString(R.string.ui_33875a9b79e5)).assertIsDisplayed()
        f.capture("00-actual-profile-readable-username-requirements")
        compose.onNodeWithTag("profile-submit").performTouchInput { click() }
        screen(f, Screen.HOME)
        compose.runOnIdle {
            assertEquals(1, services.state().getInt("profile_writes")); assertEquals(1, services.state().getInt("registrations"))
            services.assertNoPurchase()
        }
        f.capture("01-created-profile-free-chat-without-commerce")
        compose.onNodeWithContentDescription(f.base.getString(R.string.nav_new_chat)).performTouchInput { click() }
        screen(f, Screen.NEW_CHAT)
        compose.onNode(hasSetTextAction()).performScrollTo().performTouchInput { click() }
        compose.onNode(hasSetTextAction()).performTextInput("@Process_Friend")
        compose.onNodeWithText(f.base.getString(R.string.new_chat_lookup, "process_friend")).performScrollTo().performTouchInput { click() }
        screen(f, Screen.CONVERSATION)
        compose.onNodeWithTag("message-input").performTouchInput { click() }
        compose.waitUntil(8_000) { ime(f) }
        compose.onNodeWithTag("message-input").performTextInput(PersistentJourneyRelay.PROMPT)
        compose.onNodeWithTag("message-send").assertIsEnabled().performTouchInput { click() }
        compose.waitUntil(10_000) { services.state().getInt("post_attempts") == 1 && f.model.chat?.notice != null }
        compose.onNodeWithTag("message-input").performTextInput(PersistentJourneyRelay.DRAFT)
        editor(PersistentJourneyRelay.DRAFT).assertIsFocused()
        val reason = ChatSession.explanation(f.isolated, IOException("controlled transport unavailable"))
        compose.onNodeWithText(reason).assertIsDisplayed()
        f.assertNativeTextInViewport(compose, reason, "02-offline-explanation")
        f.assertNativeTextInViewport(compose, PersistentJourneyRelay.DRAFT, "02-offline-draft", 48)
        f.capture("02-offline-message-and-independent-editable-draft")
        compose.runOnIdle {
            assertTrue(requireNotNull(f.model.chat).ready)
            assertEquals(0, services.state().getInt("accepted_posts"))
            services.assertDurableQueued(f.isolated)
            services.assertNoPurchase()
            services.change { it.put("phase", "waiting-for-host-kill") }
        }
        services.writeReadyMarker()
        check(!CountDownLatch(1).await(120, TimeUnit.SECONDS))
        error("Host did not kill the live QA process after its durable ready marker; phase1 is NOT a passing test")
    }

    @Test fun newProcessReopensOfflineDraftThenReconnectsAndExchangesExactlyOnce() {
        val token = token()
        val services = PersistentJourneyRelay(token, create = false)
        val args = InstrumentationRegistry.getArguments()
        val prior = services.state().getJSONObject("first_process")
        assertEquals(prior.getInt("pid"), requireNotNull(args.getString("vipiKilledPid")).toInt())
        assertEquals(prior.getString("start_ticks"), args.getString("vipiKilledStartTicks"))
        assertTrue(Process.myPid() != prior.getInt("pid") || PersistentJourneyRelay.startTicks() != prior.getString("start_ticks"))
        assertEquals("waiting-for-host-kill", services.state().getString("phase"))
        MainActivityJourneyFixture("process-death-resume", services::model, retainedToken = token).use { f ->
            var passed = false
            try {
                // A genuine new model reads old encrypted auth/profile/vault.
                // Neither this phase nor its boundary seeds a profile, session,
                // device, message, conversation contact or draft.
                services.assertDurableQueued(f.isolated)
                f.launch(); screen(f, Screen.HOME)
                compose.waitUntil(10_000) { f.model.chat?.ready == true && f.model.chat?.notice != null }
                compose.onNodeWithText("Process Friend").performScrollTo().performTouchInput { click() }
                screen(f, Screen.CONVERSATION)
                editor(PersistentJourneyRelay.DRAFT).performTouchInput { click() }
                compose.waitUntil(8_000) { ime(f) }
                editor(PersistentJourneyRelay.DRAFT).assertIsFocused()
                val reason = ChatSession.explanation(f.isolated, IOException("controlled transport unavailable"))
                compose.onNodeWithText(reason).assertIsDisplayed()
                f.assertNativeTextInViewport(compose, reason, "03-new-process-offline-explanation")
                val blockWarning = f.base.getString(R.string.chat_block_check_failed)
                compose.onNodeWithText(blockWarning).assertIsDisplayed()
                f.assertNativeTextInViewport(compose, blockWarning, "03-new-process-security-check-explanation")
                f.assertNativeTextInViewport(compose, PersistentJourneyRelay.DRAFT, "03-new-process-draft", 48)
                compose.runOnIdle {
                    assertEquals(1, services.state().getInt("auth_seeds"))
                    assertEquals(1, services.state().getInt("profile_writes"))
                    assertEquals(1, services.state().getInt("registrations"))
                    assertEquals(1, services.state().getInt("post_attempts"))
                    assertEquals(0, services.state().getInt("accepted_posts"))
                    services.assertDurableQueued(f.isolated)
                }
                f.capture("03-new-process-offline-history-and-draft-without-reseeding")
                // Only the controlled reachability boundary changes. Production
                // ForegroundInboxEvents performs its actual reconnect/onOpen
                // catch-up; the test never calls ChatSession.synchronize.
                compose.runOnIdle { services.restoreNetwork() }
                compose.waitUntil(12_000) {
                    services.state().getInt("accepted_posts") == 1 && services.state().getInt("reply_receipts") == 1 &&
                        f.model.chat?.messages(services.peer)?.size == 2 && f.model.chat?.syncing == false
                }
                editor(PersistentJourneyRelay.DRAFT).assertIsFocused()
                f.assertIncomingAboveComposer(compose, PersistentJourneyRelay.REPLY, "04-reconnected-peer-reply-with-original-next-draft")
                compose.runOnIdle {
                    val saved = services.state(); val rows = requireNotNull(f.model.chat).messages(services.peer)
                    assertEquals(2, saved.getInt("post_attempts")); assertEquals(1, saved.getInt("peer_decryptions"))
                    assertEquals(1, saved.getInt("auth_seeds")); assertEquals(1, saved.getInt("profile_writes"))
                    assertEquals(1, saved.getInt("registrations")); assertEquals(1, saved.getInt("accepted_posts"))
                    assertEquals(saved.getString("queued_id"), rows.single { it.outgoing }.id.toString())
                    assertEquals("delivered", rows.single { it.outgoing }.state)
                    assertEquals(PersistentJourneyRelay.PROMPT, rows.single { it.outgoing }.text)
                    assertEquals(PersistentJourneyRelay.REPLY, rows.single { !it.outgoing }.text)
                    assertEquals(PersistentJourneyRelay.DRAFT, f.model.chat?.compose(services.peer))
                    assertEquals(1, saved.getJSONArray("wire_hashes").let { a -> (0 until a.length()).map { a.getString(it) }.distinct().size })
                    assertEquals(1, saved.getJSONArray("post_ids").let { a -> (0 until a.length()).map { a.getString(it) }.distinct().size })
                    services.assertNoPurchase()
                }
                MessageVault(f.isolated, services.account).use { vault ->
                    val history = ConversationHistory(vault)
                    assertEquals(PersistentJourneyRelay.DRAFT, history.composeDraft(services.peer))
                    assertEquals(2, history.messages(services.peer).size)
                    assertTrue(MessageJournal(vault).pendingReceipts().isEmpty())
                }
                services.change { it.put("phase", "completed") }
                File(f.output, "receipt.json").writeText(services.publicProof().put("pass", true)
                    .put("actual_main_activity", true).put("actual_foreground_reconnect", true)
                    .put("same_disk_new_process_without_reseeding", true).put("real_signal_both_directions", true)
                    .put("native_editable_next_draft_retained", true).put("billing_launches", 0)
                    .put("physical_radio_push_or_live_service_claimed", false).toString(2))
                passed = true
            } catch (failure: Throwable) {
                runCatching { f.capture("failure") }.onFailure { failure.addSuppressed(it) }; throw failure
            } finally {
                f.stopActivity(); services.close()
                if (passed) { services.eraseOwnedControl(); f.eraseRetainedStorageAfterProof(token) }
            }
        }
    }
}

/** Persistent LOCAL fake relay metadata; all cryptographic sessions/history and
 * the application root are production instances. No endpoint can fall through
 * to HTTP, OAuth, a provider, a purchase or a real account operation. */
private class PersistentJourneyRelay(private val token: String, create: Boolean) : VipiWorkflowBoundary, AutoCloseable {
    companion object {
        const val PROMPT = "Please keep this message until the connection returns."
        const val DRAFT = "Keep this café draft — I have not sent it."
        const val REPLY = "Your message arrived after the connection returned."
        private const val TAG = "vipi-private-simulator-process-journey-1"
        fun startTicks() = File("/proc/self/stat").readText().split(" ")[21]
        fun hash(text: String) = MessageDigest.getInstance("SHA-256").digest(text.toByteArray()).joinToString("") { "%02x".format(it) }
        fun hash(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
    }
    private val base = InstrumentationRegistry.getInstrumentation().targetContext
    private val directory = File(base.filesDir, "controlled-process-$token")
    private val file = AtomicFile(File(directory, "relay.json"))
    private val reconnect = CompletableDeferred<Unit>()
    private var commerceRequests = 0
    private val sockets = mutableListOf<Socket>()
    private var peerVault: MessageVault? = null
    private var peerCore: MessagingCore? = null
    val account: UUID get() = UUID.fromString(state().getString("account"))
    val peer: UUID get() = UUID.fromString(state().getString("peer"))
    private val subject get() = "user_simulator_$token"
    init {
        check(BuildConfig.DEBUG && BuildConfig.APPLICATION_ID in setOf("co.fallsoft.vipi.sourcecontextqa", "co.fallsoft.vipi.uxqa"))
        require(token.matches(Regex("[a-f0-9]{32}")))
        check(!java.nio.file.Files.isSymbolicLink(directory.toPath()))
        check(directory.parentFile.canonicalFile == base.filesDir.canonicalFile)
        if (create) {
            check(!directory.exists()); check(directory.mkdirs())
            write(JSONObject().put("tag", TAG).put("token", token).put("package", BuildConfig.APPLICATION_ID)
                .put("account", UUID.randomUUID()).put("peer", UUID.randomUUID()).put("created", false)
                .put("offline", false).put("auth_seeds", 0).put("profile_writes", 0).put("registrations", 0)
                .put("post_attempts", 0).put("accepted_posts", 0).put("peer_decryptions", 0).put("reply_receipts", 0)
                .put("phase", "created").put("post_ids", JSONArray()).put("wire_hashes", JSONArray())
                .put("first_process", JSONObject().put("pid", Process.myPid()).put("start_ticks", startTicks())))
        } else check(file.baseFile.isFile)
        validate(state())
        writeOwnerMarker(if (create) "prepare-owner.json" else "resume-owner.json")
    }
    private fun writeOwnerMarker(name: String) {
        check(name in setOf("prepare-owner.json", "resume-owner.json"))
        val marker = AtomicFile(File(directory, name)); val out = marker.startWrite()
        val proof = JSONObject().put("tag", TAG).put("token", token).put("package", BuildConfig.APPLICATION_ID)
            .put("pid", Process.myPid()).put("start_ticks", startTicks())
        try { out.write(proof.toString().toByteArray()); marker.finishWrite(out) }
        catch (failure: Throwable) { marker.failWrite(out); throw failure }
    }
    @Synchronized fun state(): JSONObject = file.openRead().use { JSONObject(it.readBytes().toString(Charsets.UTF_8)) }.also(::validate)
    private fun validate(value: JSONObject) {
        check(value.getString("tag") == TAG && value.getString("token") == token && value.getString("package") == BuildConfig.APPLICATION_ID)
        check(UUID.fromString(value.getString("account")) != UUID.fromString(value.getString("peer")))
    }
    private fun write(value: JSONObject) {
        val bytes = value.toString().toByteArray(); check(bytes.size < 128 * 1024)
        val stream = file.startWrite()
        try { stream.write(bytes); file.finishWrite(stream) } catch (failure: Throwable) { file.failWrite(stream); throw failure }
    }
    @Synchronized fun change(block: (JSONObject) -> Unit) { val value = state(); block(value); validate(value); write(value) }
    fun model(application: Application): VipiModel {
        val before = state(); val records = PrivateRecords(application)
        if (before.getInt("auth_seeds") == 0) {
            check(before.getString("phase") == "created" && records.read("session") == null)
            records.write("session", IdentityAuthority.FALLSOFT_VIPI_PRODUCTION.tag(JSONObject()
                .put("userID", subject).put("accessToken", "inert-process-access").put("refreshToken", "inert-process-refresh")))
            change { it.put("auth_seeds", 1) }
        } else {
            val session = requireNotNull(records.read("session"))
            check(session.getString("userID") == subject && session.getString("accessToken") == "inert-process-access")
            val profile = requireNotNull(records.read("profile-" + hash(subject)))
            check(ChatProfile.parse(profile).id == account)
            assertDurableQueued(application)
        }
        peerVault = MessageVault(application, peer)
        peerCore = MessagingCore(requireNotNull(peerVault))
        val core = requireNotNull(peerCore)
        if (!before.has("peer_publication")) {
            val publication = core.keys.publication(System.currentTimeMillis(), 2); core.keys.published(1)
            change { it.put("peer_publication", publication).put("peer_device", core.device.id) }
        } else check(core.device.id.toString() == before.getString("peer_device"))
        return VipiModel(application, NoJourneyModelTranslation, this)
    }
    override fun transport(authentication: Authentication, userID: String): ChatTransport {
        check(userID == subject)
        return object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject {
                val current = state()
                if (current.getBoolean("offline")) throw IOException("Controlled local relay unavailable")
                fun requireDevice() {
                    check(device != null && device.id.toString() == current.getString("device_id") && device.secret == current.getString("device_secret"))
                }
                return when {
                    method == "GET" && path == "/v1/me" -> {
                        if (!current.getBoolean("created")) throw ServiceFailure(404, "profile_required")
                        ChatProfile(account, "process_tester", "Process Tester").json()
                    }
                    method == "PUT" && path == "/v1/me" -> {
                        check(!current.getBoolean("created")); val input = requireNotNull(body)
                        check(input.getString("username") == "process_tester" && input.getString("display_name") == "Process Tester")
                        val start = Instant.now()
                        change { it.put("created", true).put("profile_writes", it.getInt("profile_writes") + 1)
                            .put("trial_started", start.toString()).put("trial_ends", start.plus(Duration.ofDays(30)).toString()) }
                        ChatProfile(account, "process_tester", "Process Tester").json()
                    }
                    method == "POST" && path == "/v1/devices" -> {
                        check(current.getInt("registrations") == 0)
                        val input = requireNotNull(body); check(!input.optBoolean("replace_active"))
                        change { it.put("registrations", 1).put("device_id", input.getString("device_id")).put("device_secret", input.getString("secret")) }
                        JSONObject().put("id", input.getString("device_id")).put("active", true)
                    }
                    path == "/v1/keys" -> { requireDevice(); JSONObject().put("revision", 1).put("remaining", 20) }
                    method == "GET" && path.startsWith("/v1/blocks/") -> { requireDevice(); JSONObject().put("blocked", false) }
                    method == "GET" && path == "/v1/people/process_friend" -> {
                        requireDevice(); ChatProfile(peer, "process_friend", "Process Friend").json()
                    }
                    method == "POST" && path == "/v1/people/$peer/keys" -> {
                        requireDevice(); val publication = current.getJSONObject("peer_publication")
                        JSONObject().put("request_id", requireNotNull(body).getString("request_id"))
                            .put("user_id", peer).put("device_id", current.getString("peer_device")).put("signal_device_id", 1)
                            .put("registration_id", publication.getInt("registration_id")).put("identity_key", publication.getString("identity_key"))
                            .put("signed", publication.getJSONObject("signed")).put("one_time", publication.getJSONArray("one_time").getJSONObject(0))
                    }
                    method == "GET" && path == "/v1/messages/pending" -> {
                        requireDevice(); JSONObject().put("messages", JSONArray().apply {
                            current.optJSONObject("pending_reply")?.let { put(JSONObject(it.toString())) }
                        }).put("next_cursor", JSONObject.NULL)
                    }
                    method == "POST" && path == "/v1/messages" -> {
                        requireDevice(); val wire = JSONObject(requireNotNull(body).toString())
                        check(!wire.toString().contains(PROMPT)); val id = wire.getString("id")
                        val fingerprint = hash(listOf("id", "recipient_id", "recipient_device_id", "created_at", "cipher_type", "ciphertext")
                            .joinToString("\n") { wire.get(it).toString() })
                        change {
                            check(it.getInt("post_attempts") < 8)
                            it.put("post_attempts", it.getInt("post_attempts") + 1)
                            it.getJSONArray("post_ids").put(id); it.getJSONArray("wire_hashes").put(fingerprint)
                        }
                        if (!current.has("queued_id")) {
                            change { it.put("queued_id", id).put("queued_wire_hash", fingerprint)
                                .put("queued_cipher_hash", hash(android.util.Base64.decode(wire.getString("ciphertext"), android.util.Base64.NO_WRAP)))
                                .put("offline", true) }
                            throw IOException("Connection dropped at first encrypted send")
                        }
                        check(id == current.getString("queued_id") && fingerprint == current.getString("queued_wire_hash"))
                        if (current.getInt("accepted_posts") == 0) {
                            wire.put("sender_id", account).put("sender_device_id", current.getString("device_id"))
                            val core = requireNotNull(peerCore)
                            check(core.receive(RoutedMessage.received(wire, peer), System.currentTimeMillis()).text == PROMPT)
                            val now = System.currentTimeMillis(); val replyId = UUID.randomUUID()
                            val reply = core.queue(replyId, account, REPLY, now, now).sendJSON()
                                .put("sender_id", peer).put("sender_device_id", core.device.id)
                            change { it.put("accepted_posts", 1).put("peer_decryptions", 1).put("reply_id", replyId)
                                .put("pending_reply", reply) }
                            sockets.last { it.active }.hint()
                        }
                        JSONObject().put("state", "delivered")
                    }
                    method == "POST" && current.has("reply_id") && path == "/v1/messages/${current.getString("reply_id")}/receipt" -> {
                        requireDevice(); check(current.has("pending_reply") && current.getInt("reply_receipts") == 0)
                        change { it.remove("pending_reply"); it.put("reply_receipts", 1) }
                        JSONObject().put("state", "delivered")
                    }
                    path == "/v1/entitlements" || path.startsWith("/v1/billing/") || path.startsWith("/v1/bot/") -> {
                        commerceRequests++; error("Free friend chat must not request commerce or Bot")
                    }
                    else -> error("Unlisted controlled journey boundary: $method $path")
                }
            }
        }
    }
    override fun foregroundEvents(scope: CoroutineScope, authentication: Authentication, chat: ChatSession): ForegroundInboxEvents =
        ForegroundInboxEvents(scope, { "inert-process-access" }, chat::eventDevice, { chat.synchronize() },
            sockets = WebSocket.Factory { request, listener -> Socket(request, listener).also {
                sockets += it
                if (state().getBoolean("offline")) listener.onFailure(it, IOException("Controlled offline"), null)
                else listener.onOpen(it, Response.Builder().request(request).protocol(Protocol.HTTP_1_1).code(101).message("Controlled").build())
            } }, retryPause = { reconnect.await() })
    override fun requestPush(context: Context, registration: Boolean) = Unit
    override fun cancelPush(context: Context) = Unit
    override fun deletionTransport(authentication: Authentication) = object : DeletionTransport {
        override suspend fun submit(record: DeletionRecord): JSONObject = error("Deletion is not part of this local journey")
        override suspend fun status(record: DeletionRecord): JSONObject = error("Deletion is not part of this local journey")
    }
    fun restoreNetwork() { check(state().getBoolean("offline")); change { it.put("offline", false) }; reconnect.complete(Unit) }
    fun assertNoPurchase() { assertEquals(0, commerceRequests) }
    fun assertDurableQueued(context: Context) {
        val saved = state(); val id = UUID.fromString(saved.getString("queued_id"))
        MessageVault(context, account).use { vault ->
            val history = ConversationHistory(vault); val journal = MessageJournal(vault)
            assertEquals(DRAFT, history.composeDraft(peer))
            val row = requireNotNull(journal.outgoing(id)); assertEquals(PROMPT, row.text); assertNotEquals("delivered", row.state)
            assertEquals(saved.getString("queued_cipher_hash"), hash(row.envelope.ciphertext))
            vault.transaction { assertEquals(listOf(id.toString()), vault.ids("pending")) }
        }
    }
    fun writeReadyMarker() {
        val marker = AtomicFile(File(directory, "ready.json")); val out = marker.startWrite()
        try { out.write(publicProof().put("requires_host_force_stop", true).toString().toByteArray()); marker.finishWrite(out) }
        catch (failure: Throwable) { marker.failWrite(out); throw failure }
    }
    fun publicProof(): JSONObject {
        val s = state()
        return JSONObject().put("token", token).put("first_process", s.getJSONObject("first_process"))
            .put("current_process", JSONObject().put("pid", Process.myPid()).put("start_ticks", startTicks()))
            .put("profile_writes", s.getInt("profile_writes")).put("auth_seeds", s.getInt("auth_seeds"))
            .put("device_registrations", s.getInt("registrations")).put("post_attempts", s.getInt("post_attempts"))
            .put("accepted_posts", s.getInt("accepted_posts")).put("peer_decryptions", s.getInt("peer_decryptions"))
            .put("incoming_receipts", s.getInt("reply_receipts")).put("queued_id_sha256", hash(s.getString("queued_id")))
            .put("wire_sha256", s.getString("queued_wire_hash")).put("cipher_sha256", s.getString("queued_cipher_hash"))
            .put("draft_sha256", hash(DRAFT)).put("account_sha256", hash(s.getString("account")))
            .put("peer_sha256", hash(s.getString("peer"))).put("phase", s.getString("phase"))
    }
    override fun close() { sockets.forEach { it.cancel() }; peerVault?.close(); peerVault = null; peerCore = null }
    fun eraseOwnedControl() {
        val s = state(); check(s.getString("phase") == "completed" && s.getInt("accepted_posts") == 1 && s.getInt("reply_receipts") == 1)
        check(directory.listFiles().orEmpty().all { it.name in setOf("relay.json", "relay.json.bak", "relay.json.new", "ready.json", "ready.json.bak", "ready.json.new", "prepare-owner.json", "prepare-owner.json.bak", "prepare-owner.json.new", "resume-owner.json", "resume-owner.json.bak", "resume-owner.json.new") &&
            it.isFile && !java.nio.file.Files.isSymbolicLink(it.toPath()) })
        val keys = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        listOf(account, peer).forEach { keys.deleteEntry("co.fallsoft.vipi.messages.$it") }
        check(directory.deleteRecursively())
    }
    private class Socket(private val request: Request, private val listener: WebSocketListener) : WebSocket {
        var active = true
        override fun request() = request
        override fun queueSize() = 0L
        override fun send(text: String): Boolean = error("Application content must not use the event socket")
        override fun send(bytes: ByteString): Boolean = error("Application content must not use the event socket")
        override fun close(code: Int, reason: String?): Boolean { active = false; return true }
        override fun cancel() { active = false }
        fun hint() { check(active); listener.onMessage(this, "{\"event\":\"inbox_changed\"}") }
    }
}
