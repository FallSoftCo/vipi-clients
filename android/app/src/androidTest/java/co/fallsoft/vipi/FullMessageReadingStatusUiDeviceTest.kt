package co.fallsoft.vipi

import android.graphics.Rect
import android.view.View
import android.view.ViewGroup
import android.view.ViewConfiguration
import android.os.SystemClock
import androidx.compose.foundation.layout.Column
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.core.view.accessibility.AccessibilityNodeInfoCompat
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import co.fallsoft.vipi.core.SpeechSpan
import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.security.KeyStore
import java.util.UUID
import java.util.concurrent.CopyOnWriteArrayList

/** Actual production bubble/owner, isolated cached failure and speech boundary.
 * This tests presentation, not MainActivity routing, gestures or real PCM. */
class FullMessageReadingStatusUiDeviceTest {
    @get:Rule val compose = createComposeRule()
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrumentation.targetContext
    private data class Native(val displayed: String, val bounds: Rect, val state: String?)
    private fun paragraph(original: String): Native {
        var result: Native? = null
        instrumentation.runOnMainSync {
            val found = mutableListOf<FullMessageTextView>()
            fun visit(view: View) {
                if (view is FullMessageTextView && view.originalMessage == original) found += view
                if (view is ViewGroup) for (index in 0 until view.childCount) visit(view.getChildAt(index))
            }
            ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).forEach { visit(it.window.decorView) }
            val view = found.single(); val location = IntArray(2); view.getLocationOnScreen(location)
            val info = view.createAccessibilityNodeInfo()
            try { result = Native(view.text.toString(), Rect(location[0], location[1], location[0]+view.width, location[1]+view.height),
                AccessibilityNodeInfoCompat.wrap(info).stateDescription?.toString()) }
            finally { info.recycle() }
        }
        return requireNotNull(result)
    }
    private fun nativeRetryBounds(label: String): Pair<Rect, Rect> {
        data class Node(val bounds: Rect, val visible: Boolean)
        val deadline = SystemClock.uptimeMillis() + 5_000
        var attempts = 0
        do {
            attempts++
            val root = instrumentation.uiAutomation.rootInActiveWindow
            val tree = org.json.JSONArray()
            val matches = mutableListOf<Pair<Node?, Node>>()
            if (root != null) {
                fun visit(node: android.view.accessibility.AccessibilityNodeInfo, ancestor: Node?) {
                    val bounds = Rect(); node.getBoundsInScreen(bounds)
                    val current = Node(bounds, node.isVisibleToUser)
                    val owner = if (node.isClickable) current else ancestor
                    tree.put(JSONObject().put("text", node.text?.toString() ?: JSONObject.NULL)
                        .put("description", node.contentDescription?.toString() ?: JSONObject.NULL)
                        .put("class", node.className?.toString()).put("package", node.packageName?.toString())
                        .put("bounds", bounds.toShortString()).put("clickable", node.isClickable)
                        .put("visible", node.isVisibleToUser).put("child_count", node.childCount))
                    if (node.text?.toString() == label || node.contentDescription?.toString() == label) matches += owner to current
                    for (index in 0 until node.childCount) node.getChild(index)?.let { child ->
                        try { visit(child, owner) } finally { child.recycle() }
                    }
                }
                try { visit(root, null) } finally { root.recycle() }
            }
            // Compose1.9.3's provider implements node creation/children, not
            // findAccessibilityNodeInfosByText. Retain the actual observed tree,
            // including on a miss, instead of guessing a different label.
            readingRegressionFile(context, "reading-status-native-tree.json").writeText(JSONObject()
                .put("attempts", attempts).put("matching_labels", matches.size).put("nodes", tree).toString(2))
            check(matches.size <= 1) { "Ambiguous actual retry AX label; native tree retained" }
            if (matches.size == 1) {
                val (possibleOwner, text) = matches.single()
                val owner = requireNotNull(possibleOwner) { "Retry label has no actual clickable AX owner" }
                check(owner.visible && text.visible && owner.bounds.contains(text.bounds)) { "AX click owner must contain visible label" }
                return owner.bounds to text.bounds
            }
            SystemClock.sleep(20)
        } while (SystemClock.uptimeMillis() < deadline)
        error("Actual retry AX label did not appear; native child tree retained")
    }
    @Test fun gestureCueExposesNativeActionNamesInsteadOfPhysicalScreenReaderInstructions() {
        check(BuildConfig.DEBUG && BuildConfig.APPLICATION_ID == "co.fallsoft.vipi.sourcecontextqa")
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val preferences = context.getSharedPreferences("full-message-gestures", android.content.Context.MODE_PRIVATE)
        val key = "hold-script-policy-1"; val present = preferences.contains(key); val seen = preferences.getBoolean(key, false)
        val gestures = FullMessageGestures(); val mounted = androidx.compose.runtime.mutableStateOf(true)
        val expected = listOf(context.getString(R.string.full_translation_play), context.getString(R.string.full_translation_meaning),
            context.getString(R.string.full_translation_script)).joinToString(". ")
        val physical = context.getString(R.string.full_translation_gestures)
        try {
            check(preferences.edit().remove(key).commit())
            compose.setContent { if (mounted.value) VipiTheme(Appearance.LIGHT) {
                FullMessageGestureCue(gestures, composing = false, deferred = false)
            } }
            compose.onNodeWithTag("full-message-gesture-cue").assertContentDescriptionEquals(expected)
            compose.onNodeWithText(physical).assertDoesNotExist() // visual ink is replaced only in the AX tree
            val spoken = mutableListOf<String>()
            fun visit(node: android.view.accessibility.AccessibilityNodeInfo) {
                node.text?.toString()?.let { spoken += it }; node.contentDescription?.toString()?.let { spoken += it }
                for (index in 0 until node.childCount) node.getChild(index)?.let { child ->
                    try { visit(child) } finally { child.recycle() }
                }
            }
            compose.waitUntil(3_000) {
                spoken.clear()
                instrumentation.uiAutomation.rootInActiveWindow?.let { root -> try { visit(root) } finally { root.recycle() } }
                spoken.contains(expected)
            }
            assertTrue("Actual native AX must advertise message actions", spoken.contains(expected))
            assertFalse("Native AX must not claim the screen-reader double tap changes script", spoken.contains(physical))
        } finally {
            compose.runOnIdle { mounted.value = false }
            val editor = preferences.edit(); if (present) editor.putBoolean(key, seen) else editor.remove(key)
            check(editor.commit())
        }
    }

    @Test fun unavailableFeedbackIsConditionalAccessibleAndDoesNotShiftFacesOrChangePracticeAudio(): Unit = runBlocking {
        check(BuildConfig.DEBUG && BuildConfig.APPLICATION_ID == "co.fallsoft.vipi.sourcecontextqa")
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val account = UUID.randomUUID(); val vault = MessageVault(context, account); val store = FullMessageTranslationStore(vault)
        val original = "Original retained message."; val practice = "銀行"; val id = UUID.randomUUID().toString()
        val copy = context.getString(R.string.lookup_reading_unavailable)
        val feedback = "$copy ${context.getString(R.string.try_again)}"; val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        val calls = CopyOnWriteArrayList<List<SpeechSpan>>()
        val entered = CompletableDeferred<Unit>(); val release = CompletableDeferred<Unit>()
        val reads = java.util.concurrent.atomic.AtomicInteger()
        val speech = object : ConversationSpeech {
            override val state = SpeechState.READY; override val error: String? = null
            override val activeMessage: String? = null; override val interruption = 0L
            override fun toggle(message: String, spans: List<SpeechSpan>) { calls += spans }
            override fun stop() = Unit
            override fun showMutedVolumeControl() = Unit
            override fun failureMessage() = "Unexpected controlled voice failure"
        }
        val model = object : LanguageTranslation {
            override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = Unit
            override suspend fun translate(text: String, source: String, target: String): String = error("Cached UI fixture must not translate")
            override fun close() = Unit
        }
        store.write(FullMessageTranslation.key(id, original, "en", "ja"), FullMessageTranslation(original, practice, original, "en", "ja", "en",
            readingPolicy = FullMessageReadings.policy("ja"), readingStatus = FullMessageReadingStatus.UNAVAILABLE,
            readingFailure = FullMessageReadingFailure.PRODUCER_FAILURE))
        val literalId = UUID.randomUUID().toString(); val literalOriginal = "Second original."
        store.write(FullMessageTranslation.key(literalId, literalOriginal, "en", "ja"),
            FullMessageTranslation(literalOriginal, "OK 🙂", literalOriginal, "en", "ja", "en",
                readingPolicy = FullMessageReadings.policy("ja"), readingStatus = FullMessageReadingStatus.NOT_NEEDED))
        val limitId = UUID.randomUUID().toString(); val limitOriginal = "Static refusal original."
        store.write(FullMessageTranslation.key(limitId, limitOriginal, "en", "ja"),
            FullMessageTranslation(limitOriginal, "追加", limitOriginal, "en", "ja", "en",
                readingPolicy = FullMessageReadings.policy("ja"), readingStatus = FullMessageReadingStatus.UNAVAILABLE,
                readingFailure = FullMessageReadingFailure.INPUT_LIMIT))
        val translation = ConversationTranslation(context, "en", "ja", store, model,
            object : MessageTranslationLanguage {
                override suspend fun identify(text: String): String? = error("Cached UI fixture must not identify")
                override fun close() = Unit
            }, reading = { text, code -> reads.incrementAndGet(); entered.complete(Unit); release.await(); FullMessageReadings.read(context, text, code) })
        val audio = withContext(Dispatchers.Main) { ConversationAutoplay(translation, speech, scope) { error("No voice help expected") } }
        val gestures = FullMessageGestures()
        val mounted = androidx.compose.runtime.mutableStateOf(true)
        try {
            translation.resolve(id, original); translation.resolve(literalId, literalOriginal); translation.resolve(limitId, limitOriginal)
            assertEquals(0, reads.get())
            compose.setContent { if (mounted.value) VipiTheme(Appearance.LIGHT) {
                Column(Modifier.testTag("reading-status-layout").fullMessageGestures(gestures)) {
                    FullMessageBubble(original, id, translation, gestures, audio) { }
                    FullMessageBubble(literalOriginal, literalId, translation, gestures, audio) { }
                    FullMessageBubble(limitOriginal, limitId, translation, gestures, audio) { }
                }
            } }
            compose.onNodeWithText(feedback).assertIsDisplayed().assertHasClickAction()
            compose.onNodeWithText(copy).assertIsDisplayed().assertHasNoClickAction()
            val actionBounds = compose.onNodeWithText(feedback).fetchSemanticsNode().boundsInWindow
            val before = paragraph(original)
            readingRegressionFile(context, "reading-status-preassert.json").writeText(JSONObject()
                .put("action_bounds_window", actionBounds.toString()).put("action_height_px", actionBounds.height)
                .put("density", context.resources.displayMetrics.density).put("required_minimum_px", 48 * context.resources.displayMetrics.density)
                .put("native_body_bounds_screen", before.bounds.toShortString()).put("native_body_state_description", before.state)
                .put("semantics", compose.onNodeWithText(feedback).printToString()).toString(2))
            instrumentation.uiAutomation.takeScreenshot().let { image ->
                readingRegressionFile(context, "reading-status-unavailable.png").outputStream().use { image.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }; image.recycle()
            }
            val (nativeOwner, nativeLabel) = nativeRetryBounds(feedback)
            readingRegressionFile(context, "reading-status-native-target.json").writeText(JSONObject()
                .put("click_owner_screen", nativeOwner.toShortString()).put("label_screen", nativeLabel.toShortString())
                .put("required_minimum_px", 48 * context.resources.displayMetrics.density).toString(2))
            assertTrue("Retry click owner $actionBounds must be at least48dp at density ${context.resources.displayMetrics.density}",
                actionBounds.height >= 48 * context.resources.displayMetrics.density)
            assertTrue("Actual native AX click owner $nativeOwner must be at least48dp", nativeOwner.height() >= 48 * context.resources.displayMetrics.density)
            assertEquals(practice, before.displayed); assertEquals(copy, before.state)
            assertNull(paragraph(literalOriginal).state)
            val layout = compose.onNodeWithTag("reading-status-layout").fetchSemanticsNode().boundsInWindow
            compose.runOnIdle { gestures.held = true }
            compose.onNodeWithText(copy).assertDoesNotExist(); compose.onNodeWithText(feedback).assertDoesNotExist()
            val meaning = paragraph(original); assertEquals(original, meaning.displayed); assertNull(meaning.state); assertEquals(before.bounds, meaning.bounds)
            assertEquals(layout, compose.onNodeWithTag("reading-status-layout").fetchSemanticsNode().boundsInWindow)
            compose.runOnIdle { gestures.held = false; gestures.nativeScript = true }
            compose.onNodeWithText(copy).assertDoesNotExist(); compose.onNodeWithText(feedback).assertDoesNotExist()
            val script = paragraph(original); assertEquals(practice, script.displayed); assertNull(script.state); assertEquals(before.bounds, script.bounds)
            assertEquals(layout, compose.onNodeWithTag("reading-status-layout").fetchSemanticsNode().boundsInWindow)
            withContext(Dispatchers.Main) { audio.manual(id, original) }
            withTimeout(5_000) { while (calls.isEmpty()) delay(10) }
            assertEquals(listOf(listOf(SpeechSpan(practice, "ja"))), calls.toList())
            compose.runOnIdle { gestures.nativeScript = false }
            compose.onNodeWithText(feedback).assertIsDisplayed(); assertEquals(copy, paragraph(original).state)
            compose.onNodeWithText(feedback).performTouchInput { click() }
            compose.waitUntil(5_000) { entered.isCompleted }
            assertEquals(1, reads.get())
            assertEquals(MessageTranslationPhase.READY, translation.state(id, original)?.phase)
            assertEquals(practice, translation.state(id, original)?.value?.practiceText)
            assertEquals(1, calls.size)
            // The conversation gesture handler delays a single tap until this
            // actual platform window expires. Keep the surface mounted through
            // that window; immediate callback counts would miss a late listen.
            val observationStarted = SystemClock.uptimeMillis()
            val doubleTapTimeout = ViewConfiguration.getDoubleTapTimeout().toLong()
            do {
                compose.waitForIdle()
                assertEquals("Feedback tap dispatched delayed message audio", 1, calls.size)
                SystemClock.sleep(10)
            } while (SystemClock.uptimeMillis() - observationStarted <= doubleTapTimeout)
            compose.waitForIdle(); assertEquals(1, calls.size)
            release.complete(Unit)
            compose.waitUntil(8_000) { translation.state(id, original)?.value?.readingStatus == FullMessageReadingStatus.AVAILABLE }
            compose.onNodeWithText(feedback).assertDoesNotExist()
            compose.onNodeWithText(copy).assertIsDisplayed().assertHasNoClickAction() // Only the permanent limit remains.
            assertNull(paragraph(original).state); assertEquals(1, reads.get()); assertEquals(1, calls.size)
            readingRegressionFile(context, "reading-status-ui.json").writeText(JSONObject().put("passed", true)
                .put("native_state_description", copy).put("no_notice_for_literal", true).put("hold_script_geometry_preserved", true)
                .put("practice_audio_command_preserved", true).put("reading_only_touch_retry", true).put("ready_during_retry", true)
                .put("no_feedback_tap_audio", true).put("deferred_tap_observation_ms", SystemClock.uptimeMillis() - observationStarted)
                .put("platform_double_tap_timeout_ms", doubleTapTimeout).put("no_retry_for_input_limit", true).put("scope", "Production component with controlled cached failure and speech boundary; not actual root/gesture/PCM proof").toString(2))
        } finally {
            compose.runOnIdle { mounted.value = false }
            withContext(Dispatchers.Main) { audio.close(); scope.cancel() }; translation.close()
            vault.close(); vault.file.parentFile!!.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
        }
    }
}
