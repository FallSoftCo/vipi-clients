package co.fallsoft.vipi

import android.text.Spanned
import android.text.style.ForegroundColorSpan
import android.view.View
import android.view.ViewGroup
import androidx.compose.foundation.layout.Column
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import co.fallsoft.vipi.core.SpeechSpan
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.Channel
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

class SpokenWordDeviceTest {
    @get:Rule val compose = createComposeRule()
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrumentation.targetContext

    @Test fun spokenPracticeRunsContainExactDisjointSilenceAndPreserveAdjacentProsody() = runBlocking {
        val original = "red blue behind red"
        val words = listOf(WordReplacement(0, 3, "red", "rojo"), WordReplacement(4, 4, "blue", "azul"),
            WordReplacement(16, 3, "red", "rojo"))
        val mixed = FullMessageTranslation(original, WordReplacement.compose(original, words, false), original,
            "en", "es", "en", words = words)
        val parts = MessageSpeech.pieces(mixed)
        assertEquals(listOf(SpeechPiece("rojo azul", 0), SpeechPiece("rojo", 17, true)), parts)
        val pair = withContext(Dispatchers.Main) { LocalSpeechPair(context, "es", "es") }
        try {
            pair.prepare(mapOf("es" to "Hola"))
            val timed = TimedSpeech(pair, "es", SpeechProjection.build(context, mixed))
            val output = Channel<TimedPcm>(Channel.UNLIMITED)
            for (part in parts) timed.enqueue(part, output)
            output.close()
            val packets = mutableListOf<TimedPcm>()
            for (packet in output) packets += packet
            val gap = packets.single { packet -> packet.wave.samples.all { it.toInt() == 0 } }
            assertEquals(160.0, gap.wave.durationMs, 0.01)
            assertTrue(gap.cues.isEmpty())
            assertEquals(listOf(0..3, 5..8, 17..20), packets.flatMap { it.cues }.map { it.word!!.script })
            val timeline = PlaybackWords()
            var count = 0L
            for (packet in packets) {
                timeline.append(packet)
                if (packet === gap) assertNull(timeline.at(count))
                count += packet.wave.samples.size / 2
            }
            assertNull(timeline.at(count))
            val fixture = "habari yako rafiki"
            val file = java.io.File.createTempFile("sw-word-", ".wav", context.cacheDir)
            try {
                val actual = SwahiliSpeech.render(context, fixture, file, SwahiliSpeech.Job(), "sw")
                assertEquals(listOf("habari", "yako", "rafiki"), actual.marks.map { fixture.substring(it.start, it.end) })
                assertTrue(actual.marks.zipWithNext().all { (a, b) -> a.frame < b.frame })
            } finally { file.delete() }
        } finally { withContext(Dispatchers.Main) { pair.close() } }
    }

    @Test fun tappingFullMessageHighlightsTheAudibleWordsInPinyinAndScriptAndClearsOnStop(): Unit = runBlocking {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        val original = "Where are we meeting tomorrow?"
        val mandarin = "明天我们在哪里见面？"
        val model = object : LanguageTranslation {
            override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = Unit
            override suspend fun translate(text: String, source: String, target: String) = if (text == original) mandarin else error("Unexpected input")
            override fun close() = Unit
        }
        val translation = ConversationTranslation(context, "en", "zh", translator = model,
            language = object : MessageTranslationLanguage {
                override suspend fun identify(text: String) = "en"
                override fun close() = Unit
            }, mode = ImmersionMode.FULL_MESSAGES)
        val speech = withContext(Dispatchers.Main) { SpeechPlayback(context, "zh", scope).also { it.prepare(mapOf("zh" to "好")) } }
        val audio = withContext(Dispatchers.Main) { ConversationAutoplay(translation, speech, scope) {} }
        val gestures = FullMessageGestures()
        try {
            compose.setContent { Column(Modifier.testTag("chat").fullMessageGestures(gestures)) {
                FullMessageBubble(original, "sample", translation, gestures, audio) {}
            } }
            val snapshot = translation.resolve("sample", original)
            assertEquals(mandarin, snapshot.practiceText)
            val reading = requireNotNull(snapshot.practiceReading)
            withTimeout(90_000) { while (speech.state == SpeechState.PREPARING) delay(10) }
            assertEquals(SpeechState.READY, speech.state)
            fun paragraph(): FullMessageTextView {
                fun find(v: View): FullMessageTextView? {
                    if (v is FullMessageTextView && v.originalMessage == original) return v
                    if (v is ViewGroup) for (i in 0 until v.childCount) find(v.getChildAt(i))?.let { return it }
                    return null
                }
                return ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED)
                    .firstNotNullOf { find(it.window.decorView) }
            }
            compose.waitForIdle()
            for (native in listOf(false, true)) {
                val expected = if (native) mandarin else reading
                if (native) compose.runOnIdle {
                    assertTrue("The visible Mandarin bubble must offer its script", gestures.canSwitchScript)
                    gestures.toggleScript()
                    assertTrue(gestures.nativeScript)
                }
                compose.waitForIdle()
                compose.runOnIdle { assertEquals("Visible face before playback", expected, paragraph().text.toString()) }
                withContext(Dispatchers.Main) { assertTrue(paragraph().performAccessibilityAction(
                    android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK, null)) }
                val seen = linkedSetOf<IntRange>()
                withTimeout(30_000) {
                    while (seen.size < 2) {
                        withContext(Dispatchers.Main) {
                            val view = paragraph()
                            val styled = view.text as Spanned
                            val highlight = styled.getSpans(0, styled.length, ForegroundColorSpan::class.java).singleOrNull()
                            if (highlight != null) {
                                val visible = styled.getSpanStart(highlight) until styled.getSpanEnd(highlight)
                                assertEquals(expected, styled.toString())
                                assertEquals(view.highlightedWord, visible)
                                assertTrue(styled.substring(visible).isNotBlank())
                                seen.add(visible)
                            }
                        }
                        delay(12)
                    }
                }
                withContext(Dispatchers.Main) { audio.manual("sample", original) }
                compose.waitForIdle()
                withContext(Dispatchers.Main) { assertNull(paragraph().highlightedWord); assertNull(speech.activeMessage) }
            }
        } finally { withContext(Dispatchers.Main) { audio.close(); translation.close(); speech.close(); scope.cancel() } }
    }
}
