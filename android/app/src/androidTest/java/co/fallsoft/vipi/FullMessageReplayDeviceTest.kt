package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test
import java.security.KeyStore
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CopyOnWriteArrayList

/** Real encrypted derived-cache/owner; controlled model proves replay memory,
 * ordering and cancellation, not translation quality. */
class FullMessageReplayDeviceTest {
    private class Provider : LanguageTranslation {
        val calls = CopyOnWriteArrayList<String>()
        val gates = ConcurrentHashMap<String, CompletableDeferred<Unit>>()
        override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = Unit
        override suspend fun translate(text: String, source: String, target: String): String {
            calls += text; gates[text]?.await(); return "$target:$text"
        }
        override fun close() = Unit
    }
    private val language = object : MessageTranslationLanguage {
        override suspend fun identify(text: String): String? = "en"
        override fun close() = Unit
    }
    private suspend fun until(condition: () -> Boolean) = withTimeout(10_000) { while (!condition()) delay(10) }

    @Test fun savedReplayBeyondMemoryLimitKeepsVisibleFaceAndPersistsEveryResult(): Unit = runBlocking {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val account = UUID.randomUUID(); val vault = MessageVault(context, account)
        val provider = Provider(); val cache = FullMessageTranslationStore(vault)
        val owner = ConversationTranslation(context, "en", "es", cache, provider, language,
            reading = { _, _ -> FullMessageReading.notNeeded() }, cacheByteLimit = 1_024)
        try {
            owner.retain("visible", "Pinned visible paragraph")
            val pinned = owner.resolve("visible", "Pinned visible paragraph")
            val saved = (0 until 180).map { ConversationTranslation.SavedMessage("old-$it", "Saved paragraph $it") }
            owner.replaySaved { saved.asSequence() }
            until { !owner.replayActive }
            assertNull(owner.replayFailure)
            assertEquals(181, provider.calls.size)
            assertTrue(owner.cachedBytes <= 1_024)
            assertSame(pinned, owner.state("visible", "Pinned visible paragraph")?.value)
            assertTrue("Background replay must not materialize the whole archive in Compose state", owner.states.size <= 129)
            for (message in saved) {
                assertEquals("es:${message.text}", cache.read(owner.key(message.id, message.text))?.practiceText)
            }
            val before = provider.calls.size
            owner.release("visible", "Pinned visible paragraph")
            owner.retain("old-0", saved.first().text)
            assertEquals("es:${saved.first().text}", owner.resolve("old-0", saved.first().text).practiceText)
            assertEquals("Evicted memory must use genuine persisted completion", before, provider.calls.size)
        } finally {
            owner.close(); vault.close(); vault.file.parentFile!!.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
        }
    }

    @Test fun foregroundRequestPrecedesNextOldRecordAndCloseStopsReplay(): Unit = runBlocking {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val provider = Provider(); val old = CompletableDeferred<Unit>(); val live = CompletableDeferred<Unit>()
        provider.gates["old first"] = old; provider.gates["live new"] = live
        val owner = ConversationTranslation(context, "en", "es", translator = provider, language = language, reading = { _, _ -> FullMessageReading.notNeeded() })
        try {
            owner.replaySaved { sequenceOf(ConversationTranslation.SavedMessage("old-a", "old first"), ConversationTranslation.SavedMessage("old-b", "old second")) }
            until { "old first" in provider.calls }
            val foreground = async { owner.resolve("live", "live new") }
            delay(80)
            assertEquals("A native model is admitted serially; waiting is outside its execution timeout", listOf("old first"), provider.calls.toList())
            old.complete(Unit)
            until { "live new" in provider.calls }
            assertEquals(listOf("old first", "live new"), provider.calls.toList())
            live.complete(Unit); assertEquals("es:live new", foreground.await().practiceText)
            until { !owner.replayActive }
            assertEquals(listOf("old first", "live new", "old second"), provider.calls.toList())
            val held = CompletableDeferred<Unit>(); provider.gates["close first"] = held
            owner.replaySaved { sequenceOf(ConversationTranslation.SavedMessage("close-a", "close first"), ConversationTranslation.SavedMessage("close-b", "never after close")) }
            until { "close first" in provider.calls }
            owner.close(); held.complete(Unit); delay(80)
            assertFalse("never after close" in provider.calls)
            assertTrue(owner.states.isEmpty())
        } finally { old.complete(Unit); live.complete(Unit); owner.close() }
    }
    @Test fun durableCatchupLoadsOneOriginalAtATimeAndDoesNotStarveVisibleDemand(): Unit = runBlocking {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val account = UUID.randomUUID(); val vault = MessageVault(context, account)
        val provider = Provider(); val gate = CompletableDeferred<Unit>(); provider.gates["Saved catchup 0"] = gate
        val cache = FullMessageTranslationStore(vault)
        val owner = ConversationTranslation(context, "en", "es", cache, provider, language, reading = { _, _ -> FullMessageReading.notNeeded() }, cacheByteLimit = 1_024)
        val loads = CopyOnWriteArrayList<String>()
        try {
            vault.transaction { repeat(1_000) { vault.put("catchup-test", "id-$it", "Saved catchup $it".toByteArray()) } }
            repeat(1_000) { index ->
                val id = "id-$index"
                owner.enqueueStored(id) { loads += id; vault.transaction { vault.get("catchup-test", id)?.toString(Charsets.UTF_8) } }
            }
            until { "Saved catchup 0" in provider.calls }
            assertEquals(listOf("id-0"), loads.toList())
            assertEquals(999, owner.pendingDurableCount)
            assertEquals(1, owner.activeTaskCount)
            // Missing/deleted originals are not reconstructed from cached text.
            vault.transaction { vault.remove("catchup-test", "id-700") }
            owner.retain("visible", "Visible incoming")
            val visible = async { owner.resolve("visible", "Visible incoming") }
            delay(80); assertEquals(listOf("Saved catchup 0"), provider.calls.toList())
            gate.complete(Unit)
            val value = visible.await()
            assertEquals("es:Visible incoming", value.practiceText)
            withTimeout(60_000) { while (owner.durableActive) delay(10) }
            assertEquals("Visible demand precedes the next durable backlog record", listOf("Saved catchup 0", "Visible incoming"), provider.calls.take(2))
            assertSame(value, owner.state("visible", "Visible incoming")?.value)
            assertEquals(1_000, provider.calls.size) //999 extant originals + visible.
            assertFalse("Saved catchup 700" in provider.calls)
            assertTrue(owner.cachedBytes <= 1_024)
            repeat(1_000) { index -> if (index != 700) {
                assertEquals("es:Saved catchup $index", cache.read(owner.key("id-$index", "Saved catchup $index"))?.practiceText)
            } }
            val closed = CompletableDeferred<Unit>(); provider.gates["blocked close"] = closed
            owner.enqueueStored("closing") { "blocked close" }
            until { "blocked close" in provider.calls }
            owner.enqueueStored("never") { fail("A closed owner must not even load the next original"); "never" }
            owner.close(); closed.complete(Unit); delay(80)
            assertEquals(0, owner.pendingDurableCount)
            assertTrue(owner.states.isEmpty())
        } finally {
            gate.complete(Unit); owner.close(); vault.close(); vault.file.parentFile!!.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
        }
    }

}
