package co.fallsoft.vipi

import android.graphics.Rect
import android.media.AudioManager
import android.os.SystemClock
import android.view.MotionEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.google.mlkit.common.model.RemoteModelManager
import com.google.mlkit.nl.translate.TranslateRemoteModel
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File

/** Actual MainActivity/editor/Signal/vault/Bot owner and real ML Kit/TTS.
 * External relay/account/Bot reply/billing are controlled; no live sends.
 * OS playback is not an acoustic quality claim. */
class FullMessageJourneyDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()
    private val practice: String get() = (androidx.test.platform.app.InstrumentationRegistry.getArguments()
        .getString("vipiFullPractice") ?: "zh").also { require(it in setOf("zh", "ar")) }
    /** Existing downloaded platform models only. This suite never calls a
     * download API; inference still delegates to the real ML Kit client. */
    private fun cachedLocalTranslation(events: MutableList<JSONObject>? = null): LanguageTranslation = object : LanguageTranslation {
        private val actual = LocalTranslation()
        override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) {
            val manager = RemoteModelManager.getInstance()
            for (code in listOf(source, target).distinct().filter { it != "en" }) {
                val installed = withTimeout(10_000) { manager.isModelDownloaded(TranslateRemoteModel.Builder(code).build()).await() }
                events?.add(JSONObject().put("stage", "cached_model_checked").put("language", code).put("installed", installed))
                check(installed) { "Required existing ML Kit model $code is absent; no acquisition authorized by this suite" }
            }
        }
        override suspend fun translate(text: String, source: String, target: String): String {
            events?.add(JSONObject().put("stage", "provider_requested").put("original", text).put("source", source).put("target", target))
            val value = actual.translate(text, source, target)
            events?.add(JSONObject().put("stage", "provider_completed").put("original", text).put("source", source).put("target", target).put("output", value))
            return value
        }
        override fun close() = actual.close()
    }
    /** Retain the exact real owner task before close clears its registry.
     * Reflection is read-only and bound to its actual lock/key/Deferred type;
     * isCompleted proves finally ran, unlike registry size after close. */
    private fun retainedTask(owner: ConversationTranslation, id: String, text: String, source: String, target: String): Deferred<*> {
        val type = ConversationTranslation::class.java
        val lock = type.getDeclaredField("lock").apply { isAccessible = true }.get(owner)
        val tasks = type.getDeclaredField("tasks").apply { isAccessible = true }
        return synchronized(lock) {
            val actual = tasks.get(owner) as? Map<*, *> ?: error("Actual owner task map is unavailable")
            val key = FullMessageTranslation.key(id, text, source, target)
            (actual[key] as? Deferred<*>)?.also { check(!it.isCompleted) { "Expected real pending translation task for $id" } }
                ?: error("Exact pending owner key was not present: $key")
        }
    }
    private data class Face(val original: String, val displayed: String, val bounds: Rect)
    private fun faces(f: MainActivityJourneyFixture, originals: Set<String>): List<Face> {
        var value = emptyList<Face>()
        f.instrumentation.runOnMainSync {
            value = f.paragraphs().filter { it.originalMessage in originals }.map { view ->
                val origin = IntArray(2); view.getLocationOnScreen(origin)
                Face(view.originalMessage, view.text.toString(), Rect(origin[0], origin[1], origin[0]+view.width, origin[1]+view.height))
            }
        }
        return value
    }
    private fun pointer(f: MainActivityJourneyFixture, action: Int, x: Float, y: Float, down: Long): Boolean {
        val event = MotionEvent.obtain(down, SystemClock.uptimeMillis(), action, x, y, 0)
        return try { f.instrumentation.uiAutomation.injectInputEvent(event, true) } finally { event.recycle() }
    }
    private fun screen(f: MainActivityJourneyFixture, screen: Screen) = compose.waitUntil(15_000) { f.model.screen == screen }
    private fun noPlayback(f: MainActivityJourneyFixture) {
        val audio = f.base.getSystemService(AudioManager::class.java)
        val until = SystemClock.uptimeMillis() + 1_000
        while (SystemClock.uptimeMillis() < until) {
            assertFalse("Double/long press or history restoration started audio", audio.isMusicActive)
            SystemClock.sleep(20)
        }
    }
    private fun nativeImeVisible(f: MainActivityJourneyFixture): Boolean {
        var result: Boolean? = null
        f.instrumentation.runOnMainSync {
            val root = f.paragraphs().first().rootView
            result = androidx.core.view.ViewCompat.getRootWindowInsets(root)
                ?.isVisible(androidx.core.view.WindowInsetsCompat.Type.ime())
        }
        return requireNotNull(result) { "Actual activity IME insets unavailable" }
    }
    private fun touchCopyOriginals(f: MainActivityJourneyFixture, prefix: String, input: String,
        rows: Map<String, String>, audioEvents: List<JSONObject>, expectImeVisible: Boolean, stopPlayingManual: Boolean = true) {
        val proofName = "$prefix-copy-original-${if (expectImeVisible) "typing" else "keyboard-hidden"}"
        val translation = requireNotNull(if (prefix == "bot") f.model.bot?.translations else f.model.chat?.translations)
        compose.waitUntil(180_000) { rows.all { (id, text) -> translation.state(id, text)?.phase == MessageTranslationPhase.READY } }
        compose.waitUntil(8_000) { nativeImeVisible(f) == expectImeVisible }
        fun timeline() = if (prefix == "bot") compose.onNode(SemanticsMatcher.keyIsDefined(androidx.compose.ui.semantics.SemanticsActions.ScrollToIndex))
            else compose.onNodeWithTag("conversation-timeline")
        fun visibleAnchors(): List<Face> {
            val timeline = timeline().fetchSemanticsNode().boundsInWindow
            val editor = compose.onNodeWithTag(input).fetchSemanticsNode().boundsInWindow
            var result = emptyList<Face>()
            f.instrumentation.runOnMainSync {
                result = f.paragraphs().mapNotNull { view ->
                    val window = IntArray(2); view.getLocationInWindow(window)
                    val visible = Rect()
                    if (!view.isShown || !view.hasWindowFocus() || !view.getGlobalVisibleRect(visible) ||
                        view.width <= 0 || view.height <= 0 || window[0] < timeline.left || window[1] < timeline.top ||
                        window[0] + view.width > timeline.right || window[1] + view.height > minOf(timeline.bottom, editor.top)) null
                    else {
                        val screen = IntArray(2); view.getLocationOnScreen(screen)
                        Face(view.originalMessage, view.text.toString(), Rect(screen[0], screen[1], screen[0] + view.width, screen[1] + view.height))
                    }
                }
            }
            return result
        }
        val clipboard = f.base.getSystemService(android.content.ClipboardManager::class.java)
        var previous: android.content.ClipData? = null
        f.instrumentation.runOnMainSync { previous = clipboard.primaryClip }
        fun clipboardText(): String? {
            var value: String? = null
            f.instrumentation.runOnMainSync { value = clipboard.primaryClip?.takeIf { it.itemCount == 1 }?.getItemAt(0)?.text?.toString() }
            return value
        }
        val editor = compose.onNodeWithTag(input).fetchSemanticsNode().config
        val draft = editor[SemanticsProperties.EditableText].text
        val selection = editor[SemanticsProperties.TextSelectionRange]
        val before = visibleAnchors()
        assertTrue("Copy must retain actual nonempty visible history anchors independent of selected copy rows", before.isNotEmpty())
        val beforeWindow = f.unobscuredWindow()
        val observations = JSONArray()
        fun observe(label: String) {
            val value = compose.onNodeWithTag(input).fetchSemanticsNode().config
            observations.put(JSONObject().put("label", label).put("uptime_ms", SystemClock.uptimeMillis())
                .put("ime_visible", nativeImeVisible(f)).put("window", f.unobscuredWindow().toShortString())
                .put("timeline", timeline().fetchSemanticsNode().boundsInWindow.toString())
                .put("editor", compose.onNodeWithTag(input).fetchSemanticsNode().boundsInWindow.toString())
                .put("draft", value[SemanticsProperties.EditableText].text).put("selection", value[SemanticsProperties.TextSelectionRange].toString())
                .put("editor_focused", value[SemanticsProperties.Focused])
                .put("visible_anchors", JSONArray(visibleAnchors().map { JSONObject().put("original", it.original).put("bounds", it.bounds.toShortString()) })))
            File(f.output, "$proofName-observations.json").writeText(observations.toString(2))
        }
        observe("before-header-popup")
        f.capture("$proofName-before")
        compose.onNodeWithTag("$prefix-autoplay").assertIsOff()
        var stoppedManualId: String? = null
        if (stopPlayingManual) {
            val selected = before.first { it.original in rows.values }
            stoppedManualId = rows.entries.single { it.value == selected.original }.key
            val initialStarts = audioEvents.count { it.optString("stage") == "pcm_started" && it.optString("id") == stoppedManualId }
            tap(f, selected)
            compose.waitUntil(90_000) { audioEvents.count { it.optString("stage") == "pcm_started" && it.optString("id") == stoppedManualId } == initialStarts + 1 &&
                f.base.getSystemService(AudioManager::class.java).isMusicActive }
        }
        val eventStart = audioEvents.size
        var firstOpen = true
        fun open() {
            compose.waitUntil(8_000) { nativeImeVisible(f) == expectImeVisible && f.unobscuredWindow() == beforeWindow }
            observe("before-header-popup-${observations.length()}")
            compose.onNodeWithTag("$prefix-options").performTouchInput { click() }
            if (firstOpen && stopPlayingManual) assertTrue("Manual playback must still be active immediately before Copy",
                f.base.getSystemService(AudioManager::class.java).isMusicActive)
            compose.onNodeWithTag("$prefix-copy").performTouchInput { click() }
            compose.onNodeWithTag("$prefix-autoplay").assertIsOff()
            if (firstOpen && stopPlayingManual) {
                compose.waitUntil(5_000) { audioEvents.drop(eventStart).any { it.optString("stage") == "speech_stopped" && it.optString("id") == stoppedManualId } }
                assertTrue("Copy must interrupt playback, not wait for natural completion", audioEvents.drop(eventStart).none {
                    it.optString("stage") == "pcm_completed" && it.optString("id") == stoppedManualId })
            }
            firstOpen = false
        }
        try {
            f.instrumentation.runOnMainSync { clipboard.setPrimaryClip(android.content.ClipData.newPlainText("", "Original-copy cancel sentinel")) }
            open()
            rows.keys.forEach {
                compose.onNodeWithTag("copy-choices").performScrollToNode(hasTestTag("copy-choice-$it"))
                compose.onNodeWithTag("copy-choice-$it").assertIsDisplayed()
            }
            f.capture("$proofName-chooser")
            compose.onNodeWithText(f.base.getString(R.string.cancel_action)).performTouchInput { click() }
            compose.waitUntil(8_000) { nativeImeVisible(f) == expectImeVisible && f.unobscuredWindow() == beforeWindow }
            observe("after-cancel")
            assertEquals("Original-copy cancel sentinel", clipboardText())
            for ((id, original) in rows) {
                open()
                compose.onNodeWithTag("copy-choices").performScrollToNode(hasTestTag("copy-choice-$id"))
                compose.onNodeWithTag("copy-choice-$id").performTouchInput { click() }
                compose.waitUntil(5_000) { clipboardText() == original }
                compose.onAllNodesWithTag("copy-choice-$id").assertCountEquals(0)
                compose.waitUntil(8_000) { nativeImeVisible(f) == expectImeVisible && f.unobscuredWindow() == beforeWindow }
                observe("after-copy-$id")
            }
            noPlayback(f)
            assertTrue("No listen request or brief PCM start may occur during any chooser interaction",
                audioEvents.drop(eventStart).none { it.optString("stage") in setOf("speech_request", "pcm_started") })
            val after = compose.onNodeWithTag(input).fetchSemanticsNode().config
            assertEquals(draft, after[SemanticsProperties.EditableText].text)
            assertEquals(selection, after[SemanticsProperties.TextSelectionRange])
            if (expectImeVisible) assertTrue("Typing focus must return after copy/cancel", after[SemanticsProperties.Focused])
            compose.waitUntil(5_000) { visibleAnchors() == before }
            observe("completed")
            f.capture("$proofName-after")
            File(f.output, "$proofName-proof.json").writeText(JSONObject()
                .put("copied_exact_originals", JSONArray(rows.values.toList())).put("cancel_preserved_clipboard", true)
                .put("autoplay_off_before_chooser", true).put("no_audio_from_selection", true)
                .put("manual_playback_stopped_while_already_off", stopPlayingManual)
                .put("original_ime_visible", expectImeVisible).put("viewport_preserved", beforeWindow.toShortString())
                .put("visible_anchors", JSONArray(before.map { JSONObject().put("original", it.original).put("bounds", it.bounds.toShortString()) }))
                .put("audio_event_window", JSONArray(audioEvents.drop(eventStart)))
                .put("draft_selection_and_history_position_preserved", true).toString(2))
        } catch (failure: Throwable) {
            runCatching { observe("failure") }
            throw failure
        } finally {
            f.instrumentation.runOnMainSync {
                previous?.let { clipboard.setPrimaryClip(it) } ?: clipboard.clearPrimaryClip()
            }
        }
    }
    private fun tap(f: MainActivityJourneyFixture, face: Face) = assertTrue(f.device.click(face.bounds.centerX(), face.bounds.centerY()))
    private fun nativeMeaningsAndScriptAndAudio(f: MainActivityJourneyFixture, translation: ConversationTranslation,
        rows: Map<String,String>, name: String) {
        val originals = rows.values.toSet()
        compose.waitUntil(180_000) { rows.all { (id,text) -> translation.state(id,text)?.phase == MessageTranslationPhase.READY } }
        val values = rows.mapValues { (id,text) -> requireNotNull(translation.state(id,text)?.value) }
        compose.waitUntil(10_000) { faces(f, originals).size == rows.size && faces(f, originals).all { face ->
            val value = values.values.single { it.original == face.original }
            face.displayed == (value.practiceReading ?: value.practiceText)
        } }
        val before = faces(f, originals)
        assertEquals(rows.size, before.size)
        before.forEach { assertTrue("Whole native row must be visible before gesture: $it", f.unobscuredWindow().contains(it.bounds)) }
        f.capture("$name-01-practice-reading-default")
        noPlayback(f)
        if (name == "friend") {
            // Blank timeline background shares reveal behavior, without audio.
            val timeline = compose.onNodeWithTag("conversation-timeline")
                .fetchSemanticsNode().boundsInWindow
            val blankX = timeline.left + 1f
            val blankY = timeline.center.y
            assertFalse(before.any { it.bounds.contains(blankX.toInt(), blankY.toInt()) })
            val blankDown = SystemClock.uptimeMillis()
            assertTrue(pointer(f, MotionEvent.ACTION_DOWN, blankX, blankY, blankDown))
            try {
                compose.waitUntil(5_000) { faces(f, originals).all { face -> face.displayed == values.values.single { it.original == face.original }.meaningText } }
                assertEquals(before.map { it.original to it.bounds }, faces(f, originals).map { it.original to it.bounds })
                noPlayback(f)
            } finally { assertTrue(pointer(f, MotionEvent.ACTION_UP, blankX, blankY, blankDown)) }
            compose.waitUntil(5_000) { faces(f, originals) == before }
        }
        val first = before.first()
        val down = SystemClock.uptimeMillis()
        assertTrue(pointer(f, MotionEvent.ACTION_DOWN, first.bounds.centerX().toFloat(), first.bounds.centerY().toFloat(), down))
        try {
            compose.waitUntil(5_000) { faces(f, originals).all { face -> face.displayed == values.values.single { it.original == face.original }.meaningText } }
            assertEquals(before.map { it.original to it.bounds }, faces(f, originals).map { it.original to it.bounds })
            noPlayback(f)
            f.capture("$name-02-held-all-native-meanings")
        } finally { assertTrue(pointer(f, MotionEvent.ACTION_UP, first.bounds.centerX().toFloat(), first.bounds.centerY().toFloat(), down)) }
        compose.waitUntil(5_000) { faces(f, originals) == before }
        // Native double tap, not a semantics action: suppress the delayed tap.
        repeat(2) { index ->
            val began = SystemClock.uptimeMillis()
            assertTrue(pointer(f, MotionEvent.ACTION_DOWN, first.bounds.centerX().toFloat(), first.bounds.centerY().toFloat(), began))
            assertTrue(pointer(f, MotionEvent.ACTION_UP, first.bounds.centerX().toFloat(), first.bounds.centerY().toFloat(), began))
            if (index == 0) SystemClock.sleep(70)
        }
        compose.waitUntil(5_000) { faces(f, originals).all { face -> face.displayed == values.values.single { it.original == face.original }.practiceText } }
        assertEquals(before.map { it.original to it.bounds }, faces(f, originals).map { it.original to it.bounds })
        noPlayback(f)
        f.capture("$name-03-all-native-practice-script")
        // Actual native AX click must play practice audio, never toggle script.
        var clicked = false
        f.instrumentation.runOnMainSync {
            val view = f.paragraphs().single { it.originalMessage == first.original }
            clicked = view.performAccessibilityAction(AccessibilityNodeInfo.ACTION_CLICK, null)
        }
        assertTrue(clicked)
        val audio = f.base.getSystemService(AudioManager::class.java)
        compose.waitUntil(90_000) { audio.isMusicActive }
        assertEquals(values.values.single { it.original == first.original }.practiceText,
            faces(f, originals).single { it.original == first.original }.displayed)
        f.capture("$name-04-actual-practice-audio-with-native-script")
        tap(f, faces(f, originals).single { it.original == first.original })
        compose.waitUntil(10_000) { !audio.isMusicActive }
        noPlayback(f)
        val summary = JSONObject().put("policy", FullMessageTranslation.POLICY).put("whole_rows", rows.size)
            .put("real_translator", true).put("real_signal_or_bot_owner", true).put("native_OS_audio_started_stopped", true)
            .put("acoustic_correctness_claimed", false).put("held_reveal_audio", false).put("hidden_variants_in_AX", false)
            .put("results", JSONArray(values.values.map { it.json() }))
        File(f.output,"$name-proof.json").writeText(summary.toString(2))
    }
    @Test fun actualFriendSendIncomingHoldScriptAndPracticeAudioKeepDraftAndHistory() {
        runBlocking { cachedLocalTranslation().use { it.prepare("en", practice, cellularAllowed = false) } }
        val audioEvents = java.util.concurrent.CopyOnWriteArrayList<JSONObject>()
        MessageAudioQualification.attach { audioEvents += it }
        val previewText = "The orange umbrella is next to the front door."
        val previewGate = kotlinx.coroutines.CompletableDeferred<Unit>()
        val previewCalls = java.util.concurrent.atomic.AtomicInteger()
        val services = JourneyServices(profileRequired = false, expectedFriendPosts = 2, translationFactory = {
            object : LanguageTranslation {
                private val actual = cachedLocalTranslation()
                override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = actual.prepare(source, target, cellularAllowed)
                override suspend fun translate(text: String, source: String, target: String): String {
                    if (text == previewText) { previewCalls.incrementAndGet(); previewGate.await() }
                    return actual.translate(text, source, target)
                }
                override fun close() = actual.close()
            }
        })
        MainActivityJourneyFixture("full-message-friend", { app -> services.model(app).apply { selectTarget(practice) } }).use { f ->
            f.bindConversationCapture(compose, "message-input")
            val cuePreferences = f.base.getSharedPreferences("full-message-gestures", android.content.Context.MODE_PRIVATE)
            val cueWasPresent = cuePreferences.contains("hold-script-policy-1")
            val cueWasSeen = cuePreferences.getBoolean("hold-script-policy-1", false)
            try {
                f.launch(); screen(f, Screen.HOME)
                compose.onNodeWithContentDescription(f.base.getString(R.string.nav_new_chat)).performTouchInput { click() }
                screen(f, Screen.NEW_CHAT)
                compose.onNode(hasSetTextAction()).performScrollTo().performTextInput("journey_friend")
                compose.onNode(hasSetTextAction()).performImeAction()
                screen(f, Screen.CONVERSATION)
                compose.onNodeWithTag("message-input").assertIsDisplayed()
                val prompt = "I left my blue notebook by the kitchen window yesterday."
                compose.onNodeWithTag("message-input").performTouchInput { click() }.performTextInput(prompt)
                compose.onNodeWithTag("message-send").assertIsEnabled().performTouchInput { click() }
                compose.waitUntil(15_000) { services.friendPosts.get() == 1 && services.peerReceived == prompt }
                f.device.pressBack()
                noPlayback(f) // Existing sent history is silent with OFF default.
                compose.onNodeWithTag("conversation-autoplay").assertIsOff().performTouchInput { click() }
                compose.onNodeWithTag("conversation-autoplay").assertIsOn()
                noPlayback(f) // Enabling must not replay that existing message.
                compose.runOnIdle { services.queuePeerReplyAndSignalInbox() }
                compose.waitUntil(15_000) { services.friendReplyReceipts.get() == 1 }
                val audioProof = JSONArray()
                fun stage(name: String, id: String) = audioEvents.filter { it.optString("stage") == name && it.optString("id") == id }
                fun awaitFullAutoplay(id: String, original: String) {
                    val deviceAudio = f.base.getSystemService(AudioManager::class.java)
                    var osActiveObserved = false
                    compose.waitUntil(180_000) {
                        osActiveObserved = osActiveObserved || deviceAudio.isMusicActive
                        stage("pcm_completed", id).size == 1
                    }
                    val value = requireNotNull(f.model.chat?.translations?.state(id, original)?.value)
                    val request = stage("speech_request", id).single()
                    assertEquals(practice, request.getString("practice_language"))
                    assertEquals(value.practiceText, request.getString("practice_text"))
                    assertEquals(1, stage("pcm_started", id).size)
                    assertEquals(1, stage("pcm_completed", id).size)
                    assertTrue(stage("auto_failure", id).isEmpty() && stage("speech_failure", id).isEmpty())
                    audioProof.put(JSONObject().put("id", id).put("original", original).put("practice", value.practiceText)
                        .put("native_pcm_start_and_end", true).put("os_music_active_observed", osActiveObserved))
                    File(f.output, "ordered-autoplay-proof.json").writeText(audioProof.toString(2))
                }
                awaitFullAutoplay(requireNotNull(services.friendReplyId).toString(), services.friendReply)
                f.capture("friend-00-new-incoming-autoplay-completed")
                compose.onNodeWithTag("conversation-autoplay").performTouchInput { click() }
                compose.onNodeWithTag("conversation-autoplay").assertIsOff()
                val chat = requireNotNull(f.model.chat)
                val messages = chat.messages(services.peer).sortedBy { it.createdAt }
                assertEquals(listOf(prompt, services.friendReply), messages.map { it.text })
                val translation = requireNotNull(chat.translations)
                nativeMeaningsAndScriptAndAudio(f, translation, messages.associate { it.id.toString() to it.text }, "friend")
                compose.onNodeWithTag("conversation-options").performTouchInput { click() }
                compose.onNodeWithTag("conversation-report").performTouchInput { click() }
                compose.onNodeWithTag("report-choice-${services.friendReplyId}").performScrollTo().performTouchInput { click() }
                compose.onNodeWithText(services.friendReply).performScrollTo().assertIsDisplayed()
                f.capture("friend-report-original-review")
                compose.onNodeWithText(f.base.getString(R.string.cancel_action)).performTouchInput { click() }
                assertEquals(0, services.reportPosts.get())
                val savedDraft = "Keep this exact unsent draft: café ☕."
                fun draftSnapshot(label: String): JSONObject {
                    val config = compose.onNodeWithTag("message-input").fetchSemanticsNode().config
                    var stored: String? = null
                    f.instrumentation.runOnMainSync { stored = f.model.chat?.compose(services.peer) }
                    val result = JSONObject().put("editor", config[SemanticsProperties.EditableText].text)
                        .put("editor_enabled", !config.contains(SemanticsProperties.Disabled))
                        .put("editor_focused", config[SemanticsProperties.Focused])
                        .put("vault", stored ?: JSONObject.NULL).put("screen", f.model.screen.name)
                        .put("uptime_ms", SystemClock.uptimeMillis())
                    File(f.output, "$label-draft.json").writeText(result.toString(2))
                    return result
                }
                fun restoredDraft(label: String) {
                    val initial = draftSnapshot("$label-initial")
                    assertEquals("Lifecycle must retain exact encrypted draft", savedDraft, initial.getString("vault"))
                    if (initial.getString("editor") != savedDraft)
                        assertFalse("An unhydrated editor must not accept edits over an existing saved draft: $initial", initial.getBoolean("editor_enabled"))
                    compose.waitUntil(8_000) { compose.onNodeWithTag("message-input").fetchSemanticsNode().config[SemanticsProperties.EditableText].text == savedDraft }
                    val final = draftSnapshot("$label-restored")
                    assertEquals(savedDraft, final.getString("vault"))
                }
                compose.onNodeWithTag("message-input").performTouchInput { click() }.assertIsFocused().performTextInput(savedDraft)
                compose.waitUntil(8_000) { compose.onNodeWithTag("message-input").fetchSemanticsNode().config[SemanticsProperties.EditableText].text == savedDraft }
                selectNativeDraftEnd(compose, f, savedDraft, "friend-draft-native-end-before-background")
                assertTrue(f.device.pressKeyCode(android.view.KeyEvent.KEYCODE_X))
                compose.waitUntil(5_000) { f.focusedNativeEditor(savedDraft + "x")?.textSelectionEnd == savedDraft.length + 1 }
                assertTrue(f.device.pressKeyCode(android.view.KeyEvent.KEYCODE_DEL))
                compose.waitUntil(5_000) { f.focusedNativeEditor(savedDraft)?.textSelectionEnd == savedDraft.length }
                assertNativeDraftEndLine(compose, f, "message-input", savedDraft,
                    "friend-draft-current-line-caret-before-background", requireInternalScroll = false)
                assertEquals(savedDraft, draftSnapshot("before-background").getString("vault"))
                touchCopyOriginals(f, "conversation", "message-input", messages.associate { it.id.toString() to it.text }, audioEvents, expectImeVisible = true)
                assertEquals(savedDraft, chat.compose(services.peer)); assertEquals(0, services.reportPosts.get())
                f.backgroundAndResume(); restoredDraft("after-background")
                f.recreate(); screen(f, Screen.CONVERSATION); restoredDraft("after-recreation")
                assertEquals(listOf(prompt, services.friendReply), requireNotNull(f.model.chat).messages(services.peer).sortedBy { it.createdAt }.map { it.text })
                assertEquals(1, services.friendPosts.get()); services.assertNoPurchase()
                f.capture("friend-05-draft-and-history-after-recreation")
                // Several distinct durable arrivals, no retry/replay of a missed
                // item. The actual UI must publish and consume each once.
                compose.onNodeWithTag("conversation-autoplay").assertIsOff().performTouchInput { click() }
                noPlayback(f)
                val secondText = "The green folder is beside the front door."
                var second: java.util.UUID? = null
                compose.runOnIdle { second = services.queueAdditionalPeerReplyAndSignalInbox(secondText) }
                awaitFullAutoplay(requireNotNull(second).toString(), secondText)
                compose.onNodeWithTag("conversation-autoplay").performTouchInput { click() }
                val silentText = "This third message arrives while autoplay is off."
                var silent: java.util.UUID? = null
                compose.runOnIdle { silent = services.queueAdditionalPeerReplyAndSignalInbox(silentText) }
                compose.waitUntil(15_000) { services.friendReplyReceipts.get() == 3 }
                compose.waitUntil(180_000) { f.model.chat?.translations?.state(requireNotNull(silent).toString(), silentText)?.phase == MessageTranslationPhase.READY }
                noPlayback(f)
                assertTrue(stage("speech_request", requireNotNull(silent).toString()).isEmpty())
                compose.onNodeWithTag("conversation-autoplay").performTouchInput { click() }
                noPlayback(f)
                f.backgroundAndResume()
                compose.onNodeWithTag("conversation-autoplay").assertIsOff()
                noPlayback(f)
                compose.onNodeWithContentDescription(f.base.getString(R.string.nav_back)).performTouchInput { click() }
                screen(f, Screen.HOME)
                compose.onNodeWithText("Journey Friend").performScrollTo().performTouchInput { click() }
                screen(f, Screen.CONVERSATION)
                compose.onNodeWithTag("conversation-autoplay").assertIsOff()
                noPlayback(f)
                compose.onNodeWithTag("conversation-autoplay").performTouchInput { click() }
                val reopenedText = "We can meet near the station after lunch."
                var reopened: java.util.UUID? = null
                compose.runOnIdle { reopened = services.queueAdditionalPeerReplyAndSignalInbox(reopenedText) }
                awaitFullAutoplay(requireNotNull(reopened).toString(), reopenedText)
                val nextSent = "I will bring the small green folder tomorrow."
                compose.onNodeWithTag("message-input").performTouchInput { click() }.performTextReplacement(nextSent)
                compose.onNodeWithTag("message-send").assertIsEnabled().performTouchInput { click() }
                compose.waitUntil(15_000) { services.friendPosts.get() == 2 && services.peerReceived == nextSent }
                awaitFullAutoplay(requireNotNull(services.outgoingFriendId).toString(), nextSent)
                compose.onNodeWithTag("conversation-autoplay").performTouchInput { click() }
                assertEquals(4, services.friendReplyReceipts.get())
                assertEquals(4, audioProof.length())
                assertTrue(stage("speech_request", requireNotNull(silent).toString()).isEmpty())
                assertEquals(6, requireNotNull(f.model.chat).messages(services.peer).size)
                compose.onNodeWithTag("message-input").performTextInput("Keep this exact unsent draft: café ☕.")
                f.recreate(); screen(f, Screen.CONVERSATION); restoredDraft("final-recreation")
                services.assertNoPurchase()
                f.capture("friend-06-arrival-sequence-and-originals-retained")
                f.device.pressBack(); screen(f, Screen.HOME)
                val translatedSent = requireNotNull(chat.translations).state(requireNotNull(services.outgoingFriendId).toString(), nextSent)?.value
                assertNotNull(translatedSent)
                compose.onNodeWithTag("home-message-preview-${services.outgoingFriendId}", useUnmergedTree = true)
                    .assertTextEquals(requireNotNull(translatedSent).let { it.practiceReading ?: it.practiceText }).assertIsDisplayed()
                f.capture("friend-07-home-cached-practice-preview")
                var uncached: java.util.UUID? = null
                compose.runOnIdle { uncached = services.queueAdditionalPeerReplyAndSignalInbox(previewText) }
                compose.waitUntil(15_000) { previewCalls.get() == 1 && compose.onAllNodesWithTag("home-message-preview-${requireNotNull(uncached)}", useUnmergedTree = true).fetchSemanticsNodes().size == 1 }
                compose.onNodeWithTag("home-message-preview-${requireNotNull(uncached)}", useUnmergedTree = true)
                    .assertTextEquals(f.base.getString(R.string.full_translation_preparing)).assertIsDisplayed()
                f.capture("friend-08-home-pending-visible-preview")
                compose.onNodeWithText("Journey Friend").performTouchInput { click() }
                screen(f, Screen.CONVERSATION); compose.onNodeWithTag("message-input").assertIsDisplayed()
                previewGate.complete(Unit)
                compose.waitUntil(180_000) { chat.translations?.state(requireNotNull(uncached).toString(), previewText)?.phase == MessageTranslationPhase.READY }
                assertEquals("Home and opened chat must share one actual native translation", 1, previewCalls.get())
                f.device.pressBack(); screen(f, Screen.HOME)
                val previewResult = requireNotNull(chat.translations?.state(requireNotNull(uncached).toString(), previewText)?.value)
                compose.onNodeWithTag("home-message-preview-${requireNotNull(uncached)}", useUnmergedTree = true)
                    .assertTextEquals(previewResult.practiceReading ?: previewResult.practiceText).assertIsDisplayed()
                f.capture("friend-09-home-completed-practice-preview")
                // QA-owned policy flag only. Existing signed-in history must
                // discover the new gesture policy without onboarding again.
                assertTrue(cuePreferences.edit().remove("hold-script-policy-1").commit())
                compose.onNodeWithText("Journey Friend").performTouchInput { click() }
                screen(f, Screen.CONVERSATION); compose.onNodeWithTag("message-input").assertIsDisplayed()
                if (f.base.resources.configuration.orientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE) {
                    compose.onNodeWithTag("full-message-gesture-cue").assertDoesNotExist()
                    assertFalse("Deferred cue must not mark itself learned", cuePreferences.getBoolean("hold-script-policy-1", false))
                    f.capture("friend-10-constrained-cue-deferred")
                } else {
                    compose.waitUntil(5_000) { compose.onAllNodesWithTag("full-message-gesture-cue").fetchSemanticsNodes().size == 1 }
                    val cue = compose.onNodeWithTag("full-message-gesture-cue").fetchSemanticsNode().boundsInWindow
                    val timeline = compose.onNodeWithTag("conversation-timeline").fetchSemanticsNode().boundsInWindow
                    val editor = compose.onNodeWithTag("message-input").fetchSemanticsNode().boundsInWindow
                    assertTrue(timeline.bottom <= cue.top && cue.bottom <= editor.top)
                    assertTrue(f.unobscuredWindow().contains(Rect(kotlin.math.floor(cue.left).toInt(), kotlin.math.floor(cue.top).toInt(), kotlin.math.ceil(cue.right).toInt(), kotlin.math.ceil(cue.bottom).toInt())))
                    f.instrumentation.runOnMainSync { f.paragraphs().forEach { view ->
                        val visible = Rect()
                        if (view.getGlobalVisibleRect(visible)) assertTrue("Cue must not cover actual visible message paint", visible.bottom <= cue.top)
                    } }
                    f.capture("friend-10-existing-history-gesture-cue")
                    compose.onNodeWithTag("conversation-timeline").performTouchInput { doubleClick(center) }
                    compose.waitUntil(5_000) { compose.onAllNodesWithTag("full-message-gesture-cue").fetchSemanticsNodes().isEmpty() }
                    compose.waitUntil(5_000) { faces(f, setOf(previewText)).any { it.displayed == previewResult.practiceText } }
                    noPlayback(f)
                    assertEquals("Learning gestures must preserve the timeline reservation", timeline,
                        compose.onNodeWithTag("conversation-timeline").fetchSemanticsNode().boundsInWindow)
                    f.capture("friend-11-cue-learned-reservation-retained")
                }
                // Reuse the real Gboard/layout/painted-caret regression rather
                // than inferring text visibility from a containing field.
                assertTrue(cuePreferences.edit().remove("hold-script-policy-1").commit())
                exerciseShortLandscapeComposer(compose, f, "message-input", "message-send", savedDraft,
                    "friend-12-current-draft-short-landscape", requireContentDirection = true)
                val constrainedCapture = JSONObject(File(f.output, "friend-12-current-draft-short-landscape.json").readText())
                assertEquals("actual_compose_timeline_editor_window_IME_intersection", constrainedCapture.getString("visibility_qualification"))
                val nativeRows = constrainedCapture.getJSONArray("native_paragraphs")
                assertTrue("The real clipped native history must be observed", nativeRows.length() > 0)
                assertTrue("A native local rectangle must not qualify history behind the composer as fully visible",
                    (0 until nativeRows.length()).none { nativeRows.getJSONObject(it).getBoolean("fully_visible") })
                assertEquals(savedDraft, chat.compose(services.peer))
                assertEquals(2, services.friendPosts.get()); assertEquals(0, services.reportPosts.get())
                // Import through the actual encrypted backup/session boundary:
                // copy includes imported history while report still excludes it.
                val importedId = java.util.UUID.randomUUID()
                val importedOriginal = "Imported original: café ☕ https://example.test/9"
                val backup = File(f.output, "copy-imported-fixture.vipihistory")
                val password = "Isolated copy fixture passphrase"
                try {
                    HistoryBackupCodec.write(backup, password, services.account) { emit ->
                        emit(JSONObject().put("type", "peer").put("id", services.peer.toString())
                            .put("username", JSONObject.NULL).put("display_name", JSONObject.NULL))
                        emit(JSONObject().put("type", "message").put("id", importedId.toString())
                            .put("peer_id", services.peer.toString()).put("direction", "incoming")
                            .put("sent_at_ms", System.currentTimeMillis()).put("text", importedOriginal))
                    }
                    kotlinx.coroutines.runBlocking {
                        val inspected = chat.inspectHistory(backup, password)
                        assertEquals(HistoryBackupStore.Imported(1, 0), chat.importHistory(backup, password, inspected))
                    }
                } finally { backup.delete() }
                compose.waitUntil(8_000) { chat.messages(services.peer).any { it.id == importedId && it.state == "imported" } }
                f.device.pressBack()
                touchCopyOriginals(f, "conversation", "message-input", mapOf(importedId.toString() to importedOriginal), audioEvents, expectImeVisible = false, stopPlayingManual = false)
                compose.onNodeWithTag("conversation-options").performTouchInput { click() }
                compose.onNodeWithTag("conversation-report").performTouchInput { click() }
                val excluded = runCatching {
                    compose.onNodeWithTag("report-choices").performScrollToNode(hasTestTag("report-choice-$importedId"))
                }.exceptionOrNull()
                assertTrue("Imported copyable history must remain absent after searching the whole report chooser: $excluded",
                    excluded is AssertionError && excluded.message?.contains("No node found", ignoreCase = true) == true)
                compose.onNodeWithText(f.base.getString(R.string.cancel_action)).performTouchInput { click() }
                assertEquals(savedDraft, chat.compose(services.peer))
                assertEquals(2, services.friendPosts.get()); assertEquals(0, services.reportPosts.get())
            } catch (failure: Throwable) { runCatching { f.capture("failure") }; throw failure }
            finally {
                File(f.output, "audio-events.json").writeText(JSONArray(audioEvents).toString(2))
                MessageAudioQualification.attach(null)
                previewGate.complete(Unit)
                f.stopActivity(); services.close()
                assertTrue(cuePreferences.edit().let { edit ->
                    if (cueWasPresent) edit.putBoolean("hold-script-policy-1", cueWasSeen) else edit.remove("hold-script-policy-1")
                }.commit())
            }
        }
    }
    @Test fun actualLanguagePickerCancelsPendingPairTranslationAndAudioWithoutLosingMessagesOrDraft() {
        val audioEvents = java.util.concurrent.CopyOnWriteArrayList<JSONObject>()
        val modelEvents = java.util.concurrent.CopyOnWriteArrayList<JSONObject>()
        val completedBeforeReturn = CompletableDeferred<Unit>()
        val release = CompletableDeferred<Unit>()
        val lateReturns = java.util.concurrent.atomic.AtomicInteger()
        val firstIncoming = "The purple umbrella is beside the back door."
        val secondIncoming = "Please bring the small blue notebook tomorrow."
        runBlocking { cachedLocalTranslation(modelEvents).use { model ->
            model.prepare("en", "zh", cellularAllowed = false); model.prepare("en", "ar", cellularAllowed = false)
        } }
        var retainedFirst: Deferred<*>? = null
        var retainedSecond: Deferred<*>? = null
        MessageAudioQualification.attach { audioEvents += it }
        val services = JourneyServices(profileRequired = false, expectedFriendPosts = 1, translationFactory = {
            object : LanguageTranslation {
                private val actual = cachedLocalTranslation(modelEvents)
                override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = actual.prepare(source, target, cellularAllowed)
                override suspend fun translate(text: String, source: String, target: String): String {
                    val value = actual.translate(text, source, target)
                    if (text == firstIncoming && target == "zh") {
                        check(!completedBeforeReturn.isCompleted) { "Unexpected duplicate real old-pair inference" }
                        completedBeforeReturn.complete(Unit)
                        // Only the completed provider return is delayed. The
                        // actual target/detector/reading outputs are untouched.
                        withContext(NonCancellable) { withTimeout(120_000) { release.await() } }
                        lateReturns.incrementAndGet()
                    }
                    return value
                }
                override fun close() = actual.close()
            }
        })
        MainActivityJourneyFixture("full-message-pending-pair", { app -> services.model(app).apply { selectTarget("zh") } }).use { f ->
            f.bindConversationCapture(compose, "message-input")
            val snapshots = JSONArray()
            fun audio(stage: String, id: String? = null) = audioEvents.filter { it.optString("stage") == stage && (id == null || it.optString("id") == id) }
            fun checkpoint(label: String) {
                snapshots.put(JSONObject().put("label", label).put("screen", f.model.screen.name)
                    .put("known", f.model.knownLanguage).put("practice", f.model.targetLanguage)
                    .put("late_returns", lateReturns.get()).put("old_first_completed", retainedFirst?.isCompleted ?: JSONObject.NULL)
                    .put("old_second_completed", retainedSecond?.isCompleted ?: JSONObject.NULL)
                    .put("audio_events", JSONArray(audioEvents)).put("model_events", JSONArray(modelEvents)))
                File(f.output, "pair-lifecycle-checkpoints.json").writeText(snapshots.toString(2))
            }
            try {
                f.launch(); screen(f, Screen.HOME)
                compose.onNodeWithContentDescription(f.base.getString(R.string.nav_new_chat)).performTouchInput { click() }
                screen(f, Screen.NEW_CHAT)
                compose.onNode(hasSetTextAction()).performScrollTo().performTextInput("journey_friend")
                compose.onNode(hasSetTextAction()).performImeAction()
                screen(f, Screen.CONVERSATION)
                val prompt = "I left the blue notebook on the kitchen table."
                compose.onNodeWithTag("message-input").performTouchInput { click() }.performTextInput(prompt)
                compose.onNodeWithTag("message-send").assertIsEnabled().performTouchInput { click() }
                compose.waitUntil(15_000) { services.friendPosts.get() == 1 && services.peerReceived == prompt }
                f.device.pressBack()
                val chat = requireNotNull(f.model.chat)
                val oldOwner = requireNotNull(chat.translations)
                val savedDraft = "Keep this unsent draft: café ☕."
                compose.onNodeWithTag("message-input").performTouchInput { click() }.performTextInput(savedDraft)
                selectNativeDraftEnd(compose, f, savedDraft, "pair-draft-end-before-transition")
                assertNativeDraftEndLine(compose, f, "message-input", savedDraft, "pair-draft-before-transition", requireInternalScroll = false)
                val beforeSelection = compose.onNodeWithTag("message-input").fetchSemanticsNode().config[SemanticsProperties.TextSelectionRange]
                assertEquals(savedDraft, chat.compose(services.peer))
                f.device.pressBack()
                compose.onNodeWithTag("conversation-autoplay").assertIsOff().performTouchInput { click() }
                compose.onNodeWithTag("conversation-autoplay").assertIsOn()
                var first: java.util.UUID? = null
                compose.runOnIdle { first = services.queueAdditionalPeerReplyAndSignalInbox(firstIncoming) }
                val firstId = requireNotNull(first).toString()
                compose.waitUntil(90_000) { completedBeforeReturn.isCompleted && audio("translation_wait", firstId).any { it.optBoolean("automatic") } }
                retainedFirst = retainedTask(oldOwner, firstId, firstIncoming, "en", "zh")
                assertTrue(oldOwner.activeTaskCount > 0)
                var second: java.util.UUID? = null
                compose.runOnIdle { second = services.queueAdditionalPeerReplyAndSignalInbox(secondIncoming) }
                val secondId = requireNotNull(second).toString()
                compose.waitUntil(15_000) { services.friendReplyReceipts.get() == 2 }
                compose.onNodeWithTag("conversation-timeline").performScrollToNode(hasTestTag("message-meta-$secondId"))
                compose.waitUntil(5_000) { faces(f, setOf(secondIncoming)).size == 1 }
                val secondFace = faces(f, setOf(secondIncoming)).single()
                assertTrue(f.unobscuredWindow().contains(secondFace.bounds))
                tap(f, secondFace)
                compose.waitUntil(5_000) { audio("translation_wait", secondId).any { !it.optBoolean("automatic") } }
                retainedSecond = retainedTask(oldOwner, secondId, secondIncoming, "en", "zh")
                compose.onNodeWithTag("conversation-autoplay").assertIsOn()
                assertTrue(audio("speech_request").isEmpty() && audio("pcm_started").isEmpty())
                checkpoint("real-old-model-return-held-with-manual-audio-pending")
                f.capture("pair-01-real-old-model-and-manual-pending")
                val exactMessages = chat.messages(services.peer).associate { it.id.toString() to it.text }
                assertEquals(setOf(requireNotNull(services.outgoingFriendId).toString(), firstId, secondId), exactMessages.keys)
                fun durableSources(): Map<String, Pair<String, String>> = MessageVault(f.isolated, services.account).use { vault ->
                    vault.transaction { exactMessages.mapValues { (id, original) ->
                        val kind = if (id == services.outgoingFriendId.toString()) "outgoing" else "incoming"
                        val record = StoredChat.parse(requireNotNull(vault.get(kind, id)))
                        assertEquals(original, record.text)
                        record.text to record.envelope.fingerprint().joinToString("") { "%02x".format(it) }
                    } }
                }
                val exactJournal = durableSources()
                compose.onNodeWithTag("conversation-options").performTouchInput { click() }
                compose.onNodeWithText(f.base.getString(R.string.ui_318655cea4bd)).performTouchInput { click() }
                screen(f, Screen.LANGUAGE_DOWNLOAD)
                compose.onNodeWithContentDescription(f.base.getString(R.string.want_learn)).performScrollTo().performTouchInput { click() }
                compose.onNodeWithText("${languageName("ar")} · ${initialLanguages.single { it.code == "ar" }.localName}").performTouchInput { click() }
                compose.waitUntil(10_000) { f.model.targetLanguage == "ar" && chat.translations !== oldOwner }
                val newOwner = requireNotNull(chat.translations)
                assertNotSame(oldOwner, newOwner)
                // Registry clear is not completion: the retained real task is
                // still unwinding a deliberately late provider return here.
                assertFalse(requireNotNull(retainedFirst).isCompleted)
                assertTrue(requireNotNull(retainedFirst).isCancelled)
                assertEquals(0, lateReturns.get())
                checkpoint("actual-picker-arabic-old-real-task-cancelling")
                f.capture("pair-02-actual-language-picker-arabic")
                release.complete(Unit)
                compose.waitUntil(10_000) { lateReturns.get() == 1 && requireNotNull(retainedFirst).isCompleted &&
                    requireNotNull(retainedSecond).isCompleted && oldOwner.activeTaskCount == 0 }
                assertTrue(requireNotNull(retainedFirst).isCancelled && requireNotNull(retainedSecond).isCancelled)
                assertNull(oldOwner.state(firstId, firstIncoming)); assertNull(oldOwner.state(secondId, secondIncoming))
                assertEquals(1, modelEvents.count { it.optString("stage") == "provider_completed" && it.optString("original") == firstIncoming && it.optString("target") == "zh" })
                assertTrue(modelEvents.none { it.optString("stage") == "provider_requested" && it.optString("original") == secondIncoming && it.optString("target") == "zh" })
                MessageVault(f.isolated, services.account).use { vault ->
                    val store = FullMessageTranslationStore(vault)
                    assertNull(store.read(FullMessageTranslation.key(firstId, firstIncoming, "en", "zh")))
                    assertNull(store.read(FullMessageTranslation.key(secondId, secondIncoming, "en", "zh")))
                }
                assertTrue(audio("speech_request").isEmpty() && audio("pcm_started").isEmpty())
                assertEquals(exactMessages, chat.messages(services.peer).associate { it.id.toString() to it.text })
                assertEquals(exactJournal, durableSources())
                assertEquals(savedDraft, chat.compose(services.peer))
                checkpoint("late-old-result-disposed-real-task-completed")
                compose.onNodeWithContentDescription(f.base.getString(R.string.nav_back)).performTouchInput { click() }
                screen(f, Screen.CONVERSATION)
                compose.onNodeWithTag("conversation-autoplay").assertIsOff()
                compose.waitUntil(180_000) { exactMessages.all { (id, text) -> newOwner.state(id, text)?.phase == MessageTranslationPhase.READY } }
                val values = exactMessages.mapValues { (id, text) -> requireNotNull(newOwner.state(id, text)?.value) }
                values.forEach { (id, value) ->
                    assertEquals(exactMessages[id], value.original); assertEquals("ar", value.practiceLanguage); assertEquals("en", value.meaningLanguage)
                    assertTrue("Ordinary English input must receive a genuine Arabic practice face", value.practiceText.codePoints().anyMatch { Character.UnicodeScript.of(it) == Character.UnicodeScript.ARABIC })
                    assertEquals(FullMessageReadingStatus.AVAILABLE, value.readingStatus)
                    assertFalse(value.practiceReading.isNullOrBlank())
                    assertTrue(modelEvents.any { it.optString("stage") == "provider_completed" && it.optString("original") == value.original && it.optString("target") == "ar" })
                }
                val initialReturnedEditor = compose.onNodeWithTag("message-input").fetchSemanticsNode().config
                val initiallyHydrated = initialReturnedEditor[SemanticsProperties.EditableText].text == savedDraft
                if (!initiallyHydrated) assertTrue("Restoring draft must not be editable before hydration", initialReturnedEditor.contains(SemanticsProperties.Disabled))
                assertEquals(savedDraft, chat.compose(services.peer))
                compose.waitUntil(8_000) { compose.onNodeWithTag("message-input").fetchSemanticsNode().config[SemanticsProperties.EditableText].text == savedDraft }
                val returnedEditor = compose.onNodeWithTag("message-input").fetchSemanticsNode().config
                assertFalse(returnedEditor.contains(SemanticsProperties.Disabled))
                val returnedSelection = returnedEditor[SemanticsProperties.TextSelectionRange]
                assertTrue(returnedSelection.start in 0..savedDraft.length && returnedSelection.end in 0..savedDraft.length)
                assertEquals(savedDraft, returnedEditor[SemanticsProperties.EditableText].text)
                assertEquals(savedDraft, chat.compose(services.peer))
                compose.onNodeWithTag("conversation-timeline").performScrollToNode(hasTestTag("message-meta-$secondId"))
                // A deliberate user edit after returning; do not confuse
                // draft survival with a selection-persistence claim across
                // different screens. Retain both observed selections below.
                compose.onNodeWithTag("message-input").performTouchInput { click() }
                selectNativeDraftEnd(compose, f, savedDraft, "pair-user-selects-draft-end-after-transition")
                assertNativeDraftEndLine(compose, f, "message-input", savedDraft, "pair-draft-current-end-after-transition", requireInternalScroll = false)
                f.assertIncomingAboveComposer(compose, secondIncoming, "pair-03-arabic-practice-and-exact-draft")
                noPlayback(f)
                assertTrue(audio("speech_request").isEmpty() && audio("pcm_started").isEmpty())
                val current = faces(f, setOf(secondIncoming)).single()
                assertEquals(values.getValue(secondId).let { it.practiceReading ?: it.practiceText }, current.displayed)
                tap(f, current)
                compose.waitUntil(90_000) { audio("pcm_completed", secondId).size == 1 }
                val request = audio("speech_request", secondId).single()
                assertEquals("ar", request.getString("practice_language"))
                assertEquals(values.getValue(secondId).practiceText, request.getString("practice_text"))
                assertEquals(1, audio("pcm_started", secondId).size)
                assertTrue(audio("speech_request").all { it.optString("practice_language") == "ar" })
                assertTrue(audio("auto_failure").isEmpty() && audio("speech_failure").isEmpty())
                assertEquals(exactMessages, chat.messages(services.peer).associate { it.id.toString() to it.text })
                assertEquals(exactJournal, durableSources())
                assertEquals(savedDraft, chat.compose(services.peer)); assertEquals(0, services.reportPosts.get()); services.assertNoPurchase()
                checkpoint("new-pair-deliberate-native-practice-pcm-complete")
                f.capture("pair-04-new-practice-audio-completed")
                File(f.output, "pair-lifecycle-proof.json").writeText(JSONObject().put("passed", true)
                    .put("actual_main_activity_picker", true).put("old_pair", "en->zh").put("new_pair", "en->ar")
                    .put("real_old_provider_completed_before_gate", true).put("late_old_returns", lateReturns.get())
                    .put("actual_old_deferred_completed_cancelled", requireNotNull(retainedFirst).isCompleted && requireNotNull(retainedFirst).isCancelled)
                    .put("old_registry_count_after_completion", oldOwner.activeTaskCount).put("old_pair_cache_absent", true)
                    .put("durable_originals", JSONObject(exactMessages)).put("saved_draft", savedDraft)
                    .put("journal_envelope_fingerprints", JSONObject(exactJournal.mapValues { it.value.second }))
                    .put("before_navigation_selection", beforeSelection.toString()).put("returned_selection", returnedSelection.toString())
                    .put("returned_editor_initially_hydrated", initiallyHydrated).put("draft_hydration_preserved", true)
                    .put("selection_persistence_across_screens_claimed", false)
                    .put("no_old_or_replayed_audio", true).put("new_pair_practice_pcm_started_completed", true)
                    .put("new_pair_results", JSONArray(values.values.map { it.json() }))
                    .put("cached_models_only_no_acquisition", true).put("acoustic_semantic_quality_claimed", false).toString(2))
            } catch (failure: Throwable) { runCatching { checkpoint("failure"); f.capture("failure") }; throw failure }
            finally {
                release.complete(Unit)
                // Await the exact retained tasks after releasing their gate,
                // before fixture teardown can hide a pending real completion.
                try { runBlocking { withTimeout(10_000) { retainedFirst?.join(); retainedSecond?.join() } } }
                finally {
                    File(f.output, "audio-events.json").writeText(JSONArray(audioEvents).toString(2))
                    File(f.output, "model-events.json").writeText(JSONArray(modelEvents).toString(2))
                    MessageAudioQualification.attach(null); f.stopActivity(); services.close()
                }
            }
        }
    }
    @Test fun actualBotConsentSendResponseAndFullMessageGestures() {
        runBlocking { cachedLocalTranslation().use { it.prepare("en", practice, cellularAllowed = false) } }
        val audioEvents = java.util.concurrent.CopyOnWriteArrayList<JSONObject>()
        MessageAudioQualification.attach { audioEvents += it }
        val services = JourneyServices(profileRequired = false, expectedFriendPosts = 0, translationFactory = { cachedLocalTranslation() })
        MainActivityJourneyFixture("full-message-bot", { app -> services.model(app).apply { selectTarget(practice) } }).use { f ->
            f.bindConversationCapture(compose, "bot-message-input")
            try {
                f.launch(); screen(f, Screen.HOME)
                compose.onNodeWithText(f.base.getString(R.string.ui_f173182378d0)).performScrollTo().performTouchInput { click() }
                screen(f, Screen.BOT)
                compose.waitUntil(15_000) { f.model.subscriptions?.accessCheckState == AccessCheckState.LOADED && f.model.bot?.allowance != null }
                compose.onNodeWithTag("bot-consent-choice").performScrollTo().performTouchInput { click() }
                compose.onNodeWithTag("bot-consent-continue").performScrollTo().performTouchInput { click() }
                val prompt = "My blue notebook is still beside the kitchen window."
                compose.onNodeWithTag("bot-message-input").performTouchInput { click() }.performTextInput(prompt)
                compose.onNodeWithTag("bot-message-send").assertIsEnabled().performTouchInput { click() }
                compose.waitUntil(15_000) { services.botPosts.get() == 1 }
                services.botReplyGate.complete(Unit)
                compose.waitUntil(15_000) { f.model.bot?.messages?.size == 2 && f.model.bot?.busy == false }
                f.device.pressBack()
                val bot = requireNotNull(f.model.bot)
                nativeMeaningsAndScriptAndAudio(f, requireNotNull(bot.translations), bot.messages.associate { it.id to it.text }, "bot")
                assertEquals(prompt, bot.messages.first().text)
                assertEquals(services.botReply, bot.messages.last().text)
                compose.onNodeWithTag("bot-options").performTouchInput { click() }
                compose.onNodeWithTag("bot-report").performTouchInput { click() }
                compose.onNodeWithTag("report-choice-${bot.messages.last().id}").performScrollTo().performTouchInput { click() }
                compose.onNodeWithText(services.botReply).assertIsDisplayed()
                f.capture("bot-report-original-review")
                compose.onNodeWithText(f.base.getString(R.string.cancel_action)).performTouchInput { click() }
                assertEquals(0, services.reportPosts.get())
                val copyDraft = "An unsent original-copy draft: café ☕."
                compose.onNodeWithTag("bot-message-input").performTouchInput { click() }.performTextInput(copyDraft)
                touchCopyOriginals(f, "bot", "bot-message-input", bot.messages.associate { it.id to it.text }, audioEvents, expectImeVisible = true)
                f.device.pressBack()
                touchCopyOriginals(f, "bot", "bot-message-input", bot.messages.associate { it.id to it.text }, audioEvents, expectImeVisible = false, stopPlayingManual = false)
                assertEquals(copyDraft, bot.draft); assertEquals(0, services.reportPosts.get())
                assertEquals(1, services.botPosts.get()); services.assertNoPurchase()
            } catch (failure: Throwable) { runCatching { f.capture("failure") }; throw failure }
            finally { MessageAudioQualification.attach(null); services.botReplyGate.complete(Unit); f.stopActivity(); services.close() }
        }
    }
}
