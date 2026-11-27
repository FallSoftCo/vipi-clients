package co.fallsoft.vipi

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.SpeechSpan
import java.security.KeyStore
import java.util.UUID
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test

/**
 * Deterministic lifecycle/error regressions. These boundaries do NOT prove ML Kit quality or
 * acoustic output; the real-provider suite covers those.
 */
class FullMessageOwnershipDeviceTest {
    private val context
        get() = InstrumentationRegistry.getInstrumentation().targetContext

    private class Model : LanguageTranslation {
        val calls = CopyOnWriteArrayList<String>()
        var failure = false
        var gate: CompletableDeferred<Unit>? = null

        override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) =
            Unit

        override suspend fun translate(text: String, source: String, target: String): String {
            calls += "$source->$target:$text"
            gate?.await()
            if (failure) error("Injected local model failure")
            return "$target:$text"
        }

        override fun close() = Unit
    }

    private fun language(code: String?) =
        object : MessageTranslationLanguage {
            override suspend fun identify(text: String) = code

            override fun close() = Unit
        }

    private fun owner(
        model: Model,
        language: MessageTranslationLanguage = language("en"),
        store: FullMessageTranslationStore? = null,
    ) =
        ConversationTranslation(
            context,
            "en",
            "es",
            store,
            model,
            language,
            reading = { _, _ -> FullMessageReading.notNeeded() },
            mode = ImmersionMode.FULL_MESSAGES,
        )

    private suspend fun until(predicate: () -> Boolean) =
        withTimeout(8_000) {
            while (
                !withContext(Dispatchers.Main.immediate) {
                    androidx.compose.runtime.snapshots.Snapshot.sendApplyNotifications()
                    predicate()
                }
            ) delay(10)
        }

    @Test
    fun stalledAdvisoryIdentificationFallsBackAndParentCloseStillCancels(): Unit = runBlocking {
        val stalled =
            object : MessageTranslationLanguage {
                override suspend fun identify(text: String): String? {
                    awaitCancellation()
                }

                override fun close() = Unit
            }
        val model = Model()
        owner(model, stalled).use { translation ->
            val value =
                withTimeout(5_000) {
                    translation.resolve("unseen", "An unseen sentence, not a catalog key.")
                }
            assertEquals("en", value.inputLanguage)
            assertEquals(listOf("en->es:An unseen sentence, not a catalog key."), model.calls)
        }
        val cancelled = owner(Model(), stalled)
        val pending = async { cancelled.resolve("closed", "Never finish identification") }
        cancelled.close()
        try {
            pending.await()
            fail("Closed owner must cancel")
        } catch (_: CancellationException) {}
    }

    @Test
    fun everyMessageUsesFullModelSingleFlightAndExactEncryptedCacheHeals(): Unit = runBlocking {
        val account = UUID.randomUUID()
        val vault = MessageVault(context, account)
        try {
            val store = FullMessageTranslationStore(vault)
            val model = Model()
            val text = "OK, José: https://example.test/9 ☕."
            val key = FullMessageTranslation.key("same", text, "en", "es")
            vault.transaction {
                vault.put("full-message-translation", key, "not JSON".toByteArray())
            }
            owner(model, store = store).use { translation ->
                val values = coroutineScope {
                    List(8) { async { translation.resolve("same", text) } }.awaitAll()
                }
                assertEquals(1, model.calls.size)
                assertEquals(1, values.distinct().size)
                assertEquals(text, values.first().original)
                assertEquals("es:$text", store.read(key)?.practiceText)
            }
            val neverCalled = Model().also { it.failure = true }
            owner(neverCalled, store = store).use { restored ->
                assertEquals("es:$text", restored.resolve("same", text).practiceText)
                assertTrue(neverCalled.calls.isEmpty())
            }
            owner(model).use { translation ->
                for (sample in
                    listOf(
                        "Yes.",
                        "I am reading a book now.",
                        "Tomorrow, a totally unfamiliar message.",
                    )) assertEquals(
                    "es:$sample",
                    translation.resolve(UUID.randomUUID().toString(), sample).practiceText,
                )
                assertEquals(4, model.calls.size)
            }
        } finally {
            vault.close()
            vault.file.parentFile!!.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply {
                load(null)
                deleteEntry("co.fallsoft.vipi.messages.$account")
            }
        }
    }

    @Test
    fun detectedPracticeAndThirdLanguageHaveRealReverseMeaningAndRetry(): Unit = runBlocking {
        val model = Model()
        owner(model, language("es")).use { translation ->
            val value = translation.resolve("practice", "Hola.")
            assertEquals("Hola.", value.practiceText)
            assertEquals("en:Hola.", value.meaningText)
            assertEquals(listOf("es->en:Hola."), model.calls)
        }
        model.calls.clear()
        owner(model, language("fr")).use { translation ->
            model.failure = true
            try {
                translation.resolve("third", "Bonjour.")
                fail("Provider failure must not be READY")
            } catch (_: IllegalStateException) {}
            assertEquals(
                MessageTranslationPhase.FAILED,
                translation.state("third", "Bonjour.")?.phase,
            )
            model.failure = false
            val value = translation.resolve("third", "Bonjour.", retry = true)
            assertEquals("es:Bonjour.", value.practiceText)
            assertEquals("en:Bonjour.", value.meaningText)
            assertEquals("fr", value.inputLanguage)
            assertEquals(3, model.calls.size)
        }
    }

    private class Speech : ConversationSpeech {
        override var interruption by mutableStateOf(0L)
        override var state by mutableStateOf(SpeechState.READY)
        override var error by mutableStateOf<String?>(null)
        override var activeMessage by mutableStateOf<String?>(null)
        val started = mutableListOf<Pair<String, List<SpeechSpan>>>()
        var fail = false

        override fun showMutedVolumeControl() = Unit

        override fun failureMessage() = error ?: "Controlled playback failure"

        override fun toggle(message: String, spans: List<SpeechSpan>) {
            started += message to spans
            if (fail) {
                error = "Injected synthesis failure"
                activeMessage = null
                state = SpeechState.READY
            } else {
                error = null
                activeMessage = message
                state = SpeechState.PLAYING
            }
        }

        override fun stop() {
            activeMessage = null
            if (state != SpeechState.UNAVAILABLE) state = SpeechState.READY
        }

        fun complete() = stop()
    }

    @Test
    fun durableEventsPlayFifoOnceAndManualStopDisablesMode(): Unit = runBlocking {
        val model = Model()
        owner(model).use { translation ->
            val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
            val speech = Speech()
            val audio =
                withContext(Dispatchers.Main) {
                    ConversationAutoplay(translation, speech, scope) {
                        fail("Unexpected voice help")
                    }
                }
            try {
                withContext(Dispatchers.Main) {
                    audio.offer("history", "Old transcript")
                    audio.setAutoplayEnabled(true)
                    audio.offer("a", "First")
                    audio.offer("a", "Duplicate acknowledgement")
                    audio.offer("b", "Second")
                }
                until { speech.started.size == 1 }
                assertEquals("a", speech.started[0].first)
                assertEquals(listOf(SpeechSpan("es:First", "es")), speech.started[0].second)
                withContext(Dispatchers.Main) { speech.complete() }
                until { speech.started.size == 2 }
                assertEquals("b", speech.started[1].first)
                withContext(Dispatchers.Main) { audio.manual("b", "Second") }
                assertFalse(audio.enabled)
                assertNull(speech.activeMessage)
                withContext(Dispatchers.Main) { audio.offer("c", "Disabled") }
                delay(80)
                assertEquals(2, speech.started.size)
            } finally {
                withContext(Dispatchers.Main) { audio.close() }
                scope.cancel()
            }
        }
    }

    @Test
    fun missingVoiceTurnsOffAndRenderFailureSurvivesLaterRowsUntilManualRetry(): Unit =
        runBlocking {
            owner(Model()).use { translation ->
                val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
                val speech = Speech()
                val help = AtomicInteger()
                val audio =
                    withContext(Dispatchers.Main) {
                        ConversationAutoplay(translation, speech, scope) { help.incrementAndGet() }
                    }
                try {
                    withContext(Dispatchers.Main) {
                        speech.state = SpeechState.UNAVAILABLE
                        speech.error = "Voice not installed"
                        audio.setAutoplayEnabled(true)
                        audio.offer("missing", "One")
                        audio.offer("not-spoken", "Two")
                    }
                    until { help.get() == 1 }
                    assertFalse(audio.enabled)
                    assertTrue(speech.started.isEmpty())
                    assertFalse(audio.failures.containsKey("missing"))
                    withContext(Dispatchers.Main) {
                        speech.state = SpeechState.READY
                        speech.fail = true
                        audio.setAutoplayEnabled(true)
                        audio.offer("bad", "Three")
                    }
                    until { audio.failures.containsKey("bad") }
                    withContext(Dispatchers.Main) {
                        speech.fail = false
                        audio.offer("good", "Four")
                    }
                    until { speech.activeMessage == "good" }
                    assertEquals("Injected synthesis failure", audio.failures["bad"])
                    withContext(Dispatchers.Main) {
                        speech.complete()
                        audio.manual("bad", "Three")
                    }
                    until { speech.activeMessage == "bad" }
                    withContext(Dispatchers.Main) { speech.complete() }
                    until { !audio.failures.containsKey("bad") }
                    assertEquals(listOf("bad", "good", "bad"), speech.started.map { it.first })
                } finally {
                    withContext(Dispatchers.Main) { audio.close() }
                    scope.cancel()
                }
            }
        }

    @Test
    fun offAndBackgroundCancelPendingManualAndLateTranslationCannotSpeak(): Unit = runBlocking {
        val model = Model().also { it.gate = CompletableDeferred() }
        owner(model).use { translation ->
            val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
            val speech = Speech()
            val audio =
                withContext(Dispatchers.Main) {
                    ConversationAutoplay(translation, speech, scope) {}
                }
            try {
                withContext(Dispatchers.Main) {
                    audio.setAutoplayEnabled(true)
                    audio.manual("early", "Not admitted")
                    audio.setAutoplayEnabled(false)
                }
                // Account-owned translation may already have been admitted;
                // OFF cancels the audio intent, not the message translation.
                model.gate!!.complete(Unit)
                until { translation.activeTaskCount == 0 }
                delay(80)
                assertTrue("Immediate OFF must not produce late speech", speech.started.isEmpty())
                assertFalse(audio.enabled)
                model.gate = CompletableDeferred()
                withContext(Dispatchers.Main) {
                    audio.setAutoplayEnabled(true)
                    audio.manual("a", "Delayed")
                }
                until { "en->es:Delayed" in model.calls }
                withContext(Dispatchers.Main) { audio.setAutoplayEnabled(false) }
                model.gate!!.complete(Unit)
                until { translation.state("a", "Delayed")?.phase == MessageTranslationPhase.READY }
                delay(80)
                assertTrue(speech.started.isEmpty())
                model.gate = CompletableDeferred()
                withContext(Dispatchers.Main) {
                    audio.setAutoplayEnabled(true)
                    audio.manual("b", "Another")
                }
                until { "en->es:Another" in model.calls }
                withContext(Dispatchers.Main) { audio.background() }
                model.gate!!.complete(Unit)
                until { translation.state("b", "Another")?.phase == MessageTranslationPhase.READY }
                delay(80)
                assertTrue(speech.started.isEmpty())
                assertFalse(audio.enabled)
            } finally {
                withContext(Dispatchers.Main) { audio.close() }
                scope.cancel()
            }
        }
    }

    @Test
    fun alreadyOffStillCancelsPendingAndPlayingManualRequests(): Unit = runBlocking {
        val model = Model().also { it.gate = CompletableDeferred() }
        owner(model).use { translation ->
            val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
            val speech = Speech()
            val audio =
                withContext(Dispatchers.Main) {
                    ConversationAutoplay(translation, speech, scope) {}
                }
            try {
                assertFalse(audio.enabled)
                withContext(Dispatchers.Main) { audio.manual("pending-off", "Pending while off") }
                until { "en->es:Pending while off" in model.calls }
                assertEquals("pending-off", audio.manualMessage)
                withContext(Dispatchers.Main) { audio.setAutoplayEnabled(false) }
                assertNull(audio.manualMessage)
                model.gate!!.complete(Unit)
                until { translation.activeTaskCount == 0 }
                assertTrue(speech.started.isEmpty())
                withContext(Dispatchers.Main) { audio.manual("playing-off", "Playing while off") }
                until { speech.activeMessage == "playing-off" }
                assertFalse(audio.enabled)
                withContext(Dispatchers.Main) { audio.setAutoplayEnabled(false) }
                assertNull(speech.activeMessage)
                assertNull(audio.manualMessage)
                assertFalse(audio.enabled)
                assertEquals(listOf("playing-off"), speech.started.map { it.first })
            } finally {
                withContext(Dispatchers.Main) { audio.close() }
                scope.cancel()
            }
        }
    }

    @Test
    fun fullAcceptedAndExpandedMessageSpeechIsChunkedWithoutTruncation() {
        for (text in
            listOf(
                "a".repeat(32_768),
                "中文。".repeat(22_000),
                "Read " + ".".repeat(32_000),
                "café ☕ ".repeat(10_000),
            )) {
            val original = SpeechSpan(text, "zh")
            val chunks = SpeechChunks.plan(listOf(original))
            assertEquals(text, chunks.flatten().joinToString("") { it.text })
            assertTrue(chunks.all { chunk -> chunk.sumOf { it.text.length } <= 160 })
            assertTrue(chunks.flatten().all { it.language == "zh" })
        }
    }

    @Test
    fun internalModelTimeoutIsFailedAndRetryableRatherThanPermanentPreparing(): Unit = runBlocking {
        var timeout = true
        val model =
            object : LanguageTranslation {
                override suspend fun prepare(
                    source: String,
                    target: String,
                    cellularAllowed: Boolean,
                ) = Unit

                override suspend fun translate(
                    text: String,
                    source: String,
                    target: String,
                ): String {
                    if (timeout) withTimeout(1) { delay(1_000) }
                    return "es:$text"
                }

                override fun close() = Unit
            }
        val translation =
            ConversationTranslation(
                context,
                "en",
                "es",
                translator = model,
                language = language("en"),
                reading = { _, _ -> FullMessageReading.notNeeded() },
            )
        try {
            try {
                translation.resolve("timed", "Message")
                fail("Timeout must be visible")
            } catch (_: java.io.IOException) {}
            assertEquals(
                MessageTranslationPhase.FAILED,
                translation.state("timed", "Message")?.phase,
            )
            timeout = false
            assertEquals(
                "es:Message",
                translation.resolve("timed", "Message", retry = true).practiceText,
            )
        } finally {
            translation.close()
        }
    }
}
