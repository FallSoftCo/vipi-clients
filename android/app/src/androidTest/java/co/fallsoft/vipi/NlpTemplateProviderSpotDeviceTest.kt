package co.fallsoft.vipi

import android.net.ConnectivityManager
import android.os.Debug
import android.os.SystemClock
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.ImmersionPresentation
import co.fallsoft.vipi.core.ImmersionText
import co.fallsoft.vipi.core.TranslationIntegrity
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.time.Instant

/** Current clean app route only. No template provider, manufactured reference or model download. */
class NlpTemplateProviderSpotDeviceTest {
    private class Tracking(private val network: ConnectivityManager) : LanguageTranslation {
        private val native = LocalTranslation()
        val calls = JSONArray()
        override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = error("No model downloads")
        override suspend fun translate(text: String, source: String, target: String): String {
            assertNull(network.activeNetwork)
            val row = JSONObject().put("input", text).put("source", source).put("target", target); calls.put(row)
            val start = SystemClock.elapsedRealtimeNanos()
            try {
                return withTimeout(30_000) { native.translate(text, source, target) }.also { row.put("translation", it)
                    .put("identifiers_preserved", TranslationIntegrity.preservesIdentifiers(text, it)) }
            } catch (error: Throwable) { row.put("error", error.javaClass.simpleName); throw error }
            finally { row.put("elapsed_ms", (SystemClock.elapsedRealtimeNanos() - start) / 1e6); assertNull(network.activeNetwork) }
        }
        override fun close() = native.close()
    }
    private fun presentation(value: ImmersionPresentation?): Any = value?.let { result -> JSONObject()
        .put("complete_translation", result.translation ?: JSONObject.NULL).put("mixed", ImmersionText.project(result))
        .put("spans", JSONArray(result.spans.map { span -> JSONObject().put("original", span.original).put("target", span.translated)
            .put("reading", span.romanization ?: JSONObject.NULL).put("source_range_utf16", JSONArray(listOf(span.start, span.end))) }))
    } ?: JSONObject.NULL

    @Test fun captureCurrentRouteOnFrozenSources(): Unit = runBlocking {
        val ins = InstrumentationRegistry.getInstrumentation(); val args = InstrumentationRegistry.getArguments()
        require(args.getString("vipiDedicatedEmulator") == "true")
        require(android.os.Build.MODEL.contains("sdk_gphone") || android.os.Build.FINGERPRINT.contains("generic"))
        val run = requireNotNull(args.getString("vipiNlpRun")).also { require(it.matches(Regex("[0-9]{3}"))) }
        val context = ins.targetContext; val network = context.getSystemService(ConnectivityManager::class.java)
        assertNull(network.activeNetwork)
        val input = File(context.filesDir, "nlp-template-inputs-r01/provider-spot-protocol.json").readBytes()
        val expected = "9ee9c3d25da7fd8acc1e10054e654ec6d4652f8ebcf44d79368e18b255669d83"
        assertEquals(expected, NlpTemplateQaCatalog.sha(input))
        val protocol = JSONObject(input.toString(Charsets.UTF_8)); val cases = protocol.getJSONArray("cases")
        assertEquals(12, cases.length()); assertEquals(12, (0 until cases.length()).map { cases.getJSONObject(it).getString("id") }.distinct().size)
        val output = File(context.filesDir, "nlp-template-provider-$run.json"); check(!output.exists())
        val report = JSONObject().put("schema", "vipi-android-nlp-current-provider-spot-1").put("complete", false)
            .put("input_sha256", expected).put("production", false).put("candidate_source_unit_provider", "absent")
            .put("density", .25).put("started_at", Instant.now().toString()).put("model_downloads", 0)
            .put("mask_limitation", "Existing nullable source-result contract cannot carry template atomic scopes into provider/alignment. This is the unchanged route, not a safety claim.")
        val rows = JSONArray(); val pairs = JSONArray(); report.put("cases", rows).put("pairs", pairs)
        fun save() { val temp = File(output.parentFile, output.name + ".tmp"); temp.writeText(report.toString(2)); check(temp.renameTo(output)) }
        save()
        try {
            withTimeout(600_000) {
                for (target in listOf("sw", "ja", "es")) for (mode in listOf("explicit_en", "automatic_language")) {
                    val tracker = Tracking(network)
                    ConversationImmersion(context, "en", target, .25, translator = tracker).use { engine ->
                        val at = SystemClock.elapsedRealtimeNanos(); engine.checkDownloads()
                        val info = Debug.MemoryInfo(); Debug.getMemoryInfo(info)
                        val pair = JSONObject().put("source", "en").put("target", target).put("mode", mode)
                            .put("installed_models_ready", engine.ready).put("status_elapsed_ms", (SystemClock.elapsedRealtimeNanos() - at) / 1e6)
                            .put("pss_kib", info.totalPss); pairs.put(pair); save()
                        if (engine.ready != true) { pair.put("skipped", "existing_models_unavailable_no_download"); return@use }
                        for (index in 0 until cases.length()) {
                            val inputCase = cases.getJSONObject(index); val text = inputCase.getString("text")
                            val selectedLanguage = if (mode == "explicit_en") "en" else null
                            val row = JSONObject().put("id", inputCase.getString("id")).put("text", text).put("source", "en").put("target", target)
                                .put("mode", mode).put("native_source_word_ranges_utf16", JSONArray(LocalImmersion.words(text, "en").map { JSONArray(listOf(it.first, it.last + 1)) }))
                            rows.put(row); val phases = JSONArray(); row.put("phases", phases); val startCall = tracker.calls.length()
                            for (phase in listOf("automatic_first", "automatic_warm", "explicit_full")) {
                                val before = tracker.calls.length(); val began = SystemClock.elapsedRealtimeNanos()
                                val result = JSONObject().put("phase", phase); phases.put(result)
                                try {
                                    val value = if (phase == "explicit_full") engine.fullTranslation(text, selectedLanguage, null, engine.newFullTranslationEpoch()).result
                                        else engine.presentation(text, selectedLanguage)
                                    result.put("presentation", presentation(value)).put("status", engine.lastOutcome?.status?.name)
                                        .put("origin", engine.lastOutcome?.origin?.name).put("cache_hit", engine.lastOutcome?.cacheHit)
                                        .put("fallback_status", engine.lastOutcome?.fallbackStatus?.name).put("lexical_preparation", engine.lexicalPreparation)
                                } catch (error: Exception) { result.put("error", error.javaClass.simpleName); if (error is CancellationException) throw error }
                                finally {
                                    val counter = engine.lastInvocation
                                    result.put("elapsed_ms", (SystemClock.elapsedRealtimeNanos() - began) / 1e6).put("provider_calls", tracker.calls.length() - before)
                                        .put("readiness_calls", counter.readiness).put("heavy_alignment_calls", counter.heavyAlignment)
                                        .put("source_partial_presentation_calls", counter.partialPresentation)
                                }
                            }
                            row.put("raw_provider_calls", JSONArray((startCall until tracker.calls.length()).map(tracker.calls::getJSONObject))); save()
                        }
                    }
                }
            }
            report.put("complete", true)
        } finally { report.put("finished_at", Instant.now().toString()); save(); assertNull(network.activeNetwork) }
    }
}
