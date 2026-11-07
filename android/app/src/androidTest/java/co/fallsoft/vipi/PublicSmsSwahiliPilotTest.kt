package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.ImmersionText
import co.fallsoft.vipi.core.TranslationIntegrity
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.MessageDigest
import java.time.Instant

/** Fixed public research SMS through the actual production lookup/MLKit/lexical path. */
class PublicSmsSwahiliPilotTest {
    private class TrackingTranslation : LanguageTranslation {
        private val native = LocalTranslation()
        val calls = JSONArray()
        override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = native.prepare(source, target, cellularAllowed)
        override suspend fun translate(text: String, source: String, target: String): String {
            val began = android.os.SystemClock.elapsedRealtimeNanos()
            val row = JSONObject().put("source", source).put("target", target)
            try { return native.translate(text, source, target).also { row.put("translation", it).put("identifiers_preserved", TranslationIntegrity.preservesIdentifiers(text, it)) } }
            catch (failure: Exception) { row.put("error_class", failure.javaClass.simpleName); throw failure }
            finally { row.put("elapsed_ms", (android.os.SystemClock.elapsedRealtimeNanos() - began) / 1e6); calls.put(row) }
        }
        override fun close() = native.close()
    }
    @Test fun captureTwentyPublicSmsCasesInActualEnglishSwahiliPipeline(): Unit = runBlocking {
        check(InstrumentationRegistry.getArguments().getString("vipiPublicSmsPilot") == "true")
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val bytes = instrumentation.context.assets.open("native-pilot-protocol.json").use { it.readBytes() }
        fun sha(value: ByteArray) = MessageDigest.getInstance("SHA-256").digest(value).joinToString("") { "%02x".format(it) }
        val inputHash = sha(bytes)
        assertEquals("13cffd415c8b73a54686bf2401f75897e7154944eab7c9e9a71a6513d2f85dad", inputHash)
        val all = JSONObject(bytes.toString(Charsets.UTF_8)).getJSONArray("cases")
        val cases = (0 until all.length()).map(all::getJSONObject).filter { it.getString("source") == "en" && it.getString("target") == "sw" }
        assertEquals(20, cases.size)
        val revision = InstrumentationRegistry.getArguments().getString("vipiPilotRun") ?: "001"
        require(revision.matches(Regex("[0-9]{3}")))
        val out = File(context.filesDir, "public-sms-sw-$revision.json"); check(!out.exists())
        val rows = JSONArray()
        val report = JSONObject().put("input_sha256", inputHash).put("started_at", Instant.now().toString()).put("complete", false)
            .put("provider", "Google ML Kit translate 17.0.3 on device").put("translation_reused", false).put("input_language_override", JSONObject.NULL)
            .put("network_observation", "Models prepared before capture. No network translation API configured; packet-level offline observation not performed.")
            .put("catalog_sha256", sha(context.assets.open("immersion/catalog.json").use { it.readBytes() }))
            .put("lexical_catalog_sha256", sha(context.assets.open("lexical/catalog.json").use { it.readBytes() })).put("cases", rows)
        out.writeText(report.toString(2))
        try {
            withTimeout(600_000) { LocalTranslation().use { it.prepare("en", "sw", true) } }
            for (item in cases) {
                val original = item.getString("text")
                val row = JSONObject().put("id", item.getString("id")).put("source", "en").put("target", "sw").put("original", original)
                    .put("native_source_word_ranges", JSONArray().apply { LocalImmersion.words(original, "en").forEach { put(JSONArray(listOf(it.first, it.last + 1))) } })
                val densities = JSONArray(); row.put("densities", densities); rows.put(row)
                for (density in listOf(.25, 1.0)) {
                    val tracking = TrackingTranslation()
                    ConversationImmersion(context, "en", "sw", density, tracking).use { engine ->
                        val result = JSONObject().put("density", density).put("provider_calls", tracking.calls)
                        val began = android.os.SystemClock.elapsedRealtimeNanos()
                        try {
                            engine.checkDownloads()
                            val value = withTimeout(90_000) { engine.presentation(original) }
                            val outcome = engine.lastOutcome
                            result.put("status", outcome?.status?.name ?: "NO_OUTCOME").put("path", outcome?.origin?.name ?: JSONObject.NULL)
                                .put("local_translation_calls", outcome?.localTranslationCalls ?: 0).put("fallback_status", outcome?.fallbackStatus?.name ?: JSONObject.NULL)
                                .put("complete_translation", value?.translation ?: JSONObject.NULL)
                                .put("visible", value?.let { ImmersionText.project(it) } ?: original)
                                .put("lexical_preparation", engine.lexicalPreparation)
                                .put("spans", JSONArray().apply { value?.spans?.forEach { s -> put(JSONObject().put("original", s.original).put("translated", s.translated)
                                    .put("sourceStartUTF16", s.start).put("sourceEndUTF16", s.end).put("targetStartUTF16", s.targetStart).put("targetEndUTF16", s.targetEnd)
                                    .put("reading", s.romanization ?: JSONObject.NULL)) } })
                        } catch (failure: Exception) { result.put("error_class", failure.javaClass.simpleName) }
                        finally { result.put("elapsed_ms", (android.os.SystemClock.elapsedRealtimeNanos() - began) / 1e6); densities.put(result); out.writeText(report.toString(2)) }
                    }
                }
            }
            report.put("complete", true)
        } finally { report.put("finished_at", Instant.now().toString()); out.writeText(report.toString(2)) }
    }
}
