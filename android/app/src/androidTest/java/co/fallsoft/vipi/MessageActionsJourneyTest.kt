package co.fallsoft.vipi

import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import org.junit.Rule
import org.junit.Test
import java.util.UUID

/** Regular MainActivity + durable synthetic account. The paired relay test covers actual transport. */
class MessageActionsJourneyTest {
    @get:Rule val compose = createEmptyComposeRule()

    @Test fun composeReplyThenOpenEmbeddedPreviewAndReactionControls() {
        val service = JourneyServices(false, accountDisplayName = "Alex", peerDisplayName = "Maya")
        val original = UUID.randomUUID()
        val featureRow = UUID.randomUUID()
        val device = UUID.randomUUID()
        val url = "https://example.com/"
        val originalBody = "Coffee by the station?"
        val msg = "Let's meet here: $url"
        MainActivityJourneyFixture("message-actions", { app ->
            MessageVault(app, service.account).use { vault ->
                ConversationHistory(vault)
                vault.transaction {
                    vault.put("contact", service.peer.toString(), ChatProfile(service.peer, "maya", "Maya").json().toString().toByteArray())
                    val now = System.currentTimeMillis()-10_000
                    fun row(id: UUID, text: String, out: Boolean, time: Long, features: ChatFeatures) {
                        val sender = if (out) service.account else service.peer
                        val e = ChatEnvelope(id, sender, if (out) service.peer else service.account, time, 2, ByteArray(64))
                        val kind = if (out) "outgoing" else "incoming"
                        vault.put(kind, id.toString(), StoredChat(e, text, "delivered", true, features = features).encode())
                        ConversationHistory.record(vault, kind, id, service.peer, time)
                    }
                    row(original, originalBody, true, now, ChatFeatures.EMPTY)
                    row(featureRow, msg, false, now + 1000, ChatFeatures(
                        MessageQuote(original, service.account, "text", originalBody), LinkSnapshot(url, "Saturday coffee • Station Café")))
                    ConversationReactions(vault).record(ConversationRef.Direct(service.peer),
                        MessageReaction(original, service.account, 1, "❤️"), service.peer, device)
                }
                service.generatedPeerReplies[featureRow] = msg
            }
            service.model(app)
        }).use { f ->
            f.launch()
            fun tag(s: String) = compose.onNodeWithTag(s, useUnmergedTree = true)
            fun await(s: String) = compose.waitUntil(20_000) { runCatching { tag(s).isDisplayed() }.getOrDefault(false) }
            fun capture(s: String) {
                compose.waitForIdle()
                android.os.SystemClock.sleep(360)
                f.capture(s)
            }
            val inbox = "inbox-row-${service.peer}"
            await(inbox)
            tag(inbox).performClick()
            val row = "message-row-$featureRow"
            await(row)
            compose.onNodeWithText("Saturday coffee • Station Café", useUnmergedTree = true).assertIsDisplayed()
            capture("01-reply-card-and-reaction")
            val editor = tag("message-input")
            editor.performTextInput("I'll be there.")
            // Swipe through the bubble body while the draft is already nonempty.
            tag(row).performTouchInput {
                val y = height * .62f
                swipe(Offset(width * .17f, y), Offset(width * .86f, y), durationMillis = 220)
            }
            val removeQuote = compose.onNodeWithContentDescription(f.base.getString(R.string.message_remove_quote), useUnmergedTree = true)
            compose.waitUntil(8_000) { runCatching { removeQuote.isDisplayed() }.getOrDefault(false) }
            editor.assertTextContains("I'll be there.")
            capture("02-swipe-reply-keeps-draft")
            removeQuote.performClick()
            editor.assertTextContains("I'll be there.")
            editor.performTextReplacement("")
            f.device.pressBack()
            val footer = hasAnyAncestor(hasTestTag(row)) and hasContentDescription(f.base.getString(R.string.message_actions))
            compose.onNode(footer, useUnmergedTree = true).performClick()
            compose.onNodeWithText(f.base.getString(R.string.message_more_emoji)).assertIsDisplayed()
            capture("03-message-action-menu")
            compose.onNodeWithText(f.base.getString(R.string.message_more_emoji)).performClick()
            compose.onNodeWithText(f.base.getString(R.string.message_any_emoji)).assertIsDisplayed()
        }
    }
}
