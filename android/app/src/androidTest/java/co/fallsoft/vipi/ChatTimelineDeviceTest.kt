package co.fallsoft.vipi

import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.core.view.WindowInsetsCompat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.json.JSONArray
import java.util.concurrent.atomic.AtomicInteger
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
            val frames = AtomicInteger()
            val ticker = object : android.view.Choreographer.FrameCallback {
                override fun doFrame(frameTimeNanos: Long) {
                    frames.incrementAndGet(); android.view.Choreographer.getInstance().postFrameCallback(this)
                }
            }
            data class ReadingLine(val tag: String, val original: String, val start: Int, val end: Int,
                val top: Float, val bottom: Float, val paragraphHeight: Int, val metadataTop: Float, val drawn: String) {
                fun json() = JSONObject().put("message_metadata_tag", tag).put("original", original)
                    .put("source_start", start).put("source_end", end).put("source_line", original.substring(start, end))
                    .put("line_top", top.toDouble()).put("line_bottom", bottom.toDouble()).put("paragraph_height", paragraphHeight)
                    .put("metadata_top", metadataTop.toDouble()).put("drawn_line", drawn)
            }
            fun readingLines(): List<ReadingLine> {
                val timeline = compose.onNodeWithTag("conversation-timeline").fetchSemanticsNode().boundsInWindow
                val viewport = f.unobscuredWindow()
                val rows = compose.onAllNodes(SemanticsMatcher("message metadata") {
                    it.config.getOrElse(SemanticsProperties.TestTag) { "" }.startsWith("message-meta-")
                }, useUnmergedTree = true).fetchSemanticsNodes().mapNotNull { meta -> meta.parent?.let {
                    Triple(meta.config[SemanticsProperties.TestTag], it.boundsInWindow, meta.boundsInWindow.top)
                } }
                val result = mutableListOf<ReadingLine>()
                f.instrumentation.runOnMainSync {
                    for (view in f.paragraphs()) {
                        if (!view.isShown || view.width <= 0 || view.height <= 0) continue
                        val layout = view.layout ?: continue
                        val point = IntArray(2); view.getLocationInWindow(point)
                        //The existing Compose metadata identifies this exact
                        //native paragraph even when authored texts repeat.
                        val row = rows.singleOrNull { (_, box, _) -> kotlin.math.abs(box.left - point[0]) <= 1f &&
                            kotlin.math.abs(box.top - point[1]) <= 1f } ?: continue
                        val original = view.displayedOriginal
                        for (line in 0 until layout.lineCount) {
                            val top = point[1] + view.totalPaddingTop - view.scrollY + layout.getLineTop(line).toFloat()
                            val bottom = point[1] + view.totalPaddingTop - view.scrollY + layout.getLineBottom(line).toFloat()
                            val start = layout.getLineStart(line).coerceAtMost(original.length)
                            val end = layout.getLineEnd(line).coerceAtMost(original.length)
                            if (end > start && top >= timeline.top && bottom <= timeline.bottom &&
                                top >= viewport.top && bottom <= viewport.bottom) {
                                result += ReadingLine(row.first, original, start, end, top, bottom, view.height,
                                    row.third, view.visibleText(start, end))
                            }
                        }
                    }
                }
                return result
            }
            fun stableReadingLine(phase: String, expected: ReadingLine? = null): ReadingLine {
                val observations = JSONArray(); var stableSince = 0L; var prior = ""; var frame = -1; var stableFrames = 0
                var accepted: ReadingLine? = null
                try {
                    compose.waitUntil(8_000) {
                        val lines = readingLines()
                        val value = if (expected == null) lines.minByOrNull { it.top } else lines.singleOrNull {
                            it.tag == expected.tag && it.original == expected.original && it.start == expected.start && it.end == expected.end
                        }
                        val now = android.os.SystemClock.uptimeMillis(); val currentFrame = frames.get()
                        if (observations.length() == 32) observations.remove(0)
                        observations.put(JSONObject().put("vsync_frame", currentFrame).put("uptime_ms", now)
                            .put("reading_line", value?.json() ?: JSONObject.NULL))
                        val geometry = value?.let { "${it.tag}:${it.start}:${it.end}:${it.top}:${it.bottom}:${it.paragraphHeight}" }.orEmpty()
                        val samePosition = value != null && (expected == null || kotlin.math.abs(value.top - expected.top) <= 1f)
                        if (!samePosition || geometry != prior) { stableSince = now; stableFrames = 0 }
                        if (samePosition && currentFrame != frame) stableFrames++
                        prior = geometry; frame = currentFrame
                        (samePosition && stableFrames >= 3 && now - stableSince >= 250).also { if (it) accepted = value }
                    }
                } finally {
                    File(output, "$phase-reading-observations.json").writeText(JSONObject().put("observations", observations)
                        .put("expected_reading_line", expected?.json() ?: JSONObject.NULL).put("y_tolerance_px", 1).toString(2))
                }
                return requireNotNull(accepted)
            }
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
                    android.view.Choreographer.getInstance().postFrameCallback(ticker)
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
                    assertTrue(chat.notice, chat.lastSyncComplete)
                    assertNull(chat.notice)
                    assertEquals(50, chat.messages(services.peer).size)
                    assertTrue(chat.messages(services.peer).all { it.outgoing && it.state == "delivered" })
                    MessageVault(f.isolated, services.account).use { vault ->
                        val journal = MessageJournal(vault)
                        assertTrue(journal.pendingDrafts(System.currentTimeMillis()).isEmpty())
                        assertTrue(journal.pending(System.currentTimeMillis()).isEmpty())
                    }
                } }
                //Open through the production chat list, not a substitute screen.
                compose.onNodeWithText("Journey Friend").performScrollTo().performTouchInput { click() }
                compose.waitUntil(8_000) { f.model.screen == Screen.CONVERSATION }
                val latestID = runBlocking { withContext(Dispatchers.Main) { chat.messages(services.peer).maxBy { it.cursor }.id } }
                compose.onNodeWithTag("message-meta-$latestID").assertIsDisplayed()
                if (immersed) {
                    compose.waitUntil(20_000) {
                        var found = false
                        f.instrumentation.runOnMainSync { found = f.paragraphs().any { it.displayedOriginal == "I like music." && it.visibleText().contains("muziki") } }
                        found
                    }
                }
                compose.onNodeWithTag("conversation-timeline").performTouchInput { swipeDown() }
                compose.onNodeWithTag("conversation-timeline").performTouchInput { swipeDown() }
                compose.onNodeWithContentDescription("Jump to latest messages").assertIsDisplayed()
                val beforeReading = stableReadingLine("before-incoming")
                val before = anchor()
                capture("android-reading-before-incoming-light")
                stableReadingLine("before-incoming-captured", beforeReading)
                compose.runOnIdle { services.queuePeerReplyAndSignalInbox() }
                compose.waitUntil(8_000) {
                    chat.messages(services.peer).singleOrNull { !it.outgoing }?.id == services.friendReplyId &&
                        services.friendReplyReceipts.get() == 1
                }
                val afterReading = stableReadingLine("after-incoming", beforeReading)
                val after = anchor()
                assertEquals(beforeReading.tag, afterReading.tag)
                assertEquals(beforeReading.top, afterReading.top, 1f)
                File(output, "incoming-anchor-proof.json").writeText(JSONObject().put("before", beforeReading.json())
                    .put("after", afterReading.json()).put("metadata_before_tag", before.first).put("metadata_after_tag", after.first)
                    .put("metadata_before_y", before.second.toDouble())
                    .put("metadata_after_y", after.second.toDouble()).toString(2))
                assertEquals(70, services.friendPosts.get())
                capture("android-reading-preserved-light")
                compose.onNodeWithTag("message-input").performTouchInput { click() }
                compose.waitUntil(5_000) { imeVisible() }
                compose.onNodeWithTag("message-input").performTextInput("A draft while reading")
                compose.onNodeWithTag(beforeReading.tag).assertExists()
                val imeReading = stableReadingLine("after-native-ime", beforeReading)
                assertEquals("Opening the native IME moved the actual reading line", beforeReading.top, imeReading.top, 1f)
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
                    .put("native_ime_preserved_exact_anchor_y", true).put("reader_anchor", "native source line, exact message ID and Y within1px")
                    .put("keyboard_preserved_reading", true)
                    .put("own_send_followed", true).put("explicit_jump_followed", true).put("followed_append", true)
                    .put("older_page_preserved_anchor", true).put("immersed_history", immersed)
                    .put("setup_outgoing_posts", 70).put("later_outgoing_posts", 2).put("physical_push_or_live_relay_claimed", false).toString(2))
            } catch (failure: Throwable) {
                runCatching { capture("android-timeline-failure") }.onFailure { failure.addSuppressed(it) }
                throw failure
            } finally {
                f.instrumentation.runOnMainSync { android.view.Choreographer.getInstance().removeFrameCallback(ticker) }
                f.device.executeShellCommand(if (handwriting == "null") "settings delete secure stylus_handwriting_enabled" else "settings put secure stylus_handwriting_enabled $handwriting")
                f.stopActivity(); services.close()
            }
        }
    }
}
