package co.fallsoft.vipi

import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.core.view.WindowInsetsCompat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File

/** Real MainActivity, native IME and encrypted history; no real contact/network. */
class ChatTimelineDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()
    @Test fun preserveReadingPositionAndExplicitlyReturnToLatest() = qualify(false)
    @Test fun preserveImmersedReadingPositionAndEarlierPage() = qualify(true)
    private fun qualify(immersed: Boolean) {
        //70 setup sends, one explicit UI Send and one append while following.
        //The earlier-reading append is an actual encrypted incoming peer reply.
        val services = JourneyServices(profileRequired = false, expectedBotPosts = 0, expectedFriendPosts = 72)
        MainActivityJourneyFixture(if (immersed) "friend-history-immersed" else "friend-history", services::model).use { f ->
            val handwriting = f.device.executeShellCommand("settings get secure stylus_handwriting_enabled").trim()
            val output = f.output
            lateinit var chat: ChatSession
            fun anchor(): Pair<String, Float> {
                compose.waitForIdle()
                val viewport = compose.onNodeWithTag("conversation-timeline").fetchSemanticsNode().boundsInRoot
                val node = compose.onAllNodes(SemanticsMatcher("message metadata") {
                    it.config.getOrElse(SemanticsProperties.TestTag) { "" }.startsWith("message-meta-")
                }).fetchSemanticsNodes().filter { it.boundsInRoot.top >= viewport.top && it.boundsInRoot.bottom <= viewport.bottom }
                    .minBy { it.boundsInRoot.top }
                return node.config[SemanticsProperties.TestTag] to node.boundsInRoot.top
            }
            fun capture(name: String) {
                compose.waitForIdle()
                f.capture(name)
                File(output, "$name-compose-tree.txt").writeText(compose.onRoot(useUnmergedTree = true).printToString())
            }
            fun message(text: String): SemanticsNodeInteraction {
                val id = runBlocking { withContext(Dispatchers.Main) { chat.messages(services.peer).single { it.text == text }.id } }
                return compose.onNodeWithTag("message-meta-$id")
            }
            fun imeVisible(): Boolean {
                var shown = false
                f.instrumentation.runOnMainSync {
                    shown = android.view.inspector.WindowInspector.getGlobalWindowViews().any { view ->
                        view.rootWindowInsets?.let { WindowInsetsCompat.toWindowInsetsCompat(it).isVisible(WindowInsetsCompat.Type.ime()) } == true
                    }
                }
                return shown
            }
            try {
                f.device.executeShellCommand("settings put secure stylus_handwriting_enabled 0")
                f.instrumentation.runOnMainSync {
                    f.model.selectKnown("en"); f.model.selectTarget("sw"); f.model.changeDensity(.5)
                    f.model.changeAppearance(Appearance.LIGHT)
                }
                f.launch()
                compose.waitUntil(10_000) { f.model.screen == Screen.HOME && f.model.chat?.ready == true }
                runBlocking { withContext(Dispatchers.Main) {
                    chat = requireNotNull(f.model.chat)
                    val peer = chat.find("journey_friend"); assertEquals(services.peer, peer.id)
                    repeat(70) { index ->
                        val extra = if (index < 20) " We can meet by the station and decide where to walk.".repeat((index + 1) % 5) else ""
                        val text = if (immersed) listOf("I am reading a book now.", "I am drinking water now.", "Where is the phone charger?", "Ninapenda muziki.")[index % 4]
                            else "History message ${index + 1}. We are making plans for tomorrow." + extra
                        chat.send(text, services.peer)
                        android.os.SystemClock.sleep(2)
                    }
                    chat.synchronize()
                    assertEquals(70, services.friendPosts.get())
                    assertNotNull(services.peerReceived)
                } }
                //Open through the production chat list, not a substitute screen.
                compose.onNodeWithText("Journey Friend").performScrollTo().performTouchInput { click() }
                compose.waitUntil(8_000) { f.model.screen == Screen.CONVERSATION }
                val latestID = runBlocking { withContext(Dispatchers.Main) { chat.messages(services.peer).maxBy { it.cursor }.id } }
                compose.onNodeWithTag("message-meta-$latestID").assertIsDisplayed()
                if (immersed) {
                    compose.waitUntil(20_000) {
                        var found = false
                        f.instrumentation.runOnMainSync { found = f.paragraphs().any { it.visibleText().contains("maji") } }
                        found
                    }
                }
                compose.onNodeWithTag("conversation-timeline").performTouchInput { swipeDown() }
                compose.onNodeWithTag("conversation-timeline").performTouchInput { swipeDown() }
                compose.onNodeWithContentDescription("Jump to latest messages").assertIsDisplayed()
                val before = anchor()
                compose.runOnIdle { services.queuePeerReplyAndSignalInbox() }
                compose.waitUntil(8_000) {
                    chat.messages(services.peer).singleOrNull { !it.outgoing }?.id == services.friendReplyId &&
                        services.friendReplyReceipts.get() == 1
                }
                val after = anchor()
                assertEquals(before.first, after.first); assertEquals(before.second, after.second, 1f)
                assertEquals(70, services.friendPosts.get())
                capture("android-reading-preserved-light")
                compose.onNodeWithTag("message-input").performTouchInput { click() }
                compose.waitUntil(5_000) { imeVisible() }
                compose.onNodeWithTag("message-input").performTextInput("A draft while reading")
                compose.onNodeWithTag(before.first).assertIsDisplayed()
                assertEquals("Opening the native IME moved the reading anchor", before.second,
                    compose.onNodeWithTag(before.first).fetchSemanticsNode().boundsInRoot.top, 1f)
                compose.onNodeWithContentDescription("Jump to latest messages").assertIsDisplayed()
                capture("android-reading-with-keyboard-light")
                compose.onNodeWithContentDescription("Send message").performTouchInput { click() }
                compose.waitUntil(8_000) { services.friendPosts.get() == 71 }
                capture("android-own-send-position")
                message("A draft while reading").assertIsDisplayed()
                compose.onNodeWithContentDescription("Jump to latest messages").assertDoesNotExist()
                f.device.pressBack(); compose.waitUntil(5_000) { !imeVisible() }
                compose.onNodeWithTag("conversation-timeline").performTouchInput { swipeDown() }
                compose.onNodeWithContentDescription("Jump to latest messages").assertIsDisplayed()
                compose.runOnIdle { f.model.changeAppearance(Appearance.DARK) }
                capture("android-jump-control-dark")
                compose.onNodeWithContentDescription("Jump to latest messages").performTouchInput { click() }
                message("A draft while reading").assertIsDisplayed()
                compose.onNodeWithContentDescription("Jump to latest messages").assertDoesNotExist()
                runBlocking { withContext(Dispatchers.Main) {
                    chat.send("Appended while following latest.", services.peer); chat.synchronize()
                } }
                compose.waitUntil(8_000) { services.friendPosts.get() == 72 }
                message("Appended while following latest.").assertIsDisplayed()
                capture("android-following-latest-dark")
                compose.onNodeWithTag("conversation-timeline").performScrollToIndex(0)
                val pageAnchor = anchor()
                compose.onNodeWithText("Earlier messages").performTouchInput { click() }
                compose.onNodeWithTag(pageAnchor.first).assertIsDisplayed()
                val afterPageY = compose.onNodeWithTag(pageAnchor.first).fetchSemanticsNode().boundsInRoot.top
                assertEquals(pageAnchor.second, afterPageY, 1f)
                compose.onNodeWithText("Earlier messages").assertDoesNotExist()
                capture("android-older-page-anchor-dark")
                compose.runOnIdle {
                    assertEquals(72, services.friendPosts.get()); assertEquals(1, services.friendReplyReceipts.get())
                    assertEquals(1, services.inboxWakeups.get()); assertEquals(0, services.botPosts.get())
                    assertEquals("", chat.compose(services.peer))
                }
                services.assertNoPurchase()
                File(output, "receipt.json").writeText(JSONObject().put("synthetic_contact_and_transport", true)
                    .put("actual_main_activity", true).put("initial_latest", true).put("append_preserved_anchor", true)
                    .put("encrypted_incoming_reply_while_reading_earlier", true).put("incoming_receipts", 1)
                    .put("native_ime_preserved_exact_anchor_y", true).put("keyboard_preserved_reading", true)
                    .put("own_send_followed", true).put("explicit_jump_followed", true).put("followed_append", true)
                    .put("older_page_preserved_anchor", true).put("immersed_history", immersed)
                    .put("setup_outgoing_posts", 70).put("later_outgoing_posts", 2).put("physical_push_or_live_relay_claimed", false).toString(2))
            } catch (failure: Throwable) {
                runCatching { capture("android-timeline-failure") }.onFailure { failure.addSuppressed(it) }
                throw failure
            } finally {
                f.device.executeShellCommand(if (handwriting == "null") "settings delete secure stylus_handwriting_enabled" else "settings put secure stylus_handwriting_enabled $handwriting")
                f.stopActivity(); services.close()
            }
        }
    }
}
