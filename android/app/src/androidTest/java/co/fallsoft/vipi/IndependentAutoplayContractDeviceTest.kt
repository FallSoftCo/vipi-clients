package co.fallsoft.vipi

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshots.Snapshot
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.SpeechSpan
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CopyOnWriteArrayList

/** Independent controller contract tests against production controller/translation
 * classes. Controlled translator/speech prove scheduling ONLY: no local-model,
 * offline, acoustic, gesture or encrypted-account proof is claimed here.
 * Authored under reset/review; platform owner must adopt/compile before execution.
 */
@RunWith(AndroidJUnit4::class)
class IndependentAutoplayContractDeviceTest {
    private class Provider : LanguageTranslation {
        val gates = ConcurrentHashMap<String, CompletableDeferred<Unit>>()
        val calls = CopyOnWriteArrayList<Triple<String, String, String>>()
        override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = Unit
        override suspend fun translate(text: String, source: String, target: String): String {
            calls += Triple(text, source, target)
            gates[text]?.await()
            return "practice($text)"
        }
        override fun close() = Unit
    }
    private class Speech : ConversationSpeech {
        private var observedInterruption by mutableStateOf(0L)
        private var withheldInterruption = 0L
        override var interruption: Long
            get() = observedInterruption + withheldInterruption
            set(value) { observedInterruption = value - withheldInterruption }
        fun interruptWithoutSnapshotNotification() { withheldInterruption++ }
        override var state by mutableStateOf(SpeechState.READY)
        override var error by mutableStateOf<String?>(null)
        override var activeMessage by mutableStateOf<String?>(null)
        val starts = mutableListOf<Pair<String, List<SpeechSpan>>>()
        override fun toggle(message: String, spans: List<SpeechSpan>) {
            check(android.os.Looper.myLooper() == android.os.Looper.getMainLooper()) { "Actual speech API requires main thread" }
            if (activeMessage == message) { stop(); return }
            check(activeMessage == null) { "Controller overlapped the current player" }
            error = null; activeMessage = message; state = SpeechState.PLAYING
            starts += message to spans
            Snapshot.sendApplyNotifications()
        }
        override fun stop() {
            activeMessage = null
            if (state != SpeechState.PREPARING && state != SpeechState.UNAVAILABLE) state = SpeechState.READY
            Snapshot.sendApplyNotifications()
        }
        override fun showMutedVolumeControl() = Unit
        override fun failureMessage() = error ?: "Controlled playback failure"
        fun complete(failure: String? = null) {
            error = failure; activeMessage = null; state = SpeechState.READY
            Snapshot.sendApplyNotifications()
        }
        fun ready() { state = SpeechState.READY; Snapshot.sendApplyNotifications() }
    }
    private class Harness(detector: MessageTranslationLanguage = object : MessageTranslationLanguage {
        override suspend fun identify(text: String): String? = "en"
        override fun close() = Unit
    }) {
        val provider = Provider()
        val speech = Speech()
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        val translation = ConversationTranslation(InstrumentationRegistry.getInstrumentation().targetContext,
            "en", "es", translator = provider, language = detector, reading = { _, _ -> FullMessageReading.notNeeded() })
        var help = 0
        val audio = ConversationAutoplay(translation, speech, scope) { help++ }
        fun ids() = speech.starts.map { it.first }
        fun close() { audio.close(); translation.close(); scope.cancel() }
    }
    private suspend fun onMain(block: () -> Unit) = withContext(Dispatchers.Main.immediate) { block() }
    private suspend fun awaitMain(condition: () -> Boolean) = withTimeout(6_000) {
        while (!withContext(Dispatchers.Main.immediate) { condition() }) delay(10)
    }
    private suspend fun makeHarness(detector: MessageTranslationLanguage? = null) = withContext(Dispatchers.Main.immediate) {
        if (detector == null) Harness() else Harness(detector)
    }

    @Test fun offBaselineAndDuplicateOffersNeverReplay() = runBlocking {
        val h = makeHarness()
        try {
            onMain { h.audio.offer("history", "old"); h.audio.setAutoplayEnabled(true); h.audio.offer("a", "first"); h.audio.offer("a", "first"); h.audio.offer("b", "second") }
            awaitMain { h.ids() == listOf("a") }
            onMain { h.speech.complete() }
            awaitMain { h.ids() == listOf("a", "b") }
            onMain { h.speech.complete() }
            delay(100)
            onMain {
                assertEquals(listOf("a", "b"), h.ids())
                assertEquals(listOf(SpeechSpan("practice(first)", "es")), h.speech.starts[0].second)
                assertEquals(listOf(SpeechSpan("practice(second)", "es")), h.speech.starts[1].second)
            }
        } finally { onMain { h.close() } }
    }

    @Test fun offCancelsPendingVoiceIntentAndLateReadiness() = runBlocking {
        val h = makeHarness()
        try {
            onMain { h.speech.state = SpeechState.PREPARING; h.audio.setAutoplayEnabled(true); h.audio.offer("a", "first") }
            awaitMain { h.provider.calls.isNotEmpty() }
            onMain { h.audio.setAutoplayEnabled(false); h.speech.ready() }
            delay(100)
            onMain { assertFalse(h.audio.enabled); assertTrue(h.ids().isEmpty()) }
        } finally { onMain { h.close() } }
    }

    @Test fun manualTapDuringModeChangeSpeaksTheVisiblePreparedFace() = runBlocking {
        val h = makeHarness()
        try {
            val visible = FullMessageTranslation("Coffee tonight?", "¿Café esta noche?", "Coffee tonight?",
                "en", "es", "en", mode = ImmersionMode.FULL_MESSAGES)
            onMain { h.audio.manual("a", visible.original, visible) }
            awaitMain { h.speech.activeMessage == "a" }
            onMain {
                assertEquals(visible, h.audio.speakingFace)
                assertEquals(listOf(SpeechSpan(visible.practiceText, "es")), h.speech.starts.single().second)
                assertTrue(h.provider.calls.isEmpty())
                h.audio.manual("a", visible.original, visible)
                assertNull(h.speech.activeMessage)
            }
        } finally { onMain { h.close() } }
    }

    @Test fun manualQueuedSelectionConsumesItAndTapStopDisablesAutoplay() = runBlocking {
        val h = makeHarness()
        try {
            onMain { h.audio.setAutoplayEnabled(true); h.audio.offer("a", "first"); h.audio.offer("b", "second"); h.audio.offer("c", "third") }
            awaitMain { h.ids() == listOf("a") }
            onMain { h.audio.manual("b", "second") }
            awaitMain { h.ids() == listOf("a", "b") }
            onMain { h.speech.complete() }
            awaitMain { h.ids() == listOf("a", "b", "c") }
            onMain { h.audio.offer("d", "fourth"); h.audio.manual("c", "third") }
            delay(100)
            onMain { assertFalse(h.audio.enabled); assertNull(h.speech.activeMessage); assertEquals(listOf("a", "b", "c"), h.ids()) }
        } finally { onMain { h.close() } }
    }

    @Test fun staleManualCancellationCannotClearNewRequestOrOverlapQueue() = runBlocking {
        val h = makeHarness(); val release = CompletableDeferred<Unit>(); h.provider.gates["first"] = release
        try {
            onMain { h.audio.setAutoplayEnabled(true); h.audio.manual("a", "first") }
            awaitMain { h.provider.calls.any { it.first == "first" } }
            onMain { h.audio.manual("b", "second"); h.audio.offer("c", "third") }
            awaitMain { h.audio.manualMessage == "b" }
            onMain { assertTrue(h.ids().isEmpty()); assertEquals("b", h.audio.manualMessage) }
            release.complete(Unit)
            awaitMain { h.ids() == listOf("b") }
            onMain { assertEquals(listOf("b"), h.ids()); assertEquals("b", h.audio.manualMessage) }
            onMain { h.speech.complete() }
            awaitMain { h.ids() == listOf("b", "c") }
        } finally { release.complete(Unit); onMain { h.close() } }
    }

    @Test fun synthesisFailureStaysWithItsMessageWhileLaterAudioContinues() = runBlocking {
        val h = makeHarness()
        try {
            onMain { h.audio.setAutoplayEnabled(true); h.audio.offer("a", "first"); h.audio.offer("b", "second") }
            awaitMain { h.ids() == listOf("a") }
            onMain { h.speech.complete("Controlled synthesis failure") }
            awaitMain { h.ids() == listOf("a", "b") }
            onMain { assertEquals("Controlled synthesis failure", h.audio.failures["a"]); h.speech.complete() }
            onMain { h.audio.manual("a", "first") }
            awaitMain { h.ids() == listOf("a", "b", "a") }
            onMain { h.speech.complete() }
            awaitMain { !h.audio.failures.containsKey("a") }
        } finally { onMain { h.close() } }
    }

    @Test fun advisoryDetectorTimeoutStillCallsNativeSourceTranslator() = runBlocking {
        val never = CompletableDeferred<String?>()
        val h = makeHarness(object : MessageTranslationLanguage {
            override suspend fun identify(text: String): String? = never.await()
            override fun close() = Unit
        })
        try {
            val value = withTimeout(6_000) { h.translation.resolve("short", "yep") }
            assertEquals("practice(yep)", value.practiceText)
            assertEquals("yep", value.meaningText)
            assertEquals(listOf(Triple("yep", "en", "es")), h.provider.calls.toList())
        } finally { onMain { h.close() } }
    }
    @Test fun suspendedModelFromUnconfinedConversationStillInvokesSpeechOnMain() = runBlocking {
        val provider = Provider()
        val gate = CompletableDeferred<Unit>()
        provider.gates["late"] = gate
        val scope = CoroutineScope(SupervisorJob() + kotlinx.coroutines.Dispatchers.Unconfined)
        val translation = ConversationTranslation(InstrumentationRegistry.getInstrumentation().targetContext,
            "en", "es", translator = provider, language = object : MessageTranslationLanguage {
                override suspend fun identify(text: String): String? = "en"
                override fun close() = Unit
            }, reading = { _, _ -> FullMessageReading.notNeeded() })
        val speech = Speech()
        val audio = ConversationAutoplay(translation, speech, scope) {}
        try {
            onMain { audio.setAutoplayEnabled(true); audio.offer("async", "late") }
            awaitMain { provider.calls.isNotEmpty() }
            withContext(Dispatchers.Default) { gate.complete(Unit) }
            awaitMain { speech.starts.size == 1 }
            onMain { assertEquals("async", speech.activeMessage); assertFalse(audio.failures.containsKey("async")); speech.complete() }
        } finally { onMain { audio.close(); translation.close(); scope.cancel() } }
    }

    @Test fun tappingPendingAutomaticItemStopsAllBeforeTranslationCompletes() = runBlocking {
        val h = makeHarness(); val release = CompletableDeferred<Unit>(); h.provider.gates["first"] = release
        try {
            onMain { h.audio.setAutoplayEnabled(true); h.audio.offer("a", "first"); h.audio.offer("b", "second") }
            awaitMain { h.provider.calls.any { it.first == "first" } }
            onMain { h.audio.manual("a", "first") }
            release.complete(Unit); delay(100)
            onMain { assertFalse(h.audio.enabled); assertTrue(h.ids().isEmpty()); assertNull(h.audio.manualMessage) }
        } finally { release.complete(Unit); onMain { h.close() } }
    }

    @Test fun missingVoiceCannotLeaveIdleHeaderEnabled() = runBlocking {
        val h = makeHarness()
        try {
            onMain { h.speech.state = SpeechState.UNAVAILABLE; h.speech.error = "Missing voice"; h.audio.setAutoplayEnabled(true) }
            onMain { assertFalse(h.audio.enabled); assertEquals(1, h.help) }
            onMain { h.speech.state = SpeechState.PREPARING; h.audio.setAutoplayEnabled(true) }
            awaitMain { h.audio.enabled }
            onMain { h.speech.state = SpeechState.UNAVAILABLE; androidx.compose.runtime.snapshots.Snapshot.sendApplyNotifications() }
            awaitMain { !h.audio.enabled }
            onMain { assertEquals(2, h.help); assertTrue(h.ids().isEmpty()) }
        } finally { onMain { h.close() } }
    }

    @Test fun osInterruptionClearsQueueAndPendingManualWithoutRestartingNextMessage() = runBlocking {
        val h = makeHarness()
        try {
            onMain { h.audio.setAutoplayEnabled(true); h.audio.offer("a", "first"); h.audio.offer("b", "second") }
            awaitMain { h.ids() == listOf("a") }
            onMain { h.speech.interruption++; h.speech.stop(); Snapshot.sendApplyNotifications() }
            awaitMain { !h.audio.enabled }
            delay(80)
            onMain { assertEquals(listOf("a"), h.ids()); assertNull(h.speech.activeMessage) }
            val gate = CompletableDeferred<Unit>(); h.provider.gates["late"] = gate
            onMain { h.audio.manual("pending", "late") }
            awaitMain { h.provider.calls.any { it.first == "late" } }
            onMain { h.speech.interruption++; h.speech.stop(); Snapshot.sendApplyNotifications() }
            awaitMain { h.audio.manualMessage == null }
            gate.complete(Unit); delay(80)
            onMain { assertEquals(listOf("a"), h.ids()) }
        } finally { onMain { h.close() } }
    }

    @Test fun modelCompletionBeforeInterruptionObserverCannotStartAudio() = runBlocking {
        val h = makeHarness(); val gate = CompletableDeferred<Unit>()
        h.provider.gates["held model"] = gate
        try {
            onMain { h.audio.setAutoplayEnabled(true); h.audio.offer("held", "held model"); h.audio.offer("later", "later message") }
            awaitMain { h.provider.calls.any { it.first == "held model" } }
            // This fake advances the real boundary value without writing any
            // snapshot state. Only the synchronous post-await check can see it.
            onMain { h.speech.interruptWithoutSnapshotNotification(); gate.complete(Unit) }
            awaitMain { !h.audio.enabled }
            onMain { assertTrue(h.ids().isEmpty()); assertNull(h.speech.activeMessage) }
            assertTrue(h.provider.calls.none { it.first == "later message" })
        } finally { gate.complete(Unit); onMain { h.close() } }
    }

}
