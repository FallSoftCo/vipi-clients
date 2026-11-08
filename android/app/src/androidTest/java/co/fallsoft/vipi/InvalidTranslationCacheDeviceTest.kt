package co.fallsoft.vipi

import android.net.ConnectivityManager
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.ImmersionStatus
import co.fallsoft.vipi.core.TranslationIntegrity
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File

class InvalidTranslationCacheDeviceTest {
    private class Counting(private val fixed: String? = null) : LanguageTranslation {
        private val native = if (fixed == null) LocalTranslation() else null
        val calls = JSONArray()
        override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = error("No downloads")
        override suspend fun translate(text: String, source: String, target: String): String {
            val translated = fixed ?: withTimeout(30_000) { requireNotNull(native).translate(text, source, target) }
            calls.put(JSONObject().put("original", text).put("translation", translated)
                .put("identifiers_preserved", TranslationIntegrity.preservesIdentifiers(text, translated)))
            return translated
        }
        override fun close() { native?.close() }
    }
    @Test fun repeatedAutomaticRejectionAndExplicitRetry(): Unit = runBlocking {
        val ins = InstrumentationRegistry.getInstrumentation(); val args = InstrumentationRegistry.getArguments()
        require(args.getString("vipiDedicatedEmulator") == "true")
        val run = requireNotNull(args.getString("vipiInvalidCacheRun")).also { require(it.matches(Regex("[0-9]{3}"))) }
        val context = ins.targetContext; val connectivity = context.getSystemService(ConnectivityManager::class.java)
        assertNull(connectivity.activeNetwork)
        val output = File(context.filesDir, "invalid-result-cache-$run.json"); check(!output.exists())
        val rows = JSONArray(); val report = JSONObject().put("complete", false).put("cases", rows).put("model_downloads", 0)
            .put("actual_model_changes", false).put("network_offline", true)
        fun save() { output.writeText(report.toString(2)) }
        try {
            val fixtures = listOf(Triple("fake_identifier", "Send @alice a message.", "sw"),
                Triple("nlp-r01-phone_number-007", "There is a phone number at alice@example.com.", "ja"),
                Triple("nlp-r01-phone_number-004", "Check the phone number at https://example.com/contact.", "ja"))
            for ((id, text, target) in fixtures) {
                val provider = Counting(if (id == "fake_identifier") "Tuma ujumbe kwa @bob." else null)
                ConversationImmersion(context, "en", target, .25, translator = provider,
                    qaModelsReady = if (id == "fake_identifier") true else null).use { engine ->
                    engine.checkDownloads(); assertEquals(true, engine.ready)
                    val row = JSONObject().put("id", id).put("text", text).put("target", target)
                        .put("actual_native_provider", id != "fake_identifier").put("raw_provider_calls", provider.calls)
                    val counts = JSONArray(); row.put("automatic_cumulative_calls", counts); rows.put(row)
                    repeat(3) {
                        assertNull(engine.presentation(text, "en")); assertEquals(ImmersionStatus.INVALID_RESULT, engine.lastOutcome!!.status)
                        counts.put(provider.calls.length()); save()
                    }
                    val epoch = engine.newFullTranslationEpoch()
                    assertEquals(ImmersionStatus.INVALID_RESULT, engine.fullTranslation(text, "en", null, epoch).status)
                    val afterExplicit = provider.calls.length()
                    assertEquals(ImmersionStatus.INVALID_RESULT, engine.fullTranslation(text, "en", null, epoch).status)
                    assertEquals(afterExplicit, provider.calls.length())
                    assertEquals(ImmersionStatus.INVALID_RESULT, engine.fullTranslation(text, "en", null, engine.newFullTranslationEpoch()).status)
                    row.put("same_epoch_deduplicated", true).put("new_explicit_epoch_added_one_call", provider.calls.length() == afterExplicit + 1)
                    assertEquals(afterExplicit + 1, provider.calls.length())
                    val beforeAutomatic = provider.calls.length(); assertNull(engine.presentation(text, "en"))
                    row.put("automatic_after_explicit_added_calls", provider.calls.length() - beforeAutomatic); save()
                }
            }
            report.put("captured_all", true); save()
            for (i in 0 until rows.length()) {
                val row = rows.getJSONObject(i)
                assertEquals("${row.getString("id")}: automatic reentry must not reinfer", "[1,1,1]", row.getJSONArray("automatic_cumulative_calls").toString())
                assertEquals(0, row.getInt("automatic_after_explicit_added_calls"))
            }
            report.put("complete", true)
        } finally { save(); assertNull(connectivity.activeNetwork) }
    }
}
