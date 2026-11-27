package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.util.UUID
import kotlinx.coroutines.runBlocking
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Two explicitly separate lanes: real owned WorkOS sessions, or fresh signed local test
 * authentication over loopback. Both use the normal API and native libsignal; the synthetic lane
 * never accesses native sessions or WorkOS.
 */
@RunWith(AndroidJUnit4::class)
class NetworkMessagingDeviceTest {
    private val context
        get() = InstrumentationRegistry.getInstrumentation().targetContext

    private fun file(name: String) = File(context.filesDir, name)

    private fun configuration(): JSONObject {
        assumeTrue(InstrumentationRegistry.getArguments().getString("vipiLiveNetwork") == "true")
        return JSONObject(file("network-config.json").readText()).also {
            require(it.getString("username").startsWith("vqa_"))
            if (it.optBoolean("isolated_signed_authentication")) {
                val endpoint = java.net.URI(it.getString("endpoint"))
                require(
                    endpoint.scheme == "http" && endpoint.host == "127.0.0.1" && endpoint.port > 0
                )
                require(
                    InstrumentationRegistry.getArguments()
                        .getString("vipiIsolatedSignedAuthentication") == "true"
                )
                require(!it.optBoolean("isolated_fresh_profile"))
                require(it.getString("expected_subject").startsWith("user_localpair_"))
                require(it.getString("access_token").length > 100)
            }
            if (it.optBoolean("isolated_fresh_profile")) {
                val endpoint = java.net.URI(it.getString("endpoint"))
                require(
                    endpoint.scheme == "http" && endpoint.host == "127.0.0.1" && endpoint.port > 0
                )
                require(
                    InstrumentationRegistry.getArguments().getString("vipiUseNativeSession") ==
                        "true"
                )
                require(it.getString("expected_subject").startsWith("user_"))
            }
        }
    }

    private fun client(config: JSONObject): ChatTransport {
        if (config.optBoolean("isolated_signed_authentication"))
            return SignedLoopbackPairTransport(
                config.getString("endpoint"),
                config.getString("access_token"),
            )
        val authentication = Authentication(context)
        return ServiceClient(
            authentication,
            requireNotNull(authentication.userID),
            config.getString("endpoint"),
        )
    }

    @Test
    fun inspectOwnedSessionWithoutExportingCredentials() {
        val config = configuration()
        require(InstrumentationRegistry.getArguments().getString("vipiUseNativeSession") == "true")
        val expected = config.getString("expected_subject")
        val session = PrivateRecords(context).read("session")
        // Export native metadata only, never encrypted records or token bytes.
        file("network-session-readiness.json")
            .writeText(
                JSONObject()
                    .put("run", config.getString("run"))
                    .put("session_present", session != null)
                    .put("matches_expected_subject", session?.getString("userID") == expected)
                    .put(
                        "authority",
                        session?.let { IdentityAuthority.read(it).recordID } ?: "absent",
                    )
                    .put("credentials_exported", false)
                    .toString()
            )
    }

    @Test
    fun publishAndroidKeys() = runBlocking {
        val config = configuration()
        val records = PrivateRecords(context)
        val synthetic = config.optBoolean("isolated_signed_authentication")
        val original = if (synthetic) null else records.read("session")
        val nativeSession =
            InstrumentationRegistry.getArguments().getString("vipiUseNativeSession") == "true"
        val fixture =
            if (synthetic) JSONObject()
            else if (nativeSession) {
                // A real hosted PKCE login remains in encrypted app storage. Bind
                // this opt-in probe to the dedicated account, never a real user.
                requireNotNull(original).also {
                    assertEquals(config.getString("expected_subject"), it.getString("userID"))
                    config.put("native_session", true)
                    file("network-config.json").writeText(config.toString())
                }
            } else {
                if (original != null) records.write("qa-session-backup", original)
                JSONObject(file("network-session.json").readText()).also {
                    file("network-session.json").delete()
                }
            }
        // The first API call must go through a real public refresh-token exchange.
        if (!synthetic) {
            fixture.put("accessToken", "expired-native-qa-token")
            records.write("session", fixture)
        }
        val api = client(config)
        val fresh = config.optBoolean("isolated_fresh_profile")
        val profile =
            if (nativeSession && !fresh) api.request("GET", "/v1/me")
            else
                api.request(
                    "PUT",
                    "/v1/me",
                    JSONObject()
                        .put("username", config.getString("username"))
                        .put("display_name", "Vipi Android QA"),
                )
        assertEquals(config.getString("username"), profile.getString("username"))
        val account = UUID.fromString(profile.getString("id"))
        MessageVault(context, account).use { vault ->
            val core = MessagingCore(vault)
            if (!nativeSession || fresh)
                api.request(
                    "POST",
                    "/v1/devices",
                    JSONObject().put("device_id", core.device.id).put("secret", core.device.secret),
                )
            else
                assertEquals(
                    core.device.id.toString(),
                    vault.transaction {
                        vault.get("local", "registered-device")?.toString(Charsets.UTF_8)
                    },
                )
            val inventory = api.request("GET", "/v1/keys", device = core.device)
            if (!nativeSession || fresh || inventory.getInt("remaining") < 10) {
                val publication = core.keys.publication(System.currentTimeMillis())
                val result = api.request("PUT", "/v1/keys", publication, core.device)
                core.keys.published(result.getInt("revision"))
                assertTrue(result.getInt("remaining") >= 20)
            } else assertTrue(inventory.getInt("remaining") >= 10)
            assertEquals(core.device.id, DeviceCredential.load(vault).id)
        }
        file("network-state.json")
            .writeText(
                JSONObject().put("account", account).put("run", config.getString("run")).toString()
            )
        file("network-published.json")
            .writeText(
                JSONObject().put("run", config.getString("run")).put("published", true).toString()
            )
    }

    @Test
    fun receiveSwiftAndReply() = runBlocking {
        val config = configuration()
        val api = client(config)
        val state = JSONObject(file("network-state.json").readText())
        assertEquals(config.getString("run"), state.getString("run"))
        val account = UUID.fromString(state.getString("account"))
        MessageVault(context, account).use { vault ->
            val core = MessagingCore(vault)
            val messages =
                api.request("GET", "/v1/messages/pending", device = core.device)
                    .getJSONArray("messages")
            assertEquals(1, messages.length())
            val routed = RoutedMessage.received(messages.getJSONObject(0), account)
            val received = core.receive(routed, System.currentTimeMillis())
            assertEquals("Swift over the real relay — café ☕ مرحباً", received.text)
            assertEquals(received.text, core.receive(routed, System.currentTimeMillis()).text)
            assertTrue(
                runCatching {
                    core.receive(
                        routed.copy(senderDevice = UUID.randomUUID()),
                        System.currentTimeMillis(),
                    )
                }
                    .isFailure
            )
            assertEquals(
                "delivered",
                api.request(
                        "POST",
                        "/v1/messages/${routed.envelope.id}/receipt",
                        device = core.device,
                    )
                    .getString("state"),
            )
            assertEquals(
                config.getString("peer"),
                FriendInvitationLink.username(
                    "https://api.mambovipi.app/invite/${config.getString("peer")}"
                ),
            )
            val peer =
                api.request("GET", "/v1/people/${config.getString("peer")}", device = core.device)
            assertEquals(routed.envelope.sender.toString(), peer.getString("id"))
            val outgoing = JSONArray()
            for (index in 0..2) {
                val now = System.currentTimeMillis()
                val id = UUID.randomUUID()
                val message =
                    core.queue(
                        id,
                        routed.envelope.sender,
                        "Android HTTP reply $index — río ☕",
                        now,
                        now,
                    )
                // Reopen durable state before first transport dispatch. Retrying the
                // queued original must neither re-encrypt nor allocate a new ID.
                val retry =
                    MessageVault(context, account).use { reopened ->
                        val reopenedCore = MessagingCore(reopened)
                        assertTrue(reopenedCore.journal.pending(now).any { it.id == id })
                        reopenedCore.queue(
                            id,
                            routed.envelope.sender,
                            "Android HTTP reply $index — río ☕",
                            now,
                            now,
                        )
                    }
                assertEquals(message.envelope.id, retry.envelope.id)
                assertArrayEquals(message.envelope.ciphertext, retry.envelope.ciphertext)
                val status = api.request("POST", "/v1/messages", retry.sendJSON(), core.device)
                assertEquals("accepted", status.getString("state"))
                core.journal.applyStatus(id, "accepted")
                outgoing.put(message.sendJSON())
            }
            state.put("outgoing", outgoing)
        }
        file("network-state.json").writeText(state.toString())
        file("network-replied.json")
            .writeText(
                JSONObject()
                    .put("run", config.getString("run"))
                    .put("received", 1)
                    .put("sent", 3)
                    .toString()
            )
    }

    @Test
    fun verifyDeliveryAndRestoreSession() = runBlocking {
        val config = configuration()
        val api = client(config)
        val state = JSONObject(file("network-state.json").readText())
        assertEquals(config.getString("run"), state.getString("run"))
        MessageVault(context, UUID.fromString(state.getString("account"))).use { vault ->
            val core = MessagingCore(vault)
            val outgoing = state.getJSONArray("outgoing")
            for (index in 0 until outgoing.length()) {
                val item = outgoing.getJSONObject(index)
                val id = UUID.fromString(item.getString("id"))
                val status = api.request("GET", "/v1/messages/$id", device = core.device)
                assertEquals("delivered", status.getString("state"))
                core.journal.applyStatus(id, "delivered")
                assertEquals(
                    "delivered",
                    api.request("POST", "/v1/messages", item, core.device).getString("state"),
                )
            }
            assertTrue(core.journal.pending(System.currentTimeMillis()).isEmpty())
        }
        val records = PrivateRecords(context)
        if (config.optBoolean("isolated_signed_authentication")) {
            // Native session storage remains untouched in this explicit lane.
        } else if (!config.optBoolean("native_session", false)) {
            records.read("qa-session-backup")?.let { records.write("session", it) }
                ?: records.remove("session")
            records.remove("qa-session-backup")
        } else
            assertEquals(
                config.getString("expected_subject"),
                records.read("session")!!.getString("userID"),
            )
        file("network-config.json").delete()
        file("network-complete.json")
            .writeText(
                JSONObject()
                    .put("run", config.getString("run"))
                    .put("delivered", 3)
                    .put("duplicate_send_preserved_delivery", true)
                    .put("offline_queue_reopened", true)
                    .put("stable_id_and_ciphertext", true)
                    .put("invitation_username_preserved", true)
                    .put(
                        "authentication_lane",
                        if (config.optBoolean("isolated_signed_authentication"))
                            "explicit local signed test authentication"
                        else "real WorkOS",
                    )
                    .put(
                        "scope",
                        "native libsignal/durable stores/real HTTP; no hosted sign-up UI or FCM",
                    )
                    .toString()
            )
    }
}

/** Explicit test lane; no native session/token refresh or production endpoint. */
internal class SignedLoopbackPairTransport(endpoint: String, private val token: String) :
    ChatTransport {
    private val base = endpoint.toHttpUrl()
    private val http =
        okhttp3.OkHttpClient.Builder()
            .followRedirects(false)
            .followSslRedirects(false)
            .retryOnConnectionFailure(false)
            .callTimeout(25, java.util.concurrent.TimeUnit.SECONDS)
            .build()

    init {
        require(
            base.scheme == "http" &&
                base.host == "127.0.0.1" &&
                base.encodedPath == "/" &&
                base.query == null &&
                base.fragment == null &&
                base.username.isEmpty() &&
                base.password.isEmpty()
        )
    }

    override suspend fun request(
        method: String,
        path: String,
        body: JSONObject?,
        device: DeviceCredential?,
        query: Map<String, String>,
    ): JSONObject =
        kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
            require(
                path.startsWith("/v1/") &&
                    !path.contains("..") &&
                    !path.contains('?') &&
                    !path.contains('#')
            )
            val content =
                body?.toString()?.let { it.toRequestBody("application/json".toMediaType()) }
                    ?: if (method in setOf("POST", "PUT")) ByteArray(0).toRequestBody(null)
                    else null
            val url =
                base
                    .newBuilder()
                    .encodedPath(path)
                    .apply { query.forEach { (key, value) -> addQueryParameter(key, value) } }
                    .build()
            val request =
                okhttp3.Request.Builder()
                    .url(url)
                    .method(method, content)
                    .header("Authorization", "Bearer $token")
            device?.let {
                request
                    .header("X-Vipi-Device-ID", it.id.toString())
                    .header("X-Vipi-Device-Secret", it.secret)
            }
            http.newCall(request.build()).execute().use { response ->
                check(response.isSuccessful) { "Local fixture HTTP ${response.code}" }
                val source = requireNotNull(response.body).source()
                source.request(12_000_001)
                check(source.buffer.size <= 12_000_000)
                JSONObject(source.readUtf8())
            }
        }
}
