package co.fallsoft.vipi

import android.graphics.Rect
import android.os.SystemClock
import android.view.MotionEvent
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import com.google.mlkit.common.model.RemoteModelManager
import com.google.mlkit.nl.translate.TranslateRemoteModel
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.CopyOnWriteArrayList

/** Native marketing captures, not a replay of qualification. MainActivity, journal,
 * Signal receive, complete local ML Kit translation/readings and gestures are real.
 * Only synthetic account/relay/Bot/billing boundaries are controlled. No live sends.
 * Source-only copy is frozen before output; no target strings are supplied. */
class FullMessageMarketingDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()
    private val args get() = InstrumentationRegistry.getArguments()
    private val storyBytes by lazy { InstrumentationRegistry.getInstrumentation().context.assets
        .open("marketing/full-message-story-r01.json").use { it.readBytes() } }
    private val story by lazy { JSONObject(storyBytes.toString(Charsets.UTF_8)) }
    private val providerEvents = CopyOnWriteArrayList<JSONObject>()
    private val source get() = story.getString("known_language")
    private val target get() = story.getString("practice_language")
    private fun localProvider(): LanguageTranslation = object : LanguageTranslation {
        private val actual = LocalTranslation()
        override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) {
            val manager = RemoteModelManager.getInstance()
            for (code in listOf(source, target).distinct().filter { it != "en" }) {
                check(withTimeout(10_000) { manager.isModelDownloaded(TranslateRemoteModel.Builder(code).build()).await() }) {
                    "Marketing capture requires separately prepared local model: $code"
                }
            }
        }
        override suspend fun translate(text: String, source: String, target: String): String {
            val start = SystemClock.elapsedRealtime()
            val result = actual.translate(text, source, target)
            providerEvents += JSONObject().put("source", source).put("target", target).put("original", text)
                .put("output", result).put("elapsed_ms", SystemClock.elapsedRealtime() - start)
            return result
        }
        override fun close() = actual.close()
    }
    private fun screen(f: MainActivityJourneyFixture, expected: Screen) =
        compose.waitUntil(20_000) { f.model.screen == expected }
    private fun ready(owner: ConversationTranslation, rows: Map<String, String>) {
        compose.waitUntil(120_000) { rows.all { (id, text) -> owner.state(id, text)?.phase == MessageTranslationPhase.READY } }
        rows.forEach { (id, text) ->
            val value = requireNotNull(owner.state(id, text)?.value)
            assertEquals(text, value.original)
            assertEquals(target, value.practiceLanguage)
            assertTrue(value.practiceText.isNotBlank())
            assertEquals(FullMessageReadingStatus.AVAILABLE, value.readingStatus)
            assertFalse(value.practiceReading.isNullOrBlank())
        }
    }
    private fun pointer(f: MainActivityJourneyFixture, action: Int, x: Float, y: Float, down: Long) {
        val event = MotionEvent.obtain(down, SystemClock.uptimeMillis(), action, x, y, 0)
        try { check(f.instrumentation.uiAutomation.injectInputEvent(event, true)) } finally { event.recycle() }
    }
    private fun paragraph(f: MainActivityJourneyFixture, original: String): Rect {
        var bounds: Rect? = null
        f.instrumentation.runOnMainSync {
            val view = f.paragraphs().single { it.originalMessage == original }
            val position = IntArray(2); view.getLocationOnScreen(position)
            bounds = Rect(position[0], position[1], position[0] + view.width, position[1] + view.height)
        }
        return requireNotNull(bounds)
    }
    private fun doubleTap(f: MainActivityJourneyFixture, original: String) {
        val b = paragraph(f, original)
        repeat(2) {
            val down = SystemClock.uptimeMillis()
            pointer(f, MotionEvent.ACTION_DOWN, b.exactCenterX(), b.exactCenterY(), down)
            SystemClock.sleep(45)
            pointer(f, MotionEvent.ACTION_UP, b.exactCenterX(), b.exactCenterY(), down)
            if (it == 0) SystemClock.sleep(90)
        }
    }
    /** The semantic/native text update can precede SurfaceFlinger presentation.
     * Drain Compose/native work and observe three display frames, then allow a short static display
     * settle before PNG; domain/geometry assertions are unchanged. Pixel review
     * remains mandatory, and capture XML is still sequential evidence. */
    private fun captureSettled(f: MainActivityJourneyFixture, name: String) {
        compose.waitForIdle()
        f.instrumentation.waitForIdleSync()
        val frames = java.util.concurrent.CountDownLatch(1)
        f.instrumentation.runOnMainSync {
            android.view.Choreographer.getInstance().postFrameCallback {
                android.view.Choreographer.getInstance().postFrameCallback {
                    android.view.Choreographer.getInstance().postFrameCallback { frames.countDown() }
                }
            }
        }
        check(frames.await(2, java.util.concurrent.TimeUnit.SECONDS)) { "Native display frames did not advance" }
        f.instrumentation.waitForIdleSync()
        SystemClock.sleep(300)
        f.capture(name)
    }
    private fun captureRows(f: MainActivityJourneyFixture, name: String, rows: Map<String, String>,
        owner: ConversationTranslation, face: String) {
        compose.waitUntil(10_000) {
            var matches = false
            f.instrumentation.runOnMainSync {
                matches = rows.all { (id, text) ->
                    val value = owner.state(id, text)?.value
                    val expected = when (face) { "meaning" -> value?.meaningText; "script" -> value?.practiceText; else -> value?.practiceReading }
                    f.paragraphs().singleOrNull { it.originalMessage == text }?.text?.toString() == expected
                }
            }
            matches
        }
        captureSettled(f, name)
        val snapshot = JSONObject(File(f.output, "$name.json").readText())
        val paragraphs = snapshot.getJSONArray("native_paragraphs")
        rows.values.forEach { original ->
            val row = (0 until paragraphs.length()).map { paragraphs.getJSONObject(it) }.single { it.getString("original") == original }
            assertTrue("Marketing requires complete actual paragraph inside clipped timeline: $original", row.getBoolean("fully_visible"))
        }
        File(f.output, "$name-translations.json").writeText(JSONArray(rows.map { (id, text) ->
            JSONObject().put("id", id).put("value", requireNotNull(owner.state(id, text)?.value).json())
        }).toString(2))
    }
    private fun nativeBounds(value: String): Rect {
        require(Regex("\\[-?[0-9]+,-?[0-9]+\\]\\[-?[0-9]+,-?[0-9]+\\]").matches(value))
        val parts = Regex("-?[0-9]+").findAll(value).map { it.value.toInt() }.toList()
        return Rect(parts[0], parts[1], parts[2], parts[3])
    }
    /** Compare the actual retained phone renderer, then exercise the wide
     * scrolling surface outside the centered items (not a test-only scene). */
    private fun qualifyLane(f: MainActivityJourneyFixture, name: String, rows: Map<String, String>,
        owner: ConversationTranslation, viewport: String, audioEvents: List<JSONObject>) {
        val snapshot = JSONObject(File(f.output, "$name.json").readText())
        val list = compose.onAllNodes(SemanticsMatcher("Actual transcript LazyColumn") {
            it.config.contains(androidx.compose.ui.semantics.SemanticsActions.ScrollToIndex)
        }, useUnmergedTree = true).fetchSemanticsNodes().filter { it.boundsInWindow.width > 0 && it.boundsInWindow.height > 0 }.single().boundsInWindow
        val delta = IntArray(2)
        var density = 0f
        f.instrumentation.runOnMainSync {
            val decor = f.paragraphs().first().rootView
            val screen = IntArray(2); val window = IntArray(2)
            decor.getLocationOnScreen(screen); decor.getLocationInWindow(window)
            delta[0] = screen[0] - window[0]; delta[1] = screen[1] - window[1]
            density = decor.resources.displayMetrics.density
        }
        val insetDp = if (name.startsWith("friend")) 18f else 16f
        val laneWidth = minOf(644f * density, list.width - 2 * insetDp * density)
        val laneLeft = list.center.x + delta[0] - laneWidth / 2
        val laneRight = laneLeft + laneWidth
        val paragraphs = snapshot.getJSONArray("native_paragraphs")
        val observed = (0 until paragraphs.length()).map { paragraphs.getJSONObject(it) }.filter { it.getString("original") in rows.values }
        assertEquals(rows.size, observed.size)
        observed.forEach {
            val bounds = nativeBounds(it.getString("native_full_bounds"))
            assertTrue("Native paragraph outside centered lane: $bounds", bounds.left >= laneLeft && bounds.right <= laneRight)
        }
        val proof = JSONObject().put("actual_lazy_column", list.toString()).put("density", density)
            .put("lane_left", laneLeft).put("lane_right", laneRight).put("lane_width_dp", laneWidth / density)
            .put("native_paragraphs", JSONArray(observed))
        if (viewport == "phone") {
            val baseline = JSONObject(f.instrumentation.context.assets.open("marketing/phone-transcript-geometry-905.json").bufferedReader().use { it.readText() })
                .getJSONObject("captures").getJSONObject(name)
            for (key in listOf("width_px", "height_px", "screen_width_dp", "font_scale")) assertEquals(key, baseline.get(key), snapshot.get(key))
            val editor = f.device.findObjects(androidx.test.uiautomator.By.clazz("android.widget.EditText")).single().visibleBounds
            assertEquals("Phone native composer geometry", nativeBounds(baseline.getString("editor_native_bounds")), editor)
            proof.put("actual_native_editor_bounds", editor.toShortString()).put("baseline_editor_xml_sha256", baseline.getString("xml_sha256"))
            val previous = baseline.getJSONArray("native_paragraphs")
            val oldRows = (0 until previous.length()).map { previous.getJSONObject(it) }.associateBy { it.getString("original") }
            val oldTop = oldRows.values.minOf { nativeBounds(it.getString("native_full_bounds")).top }
            val newTop = observed.minOf { nativeBounds(it.getString("native_full_bounds")).top }
            observed.forEach {
                val old = requireNotNull(oldRows[it.getString("original")])
                assertEquals("Actual provider/read face changed", old.getString("drawn"), it.getString("drawn"))
                val before = nativeBounds(old.getString("native_full_bounds"))
                val after = nativeBounds(it.getString("native_full_bounds"))
                assertEquals("Phone native x", before.left, after.left)
                assertEquals("Phone paragraph width", before.width(), after.width())
                assertEquals("Phone paragraph height", before.height(), after.height())
                assertEquals("Phone relative row spacing", before.top - oldTop, after.top - newTop)
            }
            proof.put("retained_905_native_phone_geometry_equal", true).put("baseline_capture_sha256", baseline.getString("sha256"))
        } else {
            assertEquals(644f, laneWidth / density, 0.001f)
            val marginStart = list.left + delta[0]
            assertTrue("Need real blank margin outside lane", laneLeft - marginStart > 48 * density)
            val x = (marginStart + laneLeft) / 2
            val y = list.center.y + delta[1]
            assertTrue(observed.none { nativeBounds(it.getString("native_full_bounds")).contains(x.toInt(), y.toInt()) })
            val eventStart = audioEvents.size
            val down = SystemClock.uptimeMillis()
            pointer(f, MotionEvent.ACTION_DOWN, x, y, down)
            try {
                SystemClock.sleep(android.view.ViewConfiguration.getLongPressTimeout().toLong() + 150)
                captureRows(f, "$name-outside-held", rows, owner, "meaning")
            } finally { pointer(f, MotionEvent.ACTION_UP, x, y, down) }
            captureRows(f, "$name-outside-restored", rows, owner, "reading")
            repeat(2) {
                val start = SystemClock.uptimeMillis()
                pointer(f, MotionEvent.ACTION_DOWN, x, y, start); SystemClock.sleep(45)
                pointer(f, MotionEvent.ACTION_UP, x, y, start)
                if (it == 0) SystemClock.sleep(90)
            }
            captureRows(f, "$name-outside-script", rows, owner, "script")
            SystemClock.sleep(android.view.ViewConfiguration.getDoubleTapTimeout().toLong() + 100)
            assertTrue("Blank hold/double tap must not dispatch delayed audio", audioEvents.drop(eventStart).none {
                it.optString("stage") in setOf("speech_request", "pcm_started") })
            // Restore reading through the same actual blank-background gesture.
            repeat(2) {
                val start = SystemClock.uptimeMillis()
                pointer(f, MotionEvent.ACTION_DOWN, x, y, start); SystemClock.sleep(45)
                pointer(f, MotionEvent.ACTION_UP, x, y, start)
                if (it == 0) SystemClock.sleep(90)
            }
            captureRows(f, "$name-outside-reading", rows, owner, "reading")
            SystemClock.sleep(android.view.ViewConfiguration.getDoubleTapTimeout().toLong() + 100)
            assertTrue(audioEvents.drop(eventStart).none { it.optString("stage") in setOf("speech_request", "pcm_started") })
            for (face in listOf("held", "restored", "script", "reading")) {
                val changed = JSONObject(File(f.output, "$name-outside-$face.json").readText()).getJSONArray("native_paragraphs")
                val bounds = (0 until changed.length()).map { changed.getJSONObject(it) }.associate { it.getString("original") to it.getString("native_full_bounds") }
                observed.forEach { assertEquals("Background gestures must preserve actual row positions", it.getString("native_full_bounds"), bounds[it.getString("original")]) }
            }
            proof.put("blank_point_screen", JSONArray(listOf(x, y))).put("all_rows_meaning_hold_release_and_script", true)
                .put("deferred_audio_absent", true).put("audio_event_window", JSONArray(audioEvents.drop(eventStart)))
        }
        File(f.output, "$name-lane-proof.json").writeText(proof.toString(2))
    }
    private fun legalJourney(f: MainActivityJourneyFixture) {
        screen(f, Screen.HOME)
        compose.onNodeWithContentDescription(f.base.getString(R.string.nav_settings)).performTouchInput { click() }
        screen(f, Screen.SETTINGS)
        compose.onNodeWithText(f.base.getString(R.string.ui_2a6b4d12ccfb)).performScrollTo().performTouchInput { click() }
        screen(f, Screen.LICENSES)
        compose.onNodeWithText("Vipi client · AGPL-3.0-only").performScrollTo().assertIsDisplayed()
        compose.onAllNodesWithText("Immersion data").assertCountEquals(0)
        f.capture("legal-01-catalog")
        compose.onNodeWithText("Vipi client · AGPL-3.0-only").performTouchInput { click() }
        val sourceUrl = "https://github.com/FallSoftCo/vipi-clients/releases"
        compose.onNodeWithTag("licenses-client-source").performScrollTo().assertIsDisplayed().assertHasClickAction()
        compose.onNodeWithText(f.base.getString(R.string.licenses_client_source)).assertIsDisplayed()
        val sourceBounds = compose.onNodeWithTag("licenses-client-source").fetchSemanticsNode().boundsInWindow
        assertTrue("Source link must retain48dp target height", sourceBounds.height >= 48*f.base.resources.displayMetrics.density)
        assertTrue(f.base.assets.open("licenses/vipi/NOTICE").bufferedReader().use { it.readText() }.contains(sourceUrl))
        f.capture("legal-02-client-source")
        compose.onNodeWithText(f.base.getString(R.string.licenses_open_failed)).assertDoesNotExist()
        f.device.pressBack()
        compose.onNodeWithText("Vipi client · AGPL-3.0-only").assertIsDisplayed()
        f.device.pressBack(); screen(f, Screen.SETTINGS)
        f.device.pressBack(); screen(f, Screen.HOME)
        File(f.output, "legal-proof.json").writeText(JSONObject().put("settings_licenses_client_notice_back", true)
            .put("obsolete_catalog_absent", true).put("source_label_visible_clickable", f.base.getString(R.string.licenses_client_source)).put("exact_source_destination", sourceUrl)
            .put("external_source_url_opened", false).toString(2))
    }
    @Test fun captureNativeFullMessageStoryAndLegalNotices() = captureStory(qualifyTranscriptLane = false)
    @Test fun centeredTranscriptRetainsFullWidthGesturesAndPhoneGeometry() = captureStory(qualifyTranscriptLane = true)
    private fun captureStory(qualifyTranscriptLane: Boolean) {
        check(story.getString("schema") == "vipi-native-marketing-source-1")
        val storySha = MessageDigest.getInstance("SHA-256").digest(storyBytes).joinToString("") { "%02x".format(it) }
        check(args.getString("vipiMarketingStorySHA") == storySha)
        val viewport = requireNotNull(args.getString("vipiMarketingViewport")).also { require(it in setOf("phone", "tablet7", "tablet10")) }
        // Model acquisition, when explicitly admitted by the controller, uses only
        // the existing on-device SDK. It never changes inputs or provider outputs.
        if (args.getString("vipiMarketingPrepareModels") == "true") runBlocking {
            withTimeout(180_000) { LocalTranslation().use { it.prepare(source, target, cellularAllowed = true) } }
        }
        val turns = story.getJSONArray("friend_turns")
        val outgoingCount = (0 until turns.length()).count { turns.getJSONObject(it).getString("role") == "outgoing" }
        val services = JourneyServices(profileRequired = false, expectedFriendPosts = outgoingCount,
            accountDisplayName = story.getString("account_name"), peerDisplayName = story.getString("friend_name"),
            botReplyText = story.getString("bot_reply"), translationFactory = ::localProvider)
        val audioEvents = CopyOnWriteArrayList<JSONObject>()
        if (qualifyTranscriptLane) MessageAudioQualification.attach { audioEvents += it }
        MainActivityJourneyFixture("${if (qualifyTranscriptLane) "transcript-lane" else "marketing"}-$viewport", { app -> services.model(app).apply { selectKnown(source); selectTarget(target) } }).use { f ->
            try {
                f.bindConversationCapture(compose, "message-input")
                f.launch(); screen(f, Screen.HOME)
                if (!qualifyTranscriptLane && viewport == "phone" && args.getString("vipiMarketingSkipLegal") != "true") legalJourney(f)
                compose.onNodeWithContentDescription(f.base.getString(R.string.nav_new_chat)).performTouchInput { click() }
                screen(f, Screen.NEW_CHAT)
                compose.onNode(hasSetTextAction()).performScrollTo().performTextInput("journey_friend")
                compose.onNode(hasSetTextAction()).performImeAction(); screen(f, Screen.CONVERSATION)
                val originals = mutableListOf<String>()
                for (index in 0 until turns.length()) {
                    val turn = turns.getJSONObject(index); val text = turn.getString("text"); originals += text
                    when (turn.getString("role")) {
                        "outgoing" -> {
                            val expected = services.friendPosts.get() + 1
                            compose.onNodeWithTag("message-input").performTouchInput { click() }.performTextInput(text)
                            compose.onNodeWithTag("message-send").assertIsEnabled().performTouchInput { click() }
                            compose.waitUntil(20_000) { services.friendPosts.get() == expected && services.peerReceived == text }
                        }
                        "incoming" -> {
                            val expected = services.friendReplyReceipts.get() + 1
                            compose.runOnIdle { services.queueAdditionalPeerReplyAndSignalInbox(text) }
                            compose.waitUntil(20_000) { services.friendReplyReceipts.get() == expected }
                        }
                        else -> error("Unknown source story role")
                    }
                }
                f.device.pressBack()
                val chat = requireNotNull(f.model.chat); val owner = requireNotNull(chat.translations)
                val rows = chat.messages(services.peer).associate { it.id.toString() to it.text }
                assertEquals(originals.toSet(), rows.values.toSet()); assertEquals(originals.size, rows.size)
                ready(owner, rows)
                // Deliberately use the actual script gesture, acknowledging the
                // first-use cue without hiding shipping guidance in test code.
                doubleTap(f, originals.first())
                captureRows(f, "friend-01-practice-script", rows, owner, "script")
                doubleTap(f, originals.first())
                captureRows(f, "friend-02-practice-reading", rows, owner, "reading")
                if (qualifyTranscriptLane) qualifyLane(f, "friend-02-practice-reading", rows, owner, viewport, audioEvents)
                val b = paragraph(f, originals.first()); val down = SystemClock.uptimeMillis()
                pointer(f, MotionEvent.ACTION_DOWN, b.exactCenterX(), b.exactCenterY(), down)
                try { SystemClock.sleep(700); captureRows(f, "friend-03-held-meaning", rows, owner, "meaning") }
                finally { pointer(f, MotionEvent.ACTION_UP, b.exactCenterX(), b.exactCenterY(), down) }
                captureRows(f, "friend-04-restored-reading", rows, owner, "reading")
                f.device.pressBack(); screen(f, Screen.HOME)
                compose.onNodeWithContentDescription(f.base.getString(R.string.nav_settings)).assertIsDisplayed()
                captureSettled(f, "home-05-practice-preview")
                compose.onNodeWithText(f.base.getString(R.string.ui_f173182378d0)).performScrollTo().performTouchInput { click() }
                screen(f, Screen.BOT)
                f.bindConversationCapture(compose, "bot-message-input")
                compose.waitUntil(20_000) { f.model.subscriptions?.accessCheckState == AccessCheckState.LOADED && f.model.bot?.allowance != null }
                compose.onNodeWithTag("bot-consent-choice").performScrollTo().performTouchInput { click() }
                compose.onNodeWithTag("bot-consent-continue").performScrollTo().performTouchInput { click() }
                val prompt = story.getString("bot_prompt")
                compose.onNodeWithTag("bot-message-input").performTouchInput { click() }.performTextInput(prompt)
                compose.onNodeWithTag("bot-message-send").assertIsEnabled().performTouchInput { click() }
                compose.waitUntil(20_000) { services.botPosts.get() == 1 }
                services.botReplyGate.complete(Unit)
                compose.waitUntil(20_000) { f.model.bot?.messages?.size == 2 && f.model.bot?.busy == false }
                f.device.pressBack()
                val bot = requireNotNull(f.model.bot); val botOwner = requireNotNull(bot.translations)
                val botRows = bot.messages.associate { it.id to it.text }
                assertEquals(setOf(prompt, story.getString("bot_reply")), botRows.values.toSet())
                ready(botOwner, botRows)
                captureRows(f, "bot-06-practice-reading", botRows, botOwner, "reading")
                if (qualifyTranscriptLane) qualifyLane(f, "bot-06-practice-reading", botRows, botOwner, viewport, audioEvents)
                services.assertNoPurchase(); assertEquals(0, services.reportPosts.get())
                File(f.output, "marketing-provenance.json").writeText(JSONObject().put("purpose", "native_store_marketing")
                    .put("capture_settle", "Compose/native idle +3 display frames +300ms static presentation")
                    .put("legal_skipped", args.getString("vipiMarketingSkipLegal") == "true").put("story_sha256", storySha).put("viewport", viewport).put("provider_events", JSONArray(providerEvents))
                    .put("actual_main_activity", true).put("actual_local_translation_and_reading", true)
                    .put("synthetic_account_relay_bot_billing", true).put("production_auth_or_sends", false)
                    .put("audio_or_acoustic_claim", false).put("source_strings_only", true).toString(2))
            } catch (error: Throwable) { runCatching { f.capture("failure") }; throw error }
            finally {
                if (qualifyTranscriptLane) {
                    File(f.output, "lane-audio-events.json").writeText(JSONArray(audioEvents).toString(2))
                    MessageAudioQualification.attach(null)
                }
                services.botReplyGate.complete(Unit); f.stopActivity(); services.close()
            }
        }
    }
}
