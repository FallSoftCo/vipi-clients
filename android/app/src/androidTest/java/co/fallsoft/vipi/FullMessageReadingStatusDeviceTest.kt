package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.SpeechSpan
import kotlinx.coroutines.*
import org.json.JSONObject
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test
import java.security.KeyStore
import java.util.UUID
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicInteger

/** Real phonetic readers and encrypted persistence. Seeded completed translations
 * are a boundary fixture, not ML Kit semantic or acoustic evidence. */
class FullMessageReadingStatusDeviceTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private fun dedicated() {
        check(BuildConfig.DEBUG && BuildConfig.APPLICATION_ID == "co.fallsoft.vipi.sourcecontextqa")
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
    }
    private class NoModel : LanguageTranslation {
        val calls = AtomicInteger()
        override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = Unit
        override suspend fun translate(text: String, source: String, target: String): String {
            calls.incrementAndGet(); error("Completed translation must not run the model")
        }
        override fun close() = Unit
    }
    private fun owner(vault: MessageVault, target: String, model: NoModel,
        reading: suspend (String, String) -> FullMessageReading = { text, code -> FullMessageReadings.read(context, text, code) }) =
        ConversationTranslation(context, "en", target, FullMessageTranslationStore(vault), model,
            object : MessageTranslationLanguage {
                override suspend fun identify(text: String): String? = error("Completed translation must not identify")
                override fun close() = Unit
            }, reading = reading)
    private fun seed(vault: MessageVault, id: UUID, original: String, practice: String, target: String) {
        val previous = listOf("full-message-readings-2:full-text-65536:kana-65536:ja-native-span-16384:reading-720896", target,
            "native-reader-1", android.os.Build.VERSION.SDK_INT.toString(), android.os.Build.VERSION.INCREMENTAL).joinToString(":")
        val value = FullMessageTranslation(original, practice, original, "en", target, "en", "stale guide", previous)
        FullMessageTranslationStore(vault).write(FullMessageTranslation.key(id.toString(), original, "en", target), value)
    }
    private fun erase(vault: MessageVault, account: UUID) {
        vault.close(); vault.file.parentFile!!.deleteRecursively()
        KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
    }
    private suspend fun verifyNativePracticeRequest(translation: ConversationTranslation, id: String, original: String,
        practice: String, target: String) {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        val calls = CopyOnWriteArrayList<List<SpeechSpan>>()
        val speech = object : ConversationSpeech {
            override val state = SpeechState.READY
            override val error: String? = null
            override val activeMessage: String? = null
            override val interruption = 0L
            override fun toggle(message: String, spans: List<SpeechSpan>) { assertEquals(id, message); calls += spans }
            override fun stop() = Unit
            override fun showMutedVolumeControl() = Unit
            override fun failureMessage() = "Unexpected controlled voice failure"
        }
        val audio = withContext(Dispatchers.Main) { ConversationAutoplay(translation, speech, scope) { error("No voice failure expected") } }
        try {
            withContext(Dispatchers.Main) { audio.manual(id, original) }
            withTimeout(5_000) { while (calls.isEmpty()) delay(10) }
            assertEquals(listOf(listOf(SpeechSpan(practice, target))), calls.toList())
        } finally { withContext(Dispatchers.Main) { audio.close(); scope.cancel() } }
    }

    @Test fun actualScriptsAndProtectedLiteralsHaveHonestReadingStatus() {
        dedicated()
        val rows = JSONArray()
        for (code in listOf("zh", "ja", "ko", "ar")) for (text in listOf(
            "cafe\u0301 123 \uD83D\uDE42", "https://example.test/漢字", "`文件夹`", "user@例子.test")) {
            val value = FullMessageReadings.read(context, text, code)
            assertEquals("$code literal $text", FullMessageReadingStatus.NOT_NEEDED, value.status)
            assertNull(value.text); assertNull(value.failure)
            rows.put(JSONObject().put("language", code).put("text", text).put("status", value.status.name))
        }
        for ((code, text) in listOf("zh" to "你好", "ja" to "銀行", "ko" to "한글", "ar" to "غدًا")) {
            val value = FullMessageReadings.read(context, text, code)
            assertEquals("$code native", FullMessageReadingStatus.AVAILABLE, value.status)
            assertFalse(value.text.isNullOrBlank()); assertNull(value.failure)
            rows.put(JSONObject().put("language", code).put("text", text).put("status", value.status.name).put("reading", value.text))
        }
        readingRegressionFile(context, "reading-status-classification.json").writeText(JSONObject().put("passed", true)
            .put("cases", rows).put("scope", "Actual script/reader metadata, not translation semantic or pronunciation acceptance").toString(2))
    }

    @Test fun acceptedSourceAndExpandedKoreanReadingPersistWithoutRetranslation(): Unit = runBlocking {
        dedicated()
        val account = UUID.randomUUID(); var vault = MessageVault(context, account)
        val id = UUID.randomUUID(); val peer = UUID.randomUUID(); val model = NoModel()
        val original = "a".repeat(32_762) + "你好"
        val practice = "꿩".repeat(16_384)
        try {
            assertEquals(32_768, original.toByteArray(Charsets.UTF_8).size)
            val journal = MessageJournal(vault); journal.saveDraft(id, peer, original, 1_000, 1_000)
            val saved = vault.transaction { requireNotNull(vault.get("draft", id.toString())) }
            assertTrue(runCatching { journal.saveDraft(id, peer, original + "a", 1_000, 1_000) }.exceptionOrNull() is IllegalArgumentException)
            vault.transaction { assertArrayEquals(saved, vault.get("draft", id.toString())) }
            seed(vault, id, original, practice, "ko")
            var reading = ""
            owner(vault, "ko", model).use { translation ->
                val value = translation.resolve(id.toString(), original)
                assertEquals(FullMessageReadingStatus.AVAILABLE, value.readingStatus)
                reading = requireNotNull(value.practiceReading)
                assertTrue("Expanded guide must exceed the old output cap", reading.length > 65_536)
                assertTrue(reading.startsWith("kkwong")); assertTrue(reading.endsWith("kkwong"))
                assertEquals(original, value.original); assertEquals(original, value.meaningText); assertEquals(practice, value.practiceText)
                verifyNativePracticeRequest(translation, id.toString(), original, practice, "ko")
            }
            vault.close(); vault = MessageVault(context, account)
            owner(vault, "ko", model) { _, _ -> error("Current expanded guide must not rerun") }.use { translation ->
                val restored = translation.resolve(id.toString(), original)
                assertEquals(reading, restored.practiceReading); assertEquals(FullMessageReadingStatus.AVAILABLE, restored.readingStatus)
                assertEquals(practice, restored.practiceText); assertEquals(original, restored.original)
            }
            assertEquals(0, model.calls.get())
            vault.transaction { assertArrayEquals(saved, vault.get("draft", id.toString())) }
            readingRegressionFile(context, "expanded-reading-boundary.json").writeText(JSONObject().put("passed", true)
                .put("source_utf8", 32_768).put("practice_utf16", practice.length).put("reading_utf16", reading.length)
                .put("model_calls", 0).put("vault_reopened", true).put("native_practice_command_preserved", true)
                .put("scope", "Real reader/cache plus controlled speech command; no MLKit semantic or PCM claim").toString(2))
        } finally { erase(vault, account) }
    }

    @Test fun realJapaneseSpanRefusalIsDurableAndDoesNotEraseTranslationOrAudio(): Unit = runBlocking {
        dedicated()
        val account = UUID.randomUUID(); var vault = MessageVault(context, account)
        val id = UUID.randomUUID(); val original = "A retained authored message."; val model = NoModel(); val reads = AtomicInteger()
        val unit = "明日は駅の近くで会いましょう"; val practice = unit.repeat(16_385 / unit.length + 1).take(16_385)
        try {
            MessageJournal(vault).saveDraft(id, UUID.randomUUID(), original, 1_000, 1_000)
            val journalBytes = vault.transaction { requireNotNull(vault.get("draft", id.toString())) }
            seed(vault, id, original, practice, "ja")
            owner(vault, "ja", model) { text, code -> reads.incrementAndGet(); FullMessageReadings.read(context, text, code) }.use { translation ->
                val value = translation.resolve(id.toString(), original)
                assertEquals(FullMessageReadingStatus.UNAVAILABLE, value.readingStatus)
                assertEquals(FullMessageReadingFailure.INPUT_LIMIT, value.readingFailure)
                assertNull(value.practiceReading); assertEquals(FullMessageReadings.policy("ja"), value.readingPolicy)
                assertEquals(practice, value.practiceText); assertEquals(original, value.meaningText); assertEquals(original, value.original)
                assertEquals(value, translation.resolve(id.toString(), original))
                verifyNativePracticeRequest(translation, id.toString(), original, practice, "ja")
            }
            vault.close(); vault = MessageVault(context, account)
            owner(vault, "ja", model) { _, _ -> error("Known input refusal must not loop on reopen") }.use { translation ->
                val restored = translation.resolve(id.toString(), original)
                assertEquals(FullMessageReadingStatus.UNAVAILABLE, restored.readingStatus)
                assertEquals(FullMessageReadingFailure.INPUT_LIMIT, restored.readingFailure)
                assertEquals(practice, restored.practiceText); assertNull(restored.practiceReading)
            }
            assertEquals(1, reads.get()); assertEquals(0, model.calls.get())
            vault.transaction { assertArrayEquals(journalBytes, vault.get("draft", id.toString())) }
            readingRegressionFile(context, "japanese-reading-refusal.json").writeText(JSONObject().put("passed", true)
                .put("practice_utf16", 16_385).put("reading_calls", 1).put("model_calls", 0)
                .put("status", "UNAVAILABLE").put("reason", "INPUT_LIMIT").put("no_reopen_loop", true)
                .put("translation_and_native_practice_command_preserved", true).toString(2))
        } finally { erase(vault, account) }
    }
}
