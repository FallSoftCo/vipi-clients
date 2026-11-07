package co.fallsoft.vipi

import android.content.ContextWrapper
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.KeyStore
import java.util.UUID

class BotSessionDeviceTest {
    @Test fun explicitReportContainsOnlySelectedReplyAndUsesCurrentDevice(): Unit = runBlocking {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(base.cacheDir, "bot-report-${UUID.randomUUID()}").apply { mkdirs() }
        val context = object : ContextWrapper(base) { override fun getNoBackupFilesDir() = root }
        val account = UUID.randomUUID(); val requestID = UUID.randomUUID().toString()
        val assistant = BotMessage("m0000000000000000001-report", "assistant", "A reportable reply with more context.", "confirmed", requestID)
        var requests = 0
        lateinit var credential: DeviceCredential
        val api = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject {
                requests++; assertEquals("POST", method); assertEquals("/v1/bot/reports", path)
                assertEquals(credential, device); assertEquals(3, body!!.length())
                assertEquals(requestID, body.getString("request_id")); assertEquals("inaccurate", body.getString("reason"))
                assertEquals("reportable reply", body.getString("selected_reply"))
                assertFalse(body.toString().contains("PRIVATE_FRIEND"))
                return JSONObject().put("reported", true)
            }
        }
        try {
            MessageVault(context, account).use { vault ->
                credential = DeviceCredential.load(vault)
                vault.transaction {
                    vault.put("bot-message", assistant.id, assistant.json().toString().toByteArray())
                    vault.put("message", "private", "PRIVATE_FRIEND".toByteArray())
                }
            }
            BotSession(context, account, api).use { bot ->
                assertEquals(0, requests)
                assertTrue(runCatching { bot.report(assistant, "inaccurate", "Unrelated text") }.isFailure)
                assertEquals(0, requests)
                assertTrue(bot.report(assistant, "inaccurate", "reportable reply"))
                assertEquals(1, requests)
            }
            MessageVault(context, account).use { vault ->
                vault.transaction { assertArrayEquals(byteArrayOf(1), vault.get("bot-reported", requestID)) }
            }
        } finally {
            root.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
        }
    }
    @Test fun consentIsRequiredAndUncertainRequestSurvivesRestartWithoutResend() = runBlocking {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(base.cacheDir, "bot-${UUID.randomUUID()}").apply { mkdirs() }
        val context = object : ContextWrapper(base) { override fun getNoBackupFilesDir() = root }
        val account = UUID.randomUUID()
        var sends = 0
        val api = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject {
                if (path == "/v1/bot/allowance") return JSONObject().put("available", true).put("remaining_replies", 10).put("monthly_replies", 10)
                    .put("period", "2098-12").put("resets_at", "2099-01-01T00:00:00Z").put("max_context_bytes", 8192)
                assertEquals("/v1/bot/messages", path); assertEquals("POST", method); sends++
                assertEquals("deepseek-v1", body!!.getString("consent_version"))
                assertEquals(1, body.getJSONArray("messages").length())
                throw java.io.IOException("Simulated uncertain network outcome")
            }
        }
        try {
            MessageVault(context, account).use { it.transaction { it.put("message", "friend-private", "Never include this friend chat".toByteArray()) } }
            BotSession(context, account, api).use { bot ->
                bot.saveDraft("A private bot prompt"); bot.refreshAllowance(); bot.send(); assertEquals(0, sends)
                bot.acceptConsent(); bot.send(); assertEquals(1, sends); assertEquals("", bot.draft)
                assertEquals("unconfirmed", bot.messages.single().status); assertNull(bot.allowance)
            }
            BotSession(context, account, api).use { bot ->
                assertTrue(bot.consent); assertEquals("A private bot prompt", bot.messages.single().text)
                bot.refreshAllowance(); bot.send(); assertEquals(1, sends)
                assertEquals("unconfirmed", bot.messages.single().status)
            }
        } finally {
            root.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
        }
    }

    @Test fun contextIsBoundedByUtf8BytesAndExcludesUnconfirmedMessages() {
        val history = (0 until 30).map { BotMessage("$it", if (it % 2 == 0) "user" else "assistant", "界".repeat(500), "confirmed") } +
            BotMessage("uncertain", "user", "NEVER_REPEAT", "unconfirmed")
        val result = BotSession.contextFor(history, BotMessage("latest", "user", "🙂".repeat(500), "unconfirmed"))
        assertTrue(result.length() <= 12)
        assertEquals("user", result.getJSONObject(0).getString("role"))
        assertEquals("user", result.getJSONObject(result.length() - 1).getString("role"))
        assertTrue((0 until result.length()).sumOf { result.getJSONObject(it).getString("content").toByteArray(Charsets.UTF_8).size } <= 8192)
        assertFalse(result.toString().contains("NEVER_REPEAT"))
        assertTrue(runCatching { BotSession.contextFor(emptyList(), BotMessage("x", "user", "🙂".repeat(2049), "unconfirmed")) }.isFailure)
    }

    @Test fun invalidAllowanceCannotAuthorizeSending() {
        val value = JSONObject().put("available", true).put("remaining_replies", 11).put("monthly_replies", 10)
            .put("period", "2026-11").put("resets_at", "2026-12-01T00:00:00Z")
        assertTrue(runCatching { BotAllowance.parse(value) }.isFailure)
        assertTrue(runCatching { BotAllowance.parse(value.put("remaining_replies", -1)) }.isFailure)
        assertTrue(runCatching { BotAllowance.parse(value.put("remaining_replies", 2).put("resets_at", "not-a-date")) }.isFailure)
    }
}
