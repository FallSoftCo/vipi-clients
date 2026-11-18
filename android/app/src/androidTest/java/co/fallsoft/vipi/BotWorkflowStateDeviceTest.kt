package co.fallsoft.vipi

import android.content.ContextWrapper
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.io.IOException
import java.security.KeyStore
import java.util.UUID

/** Real encrypted BotSession, with only HTTP responses controlled. No provider or live account. */
class BotWorkflowStateDeviceTest {
    @Test fun olderAllowanceCannotOverwriteNewerExhaustedRead(): Unit = runBlocking(Dispatchers.Main) {
        Fixture().use { f ->
            val first = CompletableDeferred<JSONObject>(); val second = CompletableDeferred<JSONObject>()
            var reads = 0
            f.handler = { method, path, _, _ ->
                assertEquals("GET", method); assertEquals("/v1/bot/allowance", path)
                (if (++reads == 1) first else second).await()
            }
            f.session().use { bot ->
                val old = launch(start = CoroutineStart.UNDISPATCHED) { bot.refreshAllowance() }
                val newer = launch(start = CoroutineStart.UNDISPATCHED) { bot.refreshAllowance() }
                second.complete(quota(0)); newer.join()
                first.complete(quota(10)); old.join()
                assertEquals(0, bot.allowance!!.remaining)
                bot.acceptConsent(); bot.saveDraft("Must stay local"); bot.send()
                assertEquals(2, reads); assertTrue(bot.messages.isEmpty()); assertEquals("Must stay local", bot.draft)
            }
        }
    }

    @Test fun preSendReadCannotRestoreSpentQuotaAndNextDraftSurvivesReopen(): Unit = runBlocking(Dispatchers.Main) {
        Fixture().use { f ->
            val oldRead = CompletableDeferred<JSONObject>(); val posted = CompletableDeferred<JSONObject>()
            var reads = 0; var sends = 0; var requestID: String? = null
            f.handler = { method, path, body, device -> when (path) {
                "/v1/bot/allowance" -> if (++reads == 1) quota(1) else oldRead.await()
                "/v1/bot/messages" -> {
                    assertEquals("POST", method); assertEquals(f.credential, device); sends++
                    requestID = body!!.getString("request_id")
                    assertEquals("First prompt", body.getJSONArray("messages").getJSONObject(0).getString("content"))
                    posted.await()
                }
                else -> error("Unexpected endpoint")
            } }
            f.session().use { bot ->
                bot.acceptConsent(); bot.saveDraft("First prompt"); bot.refreshAllowance()
                val stale = launch(start = CoroutineStart.UNDISPATCHED) { bot.refreshAllowance() }
                val send = launch(start = CoroutineStart.UNDISPATCHED) { bot.send() }
                bot.saveDraft("Next draft while waiting"); bot.send(); assertEquals(1, sends)
                posted.complete(JSONObject().put("request_id", requestID).put("reply", "One confirmed reply").put("allowance", quota(0)))
                send.join(); oldRead.complete(quota(1)); stale.join()
                assertEquals(0, bot.allowance!!.remaining); assertEquals("Next draft while waiting", bot.draft)
                assertEquals(listOf("confirmed", "confirmed"), bot.messages.map { it.status })
            }
            f.session().use { reopened ->
                assertEquals(listOf("First prompt", "One confirmed reply"), reopened.messages.map { it.text })
                assertEquals("Next draft while waiting", reopened.draft); assertTrue(reopened.consent)
                reopened.send(); assertEquals(1, sends) // no quota refresh and no automatic replay
            }
            assertEquals(2, reads)
        }
    }

    @Test fun failedOlderReadDoesNotEraseNewerQuotaOrInjectError(): Unit = runBlocking(Dispatchers.Main) {
        Fixture().use { f ->
            val old = CompletableDeferred<JSONObject>(); var reads = 0
            f.handler = { _, _, _, _ -> if (++reads == 1) old.await() else quota(4) }
            f.session().use { bot ->
                val pending = launch(start = CoroutineStart.UNDISPATCHED) { bot.refreshAllowance() }
                bot.refreshAllowance(); old.completeExceptionally(IOException("Controlled older failure")); pending.join()
                assertEquals(4, bot.allowance!!.remaining); assertNull(bot.notice)
            }
        }
    }

    @Test fun confirmedReplyDoesNotInventAvailableAccess(): Unit = runBlocking(Dispatchers.Main) {
        Fixture().use { f ->
            var sends = 0
            f.handler = { _, path, body, _ -> if (path == "/v1/bot/allowance") quota(2) else {
                sends++; JSONObject().put("request_id", body!!.getString("request_id")).put("reply", "Confirmed before access changed")
                    .put("allowance", quota(1).put("available", false))
            } }
            f.session().use { bot ->
                bot.acceptConsent(); bot.saveDraft("Prompt"); bot.refreshAllowance(); bot.send()
                assertEquals(2, bot.messages.size); assertFalse(bot.allowance!!.available)
                bot.saveDraft("Not authorized"); bot.send(); assertEquals(1, sends); assertEquals("Not authorized", bot.draft)
            }
        }
    }

    @Test fun accountCloseDoesNotResurrectLateReplyOrLeakHistory(): Unit = runBlocking(Dispatchers.Main) {
        Fixture().use { f ->
            val response = CompletableDeferred<JSONObject>(); var requestID: String? = null; var sends = 0
            f.handler = { _, path, body, _ -> if (path == "/v1/bot/allowance") quota(2) else {
                sends++; requestID = body!!.getString("request_id"); response.await()
            } }
            val bot = f.session(); bot.acceptConsent(); bot.saveDraft("Only account A"); bot.refreshAllowance()
            val pending = launch(start = CoroutineStart.UNDISPATCHED) { bot.send() }
            bot.close()
            response.complete(JSONObject().put("request_id", requestID).put("reply", "Too late for closed account").put("allowance", quota(1)))
            pending.join()
            f.session().use { reopened -> assertEquals("unconfirmed", reopened.messages.single().status) }
            val other = UUID.randomUUID()
            try {
                BotSession(f.context, other, f.api).use { isolated ->
                    assertTrue(isolated.messages.isEmpty()); assertEquals("", isolated.draft); assertFalse(isolated.consent)
                }
            } finally { f.removeKey(other) }
            assertEquals(1, sends)
        }
    }

    @Test fun tiedAndBackwardClockKeepsNextPromptAfterPriorReplyAcrossReopen(): Unit = runBlocking(Dispatchers.Main) {
        Fixture().use { f ->
            var clock = 1000L
            var sends = 0
            f.handler = { _, path, body, _ -> if (path == "/v1/bot/allowance") quota(5) else {
                sends++
                JSONObject().put("request_id", body!!.getString("request_id")).put("reply", "Reply $sends").put("allowance", quota(5 - sends))
            } }
            BotSession(f.context, f.account, f.api) { clock }.use { bot ->
                bot.acceptConsent(); bot.refreshAllowance()
                bot.saveDraft("Prompt 1"); bot.send()
                clock = 999L // Wall clocks can tie or move backward; persisted message order cannot.
                bot.saveDraft("Prompt 2"); bot.send()
                assertEquals(listOf("Prompt 1", "Reply 1", "Prompt 2", "Reply 2"), bot.messages.map { it.text })
                assertEquals(bot.messages.map { it.id }.sorted(), bot.messages.map { it.id })
                assertEquals(listOf(1000L, 1001L, 1002L, 1003L), bot.messages.map { it.id.substring(1, 20).toLong() })
            }
            BotSession(f.context, f.account, f.api) { clock }.use { reopened ->
                assertEquals(listOf("Prompt 1", "Reply 1", "Prompt 2", "Reply 2"), reopened.messages.map { it.text })
                reopened.refreshAllowance(); reopened.saveDraft("Prompt 3"); reopened.send()
                assertEquals(1004L, reopened.messages[4].id.substring(1, 20).toLong())
                assertEquals(listOf("Prompt 1", "Reply 1", "Prompt 2", "Reply 2", "Prompt 3", "Reply 3"), reopened.messages.map { it.text })
            }
            assertEquals(3, sends)
        }
    }

    private class Fixture : AutoCloseable {
        private val base = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(base.cacheDir, "bot-workflow-${UUID.randomUUID()}").apply { mkdirs() }
        val context = object : ContextWrapper(base) { override fun getNoBackupFilesDir() = root }
        val account = UUID.randomUUID()
        val credential = MessageVault(context, account).use { vault -> DeviceCredential.load(vault).also { device ->
            vault.transaction { vault.put("local", "registered-device", device.id.toString().toByteArray()) }
        } }
        var handler: suspend (String, String, JSONObject?, DeviceCredential?) -> JSONObject = { _, _, _, _ -> error("Unexpected HTTP") }
        val api = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>) = handler(method, path, body, device)
        }
        fun session() = BotSession(context, account, api)
        fun removeKey(account: UUID) { KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") } }
        override fun close() { root.deleteRecursively(); removeKey(account) }
    }
    companion object {
        fun quota(remaining: Int) = JSONObject().put("available", true).put("service_ready", true)
            .put("remaining_replies", remaining).put("monthly_replies", 10).put("period", "2098-12")
            .put("resets_at", "2099-01-01T00:00:00Z").put("max_context_bytes", 8192)
    }
}
