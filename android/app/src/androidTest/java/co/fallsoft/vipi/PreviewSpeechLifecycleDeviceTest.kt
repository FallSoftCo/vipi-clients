package co.fallsoft.vipi

import android.graphics.Rect
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.view.inspector.WindowInspector
import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import co.fallsoft.vipi.core.SpeechSpan
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.util.concurrent.CopyOnWriteArrayList

/** Real host lifecycle, production preview renderer and native local player.
 * Rendering mode/removal are parent inputs; word activation is a native touch. */
class PreviewSpeechLifecycleDeviceTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()
    private enum class Boundary { BACKGROUND, MODE, DISPOSE }
    @Test fun pendingWordCannotStartAfterBackgroundAndResume() = stopped(Boundary.BACKGROUND, false)
    @Test fun activeWordStopsOnBackgroundAndDoesNotResume() = stopped(Boundary.BACKGROUND, true)
    @Test fun pendingWordCannotStartAfterReadingModeChange() = stopped(Boundary.MODE, false)
    @Test fun activeWordStopsWhenReadingModeChanges() = stopped(Boundary.MODE, true)
    @Test fun pendingWordCannotStartAfterBubbleRemoval() = stopped(Boundary.DISPOSE, false)
    @Test fun activeWordStopsWhenItsBubbleIsRemoved() = stopped(Boundary.DISPOSE, true)

    private fun stopped(boundary: Boundary, ready: Boolean) {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        lateinit var speech: SpeechPlayback
        val accepted = CopyOnWriteArrayList<String>()
        val shown = mutableStateOf(true)
        val mode = mutableStateOf(ReadingMode.IMMERSED)
        val result = ConversationExamples.result(context, "en", "ar")
        val word = result.spans.maxBy { it.translated.length }
        compose.runOnIdle {
            speech = SpeechPlayback(context, "en", "ar", scope)
            speech.qualificationInput = { id, _ -> accepted += id }
            if (ready) speech.prepare(mapOf("en" to result.original, "ar" to result.translation))
        }
        compose.setContent { if (shown.value) VipiTheme(Appearance.LIGHT) {
            Column(Modifier.fillMaxSize().safeDrawingPadding().padding(18.dp)) {
                ImmersionBubble(result, mode.value, speech, "en", "ar", "preview-lifecycle", onModeChange = { mode.value = it })
            }
        } }
        try {
            if (ready) {
                compose.waitUntil(30_000) { speech.state != SpeechState.PREPARING }
                compose.runOnIdle { assertEquals(speech.error.orEmpty(), SpeechState.READY, speech.state) }
            }
            lateinit var bounds: Rect
            compose.runOnIdle { bounds = paragraph(result.original).sourceRangeRect(word.start, word.end) }
            assertTrue(UiDevice.getInstance(InstrumentationRegistry.getInstrumentation()).click(bounds.centerX(), bounds.centerY()))
            if (ready) {
                compose.waitUntil(15_000) { speech.state == SpeechState.PLAYING || speech.error != null }
                assertEquals(SpeechState.PLAYING, speech.state)
            } else compose.waitForIdle()
            when (boundary) {
                Boundary.BACKGROUND -> compose.activityRule.scenario.moveToState(Lifecycle.State.CREATED)
                Boundary.MODE -> compose.runOnIdle { mode.value = ReadingMode.ORIGINAL }
                Boundary.DISPOSE -> compose.runOnIdle { shown.value = false }
            }
            if (boundary == Boundary.BACKGROUND) {
                // Inspect before RESUME: a resumed composition must not mask a missed stop.
                InstrumentationRegistry.getInstrumentation().runOnMainSync { assertNull("Owned word must stop on ON_STOP", speech.activeMessage) }
                compose.activityRule.scenario.moveToState(Lifecycle.State.RESUMED)
            }
            compose.waitForIdle()
            compose.runOnIdle {
                assertNull("Boundary must stop this bubble's word", speech.activeMessage)
                if (!ready) speech.prepare(mapOf("en" to result.original, "ar" to result.translation))
            }
            compose.waitUntil(30_000) { speech.state != SpeechState.PREPARING }
            SystemClock.sleep(300)
            compose.runOnIdle {
                assertEquals(speech.error.orEmpty(), SpeechState.READY, speech.state)
                assertNull(speech.activeMessage)
                assertEquals("No delayed playback can cross a reading/lifecycle boundary", if (ready) 1 else 0, accepted.size)
            }
        } finally {
            compose.activityRule.scenario.moveToState(Lifecycle.State.RESUMED)
            compose.runOnIdle { shown.value = false }; compose.waitForIdle()
            compose.runOnIdle { speech.close() }; scope.cancel()
        }
    }

    @Test fun modeChangeAndRemovalPreserveOtherBubbleAudioWithSimilarMessageID() {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        lateinit var speech: SpeechPlayback
        val shown = mutableStateOf(true); val mode = mutableStateOf(ReadingMode.IMMERSED)
        val result = ConversationExamples.result(context, "en", "es")
        val other = "word-preview-lifecycle-99-1" // Prefix overlap is not ownership.
        compose.runOnIdle { speech = SpeechPlayback(context, "en", "es", scope); speech.prepare(mapOf("en" to result.original, "es" to result.translation)) }
        compose.setContent { if (shown.value) VipiTheme(Appearance.LIGHT) {
            ImmersionBubble(result, mode.value, speech, "en", "es", "preview-lifecycle", onModeChange = { mode.value = it })
        } }
        try {
            compose.waitUntil(30_000) { speech.state != SpeechState.PREPARING }
            compose.runOnIdle {
                assertEquals(speech.error.orEmpty(), SpeechState.READY, speech.state)
                speech.toggle(other, listOf(SpeechSpan("Another message keeps speaking while this different bubble changes its reading. ".repeat(5), "en")))
            }
            compose.waitUntil(15_000) { speech.state == SpeechState.PLAYING }
            compose.runOnIdle { mode.value = ReadingMode.ORIGINAL }; compose.waitForIdle()
            compose.runOnIdle { assertEquals(other, speech.activeMessage); shown.value = false }
            compose.waitForIdle()
            compose.runOnIdle { assertEquals(other, speech.activeMessage); assertEquals(SpeechState.PLAYING, speech.state) }
        } finally {
            compose.runOnIdle { shown.value = false }; compose.waitForIdle()
            compose.runOnIdle { speech.close() }; scope.cancel()
        }
    }

    @Test fun wholeAndTranslationPlaybackStopWhenTheirBubbleChangesMode() {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        lateinit var speech: SpeechPlayback
        val shown = mutableStateOf(true); val mode = mutableStateOf(ReadingMode.IMMERSED)
        val result = ConversationExamples.result(context, "en", "es")
        compose.runOnIdle { speech = SpeechPlayback(context, "en", "es", scope); speech.prepare(mapOf("en" to result.original, "es" to result.translation)) }
        compose.setContent { if (shown.value) VipiTheme(Appearance.LIGHT) {
            ImmersionBubble(result, mode.value, speech, "en", "es", "owned-reading", onModeChange = { mode.value = it })
        } }
        try {
            compose.waitUntil(30_000) { speech.state != SpeechState.PREPARING }
            compose.runOnIdle { assertEquals(speech.error.orEmpty(), SpeechState.READY, speech.state) }
            for (id in listOf("owned-reading", "translation-owned-reading")) {
                compose.runOnIdle { mode.value = ReadingMode.IMMERSED }; compose.waitForIdle()
                compose.runOnIdle { speech.toggle(id, listOf(SpeechSpan(if (id.startsWith("translation-")) result.translation else result.original, if (id.startsWith("translation-")) "es" else "en"))) }
                compose.waitUntil(15_000) { speech.state == SpeechState.PLAYING }
                compose.runOnIdle { mode.value = ReadingMode.ORIGINAL }; compose.waitForIdle()
                compose.runOnIdle { assertNull("Changing the owned reading must stop $id", speech.activeMessage) }
            }
        } finally {
            compose.runOnIdle { shown.value = false }; compose.waitForIdle()
            compose.runOnIdle { speech.close() }; scope.cancel()
        }
    }

    private fun paragraph(original: String): StableImmersionText {
        fun collect(view: View): List<StableImmersionText> = when (view) {
            is StableImmersionText -> listOf(view)
            is ViewGroup -> (0 until view.childCount).flatMap { collect(view.getChildAt(it)) }
            else -> emptyList()
        }
        return WindowInspector.getGlobalWindowViews().flatMap(::collect).single { it.isShown && it.displayedOriginal == original }
    }
}
