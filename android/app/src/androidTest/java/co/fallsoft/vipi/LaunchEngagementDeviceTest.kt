package co.fallsoft.vipi

import android.content.Context
import android.os.SystemClock
import android.view.InputDevice
import android.view.MotionEvent
import android.view.accessibility.AccessibilityNodeInfo
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import com.google.android.play.core.review.testing.FakeReviewManager
import java.time.LocalDate
import java.util.UUID
import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

class LaunchEngagementDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()
    private val inst
        get() = InstrumentationRegistry.getInstrumentation()

    private val context
        get() = inst.targetContext

    private val day = 86_400_000L

    @Test
    fun thresholdsDedupHistoricalDaysSpacingAndAccountIsolation(): Unit = runBlocking {
        val who = UUID.randomUUID()
        val peer = UUID.randomUUID()
        val now = System.currentTimeMillis()
        MessageVault(context, who).use { v ->
            val ledger = LaunchFeedback(v)
            val journal = MessageJournal(v)
            val ids = List(40) { UUID.randomUUID() }
            v.transaction {
                ids.forEachIndexed { i, id ->
                    val raw =
                        StoredChat(
                            ChatEnvelope(id, who, peer, now - (i % 14) * day, 2, byteArrayOf(2)),
                            "artificial fixture",
                            if (i < 19) "delivered" else "queued",
                        )
                    v.put("outgoing", id.toString(), raw.encode())
                }
            }
            ledger.includeEarlierMessages()
            assertFalse(ledger.eligible(FeedbackPrompt.SURVEY, "a", now))
            journal.applyStatus(ids[19], "accepted")
            repeat(3) { journal.applyStatus(ids[19], "accepted") }
            assertTrue(ledger.eligible(FeedbackPrompt.SURVEY, "a", now))
            assertFalse(ledger.eligible(FeedbackPrompt.REVIEW, "a", now))
            for (id in ids.drop(20)) journal.applyStatus(id, "accepted")
            assertTrue(ledger.eligible(FeedbackPrompt.REVIEW, "a", now))
            assertTrue(ledger.claim(FeedbackPrompt.SURVEY, "a", now))
            assertFalse(ledger.eligible(FeedbackPrompt.REVIEW, "a", now + 8 * day))
            assertFalse(ledger.eligible(FeedbackPrompt.REVIEW, "b", now + 7 * day - 1))
            assertTrue(ledger.claim(FeedbackPrompt.REVIEW, "b", now + 7 * day))
            assertFalse(ledger.claim(FeedbackPrompt.REVIEW, "c", now + 30 * day))
            ledger.queue(FundingChoice.NO)
            ledger.queue(FundingChoice.YES)
        }
        MessageVault(context, who).use { v ->
            val ledger = LaunchFeedback(v)
            assertEquals("no", ledger.pending())
            ledger.submitted("no")
            assertNull(ledger.pending())
        }
        MessageVault(context, UUID.randomUUID()).use {
            assertFalse(LaunchFeedback(it).eligible(FeedbackPrompt.SURVEY, "different", now))
        }
        MessageVault(context, UUID.randomUUID()).use { v ->
            val ledger = LaunchFeedback(v)
            v.transaction { repeat(40) { i -> LaunchFeedback.groupAccepted(v, "initial-$i", now) } }
            assertFalse(ledger.eligible(FeedbackPrompt.SURVEY, "first", now))
            for (offset in 1..13) {
                v.transaction { LaunchFeedback.groupAccepted(v, "day-$offset", now - offset * day) }
                assertEquals(offset >= 6, ledger.eligible(FeedbackPrompt.SURVEY, "first", now))
                assertEquals(offset >= 13, ledger.eligible(FeedbackPrompt.REVIEW, "first", now))
            }
            assertTrue(ledger.claim(FeedbackPrompt.REVIEW, "first", now))
            assertFalse(ledger.eligible(FeedbackPrompt.SURVEY, "other", now + 6 * day))
            assertTrue(ledger.eligible(FeedbackPrompt.SURVEY, "other", now + 7 * day))
        }
    }

    @Test
    fun dailyThenWeeklyCoachingPersistsAndStopsOnlyOnMasteryOrDismissal() {
        val account = UUID.randomUUID()
        val start = LocalDate.of(2026, 1, 1)
        MessageVault(context, account).use { v ->
            val progress = HoldEducation(v)
            repeat(21) { i ->
                val d = start.plusDays(i.toLong())
                assertTrue(progress.claim(d))
                assertFalse(progress.claim(d))
            }
        }
        MessageVault(context, account).use { v ->
            val p = HoldEducation(v)
            assertFalse(p.claim(start.plusDays(21)))
            assertFalse(p.claim(start.plusDays(26)))
            assertTrue(p.claim(start.plusDays(27)))
            assertFalse(p.claim(start.plusDays(27)))
            p.independentReveal(start.plusDays(28))
            p.independentReveal(start.plusDays(28))
            p.independentReveal(start.plusDays(29))
            assertTrue(p.claim(start.plusDays(34)))
            p.independentReveal(start.plusDays(35))
            assertFalse(p.claim(start.plusDays(50)))
        }
        val other = UUID.randomUUID()
        MessageVault(context, other).use { v ->
            val p = HoldEducation(v)
            assertTrue(p.claim(start))
            p.dismiss()
        }
        MessageVault(context, other).use {
            assertFalse(HoldEducation(it).claim(start.plusDays(10)))
        }
    }

    /** Exercise the ordinary authenticated HTTP client with an actual empty 204. */
    private suspend fun proveEmptyResponse(model: VipiModel, user: String) = coroutineScope {
        val loopback = java.net.InetAddress.getByName("127.0.0.1")
        java.net.ServerSocket(0, 1, loopback).use { server ->
            server.soTimeout = 5_000
            val observed =
                async(Dispatchers.IO) {
                    server.accept().use { socket ->
                        socket.soTimeout = 5_000
                        val input = socket.getInputStream().bufferedReader(Charsets.US_ASCII)
                        val requestLine = input.readLine()
                        val headers = generateSequence {
                            input.readLine().takeIf { !it.isNullOrEmpty() }
                        }
                            .toList()
                        val length =
                            headers
                                .single { it.startsWith("Content-Length:", true) }
                                .substringAfter(':')
                                .trim()
                                .toInt()
                        val payload = CharArray(length)
                        require(input.read(payload) == length)
                        socket
                            .getOutputStream()
                            .write(
                                "HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n"
                                    .toByteArray(Charsets.US_ASCII)
                            )
                        assertTrue(
                            headers.any {
                                it.startsWith("Authorization: Bearer synthetic-inert-access", true)
                            }
                        )
                        assertTrue(headers.any { it.startsWith("X-Vipi-Device-ID:", true) })
                        assertEquals("PUT ${LaunchFeedback.PATH} HTTP/1.1", requestLine)
                        assertEquals("skip", JSONObject(String(payload)).getString("choice"))
                    }
                }
            val client =
                ServiceClient(model.authentication, user, "http://127.0.0.1:${server.localPort}")
            val result =
                client.request(
                    "PUT",
                    LaunchFeedback.PATH,
                    JSONObject().put("choice", "skip"),
                    DeviceCredential(UUID.randomUUID(), "local-test-only"),
                )
            observed.await()
            assertEquals(0, result.length())
        }
    }

    private fun originalNode(root: AccessibilityNodeInfo?, text: String): AccessibilityNodeInfo? {
        if (root == null) return null
        if (
            root.isVisibleToUser &&
                root.text?.toString() == text &&
                root.actionList.any { it.id == 0x02010001 }
        )
            return root
        for (i in 0 until root.childCount) originalNode(root.getChild(i), text)?.let {
            return it
        }
        return null
    }

    @Test
    fun actualChatReturnSurveyAndTranslatedHold(): Unit = runBlocking {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val args = InstrumentationRegistry.getArguments()
        val deep = args.getString("deep") == "true"
        val prior = args.getString("prior") == "true"
        val dismiss = args.getString("dismiss") == "true"
        val choice = if (deep) FundingChoice.SKIP else FundingChoice.MAYBE
        val provider =
            object : LanguageTranslation {
                override suspend fun prepare(
                    source: String,
                    target: String,
                    cellularAllowed: Boolean,
                ) = Unit

                override suspend fun isReady(source: String, target: String) = true

                override suspend fun translate(
                    text: String,
                    source: String,
                    target: String,
                ): String =
                    when (text.lowercase(java.util.Locale.ROOT)) {
                        "hello" -> "Hola"
                        "coffee" -> "café"
                        "coffee later?" -> "¿Café más tarde?"
                        "coffee tomorrow?" -> "¿Café mañana?"
                        "sounds good." -> "Me parece bien."
                        "see you soon!" -> "¡Hasta pronto!"
                        else -> text
                    }

                override fun close() = Unit
            }
        val service =
            JourneyServices(false, peerDisplayName = "Maya", translationFactory = { provider })
        val calls = mutableListOf<String>()
        var available = true
        var offline = true
        service.fundingRequest = { method, body, _ ->
            calls += method
            if (method == "GET") JSONObject().put("available", available)
            else {
                assertEquals(setOf("choice"), requireNotNull(body).keys().asSequence().toSet())
                assertEquals(choice.wire, body.getString("choice"))
                if (offline) throw java.io.IOException("Fixture offline")
                available = false
                JSONObject()
            }
        }
        val legacy = context.getSharedPreferences("full-message-gestures", Context.MODE_PRIVATE)
        val old = legacy.all["hold-script-policy-1"] as? Boolean
        legacy.edit().putBoolean("hold-script-policy-1", true).commit()
        MainActivityJourneyFixture(
                "launch-feedback",
                { app ->
                    val prefs = app.getSharedPreferences("preferences", 0)
                    prefs
                        .edit()
                        .putBoolean("animateConversationBackground", false)
                        .putString("immersionMode", if (deep) "FULL_MESSAGES" else "NEW_WORD")
                        .commit()
                    MessageVault(app, service.account).use { v ->
                        v.transaction {
                            val person = ChatProfile(service.peer, "maya", "Maya")
                            v.put(
                                "contact",
                                service.peer.toString(),
                                person.json().toString().toByteArray(),
                            )
                            repeat(20) { i ->
                                val id = UUID.randomUUID()
                                val whenSent = System.currentTimeMillis() - (19 - i) * day / 2
                                val text =
                                    when (i) {
                                        19 -> "Hello"
                                        18 -> "Sounds good."
                                        else -> "See you soon!"
                                    }
                                val message =
                                    StoredChat(
                                        ChatEnvelope(
                                            id,
                                            service.account,
                                            service.peer,
                                            whenSent,
                                            2,
                                            byteArrayOf(1),
                                        ),
                                        text,
                                        "delivered",
                                    )
                                v.put("outgoing", id.toString(), message.encode())
                                ConversationHistory.record(
                                    v,
                                    "outgoing",
                                    id,
                                    service.peer,
                                    whenSent,
                                )
                            }
                            val id = UUID.randomUUID()
                            val arrival = System.currentTimeMillis() - 60_000
                            val incoming =
                                StoredChat(
                                    ChatEnvelope(
                                        id,
                                        service.peer,
                                        service.account,
                                        arrival,
                                        2,
                                        byteArrayOf(1),
                                    ),
                                    "Coffee later?",
                                    "delivered",
                                )
                            v.put("incoming", id.toString(), incoming.encode())
                            ConversationHistory.record(v, "incoming", id, service.peer, arrival)
                        }
                        if (prior) HoldEducation(v).claim(LocalDate.now().minusDays(1))
                    }
                    service.model(app)
                },
            )
            .use { f ->
                try {
                    fun capture(name: String) {
                        compose.waitForIdle()
                        val frames = java.util.concurrent.CountDownLatch(1)
                        inst.runOnMainSync {
                            val view =
                                androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
                                    .getInstance()
                                    .getActivitiesInStage(
                                        androidx.test.runner.lifecycle.Stage.RESUMED
                                    )
                                    .single()
                                    .window
                                    .decorView
                            view.invalidate()
                            view.postOnAnimation {
                                view.postOnAnimation { view.postOnAnimation { frames.countDown() } }
                            }
                        }
                        check(frames.await(4, java.util.concurrent.TimeUnit.SECONDS))
                        SystemClock.sleep(750)
                        f.capture(name)
                    }
                    f.launch()
                    f.bindConversationCapture(compose, "message-input")
                    compose.waitUntil(20_000) { f.model.chat?.ready == true }
                    assertTrue("The inbox alone must not request a survey", calls.isEmpty())
                    val mode = if (deep) ImmersionMode.FULL_MESSAGES else ImmersionMode.NEW_WORD
                    compose.runOnIdle { f.model.selectImmersionMode(mode) }
                    compose.onNodeWithText("Maya").performClick()
                    val translated = { originalNode(inst.uiAutomation.rootInActiveWindow, "Hola") }
                    compose.waitUntil(24_000) { translated() != null }
                    if (!prior) {
                        compose.waitUntil(3_000) {
                            compose
                                .onAllNodesWithTag("full-message-gesture-cue")
                                .fetchSemanticsNodes()
                                .isNotEmpty()
                        }
                        capture("01-chat-hint")
                        if (dismiss)
                            compose
                                .onNodeWithText(context.getString(R.string.hold_hint_dismiss))
                                .performClick()
                    }
                    val node = requireNotNull(translated())
                    val rect = android.graphics.Rect()
                    node.getBoundsInScreen(rect)
                    val initialTimeline =
                        compose
                            .onNodeWithTag("conversation-timeline")
                            .fetchSemanticsNode()
                            .boundsInRoot
                    val down = SystemClock.uptimeMillis()
                    fun inject(action: Int) {
                        val e =
                            MotionEvent.obtain(
                                down,
                                SystemClock.uptimeMillis(),
                                action,
                                rect.exactCenterX(),
                                rect.exactCenterY(),
                                0,
                            )
                        e.source = InputDevice.SOURCE_TOUCHSCREEN
                        try {
                            check(inst.uiAutomation.injectInputEvent(e, true))
                        } finally {
                            e.recycle()
                        }
                    }
                    inject(MotionEvent.ACTION_DOWN)
                    try {
                        compose.waitUntil(3_000) {
                            originalNode(inst.uiAutomation.rootInActiveWindow, "Hello") != null
                        }
                        if (!prior && !dismiss) {
                            val heldBounds = android.graphics.Rect()
                            originalNode(inst.uiAutomation.rootInActiveWindow, "Hello")!!
                                .getBoundsInScreen(heldBounds)
                            assertEquals(
                                "Holding must keep the paragraph under the finger",
                                rect,
                                heldBounds,
                            )
                        }
                        capture("02-actual-held-original")
                    } finally {
                        inject(MotionEvent.ACTION_UP)
                    }
                    compose.waitUntil(3_000) { translated() != null }
                    if (!prior && !dismiss) {
                        compose.waitUntil(3_000) {
                            compose
                                .onNodeWithTag("conversation-timeline")
                                .fetchSemanticsNode()
                                .boundsInRoot
                                .height > initialTimeline.height + 20
                        }
                        compose
                            .onNodeWithText(context.getString(R.string.hold_hint_dismiss))
                            .assertDoesNotExist()
                    }
                    compose.onNodeWithTag("conversation-timeline").performTouchInput { swipeDown() }
                    f.device.pressBack()
                    compose.waitUntil(15_000) {
                        compose
                            .onAllNodesWithText(context.getString(R.string.funding_question))
                            .fetchSemanticsNodes()
                            .isNotEmpty()
                    }
                    capture("03-survey")
                    val label = if (deep) R.string.funding_skip else R.string.funding_maybe
                    compose.onNodeWithText(context.getString(label)).performClick()
                    compose.waitUntil(5_000) { calls.contains("PUT") }
                    assertEquals(choice.wire, f.model.chat?.feedback?.pending())
                    offline = false
                    compose.onNodeWithText("Maya").performClick()
                    compose.waitUntil(12_000) { translated() != null }
                    compose.onNodeWithTag("full-message-gesture-cue").assertDoesNotExist()
                    val ax = requireNotNull(translated())
                    check(ax.performAction(0x02010001))
                    compose.waitUntil(3_000) {
                        originalNode(inst.uiAutomation.rootInActiveWindow, "Hello") != null
                    }
                    f.device.pressBack()
                    compose.waitUntil(8_000) { !available }
                    assertNull(f.model.chat?.feedback?.pending())
                    compose
                        .onNodeWithText(context.getString(R.string.funding_question))
                        .assertDoesNotExist()
                    assertEquals(listOf("GET", "PUT", "PUT"), calls)
                    var probes = 0
                    service.fundingRequest = { method, _, _ ->
                        check(method == "GET")
                        probes++
                        throw ServiceFailure(404, "not_found")
                    }
                    val activeChat = requireNotNull(f.model.chat)
                    assertFalse(activeChat.fundingSurveyAvailable("simulated-older-service"))
                    assertFalse(activeChat.fundingSurveyAvailable("simulated-older-service"))
                    assertEquals(1, probes)
                    proveEmptyResponse(f.model, activeChat.userID)
                    withContext(Dispatchers.Main) {
                        val a =
                            androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
                                .getInstance()
                                .getActivitiesInStage(androidx.test.runner.lifecycle.Stage.RESUMED)
                                .filterIsInstance<MainActivity>()
                                .single()
                        requestNativeReview(a, FakeReviewManager(a)) { true }
                    }
                    val state =
                        MessageVault(f.isolated, service.account).use { v ->
                            v.transaction {
                                JSONObject(
                                    requireNotNull(v.get("local", "hold-original-days-v1"))
                                        .toString(Charsets.UTF_8)
                                )
                            }
                        }
                    assertEquals(1, state.getJSONArray("shown").length())
                    if (prior)
                        assertEquals(
                            LocalDate.now().minusDays(1).toString(),
                            state.getJSONArray("shown").getString(0),
                        )
                    assertEquals(
                        if (dismiss) 0 else 1,
                        state.optJSONArray("learned")?.length() ?: 0,
                    )
                    assertEquals(dismiss, state.optBoolean("dismissed"))
                    if (args.getString("guide") == "true") {
                        val reduced = args.getString("reduced") == "true"
                        compose
                            .onNodeWithContentDescription(context.getString(R.string.nav_settings))
                            .performClick()
                        compose.onNodeWithTag("settings-help").performScrollTo().performClick()
                        compose.onNodeWithTag("tutorial-reentry").performScrollTo().performClick()
                        compose.onNodeWithTag("tutorial-message").performScrollTo()
                        val sourceText = ImmersionTutorialSource.text("en")
                        val practiceText = if (deep) "¿Café mañana?" else "café tomorrow?"
                        fun drawn(wanted: String): Boolean =
                            originalNode(inst.uiAutomation.rootInActiveWindow, wanted) != null
                        compose.waitUntil(10_000) { drawn(practiceText) }
                        compose.mainClock.advanceTimeBy(1_350)
                        compose.onNodeWithTag("tutorial-hold-ring").assertIsDisplayed()
                        compose.waitUntil(3_000) {
                            drawn(if (reduced) practiceText else sourceText)
                        }
                        capture("04-guide-example")
                        compose.mainClock.advanceTimeBy(2_500)
                        compose.waitUntil(5_000) { drawn(practiceText) }
                        compose.onNodeWithTag("tutorial-message").performTouchInput {
                            down(center)
                            advanceEventTime(1_000)
                        }
                        compose.waitUntil(5_000) { drawn(sourceText) }
                        compose.onNodeWithTag("tutorial-message").performTouchInput { up() }
                        compose.waitUntil(5_000) { drawn(practiceText) }
                        compose
                            .onNodeWithText(context.getString(R.string.continue_action))
                            .performClick()
                        compose.waitUntil(5_000) { f.model.screen == Screen.HELP }
                        val after =
                            MessageVault(f.isolated, service.account).use { vault ->
                                vault.transaction {
                                    vault
                                        .get("local", "hold-original-days-v1")!!
                                        .toString(Charsets.UTF_8)
                                }
                            }
                        assertEquals(state.toString(), JSONObject(after).toString())
                    }
                    java.io
                        .File(f.output, "evidence.json")
                        .writeText(
                            JSONObject()
                                .put("deep", deep)
                                .put("prior", prior)
                                .put("transport", calls)
                                .put("hint", state)
                                .put("fakePlayReview", true)
                                .toString(2)
                        )
                } finally {
                    f.stopActivity()
                    service.close()
                    val edit = legacy.edit()
                    if (old == null) edit.remove("hold-script-policy-1")
                    else edit.putBoolean("hold-script-policy-1", old)
                    edit.commit()
                }
            }
    }
}
