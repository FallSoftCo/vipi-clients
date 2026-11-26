package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.net.InetAddress
import java.util.UUID

class ChatFeatureDeviceTest {
    @Test fun orderingTombstoneHiddenHistoryAndComposerRestart() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val account = UUID.randomUUID()
        val peer = UUID.randomUUID()
        val device = UUID.randomUUID()
        val target = UUID.randomUUID()
        val group = UUID.randomUUID()
        val ref = ConversationRef.Direct(peer)
        val q = MessageQuote(target, peer, "text", "At the café")
        MessageVault(context, account).use { vault ->
            ConversationHistory(vault)
            val journal = MessageJournal(vault)
            val ledger = ConversationReactions(vault)
            val timestamp = System.currentTimeMillis()
            fun receive(id: UUID, text: String, features: ChatFeatures): ChatEnvelope {
                val e = ChatEnvelope(id, peer, account, timestamp, 2, ByteArray(64) { 7 })
                journal.receive(e, timestamp) { _,_ ->
                    vault.put("incoming-route", id.toString(), device.toString().toByteArray())
                    vault.put("peer-device", peer.toString(), device.toString().toByteArray())
                    JSONObject().put("version", 1).put("id", id).put("sender", peer).put("recipient", account)
                        .put("createdAt", timestamp).put("text", text).also(features::write).toString().toByteArray()
                }
                return e
            }
            fun update(seq: Int, emoji: String?) = receive(UUID.randomUUID(), ChatFeatures.EVENT_BODY,
                ChatFeatures(reaction = MessageReaction(target, peer, seq, emoji)))
            val last = update(3, null)
            update(1, "👍")
            journal.receive(last, timestamp) { _,_ -> error("duplicate decrypted") }
            assertTrue(ConversationHistory(vault).threads().isEmpty())
            receive(target, "At the café", ChatFeatures.EMPTY)
            assertEquals(3 to null, ledger.observed(ref, target, peer, peer))
            update(2, "❤️")
            assertEquals(emptyMap<UUID, String>(), ledger.visible(ref, target, peer))
            update(4, "❤️")
            assertEquals(mapOf(peer to "❤️"), ledger.visible(ref, target, peer))
            assertTrue(ledger.visible(ConversationRef.Group(group), target, peer).isEmpty())
            assertEquals(1, ConversationHistory(vault).threads().single().unread)
            assertEquals(target, ConversationHistory(vault).messages(peer).single().id)
            val draft = MessageActionDraft(vault, ref)
            draft.quote(q)
            draft.preview(LinkSnapshot("https://example.com/", "Example site"))
            assertEquals(null, draft.forSend("No link here").preview)
        }
        MessageVault(context, account).use { vault ->
            assertEquals(q, MessageActionDraft(vault, ref).features.reply)
            assertEquals("Example site", MessageActionDraft(vault, ref).features.preview?.title)
            assertEquals(4 to "❤️", ConversationReactions(vault).observed(ref, target, peer, peer))
        }
    }
    @Test fun payloadBoundsAndPrivatePreviewFiltering() {
        for (url in listOf("http://example.com/", "https://localhost/", "https://192.168.1.1/", "https://[::1]/",
            "https://user@example.com/", "https://intranet.local/", "https://example.com:8443/")) assertNull(ChatFeatures.safeLink(url))
        for (ip in listOf("127.0.0.1", "10.1.2.3", "100.64.0.1", "192.0.2.1", "169.254.169.254", "fc00::1", "fe80::1", "2001:db8::1"))
            assertFalse(SenderLinkPreview.publicAddress(InetAddress.getByName(ip)))
        assertTrue(SenderLinkPreview.publicAddress(InetAddress.getByName("1.1.1.1")))
        val url = "https://example.com/"
        val title = SenderLinkPreview.metadata("<title>Tea &amp; coffee</title>").first
        assertEquals("Tea & coffee", title)
        val src = JSONObject().put("text", url)
        ChatFeatures(preview = LinkSnapshot(url, requireNotNull(title))).write(src)
        assertNull(ChatFeatures.parse(src, "different link").preview)
        assertEquals(title, ChatFeatures.parse(src, url).preview?.title)
        src.getJSONObject("chat_features").put("version", 7)
        assertEquals(ChatFeatures.EMPTY, ChatFeatures.parse(src, url))
        assertFalse(ChatFeatures.validEmoji("two 🚀🚀"))
        assertTrue(ChatFeatures.validEmoji("👨‍👩‍👧‍👦"))
    }
    @Test fun optionalPublicSenderPreviewSmoke() = runBlocking {
        assumeTrue(InstrumentationRegistry.getArguments().getString("publicPreviewSmoke") == "true")
        val preview = requireNotNull(SenderLinkPreview.load("https://example.com/"))
        assertEquals("example.com", preview.host)
        assertTrue(preview.title.contains("Example", ignoreCase = true))
    }
}
