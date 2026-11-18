package co.fallsoft.vipi

import android.graphics.Rect
import android.text.Spanned
import android.text.style.ReplacementSpan
import android.view.accessibility.AccessibilityNodeInfo
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.test.uiautomator.By
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File

/** Actual MainActivity, saved language choices, native composer and real Signal
 * send. Ordinary source-only messages use the DEFAULT production immersion;
 * no result, provider, target text, reading or model readiness is injected. */
class ConversationAppearanceJourneyDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()
    @Test fun chineseReadingAndScriptKeepActualConversationSlotAndAudioPosition() =
        qualify("en", "zh", "I left your book on the table in the kitchen.", "book")
    @Test fun arabicSourceKeepsRtlPunctuationActualConversationSlotAndAudioPosition() =
        qualify("ar", "en", "هل يمكن أن نشرب القهوة معًا بعد العمل غدًا؟", "غدًا")

    private data class NativeFace(val whole: String, val focus: String, val body: Rect,
        val word: Rect, val paragraphDirection: Int, val placeholder: String)
    private fun qualify(source: String, target: String, text: String, focus: String) {
        val services = JourneyServices(profileRequired = false, expectedBotPosts = 0)
        val start = text.indexOf(focus); val end = start + focus.length
        assertTrue(start >= 0)
        MainActivityJourneyFixture("actual-slots-$source-$target", { app -> services.model(app).also {
            it.selectKnown(source); it.selectTarget(target); it.changeDensity(.25); it.changeAppearance(Appearance.LIGHT)
        } }).use { f ->
            val observations = JSONArray()
            fun face(): NativeFace? {
                var result: NativeFace? = null
                f.instrumentation.runOnMainSync {
                    f.paragraphs().singleOrNull { it.displayedOriginal == text }?.let { view ->
                        val spanned = view.text as? Spanned
                        val slots = spanned?.getSpans(start, end, ReplacementSpan::class.java).orEmpty().filter {
                            spanned!!.getSpanStart(it) == start && spanned.getSpanEnd(it) == end
                        }
                        if (slots.size == 1 && f.fullyVisible(view)) {
                            val xy = IntArray(2); view.getLocationOnScreen(xy)
                            result = NativeFace(view.visibleText(), view.visibleText(start, end),
                                Rect(xy[0], xy[1], xy[0] + view.width, xy[1] + view.height),
                                view.sourceRangeRect(start, end), view.layout.getParagraphDirection(0), view.text.toString())
                        }
                    }
                }
                return result
            }
            fun paintedCardWidth(value: NativeFace): Rect {
                val bitmap = requireNotNull(f.instrumentation.uiAutomation.takeScreenshot())
                try {
                    val y = value.body.centerY(); val x = value.body.left - (8 * f.base.resources.displayMetrics.density).toInt()
                    val color = bitmap.getPixel(x, y)
                    assertNotEquals("Sample is actual outgoing card fill, not the canvas", bitmap.getPixel(0, y), color)
                    val pixels = (0 until bitmap.width).filter { bitmap.getPixel(it, y) == color }
                    assertTrue("Require a broad connected card row, not a text glyph", pixels.size > value.body.width() / 2)
                    return Rect(pixels.first(), y, pixels.last() + 1, y + 1)
                } finally { bitmap.recycle() }
            }
            fun captureFace(name: String): NativeFace {
                val value = requireNotNull(face())
                val card = paintedCardWidth(value)
                observations.put(JSONObject().put("phase", name).put("actual_visible_text", value.whole)
                    .put("actual_focus_face", value.focus).put("native_body", value.body.toShortString())
                    .put("actual_word_rect", value.word.toShortString()).put("painted_card_row", card.toShortString())
                    .put("paragraph_direction", value.paragraphDirection).put("native_source_placeholder", value.placeholder))
                assertEquals(text, value.placeholder); assertTrue(value.whole.endsWith(text.takeLast(1)))
                assertEquals(if (source == "ar") -1 else 1, value.paragraphDirection)
                f.capture(name)
                return value
            }
            fun audioOwner(label: String, name: String): Rect {
                fun find(n: AccessibilityNodeInfo): List<AccessibilityNodeInfo> = buildList {
                    if (n.contentDescription?.toString() == label && n.isVisibleToUser) add(n)
                    repeat(n.childCount) { i -> n.getChild(i)?.let { addAll(find(it)) } }
                }
                var result: Rect? = null; var proof = JSONObject()
                compose.waitUntil(5_000) {
                    if (android.os.Build.VERSION.SDK_INT >= 33) f.instrumentation.uiAutomation.clearCache()
                    val node = f.instrumentation.uiAutomation.windows.mapNotNull { it.root }
                        .filter { it.packageName?.toString() == f.base.packageName }.flatMap(::find).singleOrNull()
                    var owner = node
                    while (owner != null && !(owner.isClickable && owner.actionList.any { it.id == AccessibilityNodeInfo.ACTION_CLICK })) owner = owner.parent
                    val icon = Rect(); node?.getBoundsInScreen(icon)
                    val bounds = Rect(); owner?.getBoundsInScreen(bounds)
                    val accepted = owner?.isEnabled == true && owner.isVisibleToUser &&
                        f.unobscuredWindow().contains(bounds) && bounds.width() >= 48 * f.base.resources.displayMetrics.density &&
                        bounds.height() >= 48 * f.base.resources.displayMetrics.density
                    proof = JSONObject().put("label", label).put("icon_bounds", icon.toShortString())
                        .put("actual_ACTION_CLICK_owner_bounds", bounds.toShortString()).put("owner_enabled", owner?.isEnabled)
                        .put("owner_clickable", owner?.isClickable).put("owner_ACTION_CLICK", owner?.actionList?.any { it.id == AccessibilityNodeInfo.ACTION_CLICK })
                        .put("full48dp_owner_visible", accepted)
                    if (accepted) result = bounds
                    accepted
                }
                File(f.output, "$name.json").writeText(proof.toString(2))
                return requireNotNull(result)
            }
            fun action(label: String) {
                fun matches(n: AccessibilityNodeInfo): List<AccessibilityNodeInfo> = buildList {
                    if (n.text?.toString() == text && n.isVisibleToUser) add(n)
                    repeat(n.childCount) { i -> n.getChild(i)?.let { addAll(matches(it)) } }
                }
                if (android.os.Build.VERSION.SDK_INT >= 33) f.instrumentation.uiAutomation.clearCache()
                val node = matches(requireNotNull(f.instrumentation.uiAutomation.rootInActiveWindow)).single()
                val entry = node.actionList.single { it.label?.toString() == label }
                assertTrue("Actual native accessibility action: $label", node.performAction(entry.id))
            }
            try {
                f.launch(); compose.waitUntil(10_000) { f.model.screen == Screen.HOME && f.model.chat?.ready == true }
                compose.onNodeWithContentDescription(f.base.getString(R.string.nav_new_chat)).performTouchInput { click() }
                compose.waitUntil(10_000) { f.model.screen == Screen.NEW_CHAT }
                val field = compose.onNode(hasSetTextAction())
                field.performScrollTo().performTouchInput { click() }; field.performTextInput("@Journey_Friend")
                f.tapNativeGboardSearch(compose, "01-actual-native-lookup-search")
                compose.waitUntil(10_000) { f.model.screen == Screen.CONVERSATION }
                compose.onNodeWithTag("message-input").performTouchInput { click() }
                compose.onNodeWithTag("message-input").performTextInput(text)
                exerciseShortLandscapeComposer(compose, f, "message-input", "message-send", text, "02-real-source-composer-caret-and-punctuation", requireContentDirection = true)
                compose.runOnIdle { assertEquals(0, services.friendPosts.get()); assertEquals(text, f.model.chat?.compose(services.peer)) }
                compose.onNodeWithTag("message-send").assertIsEnabled().performTouchInput { click() }
                compose.waitUntil(10_000) { services.friendPosts.get() == 1 && services.peerReceived == text && f.model.chat?.messages(services.peer)?.singleOrNull()?.state == "delivered" }
                f.device.pressBack(); compose.waitForIdle()
                if (f.model.screen == Screen.HOME) {
                    compose.onNodeWithText("Journey Friend").performScrollTo().performTouchInput { click() }
                    compose.waitUntil(10_000) { f.model.screen == Screen.CONVERSATION }
                }
                compose.waitUntil(15_000) { face()?.focus?.let { it != focus } == true }
                val guide = captureFace("03-default-engine-live-reading")
                if (target == "zh") assertTrue("Actual default Chinese guide must retain a tone mark",
                    guide.focus.any { it in "āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ" })
                val cardBefore = paintedCardWidth(guide)
                // Observe the real production clock before any manual touch.
                // A single first target face is not continuous immersion proof.
                val automaticStart = android.os.SystemClock.elapsedRealtime()
                var previous = guide
                val automaticFaces = mutableListOf(guide.focus)
                repeat(3) { index ->
                    val remaining = 30_000L - (android.os.SystemClock.elapsedRealtime() - automaticStart)
                    assertTrue("Three automatic native face changes must fit the original30s bound", remaining > 0)
                    compose.waitUntil(remaining) { face()?.focus?.let { it != previous.focus } == true }
                    val changed = captureFace("03-auto-change-${index + 1}")
                    assertNotEquals("Each automatic observation must actually change the focus face", previous.focus, changed.focus)
                    assertEquals(guide.body, changed.body); assertEquals(guide.word, changed.word)
                    val card = paintedCardWidth(changed)
                    assertEquals(cardBefore.left, card.left); assertEquals(cardBefore.right, card.right)
                    automaticFaces += changed.focus; previous = changed
                }
                assertTrue("Automatic cycle must show the actual original source face", focus in automaticFaces)
                assertTrue("Automatic cycle must also show a real target/reading face", automaticFaces.any { it != focus })
                // Manual tap is still exercised from the current target face,
                // after the independently observed automatic-cycle outcome.
                compose.waitUntil(10_000) { face()?.focus?.let { it != focus } == true }
                val manualTarget = requireNotNull(face())
                assertTrue(f.device.click(manualTarget.word.centerX(), manualTarget.word.centerY()))
                compose.waitUntil(5_000) { face()?.focus == focus }
                val original = captureFace("04-native-word-tap-original-face")
                assertEquals(guide.body.width(), original.body.width()); assertEquals(guide.word, original.word)
                val cardAfter = paintedCardWidth(original)
                assertEquals(cardBefore.left, cardAfter.left); assertEquals(cardBefore.right, cardAfter.right)
                // Same actual word is the direct Stop and returns its target face.
                assertTrue(f.device.click(original.word.centerX(), original.word.centerY()))
                compose.waitUntil(10_000) { face()?.focus?.let { it != focus } == true }
                compose.waitUntil(30_000) { f.device.findObjects(By.desc(f.base.getString(R.string.lookup_play_message)).pkg(f.base.packageName)).size == 1 }
                val speakerBounds = audioOwner(f.base.getString(R.string.lookup_play_message), "native-message-play-owner")
                val audio = f.base.getSystemService(android.media.AudioManager::class.java)
                compose.waitUntil(5_000) { !audio.isMusicActive }
                assertFalse("Dedicated emulator must have no preexisting media playback", audio.isMusicActive)
                assertTrue(f.device.click(speakerBounds.centerX(), speakerBounds.centerY()))
                compose.waitUntil(15_000) { audio.isMusicActive &&
                    f.device.findObjects(By.desc(f.base.getString(R.string.ui_cae7d57bc067)).pkg(f.base.packageName)).size == 1 }
                val stopBounds = audioOwner(f.base.getString(R.string.ui_cae7d57bc067), "native-message-stop-owner")
                assertEquals(speakerBounds, stopBounds)
                observations.put(JSONObject().put("phase", "actual-message-audio")
                    .put("native_play_bounds", speakerBounds.toShortString()).put("native_stop_bounds", stopBounds.toShortString())
                    .put("os_media_playback_active_after_native_play", audio.isMusicActive)
                    .put("method", "public AudioManager media stream inactive→active after this native button; exclusive dedicated emulator"))
                f.capture("05-current-48dp-message-audio-stop-target")
                assertTrue("Stop must still be the current action; never replay after natural completion", audio.isMusicActive &&
                    f.device.findObjects(By.desc(f.base.getString(R.string.ui_cae7d57bc067)).pkg(f.base.packageName)).size == 1)
                assertTrue(f.device.click(stopBounds.centerX(), stopBounds.centerY()))
                compose.waitUntil(5_000) { !audio.isMusicActive }
                observations.put(JSONObject().put("phase", "actual-message-audio-stopped")
                    .put("os_media_playback_inactive_after_native_stop", !audio.isMusicActive))
                if (target == "zh") {
                    action(f.base.getString(R.string.access_message_actions))
                    compose.onNodeWithText(f.base.getString(R.string.ui_e52b25aa61b5)).performTouchInput { click() }
                    compose.onNodeWithText(f.base.getString(R.string.ui_127a78a187bd)).performTouchInput { click() }
                    compose.waitUntil(5_000) { face()?.focus?.any { Character.UnicodeScript.of(it.code) == Character.UnicodeScript.HAN } == true }
                    val script = captureFace("06-actual-native-script-in-same-reserved-slot")
                    assertEquals(guide.body.width(), script.body.width()); assertEquals(guide.word.width(), script.word.width())
                    val scriptCard = paintedCardWidth(script)
                    assertEquals(cardBefore.left, scriptCard.left); assertEquals(cardBefore.right, scriptCard.right)
                }
                compose.onNodeWithTag("message-input").performTouchInput { click() }
                compose.onNodeWithTag("message-input").performTextInput("Keep this next message local.")
                f.assertIncomingAboveComposer(compose, text, "07-live-slot-and-next-draft-above-native-ime")
                compose.runOnIdle { assertEquals(1, services.friendPosts.get()); assertEquals("Keep this next message local.", f.model.chat?.compose(services.peer)); services.assertNoPurchase() }
                File(f.output, "receipt.json").writeText(JSONObject().put("actual_main_activity", true)
                    .put("saved_language_choices", "$source-$target").put("density", .25).put("source_only_input", text)
                    .put("no_provider_target_reading_or_models_injected", true).put("real_signal_peer_received_exact_source", services.peerReceived)
                    .put("native_slot_observations", observations).put("automatic_native_face_changes_observed", 3)
                    .put("actual_original_face_in_automatic_cycle", true).put("no_test_clock_or_model_override", true)
                    .put("actual_message_audio_ui_start_stop_same_target", true).put("os_media_stream_observed_start_and_stop", true)
                    .put("controller_audio_input_observer_or_acoustic_pronunciation_claimed", false).put("billing_launches", 0).toString(2))
            } catch (failure: Throwable) {
                File(f.output, "slot-observations-before-failure.json").writeText(observations.toString(2))
                runCatching { f.capture("failure-before-cleanup") }.onFailure { failure.addSuppressed(it) }; throw failure
            } finally { f.stopActivity(); services.close() }
        }
    }
}
