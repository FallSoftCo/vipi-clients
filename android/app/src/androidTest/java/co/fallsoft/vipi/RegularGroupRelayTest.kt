package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import java.net.URI

class RegularGroupRelayTest {
    @Test fun twoRealClientsCreateInviteAndAcceptOnPrivateRelay() {
        assumeTrue(InstrumentationRegistry.getArguments().getString("vipiPrivateGroupRelay") == "true")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val config = JSONObject(File(context.filesDir, "group-relay-fixture.json").readText())
        val endpoint = config.getString("endpoint")
        require(URI(endpoint).let { it.host == "127.0.0.1" && it.scheme == "http" && it.port > 0 })
        val accounts = config.getJSONArray("accounts")
        MainActivityJourneyFixture("real-group-alice").use { aliceOwner ->
            MainActivityJourneyFixture("real-group-bob").use { bobOwner ->
                runBlocking { withContext(Dispatchers.Main.immediate) {
                    suspend fun start(owner: MainActivityJourneyFixture, account: JSONObject): ChatSession {
                        val app = owner.isolated
                        val user = account.getString("subject")
                        PrivateRecords(app).write("session", IdentityAuthority.FALLSOFT_VIPI_PRODUCTION.tag(JSONObject()
                            .put("userID", user).put("accessToken", account.getString("access_token")).put("refreshToken", "private-fixture")))
                        val chat = ChatSession(app, ServiceClient(Authentication(app), user, endpoint), user)
                        chat.start()
                        if (chat.needsProfile) chat.createProfile(account.getString("username"), account.getString("display_name"))
                        assertTrue(chat.notice, chat.ready)
                        assertTrue(requireNotNull(chat.groups).remoteAvailable)
                        return chat
                    }
                    start(aliceOwner, accounts.getJSONObject(0)).use { alice ->
                        start(bobOwner, accounts.getJSONObject(1)).use { bob ->
                            val friend = alice.find(accounts.getJSONObject(1).getString("username"))
                            assertEquals(requireNotNull(bob.profile).id, friend.id)
                            val sender = requireNotNull(alice.groups)
                            val receiver = requireNotNull(bob.groups)
                            val group = requireNotNull(sender.create("Native relay group", setOf(friend.id)))
                            assertTrue(sender.notice, sender.invite(group, friend.id))
                            receiver.refresh()
                            val invitation = receiver.invitations.single { it.group == group.id }
                            receiver.answer(invitation, true)
                            assertNull(receiver.notice)
                            sender.refresh()
                            assertEquals(setOf(requireNotNull(alice.profile).id, friend.id),
                                requireNotNull(sender.group(group.id)).members.map { it.id }.toSet())
                            assertEquals(group.id, requireNotNull(receiver.group(group.id)).id)
                            assertTrue(alice.savedFriends().any { it.id == friend.id })
                            val proof = JSONObject().put("group", group.id).put("members", 2).put("negotiated_protocol", 1)
                            File(aliceOwner.output, "real-relay-result.json").writeText(proof.toString())
                        }
                    }
                } }
            }
        }
    }
}
