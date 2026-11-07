package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.ImmersionText
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.MessageDigest
import java.time.Instant

/** Reuses frozen actual provider strings. Never creates a translator or calls an inference service. */
class SourceBoundaryReplayNativeTest {
    private class Fixed(private val values: Map<Triple<String, String, String>, String>) : LanguageTranslation {
        var calls = 0
        val unexpected = JSONArray()
        override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = Unit
        override suspend fun translate(text: String, source: String, target: String): String {
            calls++
            return values[Triple(source, target, text)] ?: run {
                unexpected.put(JSONObject().put("source", source).put("target", target).put("text", text))
                error("Unexpected frozen-provider query")
            }
        }
        override fun close() = Unit
    }
    @Test fun replayFrozenSpanishInputsWithoutPartialFiniteVerbRoots() = runBlocking {
        check(InstrumentationRegistry.getArguments().getString("vipiSourceBoundaryReplay") == "true")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val input = File(context.filesDir, "source-boundary-replay-protocol.json").readBytes()
        val expected = "a1428d698e5eef38c940f9c843332f8d9214923e910c5862168367f2d65000b5"
        assertEquals(expected, MessageDigest.getInstance("SHA-256").digest(input).joinToString("") { "%02x".format(it) })
        val cases = JSONObject(input.toString(Charsets.UTF_8)).getJSONArray("cases").let { a -> (0 until a.length()).map(a::getJSONObject) }
        assertEquals(200, cases.size)
        val values = cases.associate { Triple(it.getString("source"), it.getString("target"), it.getString("text")) to it.getString("translation") }
        val output = File(context.filesDir, "source-boundary-replay-001.json"); check(!output.exists())
        val rows = JSONArray()
        val report = JSONObject().put("input_sha256", expected).put("started_at", Instant.now().toString())
            .put("complete", false).put("translation_reused", true).put("new_provider_calls", 0).put("cases", rows)
        val engines = listOf(.25, 1.0).associateWith { density ->
            val provider = Fixed(values)
            ConversationImmersion(context, "es", "en", density, provider) to provider
        }
        var forbidden = 0
        fun save() = output.writeText(report.toString(2))
        try {
            withTimeout(600_000) {
                engines.values.forEach { it.first.checkDownloads() }
                for (inputRow in cases) {
                    val text = inputRow.getString("text")
                    val row = JSONObject().put("id", inputRow.getString("id")).put("source", "es").put("target", "en").put("original", text)
                    val outcomes = JSONArray(); row.put("densities", outcomes); rows.put(row)
                    val banned = inputRow.getJSONArray("forbidden_partial_source_ranges").let { a -> (0 until a.length()).map { a.getJSONArray(it).let { range -> range.getInt(0) to range.getInt(1) } }.toSet() }
                    for ((density, state) in engines) {
                        val (engine, provider) = state; val calls = provider.calls
                        val result = JSONObject().put("density", density); outcomes.put(result)
                        try {
                            val presentation = engine.presentation(text)
                            result.put("status", engine.lastOutcome?.status?.name ?: "NO_OUTCOME")
                                .put("path", engine.lastOutcome?.origin?.name ?: JSONObject.NULL)
                                .put("complete_translation", presentation?.translation ?: JSONObject.NULL)
                                .put("visible", presentation?.let { ImmersionText.project(it) } ?: text)
                            val spans = JSONArray()
                            presentation?.spans?.forEach { span ->
                                val bad = (span.start to span.end) in banned
                                if (bad) forbidden++
                                spans.put(JSONObject().put("original", span.original).put("translated", span.translated)
                                    .put("sourceStartUTF16", span.start).put("sourceEndUTF16", span.end)
                                    .put("targetStartUTF16", span.targetStart).put("targetEndUTF16", span.targetEnd)
                                    .put("reading", span.romanization ?: JSONObject.NULL).put("forbidden_partial", bad))
                            }
                            result.put("spans", spans)
                        } catch (failure: Exception) { result.put("error_class", failure.javaClass.simpleName) }
                        result.put("fixed_provider_queries", provider.calls - calls)
                    }
                    save()
                }
                report.put("complete", true)
            }
        } finally {
            engines.values.forEach { it.first.close() }
            report.put("forbidden_partial_spans", forbidden).put("unexpected_provider_queries", JSONArray(engines.values.flatMap { state ->
                (0 until state.second.unexpected.length()).map(state.second.unexpected::getJSONObject)
            })).put("finished_at", Instant.now().toString()); save()
        }
        assertEquals("Finite verb roots must not be emitted inside their source carrier", 0, forbidden)
    }
}
