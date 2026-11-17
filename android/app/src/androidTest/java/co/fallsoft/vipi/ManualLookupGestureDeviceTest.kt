package co.fallsoft.vipi

import android.content.ClipboardManager
import android.content.Context
import android.graphics.Rect
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.view.inspector.WindowInspector
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import co.fallsoft.vipi.core.ImmersionPresentation
import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference

/** Native pointer/selection qualification. The delayed provider is a lifecycle
 * fixture; this test makes no claim about machine translation quality. */
class ManualLookupGestureDeviceTest {
    @get:Rule val compose = createComposeRule()

    @Test fun nativeWordAndWhitespaceTapOnceStopAndProgrammaticSelectionKeepsCopy() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = instrumentation.targetContext
        check(context.packageName.endsWith(".uxqa"))
        val device = UiDevice.getInstance(instrumentation)
        val output = File(context.filesDir, "manual-gesture-001").apply { mkdirs() }
        val originalText = "The marmot hums."
        val fixture = object : ImmersionPresentation {
            override val original = originalText
            override val translation: String? = null
            override val spans = emptyList<co.fallsoft.vipi.core.ImmersionSpan>()
        }
        val calls = AtomicInteger()
        val touchTrace = java.util.concurrent.CopyOnWriteArrayList<JSONObject>()
        val gate = AtomicReference(CompletableDeferred<String>())
        val provider = object : LanguageTranslation {
            override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) { error("No implicit model download") }
            override suspend fun translate(text: String, source: String, target: String): String {
                assertEquals(originalText, text) // Selected word must retain sentence context.
                calls.incrementAndGet()
                return gate.get().await()
            }
            override fun close() { }
        }
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        lateinit var owner: ConversationImmersion
        lateinit var speech: SpeechPlayback
        lateinit var manual: ManualLookupInteraction
        compose.runOnIdle {
            owner = ConversationImmersion(context, "en", "zh", 0.0, translator = provider, qaModelsReady = true, sourceLookup = null)
            owner.selectInputLanguage("gesture-fixture", "en")
            speech = SpeechPlayback(context, "en", "zh", scope)
            manual = ManualLookupInteraction(owner, speech, "gesture-fixture", originalText, scope)
        }
        fun paragraphs(view: View): List<StableImmersionText> = when (view) {
            is StableImmersionText -> listOf(view)
            is ViewGroup -> (0 until view.childCount).flatMap { paragraphs(view.getChildAt(it)) }
            else -> emptyList()
        }
        fun native(): StableImmersionText = WindowInspector.getGlobalWindowViews().flatMap(::paragraphs).first()
        fun range(start: Int, end: Int): Rect {
            lateinit var result: Rect
            compose.runOnIdle { result = native().sourceRangeRect(start, end) }
            return result
        }
        try {
            compose.setContent { VipiTheme(Appearance.LIGHT) {
                Column(Modifier.fillMaxSize().safeDrawingPadding().padding(18.dp)) {
                    ImmersionBubble(fixture, ReadingMode.IMMERSED, speech, "en", "zh", "gesture-fixture",
                        embedded = true, metadata = { Text("12:52 PM · Waiting to send") }, manual = manual)
                }
            } }
            compose.waitForIdle()
            compose.runOnIdle {
                val view = native()
                var wrappedWhitespace: ((StableImmersionText) -> Unit)? = null
                var wrappedWord: ((Int, Int, StableImmersionText) -> Unit)? = null
                fun trace(event: String) {
                    touchTrace += JSONObject().put("event", event).put("uptime", SystemClock.uptimeMillis())
                        .put("selectionStart", view.selectionStart).put("selectionEnd", view.selectionEnd)
                        .put("providerCalls", calls.get()).put("requestStart", manual.request?.startUTF16 ?: -1)
                        .put("requestEnd", manual.request?.endUTF16 ?: -1).put("generation", manual.request?.generation ?: -1)
                        .put("status", manual.outcome?.status?.name ?: "pending_or_cancelled").put("visible", manual.visible)
                }
                view.setOnTouchListener { _, event ->
                    trace("before_" + android.view.MotionEvent.actionToString(event.actionMasked))
                    if (event.actionMasked == android.view.MotionEvent.ACTION_UP) {
                        if (view.onWhitespace !== wrappedWhitespace) {
                            val original = view.onWhitespace
                            wrappedWhitespace = { target -> trace("callback_whitespace"); original?.invoke(target); trace("callback_whitespace_done") }
                            view.onWhitespace = wrappedWhitespace
                        }
                        if (view.onPlainWord !== wrappedWord) {
                            val original = view.onPlainWord
                            wrappedWord = { start, end, target -> trace("callback_word_$start:$end"); original?.invoke(start, end, target); trace("callback_word_done") }
                            view.onPlainWord = wrappedWord
                        }
                    }
                    view.post { trace("after_" + android.view.MotionEvent.actionToString(event.actionMasked)) }
                    false
                }
            }
            device.takeScreenshot(File(output, "minimal-footer.png"))
            val word = range(4, 10)
            assertTrue(device.click(word.centerX(), word.centerY()))
            compose.waitUntil(15_000) { calls.get() == 1 && manual.loading }
            compose.runOnIdle {
                assertEquals(4, manual.request?.startUTF16)
                assertEquals(10, manual.request?.endUTF16)
                assertEquals(1L, manual.request?.generation) // No parent/child duplicate tap.
            }
            device.takeScreenshot(File(output, "word-loading.png"))
            assertTrue(device.click(word.centerX(), word.centerY()))
            compose.waitUntil(3_000) { manual.request == null && !manual.visible }
            gate.get().complete("旱獭在哼唱。")
            SystemClock.sleep(300)
            compose.runOnIdle { assertNull(speech.activeMessage); assertNull(manual.outcome); assertNull(manual.request); assertEquals(1, calls.get()) }

            gate.set(CompletableDeferred())
            var whitespaceX = 0; var whitespaceY = 0
            compose.runOnIdle {
                val view = native(); val location = IntArray(2); view.getLocationOnScreen(location)
                whitespaceX = location[0] + view.width - 4; whitespaceY = location[1] + view.height / 2
            }
            assertTrue(device.click(whitespaceX, whitespaceY))
            compose.waitUntil(15_000) { calls.get() == 2 && manual.loading }
            compose.runOnIdle { assertEquals(0, manual.request?.startUTF16); assertEquals(originalText.length, manual.request?.endUTF16) }
            assertTrue(device.click(whitespaceX, whitespaceY))
            compose.waitUntil(3_000) { manual.request == null && !manual.visible }
            gate.get().complete("旱獭在哼唱。")

            gate.set(CompletableDeferred())
            assertTrue(device.click(word.centerX(), word.centerY()))
            compose.waitUntil(3_000) { manual.request != null }
            compose.runOnIdle { native().selectTextFromMenu() }
            compose.waitUntil(3_000) { manual.request == null && !manual.visible }
            SystemClock.sleep(500)
            compose.runOnIdle { assertNull(manual.request); assertNull(speech.activeMessage) }
            val copy = device.wait(Until.findObject(By.text(context.getString(android.R.string.copy))), 5_000)
            checkNotNull(copy) { "Native Copy action unavailable" }.click()
            compose.runOnIdle {
                assertEquals(originalText, context.getSystemService(ClipboardManager::class.java).primaryClip?.getItemAt(0)?.text?.toString())
                assertNull(manual.request); assertNull(speech.activeMessage)
            }
            device.takeScreenshot(File(output, "copy-dismissed.png"))
            File(output, "report.json").writeText(JSONObject().put("status", "passed")
                .put("provider", "delayed_lifecycle_fixture_not_translation_quality")
                .put("word_source_utf16", "4:10").put("whole_source_utf16", "0:${originalText.length}")
                .put("checks", "one_native_word_tap_once;word_tap_again_stop;whitespace_full_context_once;same_surface_stop;programmatic_select_cancels_without_audio;native_copy_exact_source")
                .put("providerCalls", calls.get()).toString(2))
        } finally {
            val endState = JSONObject().put("providerCalls", calls.get())
            compose.runOnIdle {
                val view = native()
                endState.put("requestStart", manual.request?.startUTF16 ?: -1).put("requestEnd", manual.request?.endUTF16 ?: -1)
                    .put("status", manual.outcome?.status?.name ?: "pending_or_cancelled").put("visible", manual.visible)
                    .put("loading", manual.loading).put("nativeSelectionStart", view.selectionStart).put("nativeSelectionEnd", view.selectionEnd)
                    .put("nativeHasSelection", view.hasSelection()).put("nativeWidth", view.width).put("nativeHeight", view.height)
                    .put("displayedOriginal", view.displayedOriginal)
            }
            File(output, "end-state.json").writeText(endState.toString(2))
            File(output, "touch-trace.json").writeText(org.json.JSONArray(touchTrace).toString(2))
            device.takeScreenshot(File(output, "end-state.png"))
            gate.get().complete("旱獭在哼唱。")
            compose.runOnIdle { manual.cancel(); owner.close(); speech.close() }
            scope.cancel()
        }
    }
    @Test fun reverseReferenceUsesWholeRawSourceAndOriginalModeShowsForeignText() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = instrumentation.targetContext
        check(context.packageName.endsWith(".uxqa"))
        val raw = "Estoy leyendo un libro ahora."
        val id = "reverse-gesture-fixture"
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        lateinit var owner: ConversationImmersion
        lateinit var speech: SpeechPlayback
        lateinit var manual: ManualLookupInteraction
        lateinit var presentation: ImmersionPresentation
        val mode = mutableStateOf(ReadingMode.IMMERSED)
        val receivedInputs = java.util.concurrent.CopyOnWriteArrayList<Pair<String, List<co.fallsoft.vipi.core.SpeechSpan>>>()
        compose.runOnIdle {
            owner = ConversationImmersion(context, "en", "es", .5, sourceLookup = null)
            speech = SpeechPlayback(context, "en", "es", scope)
            speech.qualificationInput = { message, spans -> receivedInputs += message to spans.toList() }
            speech.prepare(mapOf("en" to "Hello.", "es" to "Hola."))
            manual = ManualLookupInteraction(owner, speech, id, raw, scope)
        }
        compose.waitUntil(30_000) { speech.state != SpeechState.PREPARING }
        assertEquals(speech.error.orEmpty(), SpeechState.READY, speech.state)
        presentation = runBlocking(Dispatchers.Default) { requireNotNull(owner.presentation(raw, messageID = id)) }
        assertEquals("I am reading a book now.", presentation.original)
        assertEquals("es", owner.resolvedInputLanguage(raw, id))
        assertNull(owner.resolvedInputLanguage(raw + " ", id))
        assertNull(owner.resolvedInputLanguage(raw, "another-message"))
        fun paragraphs(view: View): List<StableImmersionText> = when (view) {
            is StableImmersionText -> listOf(view)
            is ViewGroup -> (0 until view.childCount).flatMap { paragraphs(view.getChildAt(it)) }
            else -> emptyList()
        }
        fun native(): StableImmersionText = WindowInspector.getGlobalWindowViews().flatMap(::paragraphs).first()
        try {
            compose.setContent { VipiTheme(Appearance.LIGHT) {
                Column(Modifier.fillMaxSize().safeDrawingPadding().padding(18.dp)) {
                    ImmersionBubble(presentation, mode.value, speech, "en", "es", id, embedded = true,
                        originalMessage = raw, rawSourceLanguage = owner.resolvedInputLanguage(raw, id),
                        onModeChange = { mode.value = it }, metadata = { Text("12:52 PM") }, manual = manual)
                }
            } }
            lateinit var book: Rect
            compose.runOnIdle { val start = presentation.original.indexOf("reading"); assertTrue(presentation.spans.none { it.start < start + 7 && it.end > start }); book = native().sourceRangeRect(start, start + 7) }
            val device = UiDevice.getInstance(instrumentation)
            assertTrue(device.click(book.centerX(), book.centerY()))
            compose.waitUntil(15_000) { manual.outcome?.status == ManualTranslationStatus.READY }
            compose.waitUntil(15_000) { receivedInputs.any { it.first.startsWith("manual-") } }
            compose.runOnIdle {
                val input = receivedInputs.last { it.first.startsWith("manual-") }.second.single()
                assertEquals(raw, input.text); assertEquals("es", input.language)
                val request = requireNotNull(manual.request)
                assertEquals(raw, request.originalText)
                assertEquals(0, request.startUTF16); assertEquals(raw.length, request.endUTF16)
                assertEquals(raw, manual.outcome?.result?.sourceContextText)
                assertEquals("I am reading a book now.", manual.outcome?.result?.targetText)
                assertEquals(raw, manual.pronunciationText); assertEquals("es", manual.pronunciationLanguage)
                manual.cancel(); mode.value = ReadingMode.ORIGINAL
            }
            compose.waitForIdle()
            compose.runOnIdle { assertEquals(raw, native().displayedOriginal); assertEquals(raw, native().visibleText()) }
            val output = File(context.filesDir, "manual-gesture-001").apply { mkdirs() }
            device.takeScreenshot(File(output, "reverse-original-raw.png"))
            File(output, "reverse-report.json").writeText(JSONObject().put("status", "passed")
                .put("provider", "actual_bundled_reverse_reference_no_injected_translator")
                .put("sourceSelection", "mismatched_display_word_expands_to_whole_raw_source")
                .put("rawSourceLanguage", owner.resolvedInputLanguage(raw, id))
                .put("actualSpeechInputLanguage", "es")
                .put("actualSpeechInputSha256", java.security.MessageDigest.getInstance("SHA-256").digest(raw.toByteArray()).joinToString("") { "%02x".format(it) }).toString(2))
        } finally {
            compose.runOnIdle { manual.cancel(); owner.close(); speech.close() }
            assertNull(owner.resolvedInputLanguage(raw, id)); scope.cancel()
        }
    }

}
