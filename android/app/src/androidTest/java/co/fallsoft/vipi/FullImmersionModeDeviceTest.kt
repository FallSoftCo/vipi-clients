package co.fallsoft.vipi

import android.content.ContextWrapper
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.security.KeyStore
import java.util.UUID
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test

/** Controlled routing/storage/cancellation, not SDK/TTS/language certification. */
class FullImmersionModeDeviceTest {
    private class Provider(val answer: suspend (String) -> String) : LanguageTranslation {
        val calls = mutableListOf<String>()

        override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) =
            Unit

        override suspend fun translate(text: String, source: String, target: String): String {
            calls += text
            return answer(text)
        }

        override fun close() = Unit
    }

    private class Fixture : AutoCloseable {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(base.cacheDir, "full-mode-${UUID.randomUUID()}").apply { check(mkdirs()) }
        val context =
            object : ContextWrapper(base) {
                override fun getNoBackupFilesDir() = root
            }
        val account = UUID.randomUUID()
        val vault = MessageVault(context, account)
        val owners = mutableListOf<ConversationTranslation>()

        fun owner(
            mode: ImmersionMode,
            provider: Provider,
            reader: suspend (String, String) -> FullMessageReading = { _, _ ->
                FullMessageReading.notNeeded()
            },
        ) =
            ConversationTranslation(
                    context,
                    "en",
                    "es",
                    FullMessageTranslationStore(vault),
                    provider,
                    object : MessageTranslationLanguage {
                        override suspend fun identify(text: String) = "en"

                        override fun close() = Unit
                    },
                    reading = reader,
                    mode = mode,
                )
                .also { owners += it }

        fun rows(kind: String) = vault.transaction {
            vault.ids(kind).associateWith { requireNotNull(vault.get(kind, it)).toList() }
        }

        override fun close() {
            owners.forEach { it.close() }
            vault.close()
            root.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply {
                load(null)
                deleteEntry("co.fallsoft.vipi.messages.$account")
            }
        }
    }

    @Test
    fun wholeMessageUsesOneNativeRequestAndExactAuthoredHoldWithoutWordProgress(): Unit =
        runBlocking {
            Fixture().use { f ->
                val exact = "Hello, friend!  ☕\nTomorrow?"
                val provider = Provider { "¡Hola, amigo!  ☕\n¿Mañana?" }
                val readerInputs = mutableListOf<String>()
                val owner =
                    f.owner(ImmersionMode.FULL_MESSAGES, provider) { text, _ ->
                        readerInputs += text
                        FullMessageReading.notNeeded()
                    }
                val value = owner.resolve("full-one", exact)
                assertEquals(listOf(exact), provider.calls)
                assertEquals(provider.answer(exact), value.practiceText)
                assertEquals(exact, value.original)
                assertEquals(exact, value.meaningText)
                assertNull(value.words)
                assertEquals(ImmersionMode.FULL_MESSAGES, value.mode)
                assertEquals(listOf(value.practiceText), readerInputs)
                assertEquals(value, FullMessageTranslation.parse(value.json()))
                assertTrue(f.rows("introduced-word").isEmpty())
                assertTrue(f.rows("word-message-plan").isEmpty())
                assertEquals(1, f.rows("full-message-review").size)
            }
        }

    @Test
    fun switchingModesAndReopenPreserveExactImmutableIncrementalPlans(): Unit = runBlocking {
        Fixture().use { f ->
            val exact = "Hello friend!"
            val id = "same-durable-message"
            val words = f.owner(ImmersionMode.NEW_WORD, Provider { "hola" })
            val before = words.resolve(id, exact)
            words.close()
            val vocabulary = f.rows("introduced-word")
            val plans = f.rows("word-message-plan")
            val fullProvider = Provider {
                require(it == exact)
                "¡Hola amigo!"
            }
            val full = f.owner(ImmersionMode.FULL_MESSAGES, fullProvider)
            assertEquals("¡Hola amigo!", full.resolve(id, exact).practiceText)
            assertNotEquals(words.key(id, exact), full.key(id, exact))
            full.close()
            assertEquals(vocabulary, f.rows("introduced-word"))
            assertEquals(plans, f.rows("word-message-plan"))
            val never = Provider { error("Existing plan/full cache must not translate again") }
            assertEquals(
                before.practiceText,
                f.owner(ImmersionMode.NEW_WORD, never).resolve(id, exact).practiceText,
            )
            assertEquals(
                "¡Hola amigo!",
                f.owner(ImmersionMode.FULL_MESSAGES, never).resolve(id, exact).practiceText,
            )
            assertTrue(never.calls.isEmpty())
            assertEquals(vocabulary, f.rows("introduced-word"))
            assertEquals(plans, f.rows("word-message-plan"))
        }
    }

    @Test
    fun closedFullModeCannotPublishLateResultOrCreateWordState(): Unit = runBlocking {
        Fixture().use { f ->
            val entered = CompletableDeferred<Unit>()
            val release = CompletableDeferred<Unit>()
            val owner =
                f.owner(
                    ImmersionMode.FULL_MESSAGES,
                    Provider {
                        entered.complete(Unit)
                        withContext(NonCancellable) { release.await() }
                        "Texto completo"
                    },
                )
            val work = async { runCatching { owner.resolve("late", "A complete message.") } }
            entered.await()
            owner.close()
            release.complete(Unit)
            assertTrue(work.await().isFailure)
            assertTrue(f.rows("full-message-review").isEmpty())
            assertTrue(f.rows("introduced-word").isEmpty())
            assertTrue(f.rows("word-message-plan").isEmpty())
        }
    }
}
