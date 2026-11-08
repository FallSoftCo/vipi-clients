package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.ImmersionText
import co.fallsoft.vipi.core.TranslationIntegrity
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.delay
import kotlinx.coroutines.tasks.await
import android.net.ConnectivityManager
import com.google.mlkit.common.model.RemoteModelManager
import com.google.mlkit.nl.translate.TranslateRemoteModel
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.MessageDigest
import java.time.Instant

/** Held-out public SMS only. Never imported by a production catalog builder. */
class CoverageCeilingNativeTest {
    private class TrackingTranslation(private val offlineCheck: (() -> Unit)? = null) : LanguageTranslation {
        private val native = LocalTranslation()
        val calls = mutableListOf<JSONObject>()
        override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = native.prepare(source, target, cellularAllowed)
        override suspend fun translate(text: String, source: String, target: String): String {
            offlineCheck?.invoke()
            val began = android.os.SystemClock.elapsedRealtimeNanos()
            val row = JSONObject().put("source", source).put("target", target)
            try {
                return native.translate(text, source, target).also {
                    row.put("translation", it).put("identifiers_preserved", TranslationIntegrity.preservesIdentifiers(text, it))
                    row.put("native_target_word_ranges", ranges(it, target))
                }
            } catch (failure: Exception) { row.put("error_class", failure.javaClass.simpleName); throw failure }
            finally {
                offlineCheck?.invoke()
                if (offlineCheck != null) row.put("active_network", "none")
                row.put("elapsed_ms", (android.os.SystemClock.elapsedRealtimeNanos() - began) / 1e6); calls.add(row)
            }
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
            "conversational" -> "76545660657732d09a98ac749cec9365292479c9d0a463563dfbe46e4e986586"
            else -> error("Unregistered evaluation protocol")
        }
        assertEquals(expected, sha(input))
        val array = JSONObject(input.toString(Charsets.UTF_8)).getJSONArray("cases")
        val cases = (0 until array.length()).map(array::getJSONObject)
        val fresh = arm == "conversational"
        val perLanguage = if (fresh) 80 else if (arm == "normalization") 41 else 200
        assertEquals(perLanguage * if (fresh) 1 else 2, cases.size)
        val pairs = cases.map { it.getString("source") to it.getString("target") }.distinct()
        val expectedPairs = if (fresh) listOf("en" to "sw") else if (arm == "directional") listOf("en" to "ja", "es" to "en") else listOf("en" to "sw", "en" to "es")
        assertEquals(expectedPairs.toSet(), pairs.toSet())
        for ((source, target) in expectedPairs) assertEquals(perLanguage, cases.count { it.getString("source") == source && it.getString("target") == target })
        val run = InstrumentationRegistry.getArguments().getString("vipiPilotRun") ?: "001"
        require(run.matches(Regex("[0-9]{3}")))
        val stem = when (arm) { "conversational" -> "conversational-routing"; "normalization" -> "normalized-ceiling"; "taskmaster" -> "taskmaster-ceiling"; "directional" -> "directional-ceiling"; else -> "coverage-ceiling" }
        val output = File(context.filesDir, "$stem-$run.json"); check(!output.exists())
        val rows = JSONArray()
        val report = JSONObject().put("input_sha256", expected).put("started_at", Instant.now().toString()).put("complete", false)
            .put("evaluation_arm", arm)
            .put("provider", "Google ML Kit translate 17.0.3 on device").put("translation_reused", false)
            .put("engine_reused_between_messages", true).put("input_language_override", JSONObject.NULL)
            .put("process_pss_kib_start", android.os.Debug.getPss()).put("process_id", android.os.Process.myPid())
            .put("network_observation", "Native models prepared before capture; no remote translation API. Packet-level offline observation not performed.")
            .put("evaluation_probe_policy", "If both production densities make no translation request, a separate native full translation measures the evaluation ceiling only; never enters production presentation or call count.")
            .put("catalog_sha256", sha(context.assets.open("immersion/catalog.json").use { it.readBytes() }))
            .put("lexical_catalog_sha256", sha(context.assets.open("lexical/catalog.json").use { it.readBytes() })).put("cases", rows)
        fun save() = output.writeText(report.toString(2))
        val engines = mutableMapOf<Triple<String, String, Double>, Pair<ConversationImmersion, TrackingTranslation>>()
        val evaluation = mutableMapOf<Pair<String, String>, TrackingTranslation>()
        val densitiesToTest = if (fresh) listOf(.10, .25, .50) else listOf(.25, 1.0)
        val network = context.getSystemService(ConnectivityManager::class.java)
        fun shell(command: String) = InstrumentationRegistry.getInstrumentation().uiAutomation.executeShellCommand(command).use {
            java.io.FileInputStream(it.fileDescriptor).bufferedReader().use { stream -> stream.readText() }
        }
        val wifi = if (fresh) shell("settings get global wifi_on").trim() else ""
        val mobile = if (fresh) shell("settings get global mobile_data").trim() else ""
        var changedNetwork = false
        val offlineCheck: (() -> Unit)? = if (fresh) ({ assertNull(network.activeNetwork) }) else null
        save()
        try {
            withTimeout(if (fresh) 1_800_000 else 2_700_000) {
                if (fresh) {
                    check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
                    check(android.os.Build.FINGERPRINT.contains("generic") || android.os.Build.MODEL.contains("sdk_gphone"))
                    assertTrue("Swahili model must already be installed", RemoteModelManager.getInstance()
                        .isModelDownloaded(TranslateRemoteModel.Builder("sw").build()).await())
                    changedNetwork = true; shell("svc wifi disable"); shell("svc data disable")
                    withTimeout(15_000) { while (network.activeNetwork != null) delay(100) }
                    assertNull(network.activeNetwork)
                    report.put("network_observation", "Emulator Wi-Fi/data disabled; activeNetwork absent before/after every actual provider call. No model download API invoked.")
                        .put("warm_repeat_per_message", true)
                }
                for ((source, target) in pairs) {
                    if (!fresh) withTimeout(600_000) { LocalTranslation().use { it.prepare(source, target, true) } }
                    evaluation[source to target] = TrackingTranslation(offlineCheck)
                    for (density in densitiesToTest) {
                        val tracker = TrackingTranslation(offlineCheck)
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
                    for (density in densitiesToTest) {
                        val (engine, tracker) = engines.getValue(Triple(source, target, density))
                        val firstCall = tracker.calls.size
                        val value = JSONObject().put("density", density)
                        val began = android.os.SystemClock.elapsedRealtimeNanos()
                        try {
                            val presentation = withTimeout(if (fresh) 30_000L else 90_000L) { engine.presentation(original) }
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
                        if (fresh) {
                            val firstWarmCall = tracker.calls.size
                            val warm = JSONObject(); val warmBegan = android.os.SystemClock.elapsedRealtimeNanos()
                            try {
                                val presentation = withTimeout(30_000) { engine.presentation(original) }
                                val outcome = engine.lastOutcome
                                warm.put("status", outcome?.status?.name ?: "NO_OUTCOME").put("path", outcome?.origin?.name ?: JSONObject.NULL)
                                    .put("local_translation_calls", outcome?.localTranslationCalls ?: 0)
                                    .put("complete_translation", presentation?.translation ?: JSONObject.NULL)
                                    .put("visible", presentation?.let { ImmersionText.project(it) } ?: original)
                                    .put("spans", JSONArray().apply { presentation?.spans?.forEach { span ->
                                        put(JSONObject().put("original", span.original).put("translated", span.translated)
                                            .put("sourceStartUTF16", span.start).put("sourceEndUTF16", span.end)
                                            .put("targetStartUTF16", span.targetStart).put("targetEndUTF16", span.targetEnd)
                                            .put("reading", span.romanization ?: JSONObject.NULL))
                                    } })
                            } catch (failure: Exception) { currentCoroutineContext().ensureActive(); warm.put("error_class", failure.javaClass.simpleName) }
                            finally {
                                val calls = tracker.calls.drop(firstWarmCall); productionCalls += calls.size
                                warm.put("provider_calls", JSONArray(calls)).put("elapsed_ms", (android.os.SystemClock.elapsedRealtimeNanos() - warmBegan) / 1e6)
                                value.put("warm_repeat", warm); save()
                            }
                        }
                    }
                    if (productionCalls == 0) {
                        val tracker = evaluation.getValue(source to target); val first = tracker.calls.size
                        try { withTimeout(if (fresh) 30_000L else 90_000L) { tracker.translate(original, source, target) } }
                        catch (failure: Exception) { currentCoroutineContext().ensureActive() }
                        finally {
                            row.put("evaluation_full_translation_probe", tracker.calls.drop(first).singleOrNull() ?: JSONObject().put("error_class", "NoProviderResult"))
                            save()
                        }
                    }
                    if (fresh && rows.length() % 20 == 0) row.put("process_pss_kib_after_case", android.os.Debug.getPss())
                }
                report.put("complete", true)
            }
        } finally {
            engines.values.forEach { it.first.close() }; evaluation.values.forEach { it.close() }
            if (changedNetwork) { if (wifi == "1") shell("svc wifi enable"); if (mobile == "1") shell("svc data enable") }
            if (fresh) report.put("restored_wifi_setting", shell("settings get global wifi_on").trim())
                .put("restored_mobile_data_setting", shell("settings get global mobile_data").trim())
            report.put("finished_at", Instant.now().toString()).put("process_pss_kib_end", android.os.Debug.getPss()); save()
        }
    }
    companion object {
        private fun ranges(text: String, language: String) = JSONArray().apply {
            LocalImmersion.words(text, language).forEach { put(JSONArray(listOf(it.first, it.last + 1))) }
        }
        private fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
    }
}
