package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.security.KeyStore
import java.util.UUID
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/**
 * Real encrypted derived-cache upgrade and actual packaged Chinese reader. Model boundary must
 * never execute; this is not translation-quality evidence.
 */
class FullMessageReadingUpgradeDeviceTest {
    private val mode = ImmersionMode.FULL_MESSAGES
    private val context
        get() = InstrumentationRegistry.getInstrumentation().targetContext

    private class NoTranslation : LanguageTranslation {
        val calls = AtomicInteger()

        override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) =
            Unit

        override suspend fun translate(text: String, source: String, target: String): String {
            calls.incrementAndGet()
            error("A reading upgrade must reuse complete model output")
        }

        override fun close() = Unit
    }

    private fun owner(
        vault: MessageVault,
        model: NoTranslation,
        reading: suspend (String, String) -> FullMessageReading = { text, code ->
            FullMessageReadings.read(context, text, code)
        },
    ) =
        ConversationTranslation(
            context,
            "en",
            "zh",
            FullMessageTranslationStore(vault),
            model,
            object : MessageTranslationLanguage {
                override suspend fun identify(text: String): String? =
                    error("Cached translation must not identify again")

                override fun close() = Unit
            },
            reading = reading,
            mode = mode,
        )

    private fun seed(vault: MessageVault, id: UUID, stamp: String?, guide: String = "ni hao") {
        val value =
            FullMessageTranslation(
                "Hello.",
                "你好",
                "Hello.",
                "en",
                "zh",
                "en",
                guide,
                stamp,
                mode = mode,
            )
        val json = value.json().also { if (stamp == null) it.remove("reading_policy") }
        vault.transaction {
            vault.put(
                "full-message-review",
                FullMessageTranslation.key(id.toString(), "Hello.", "en", "zh", mode),
                json.toString().toByteArray(Charsets.UTF_8),
            )
        }
    }

    private fun eraseOwned(vault: MessageVault, account: UUID) {
        vault.close()
        vault.file.parentFile!!.deleteRecursively()
        KeyStore.getInstance("AndroidKeyStore").apply {
            load(null)
            deleteEntry("co.fallsoft.vipi.messages.$account")
        }
    }

    @Test
    fun legacyAndChangedReadingPoliciesRefreshWithoutModelOrMessageMutation(): Unit = runBlocking {
        val account = UUID.randomUUID()
        var vault = MessageVault(context, account)
        val ids = listOf(UUID.randomUUID(), UUID.randomUUID())
        val peer = UUID.randomUUID()
        val model = NoTranslation()
        val readings = AtomicInteger()
        try {
            val journal = MessageJournal(vault)
            ids.forEach { journal.saveDraft(it, peer, "Hello.", 1_000, 1_000) }
            val journalBytes = vault.transaction {
                ids.map { requireNotNull(vault.get("draft", it.toString())) }
            }
            seed(vault, ids[0], null) // Complete full-message record with no reading stamp.
            val previousAppPolicy =
                listOf(
                        "full-message-readings-3:status-1:full-text-65536:kana-65536:ja-native-span-16384:reading-720896",
                        "zh",
                        "${ChineseReadings.POLICY}:${ChineseReadings.DATA_SHA256}",
                        android.os.Build.VERSION.SDK_INT.toString(),
                        android.os.Build.VERSION.INCREMENTAL,
                    )
                    .joinToString(":")
            seed(
                vault,
                ids[1],
                previousAppPolicy,
                "nǐ hǎo",
            ) // Actual preceding app epoch, same valid short guide.
            val keys = ids.map {
                FullMessageTranslation.key(it.toString(), "Hello.", "en", "zh", mode)
            }
            val policy = FullMessageReadings.policy("zh")
            assertNotEquals(previousAppPolicy, policy)
            assertTrue(policy.contains(ChineseReadings.POLICY))
            assertTrue(policy.contains(ChineseReadings.DATA_SHA256))
            owner(vault, model) { text, code ->
                    readings.incrementAndGet()
                    FullMessageReadings.read(context, text, code)
                }
                .use { translation ->
                    ids.forEach { id ->
                        val value = translation.resolve(id.toString(), "Hello.")
                        assertEquals("nǐ hǎo", value.practiceReading)
                        assertEquals(policy, value.readingPolicy)
                        assertEquals(FullMessageReadingStatus.AVAILABLE, value.readingStatus)
                        assertEquals("Hello.", value.original)
                        assertEquals("你好", value.practiceText)
                        assertEquals("Hello.", value.meaningText)
                    }
                }
            assertEquals(2, readings.get())
            assertEquals(0, model.calls.get())
            vault.transaction {
                assertEquals(keys.toSet(), vault.ids("full-message-review").toSet())
                ids.forEachIndexed { i, id ->
                    assertArrayEquals(journalBytes[i], vault.get("draft", id.toString()))
                }
            }
            // Reopen the actual encrypted vault and app owner, not just RAM.
            vault.close()
            vault = MessageVault(context, account)
            owner(vault, model) { _, _ ->
                    readings.incrementAndGet()
                    error("Current reading must survive reopen")
                }
                .use { translation ->
                    ids.forEach {
                        assertEquals(
                            "nǐ hǎo",
                            translation.resolve(it.toString(), "Hello.").practiceReading,
                        )
                    }
                }
            assertEquals(2, readings.get())
            assertEquals(0, model.calls.get())
            val store = FullMessageTranslationStore(vault)
            keys.forEach { assertEquals(policy, store.read(it, mode)?.readingPolicy) }
            ids.forEachIndexed { i, id ->
                assertEquals("Hello.", MessageJournal(vault).draft(id)?.text)
                vault.transaction {
                    assertArrayEquals(journalBytes[i], vault.get("draft", id.toString()))
                }
            }
            readingRegressionFile(context, "reading-cache-upgrade-native.json")
                .writeText(
                    JSONObject()
                        .put("passed", true)
                        .put("legacy_and_changed_policy_rows", 2)
                        .put("real_reading", "nǐ hǎo")
                        .put("reading_policy", policy)
                        .put("model_calls", model.calls.get())
                        .put("reading_calls", readings.get())
                        .put("original_journal_bytes_preserved", true)
                        .put("vault_reopened", true)
                        .toString(2)
                )
        } finally {
            eraseOwned(vault, account)
        }
    }

    @Test
    fun unavailableReadingDropsStaleFaceRetriesAndClosedOwnerCannotSave(): Unit = runBlocking {
        val account = UUID.randomUUID()
        val vault = MessageVault(context, account)
        val id = UUID.randomUUID()
        val key = FullMessageTranslation.key(id.toString(), "Hello.", "en", "zh", mode)
        val model = NoTranslation()
        try {
            seed(vault, id, "previous-reader")
            owner(vault, model) { _, _ -> error("Reader unavailable") }
                .use { translation ->
                    val value = translation.resolve(id.toString(), "Hello.")
                    assertNull(value.practiceReading)
                    assertEquals(FullMessageReadings.policy("zh"), value.readingPolicy)
                    assertEquals(FullMessageReadingStatus.UNAVAILABLE, value.readingStatus)
                    assertEquals(FullMessageReadingFailure.PRODUCER_FAILURE, value.readingFailure)
                    assertEquals("你好", value.practiceText)
                    assertEquals("Hello.", value.original)
                    assertEquals("Hello.", value.meaningText)
                }
            assertNull(FullMessageTranslationStore(vault).read(key, mode)?.practiceReading)
            owner(vault, model) { _, _ ->
                    error("Known failure must not automatically rerun on reopen")
                }
                .use { translation ->
                    assertEquals(
                        FullMessageReadingStatus.UNAVAILABLE,
                        translation.resolve(id.toString(), "Hello.").readingStatus,
                    )
                }
            owner(vault, model).use { translation ->
                assertEquals(
                    "nǐ hǎo",
                    translation.resolve(id.toString(), "Hello.", retry = true).practiceReading,
                )
            }
            seed(vault, id, "old-before-close")
            val before = vault.transaction { requireNotNull(vault.get("full-message-review", key)) }
            val entered = CompletableDeferred<Unit>()
            val translation =
                owner(vault, model) { _, _ ->
                    entered.complete(Unit)
                    awaitCancellation()
                }
            try {
                val pending = async { translation.resolve(id.toString(), "Hello.") }
                withTimeout(5_000) { entered.await() }
                translation.close()
                try {
                    pending.await()
                    fail("Closed reading upgrade must cancel")
                } catch (_: CancellationException) {}
                vault.transaction {
                    assertArrayEquals(before, vault.get("full-message-review", key))
                }
            } finally {
                translation.close()
            }
            assertEquals(0, model.calls.get())
        } finally {
            eraseOwned(vault, account)
        }
    }
}
