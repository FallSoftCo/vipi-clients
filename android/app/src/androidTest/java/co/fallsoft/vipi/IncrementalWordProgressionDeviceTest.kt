package co.fallsoft.vipi

import android.content.ContextWrapper
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.KeyStore
import java.util.UUID

/** Controlled progression/storage regressions, never translation, TTS or
 * transliteration support certification. No real SDK model/provider is called. */
class IncrementalWordProgressionDeviceTest {
    private class Provider(val action: suspend (String, String, String) -> String) : LanguageTranslation {
        val calls = mutableListOf<Triple<String, String, String>>()
        val preparations = mutableListOf<Pair<String, String>>()
        var ready = true
        override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) { preparations += source to target }
        override suspend fun translate(text: String, source: String, target: String): String {
            calls += Triple(text, source, target); return action(text, source, target)
        }
        override suspend fun isReady(source: String, target: String) = ready
        override fun close() = Unit
    }
    private class Fixture : AutoCloseable {
        private val base = InstrumentationRegistry.getInstrumentation().targetContext
        private val root = File(base.cacheDir, "word-progression-${UUID.randomUUID()}").apply { check(mkdirs()) }
        private val context = object : ContextWrapper(base) { override fun getNoBackupFilesDir() = root }
        private val account = UUID.randomUUID()
        val vault = MessageVault(context, account)
        private val owners = mutableListOf<ConversationTranslation>()
        fun owner(provider: Provider, identify: suspend (String) -> String? = { "en" }): ConversationTranslation =
            ConversationTranslation(context, "en", "es", FullMessageTranslationStore(vault), provider,
                object : MessageTranslationLanguage {
                    override suspend fun identify(text: String) = identify(text)
                    override fun close() = Unit
                }, reading = { _, _ -> FullMessageReading.notNeeded() }).also { owners += it }
        fun count(kind: String) = vault.transaction { vault.ids(kind).size }
        fun clearDerivative() = vault.transaction { vault.ids("incremental-message").forEach { vault.remove("incremental-message", it) } }
        override fun close() {
            owners.forEach { it.close() }; vault.close(); root.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
        }
    }
    @Test fun oneNewSourceWordPerMessageAndCompleteEquivalentsAreReused(): Unit = runBlocking {
        Fixture().use { f ->
            val provider = Provider { word, _, _ -> when (word.lowercase()) { "hello" -> "hola"; "friend" -> "buen amigo"; else -> error("Unexpected word") } }
            val owner = f.owner(provider)
            val first = owner.resolve("m1", "Hello, friend!")
            assertEquals("hola, friend!", first.practiceText); assertEquals("Hello, friend!", first.meaningText)
            assertEquals(listOf("hola"), first.words!!.map { it.target }); assertEquals(1, f.count("introduced-word"))
            val second = owner.resolve("m2", "HELLO, friend!")
            assertEquals("hola, buen amigo!", second.practiceText)
            assertEquals(listOf("hola", "buen amigo"), second.words!!.map { it.target })
            assertEquals(2, f.count("introduced-word")); assertEquals(listOf("Hello", "friend"), provider.calls.map { it.first })
            assertEquals(second, owner.resolve("m2", "HELLO, friend!"))
            assertEquals(2, f.count("introduced-word"))
        }
    }
    @Test fun cacheLossAndReopenRestoreExactOldSnapshotWithoutIntroducingAgain(): Unit = runBlocking {
        Fixture().use { f ->
            val owner = f.owner(Provider { word, _, _ -> if (word.equals("hello", true)) "hola" else "amigo" })
            val first = owner.resolve("m1", "Hello friend!")
            owner.resolve("m2", "Hello friend!")
            assertEquals(2, f.count("introduced-word")); owner.close(); f.clearDerivative()
            val never = Provider { _, _, _ -> error("Cache loss cannot authorize another introduction") }
            val reopened = f.owner(never)
            val restored = reopened.resolve("m1", "Hello friend!")
            assertEquals(first.practiceText, restored.practiceText)
            assertEquals(first.words, restored.words)
            assertEquals("hola friend!", restored.practiceText)
            assertTrue(never.calls.isEmpty()); assertEquals(2, f.count("introduced-word"))
            f.vault.transaction { f.vault.ids("word-message-plan").forEach { id ->
                val json = f.vault.get("word-message-plan", id)!!.toString(Charsets.UTF_8)
                assertFalse(json.contains("Hello friend!"))
            } }
        }
    }
    @Test fun corruptDerivativeRebuildsMarkerButMalformedReferenceCannotChooseAnotherWord(): Unit = runBlocking {
        Fixture().use { f ->
            val owner = f.owner(Provider { _, _, _ -> "hola" })
            owner.resolve("m1", "Hello friend!"); owner.close()
            val key = FullMessageTranslation.key("m1", "Hello friend!", "en", "es")
            f.vault.transaction { f.vault.put("incremental-message", key, "malformed cache".toByteArray()) }
            val never = Provider { _, _, _ -> error("No new provider call") }
            val reopened = f.owner(never)
            assertEquals("hola friend!", reopened.resolve("m1", "Hello friend!").practiceText)
            reopened.close(); f.clearDerivative()
            f.vault.transaction {
                val id = f.vault.ids("word-message-plan").single()
                val marker = JSONObject(f.vault.get("word-message-plan", id)!!.toString(Charsets.UTF_8))
                marker.getJSONArray("words").getJSONObject(0).put("word_id", "missing-reference")
                f.vault.put("word-message-plan", id, marker.toString().toByteArray())
            }
            assertTrue(runCatching { f.owner(never).resolve("m1", "Hello friend!") }.isFailure)
            assertTrue(never.calls.isEmpty()); assertEquals(1, f.count("introduced-word"))
        }
    }
    @Test fun importedHistoryReusesOnlyExistingWordsAndCannotCreateRestoreProgress(): Unit = runBlocking {
        Fixture().use { f ->
            fun imported(id: String, text: String) = f.vault.transaction {
                f.vault.put("imported", id, JSONObject().put("id", id).put("text", text).toString().toByteArray())
            }
            val id = UUID.randomUUID().toString(); imported(id, "Hello friend!")
            val never = Provider { _, _, _ -> error("Restored history cannot introduce a word") }
            val firstOwner = f.owner(never)
            val first = firstOwner.resolve(id, "Hello friend!")
            assertEquals("Hello friend!", first.practiceText); assertTrue(first.words!!.isEmpty())
            assertEquals(0, f.count("introduced-word")); firstOwner.close()
            // New live messages may still introduce words normally.
            val live = f.owner(Provider { _, _, _ -> "hola" })
            live.resolve("new-live-message", "Hello"); live.close(); f.clearDerivative()
            val restored = f.owner(never).resolve(id, "Hello friend!")
            assertEquals(first.words, restored.words); assertEquals(first.practiceText, restored.practiceText)
            val secondID = UUID.randomUUID().toString(); imported(secondID, "Hello friend!")
            val reuse = f.owner(never).resolve(secondID, "Hello friend!")
            assertEquals("hola friend!", reuse.practiceText); assertEquals(listOf("Hello"), reuse.words!!.map { it.source })
            assertEquals(1, f.count("introduced-word")); assertTrue(never.calls.isEmpty())
        }
    }
    @Test fun malformedOrCollidingImportedIdentityCannotAuthorizeNewSelection(): Unit = runBlocking {
        Fixture().use { f ->
            val provider = Provider { _, _, _ -> error("Invalid import cannot reach native translation") }
            val owner = f.owner(provider)
            val id = UUID.randomUUID().toString()
            f.vault.transaction { f.vault.put("imported", id, "malformed".toByteArray()) }
            assertTrue(runCatching { owner.resolve(id, "Hello") }.isFailure)
            f.vault.transaction { f.vault.put("imported", id, JSONObject().put("id", id).put("text", "Other original").toString().toByteArray()) }
            assertTrue(runCatching { owner.resolve(id, "Hello", retry = true) }.isFailure)
            assertTrue(provider.calls.isEmpty()); assertEquals(0, f.count("introduced-word")); assertEquals(0, f.count("word-message-plan"))
        }
    }
    @Test fun concurrentMessagesCannotIntroduceSameUnknownWordTwice(): Unit = runBlocking {
        Fixture().use { f ->
            val owner = f.owner(Provider { word, _, _ -> delay(20); "equivalent $word" })
            val results = coroutineScope { listOf(async { owner.resolve("m1", "hello friend") }, async { owner.resolve("m2", "hello friend") }).awaitAll() }
            assertEquals(listOf(1, 2), results.map { it.words!!.size }.sorted())
            assertEquals(2, f.count("introduced-word"))
            f.vault.transaction {
                val additions = f.vault.ids("word-message-plan").map { id ->
                    JSONObject(f.vault.get("word-message-plan", id)!!.toString(Charsets.UTF_8)).getString("introduced_id")
                }
                assertEquals(2, additions.toSet().size)
            }
        }
    }
    @Test fun failedOrUnchangedTranslationsNeverCountAsIntroduced(): Unit = runBlocking {
        Fixture().use { f ->
            var fail = true
            val provider = Provider { word, _, _ -> if (fail) throw java.io.IOException("Controlled temporary failure") else if (word == "hotel") word else "hola" }
            val owner = f.owner(provider)
            assertTrue(runCatching { owner.resolve("failed", "hello") }.isFailure)
            assertEquals(0, f.count("introduced-word")); assertEquals(0, f.count("word-message-plan"))
            fail = false
            assertEquals("hola", owner.resolve("failed", "hello", retry = true).practiceText)
            assertEquals(1, f.count("introduced-word"))
            val unchanged = owner.resolve("same", "hotel")
            assertEquals("hotel", unchanged.practiceText); assertTrue(unchanged.words!!.isEmpty())
            assertEquals(1, f.count("introduced-word"))
        }
    }
    @Test fun actualSourceLedgersStaySeparateAndForeignMissingModelsNeverDownload(): Unit = runBlocking {
        Fixture().use { f ->
            val provider = Provider { word, source, _ -> check(word == "gift"); if (source == "de") "veneno" else "regalo" }
            val owner = f.owner(provider) { text -> if (text.contains("neben")) "de" else "en" }
            assertEquals("veneno neben dir", owner.resolve("de", "gift neben dir").practiceText)
            assertEquals("regalo for you", owner.resolve("en", "gift for you").practiceText)
            assertEquals(2, f.count("introduced-word"))
            assertTrue(provider.preparations.all { it == ("en" to "es") })
            val missing = Provider { _, _, _ -> error("No foreign inference") }.apply { ready = false }
            assertTrue(runCatching { f.owner(missing) { "fr" }.resolve("fr", "bonjour mon ami") }.isFailure)
            assertTrue(missing.calls.isEmpty()); assertTrue(missing.preparations.all { it == ("en" to "es") })
        }
    }
    @Test fun vocabularyGrowsBeyondIllustrativeHundredAndResidentCacheLimit(): Unit = runBlocking {
        Fixture().use { f ->
            val owner = f.owner(Provider { word, _, _ -> "complete equivalent $word" })
            repeat(180) { index ->
                val word = "item${('a'.code+index/26).toChar()}${('a'.code+index%26).toChar()}"
                assertEquals("complete equivalent $word", owner.resolve("m$index", word).practiceText)
            }
            assertEquals(180, f.count("introduced-word")); assertEquals(180, f.count("word-message-plan"))
            owner.close(); f.clearDerivative()
            val never = Provider { _, _, _ -> error("No extra introduction after eviction") }
            assertEquals("complete equivalent itemaa", f.owner(never).resolve("m0", "itemaa").practiceText)
            assertEquals(180, f.count("introduced-word")); assertTrue(never.calls.isEmpty())
        }
    }
    @Test fun nativeWordBoundariesProtectTechnicalLiteralsAndKeepSpacing() {
        val text = "Hello  https://example.com/hello @hello name@example.com `hello` #hello 123 😀!"
        val tokens = IncrementalWords.tokens(text, "en")
        assertEquals(listOf("Hello"), tokens.map { it.text })
        val span = WordReplacement(tokens.single().start, tokens.single().end-tokens.single().start, "Hello", "hola")
        assertEquals(text.replaceFirst("Hello", "hola"), WordReplacement.compose(text, listOf(span), false))
    }
}
