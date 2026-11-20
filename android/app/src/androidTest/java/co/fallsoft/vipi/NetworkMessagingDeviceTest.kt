package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.UUID

/** Explicitly invoked against the isolated real-WorkOS HTTP harness. Never
 * accepts a test verifier, server private key, or plaintext relay. */
@RunWith(AndroidJUnit4::class)
class NetworkMessagingDeviceTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private fun file(name: String) = File(context.filesDir, name)
    private fun configuration(): JSONObject {
        assumeTrue(InstrumentationRegistry.getArguments().getString("vipiLiveNetwork") == "true")
        return JSONObject(file("network-config.json").readText()).also {
            require(it.getString("username").startsWith("vqa_"))
            if (it.optBoolean("isolated_fresh_profile")) {
                val endpoint = java.net.URI(it.getString("endpoint"))
                require(endpoint.scheme == "http" && endpoint.host == "127.0.0.1" && endpoint.port > 0)
                require(InstrumentationRegistry.getArguments().getString("vipiUseNativeSession") == "true")
                require(it.getString("expected_subject").startsWith("user_"))
            }
        }
    }
    private fun client(config: JSONObject): ServiceClient {
        val authentication = Authentication(context)
        return ServiceClient(authentication, requireNotNull(authentication.userID), config.getString("endpoint"))
    }
    @Test fun inspectOwnedSessionWithoutExportingCredentials() {
        val config = configuration()
        require(InstrumentationRegistry.getArguments().getString("vipiUseNativeSession") == "true")
        val expected = config.getString("expected_subject")
        val session = PrivateRecords(context).read("session")
        // Export native metadata only, never encrypted records or token bytes.
        file("network-session-readiness.json").writeText(JSONObject().put("run", config.getString("run"))
            .put("session_present", session != null).put("matches_expected_subject", session?.getString("userID") == expected)
            .put("authority", session?.let { IdentityAuthority.read(it).recordID } ?: "absent")
            .put("credentials_exported", false).toString())
    }
    @Test fun publishAndroidKeys() = runBlocking {
        val config = configuration(); val records = PrivateRecords(context)
        val original = records.read("session")
        val nativeSession = InstrumentationRegistry.getArguments().getString("vipiUseNativeSession") == "true"
        val fixture = if (nativeSession) {
            // A real hosted PKCE login remains in encrypted app storage. Bind
            // this opt-in probe to the dedicated account, never a real user.
            requireNotNull(original).also {
                assertEquals(config.getString("expected_subject"), it.getString("userID"))
                config.put("native_session", true)
                file("network-config.json").writeText(config.toString())
            }
        } else {
            if (original != null) records.write("qa-session-backup", original)
            JSONObject(file("network-session.json").readText()).also { file("network-session.json").delete() }
        }
        // The first API call must go through a real public refresh-token exchange.
        fixture.put("accessToken", "expired-native-qa-token")
        records.write("session", fixture)
        val api = client(config)
        val fresh = config.optBoolean("isolated_fresh_profile")
        val profile = if (nativeSession && !fresh) api.request("GET", "/v1/me")
            else api.request("PUT", "/v1/me", JSONObject().put("username", config.getString("username")).put("display_name", "Vipi Android QA"))
        assertEquals(config.getString("username"), profile.getString("username"))
        val account = UUID.fromString(profile.getString("id"))
        MessageVault(context, account).use { vault ->
            val core = MessagingCore(vault)
            if (!nativeSession || fresh) api.request("POST", "/v1/devices", JSONObject().put("device_id", core.device.id).put("secret", core.device.secret))
            else assertEquals(core.device.id.toString(), vault.transaction { vault.get("local", "registered-device")?.toString(Charsets.UTF_8) })
            val inventory = api.request("GET", "/v1/keys", device = core.device)
            if (!nativeSession || fresh || inventory.getInt("remaining") < 10) {
                val publication = core.keys.publication(System.currentTimeMillis())
                val result = api.request("PUT", "/v1/keys", publication, core.device)
                core.keys.published(result.getInt("revision")); assertTrue(result.getInt("remaining") >= 20)
            } else assertTrue(inventory.getInt("remaining") >= 10)
            assertEquals(core.device.id, DeviceCredential.load(vault).id)
        }
        file("network-state.json").writeText(JSONObject().put("account", account).put("run", config.getString("run")).toString())
        file("network-published.json").writeText(JSONObject().put("run", config.getString("run")).put("published", true).toString())
    }
    @Test fun receiveSwiftAndReply() = runBlocking {
        val config = configuration(); val api = client(config)
        val state = JSONObject(file("network-state.json").readText()); assertEquals(config.getString("run"), state.getString("run"))
        val account = UUID.fromString(state.getString("account"))
        MessageVault(context, account).use { vault ->
            val core = MessagingCore(vault)
            val messages = api.request("GET", "/v1/messages/pending", device = core.device).getJSONArray("messages")
            assertEquals(1, messages.length())
            val routed = RoutedMessage.received(messages.getJSONObject(0), account)
            val received = core.receive(routed, System.currentTimeMillis())
            assertEquals("Swift over the real relay — café ☕ مرحباً", received.text)
            assertEquals(received.text, core.receive(routed, System.currentTimeMillis()).text)
            assertTrue(runCatching { core.receive(routed.copy(senderDevice = UUID.randomUUID()), System.currentTimeMillis()) }.isFailure)
            assertEquals("delivered", api.request("POST", "/v1/messages/${routed.envelope.id}/receipt", device = core.device).getString("state"))
            assertEquals(config.getString("peer"), FriendInvitationLink.username("https://api.mambovipi.app/invite/${config.getString("peer")}"))
            val peer = api.request("GET", "/v1/people/${config.getString("peer")}", device = core.device)
            assertEquals(routed.envelope.sender.toString(), peer.getString("id"))
            val outgoing = JSONArray()
            for (index in 0..2) {
                val now = System.currentTimeMillis(); val id = UUID.randomUUID()
                val message = core.queue(id, routed.envelope.sender, "Android HTTP reply $index — río ☕", now, now)
                // Reopen durable state before first transport dispatch. Retrying the
                // queued original must neither re-encrypt nor allocate a new ID.
                val retry = MessageVault(context, account).use { reopened ->
                    val reopenedCore = MessagingCore(reopened)
                    assertTrue(reopenedCore.journal.pending(now).any { it.id == id })
                    reopenedCore.queue(id, routed.envelope.sender, "Android HTTP reply $index — río ☕", now, now)
                }
                assertEquals(message.envelope.id, retry.envelope.id)
                assertArrayEquals(message.envelope.ciphertext, retry.envelope.ciphertext)
                val status = api.request("POST", "/v1/messages", retry.sendJSON(), core.device)
                assertEquals("accepted", status.getString("state")); core.journal.applyStatus(id, "accepted")
                outgoing.put(message.sendJSON())
            }
            state.put("outgoing", outgoing)
        }
        file("network-state.json").writeText(state.toString())
        file("network-replied.json").writeText(JSONObject().put("run", config.getString("run")).put("received", 1).put("sent", 3).toString())
    }
    @Test fun verifyDeliveryAndRestoreSession() = runBlocking {
        val config = configuration(); val api = client(config)
        val state = JSONObject(file("network-state.json").readText()); assertEquals(config.getString("run"), state.getString("run"))
        MessageVault(context, UUID.fromString(state.getString("account"))).use { vault ->
            val core = MessagingCore(vault); val outgoing = state.getJSONArray("outgoing")
            for (index in 0 until outgoing.length()) {
                val item = outgoing.getJSONObject(index); val id = UUID.fromString(item.getString("id"))
                val status = api.request("GET", "/v1/messages/$id", device = core.device)
                assertEquals("delivered", status.getString("state")); core.journal.applyStatus(id, "delivered")
                assertEquals("delivered", api.request("POST", "/v1/messages", item, core.device).getString("state"))
            }
            assertTrue(core.journal.pending(System.currentTimeMillis()).isEmpty())
        }
        val records = PrivateRecords(context)
        if (!config.optBoolean("native_session", false)) {
            records.read("qa-session-backup")?.let { records.write("session", it) } ?: records.remove("session")
            records.remove("qa-session-backup")
        } else assertEquals(config.getString("expected_subject"), records.read("session")!!.getString("userID"))
        file("network-config.json").delete()
        file("network-complete.json").writeText(JSONObject().put("run", config.getString("run")).put("delivered", 3).put("duplicate_send_preserved_delivery", true).put("offline_queue_reopened", true).put("stable_id_and_ciphertext", true).put("invitation_username_preserved", true).put("scope", "native libsignal/durable stores/real HTTP; existing sign-in, no sign-up UI or FCM").toString())
    }
}
