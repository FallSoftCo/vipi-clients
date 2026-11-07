package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.ImmersionText
import co.fallsoft.vipi.core.TranslationIntegrity
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.MessageDigest
import java.time.Instant

/** Held-out public SMS only. Never imported by a production catalog builder. */
class CoverageCeilingNativeTest {
    private class TrackingTranslation : LanguageTranslation {
        private val native = LocalTranslation()
        val calls = mutableListOf<JSONObject>()
        override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = native.prepare(source, target, cellularAllowed)
        override suspend fun translate(text: String, source: String, target: String): String {
            val began = android.os.SystemClock.elapsedRealtimeNanos()
            val row = JSONObject().put("source", source).put("target", target)
            try {
                return native.translate(text, source, target).also {
                    row.put("translation", it).put("identifiers_preserved", TranslationIntegrity.preservesIdentifiers(text, it))
                    row.put("native_target_word_ranges", ranges(it, target))
                }
            } catch (failure: Exception) { row.put("error_class", failure.javaClass.simpleName); throw failure }
            finally { row.put("elapsed_ms", (android.os.SystemClock.elapsedRealtimeNanos() - began) / 1e6); calls.add(row) }
        }
        override fun close() = native.close()
    }

    @Test fun captureFrozenUnseenConversationSample(): Unit = runBlocking {
        check(InstrumentationRegistry.getArguments().getString("vipiCoverageCeiling") == "true")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val input = File(context.filesDir, "coverage-ceiling-native-protocol.json").readBytes()
        val arm = InstrumentationRegistry.getArguments().getString("vipiEvaluationArm") ?: "original"
        val expected = when (arm) {
            "original" -> "2b1fdf67eed1f52a0323e678730c34f5805fc1d300a999a521bef4b8d2a26471"
            "normalization" -> "d1d6909714c810ae1d188941fe6412679bebc391f4cf0bab7a787b2dc3358dde"
            "taskmaster" -> "ee7b48847333461e6f2ac7ba584f6bef00740181232ad3dfc29310cb5a7782f0"
            "directional" -> "aec5ced94bc82c071f16f568b078703a4460841201c079bf78eb0edaab9c9e73"
            else -> error("Unregistered evaluation protocol")
        }
        assertEquals(expected, sha(input))
        val array = JSONObject(input.toString(Charsets.UTF_8)).getJSONArray("cases")
        val cases = (0 until array.length()).map(array::getJSONObject)
        val perLanguage = if (arm == "normalization") 41 else 200
        assertEquals(perLanguage * 2, cases.size)
        val pairs = cases.map { it.getString("source") to it.getString("target") }.distinct()
        val expectedPairs = if (arm == "directional") listOf("en" to "ja", "es" to "en") else listOf("en" to "sw", "en" to "es")
        assertEquals(expectedPairs.toSet(), pairs.toSet())
        for ((source, target) in expectedPairs) assertEquals(perLanguage, cases.count { it.getString("source") == source && it.getString("target") == target })
        val run = InstrumentationRegistry.getArguments().getString("vipiPilotRun") ?: "001"
        require(run.matches(Regex("[0-9]{3}")))
        val stem = when (arm) { "normalization" -> "normalized-ceiling"; "taskmaster" -> "taskmaster-ceiling"; "directional" -> "directional-ceiling"; else -> "coverage-ceiling" }
        val output = File(context.filesDir, "$stem-$run.json"); check(!output.exists())
        val rows = JSONArray()
        val report = JSONObject().put("input_sha256", expected).put("started_at", Instant.now().toString()).put("complete", false)
            .put("evaluation_arm", arm)
            .put("provider", "Google ML Kit translate 17.0.3 on device").put("translation_reused", false)
            .put("engine_reused_between_messages", true).put("input_language_override", JSONObject.NULL)
            .put("network_observation", "Native models prepared before capture; no remote translation API. Packet-level offline observation not performed.")
            .put("evaluation_probe_policy", "If both production densities make no translation request, a separate native full translation measures the evaluation ceiling only; never enters production presentation or call count.")
            .put("catalog_sha256", sha(context.assets.open("immersion/catalog.json").use { it.readBytes() }))
            .put("lexical_catalog_sha256", sha(context.assets.open("lexical/catalog.json").use { it.readBytes() })).put("cases", rows)
        fun save() = output.writeText(report.toString(2))
        val engines = mutableMapOf<Triple<String, String, Double>, Pair<ConversationImmersion, TrackingTranslation>>()
        val evaluation = mutableMapOf<Pair<String, String>, TrackingTranslation>()
        save()
        try {
            withTimeout(2_700_000) {
                for ((source, target) in pairs) {
                    withTimeout(600_000) { LocalTranslation().use { it.prepare(source, target, true) } }
                    evaluation[source to target] = TrackingTranslation()
                    for (density in listOf(.25, 1.0)) {
                        val tracker = TrackingTranslation()
                        val engine = ConversationImmersion(context, source, target, density, tracker)
                        engine.checkDownloads()
                        engines[Triple(source, target, density)] = engine to tracker
                    }
                }
                report.put("models_prepared_at", Instant.now().toString()); save()
                for (item in cases) {
                    currentCoroutineContext().ensureActive()
                    val original = item.getString("text"); val source = item.getString("source"); val target = item.getString("target")
                    val densities = JSONArray()
                    val row = JSONObject().put("id", item.getString("id")).put("source", source).put("target", target)
                        .put("original", original).put("native_source_word_ranges", ranges(original, source)).put("densities", densities)
                    for (field in listOf("original_text", "original_id", "normalization_segments")) if (item.has(field)) row.put(field, item.get(field))
                    rows.put(row)
                    var productionCalls = 0
                    for (density in listOf(.25, 1.0)) {
                        val (engine, tracker) = engines.getValue(Triple(source, target, density))
                        val firstCall = tracker.calls.size
                        val value = JSONObject().put("density", density)
                        val began = android.os.SystemClock.elapsedRealtimeNanos()
                        try {
                            val presentation = withTimeout(90_000) { engine.presentation(original) }
                            val outcome = engine.lastOutcome
                            value.put("status", outcome?.status?.name ?: "NO_OUTCOME").put("path", outcome?.origin?.name ?: JSONObject.NULL)
                                .put("local_translation_calls", outcome?.localTranslationCalls ?: 0).put("fallback_status", outcome?.fallbackStatus?.name ?: JSONObject.NULL)
                                .put("complete_translation", presentation?.translation ?: JSONObject.NULL)
                                .put("visible", presentation?.let { ImmersionText.project(it) } ?: original)
                                .put("lexical_preparation", engine.lexicalPreparation)
                                .put("spans", JSONArray().apply { presentation?.spans?.forEach { span ->
                                    put(JSONObject().put("original", span.original).put("translated", span.translated)
                                        .put("sourceStartUTF16", span.start).put("sourceEndUTF16", span.end)
                                        .put("targetStartUTF16", span.targetStart).put("targetEndUTF16", span.targetEnd)
                                        .put("reading", span.romanization ?: JSONObject.NULL))
                                } })
                        } catch (failure: Exception) {
                            currentCoroutineContext().ensureActive()
                            value.put("error_class", failure.javaClass.simpleName)
                        } finally {
                            val calls = tracker.calls.drop(firstCall); productionCalls += calls.size
                            value.put("provider_calls", JSONArray(calls)).put("elapsed_ms", (android.os.SystemClock.elapsedRealtimeNanos() - began) / 1e6)
                            densities.put(value); save()
                        }
                    }
                    if (productionCalls == 0) {
                        val tracker = evaluation.getValue(source to target); val first = tracker.calls.size
                        try { withTimeout(90_000) { tracker.translate(original, source, target) } }
                        catch (failure: Exception) { currentCoroutineContext().ensureActive() }
                        finally {
                            row.put("evaluation_full_translation_probe", tracker.calls.drop(first).singleOrNull() ?: JSONObject().put("error_class", "NoProviderResult"))
                            save()
                        }
                    }
                }
                report.put("complete", true)
            }
        } finally {
            engines.values.forEach { it.first.close() }; evaluation.values.forEach { it.close() }
            report.put("finished_at", Instant.now().toString()); save()
        }
    }
    companion object {
        private fun ranges(text: String, language: String) = JSONArray().apply {
            LocalImmersion.words(text, language).forEach { put(JSONArray(listOf(it.first, it.last + 1))) }
        }
        private fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
    }
}
