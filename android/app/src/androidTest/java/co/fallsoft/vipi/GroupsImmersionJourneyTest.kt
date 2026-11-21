package co.fallsoft.vipi

import android.graphics.Rect
import android.os.SystemClock
import android.view.MotionEvent
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import co.fallsoft.vipi.GroupSignalTestFixture.Party
import co.fallsoft.vipi.GroupSignalTestFixture.admitted
import co.fallsoft.vipi.GroupSignalTestFixture.establish
import co.fallsoft.vipi.GroupSignalTestFixture.incoming
import co.fallsoft.vipi.GroupSignalTestFixture.person
import java.io.File
import java.security.KeyStore
import java.util.UUID
import java.util.concurrent.CopyOnWriteArrayList
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

/** Synthetic accounts and group listing. Group encryption, incoming processing,
 * ML Kit, the native paragraph, touch handling and PCM playback are real. */
class GroupsImmersionJourneyTest {
    @get:Rule val compose = createEmptyComposeRule()

    @Test fun incomingSignalTextTranslatesAndSpeaksInTheGroup() {
        require(BuildConfig.GROUPS_QUALIFICATION)
        LocalTranslation().use { native ->
            assertTrue("Stage the installed Spanish model before this offline test", runBlocking { native.isReady("en", "es") })
        }
        val service = JourneyServices(profileRequired = false, translationFactory = ::LocalTranslation)
        val group = UUID.randomUUID()
        val sender = UUID.randomUUID()
        val original = "Can we meet for coffee tomorrow? I will bring the bread and you can bring the milk."
        val message = GroupMessage(UUID.randomUUID(), group, 3, 2, sender, original, System.currentTimeMillis(), GroupDelivery.QUEUED)
        lateinit var roster: GroupSnapshot
        lateinit var sealedControl: GroupIncoming
        lateinit var sealedText: GroupIncoming
        service.groupsRequest = { method, path, _, _ ->
            check(method == "GET")
            when (path) {
                "/v1/groups" -> JSONObject().put("groups", JSONArray().put(roster.json())).put("invitations", JSONArray())
                "/v1/groups/$group" -> roster.json()
                else -> error("Unexpected group service request $method $path")
            }
        }
        MainActivityJourneyFixture("groups-immersion", { app ->
            app.getSharedPreferences("preferences", 0).edit().putBoolean("animateConversationBackground", false).commit()
            Party(MessageVault(app, sender)).use { maya ->
                Party(MessageVault(app, service.account)).use { reader ->
                    establish(maya, reader, message.createdAt)
                    val owner = person(maya, true).copy(name = "Maya", username = "maya")
                    val genesis = GroupSnapshot(group, "Saturday practice", 1, "active", listOf(owner), emptyList())
                    maya.membership.createdLocally(genesis, group)
                    roster = genesis.copy(epoch = 3, members = listOf(owner, person(reader).copy(name = "Alex", username = "alex")))
                    val before = listOf(GroupApprovedPerson(sender, GroupRole.OWNER))
                    val change = GroupRosterTransition(sender, GroupControlAction.ADD, service.account, 1, 2, 3,
                        before, before + GroupApprovedPerson(service.account, GroupRole.MEMBER))
                    val control = maya.controls.prepare(UUID.randomUUID(), roster, change, message.createdAt)
                    sealedControl = incoming(control, maya, reader, "control")
                    maya.controls.accepted(admitted(control), control)
                    maya.controls.reconciled(control)
                    val ciphertext = maya.crypto.prepare(message, roster, message.createdAt)
                    sealedText = incoming(ciphertext, maya, reader, "message")
                    assertFalse(ciphertext.body.contains(original))
                }
            }
            service.model(app)
        }).use { f ->
            val events = CopyOnWriteArrayList<JSONObject>()
            val samples = JSONArray()
            val evidence = JSONObject().put("logical_id", message.renderID).put("source", original)
            MessageAudioQualification.attach { events += it }
            fun view() = f.paragraphs().single { it.originalMessage == original }
            fun drawn(): String { var result = ""; f.instrumentation.runOnMainSync { result = f.paragraphs().singleOrNull { it.originalMessage == original }?.text?.toString().orEmpty() }; return result }
            fun value() = f.model.chat?.translations?.state(message.renderID, original)?.value
            fun awaitFace(mode: ImmersionMode): FullMessageTranslation {
                compose.waitUntil(75_000) {
                    val state = f.model.chat?.translations?.state(message.renderID, original)
                    evidence.put("phase", state?.phase?.name).put("failure", state?.failure).put("drawn", drawn())
                    value()?.let { it.mode == mode && drawn() == it.practiceText } == true }
                return requireNotNull(value())
            }
            fun displayedFrame() {
                val latch = java.util.concurrent.CountDownLatch(1)
                f.instrumentation.runOnMainSync {
                    val nativeView = view()
                    assertTrue("Only capture the actual foreground conversation", nativeView.hasWindowFocus())
                    nativeView.postInvalidateOnAnimation()
                    nativeView.postOnAnimation { nativeView.postOnAnimation { latch.countDown() } }
                }
                assertTrue(latch.await(4, java.util.concurrent.TimeUnit.SECONDS))
                SystemClock.sleep(180)
            }
            fun persist() = File(f.output, "immersion.json").writeText(evidence.put("audio", JSONArray(events)).put("observed_highlights", samples).toString(2))
            try {
                f.launch()
                compose.waitUntil(15_000) { f.model.chat?.ready == true }
                compose.onNodeWithTag("inbox-compose").performClick()
                compose.onNodeWithTag("open-groups").performScrollTo().performClick()
                compose.waitUntil(10_000) { f.model.chat?.groups?.loaded == true }
                compose.onNodeWithText(roster.title).performClick()
                compose.onNodeWithText("Your group starts here").assertIsDisplayed()
                compose.runOnIdle {
                    val session = requireNotNull(f.model.chat?.groups)
                    session.receiveControl(sealedControl)
                    session.confirmBootstrap(session.pendingApprovals(group).single())
                    val arrived = requireNotNull(session.receive(sealedText))
                    assertEquals(original, arrived.text)
                    assertEquals(sender, arrived.sender)
                    assertEquals(message.renderID, arrived.renderID)
                    assertEquals(GroupDelivery.RECEIVED, arrived.delivery)
                    evidence.put("signal_ingress", true)
                }
                val shallow = awaitFace(ImmersionMode.NEW_WORD)
                evidence.put("shallow", shallow.json()); persist()
                displayedFrame(); f.capture("01-shallow")
                compose.onNodeWithTag("conversation-immersion").performClick()
                val deep = awaitFace(ImmersionMode.FULL_MESSAGES)
                assertEquals("en", deep.inputLanguage); assertEquals("es", deep.practiceLanguage)
                assertEquals(original, deep.meaningText)
                assertNotEquals(original, deep.practiceText); assertNotEquals(shallow.practiceText, deep.practiceText)
                evidence.put("deep", deep.json()); persist()
                displayedFrame(); f.capture("02-deep")
                val box = Rect()
                f.instrumentation.runOnMainSync {
                    val v = view()
                    val where = IntArray(2); v.getLocationOnScreen(where)
                    box.set(where[0], where[1], where[0] + v.width, where[1] + v.height)
                }
                val down = SystemClock.uptimeMillis()
                fun pointer(action: Int) {
                    val event = MotionEvent.obtain(down, SystemClock.uptimeMillis(), action, box.exactCenterX(), box.exactCenterY(), 0)
                    event.source = android.view.InputDevice.SOURCE_TOUCHSCREEN
                    try { assertTrue(f.instrumentation.uiAutomation.injectInputEvent(event, true)) } finally { event.recycle() }
                }
                pointer(MotionEvent.ACTION_DOWN)
                try {
                    // Compose instrumentation owns the gesture timeout clock.
                    compose.mainClock.advanceTimeBy(android.view.ViewConfiguration.getLongPressTimeout() * 2L)
                    compose.waitUntil(5_000) { drawn() == original }
                    displayedFrame(); f.capture("03-held-original")
                } finally { pointer(MotionEvent.ACTION_UP) }
                compose.waitUntil(5_000) { drawn() == deep.practiceText }
                assertTrue(f.device.click(box.centerX(), box.centerY()))
                compose.mainClock.advanceTimeBy(android.view.ViewConfiguration.getDoubleTapTimeout() + 100L)
                val deadline = SystemClock.uptimeMillis() + 20_000
                val words = linkedSetOf<IntRange>()
                while (SystemClock.uptimeMillis() < deadline && events.none { it.optString("stage") == "pcm_completed" }) {
                    var first = false
                    f.instrumentation.runOnMainSync {
                        val paragraph = view()
                        paragraph.highlightedWord?.takeIf { paragraph.playing && words.add(it) }?.let { range ->
                            samples.put(JSONObject().put("start", range.first).put("last", range.last)
                                .put("painted", paragraph.text.substring(range)).put("uptime_ms", SystemClock.uptimeMillis()))
                            first = words.size == 2
                        }
                    }
                    if (first) { displayedFrame(); f.device.takeScreenshot(File(f.output, "04-spoken-word.png")) }
                    SystemClock.sleep(15)
                }
                persist()
                val request = events.single { it.optString("stage") == "speech_request" }
                assertEquals(message.renderID, request.getString("id"))
                assertEquals("es", request.getString("practice_language"))
                assertEquals(deep.practiceText, request.getString("practice_text"))
                val rendered = events.single { it.optString("stage") == "speech_rendered" }
                val waveFile = File(rendered.getString("path"))
                val pcm = PcmWave.read(waveFile)
                assertTrue(pcm.samples.any { it != 0.toByte() } && pcm.durationMs > 500)
                assertTrue("At least two translated words must be highlighted during actual playback", words.size >= 2)
                assertTrue(events.any { it.optString("stage") == "pcm_started" })
                assertTrue(events.any { it.optString("stage") == "pcm_completed" })
                waveFile.copyTo(File(f.output, "practice-language.wav"))
                evidence.put("pcm_native_marks", pcm.marks.size).put("pcm_duration_ms", pcm.durationMs).put("complete", true)
            } finally {
                persist(); MessageAudioQualification.attach(null); f.stopActivity(); service.close()
                KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$sender") }
            }
        }
    }
}
