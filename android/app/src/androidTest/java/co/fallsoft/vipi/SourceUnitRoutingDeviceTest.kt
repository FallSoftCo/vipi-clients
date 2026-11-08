package co.fallsoft.vipi

import android.net.ConnectivityManager
import android.os.SystemClock
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.*
import com.google.mlkit.common.model.RemoteModelManager
import com.google.mlkit.nl.translate.TranslateRemoteModel
import kotlinx.coroutines.*
import kotlinx.coroutines.tasks.await
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.MessageDigest
import java.time.Instant

/** Accepted candidate: actual native callbacks and explicit full-reference requests, no new mappings. */
class SourceUnitRoutingDeviceTest {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private fun shell(command: String) = instrumentation.uiAutomation.executeShellCommand(command).use {
        java.io.FileInputStream(it.fileDescriptor).bufferedReader().use { stream -> stream.readText() }
    }
    private fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
    private fun presentation(value: ImmersionPresentation?): JSONObject = JSONObject()
        .put("original", value?.original ?: JSONObject.NULL).put("complete_translation", value?.translation ?: JSONObject.NULL)
        .put("mixed", value?.let { ImmersionText.project(it) } ?: JSONObject.NULL)
        .put("spans", JSONArray(value?.spans?.map { span -> JSONObject().put("id", span.id)
            .put("source", span.original).put("target", span.translated).put("reading", span.romanization ?: JSONObject.NULL)
            .put("source_start_utf16", span.start).put("source_end_utf16", span.end)
            .put("target_start_utf16", span.targetStart).put("target_end_utf16", span.targetEnd) } ?: emptyList<JSONObject>()))
        .put("source_references", JSONArray((value as? PartialImmersionResult)?.references?.map { unit ->
            JSONObject().put("id", unit.referenceId).put("catalog_sha256", unit.catalogSha256)
                .put("start_utf16", unit.start).put("end_utf16", unit.end) } ?: emptyList<JSONObject>()))
    private class Tracking(private val network: ConnectivityManager) : LanguageTranslation {
        private val local = LocalTranslation()
        val calls = JSONArray()
        override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) = error("No model download in routing qualification")
        override suspend fun translate(text: String, source: String, target: String): String {
            assertNull(network.activeNetwork)
            val began = SystemClock.elapsedRealtimeNanos()
            val row = JSONObject().put("source", source).put("target", target).put("input", text); calls.put(row)
            try {
                val output = withTimeout(30_000) { local.translate(text, source, target) }
                row.put("translation", output).put("identifiers_preserved", TranslationIntegrity.preservesIdentifiers(text, output))
                return output
            } catch (error: Throwable) { row.put("error_class", error.javaClass.simpleName); throw error }
            finally { row.put("elapsed_ms", (SystemClock.elapsedRealtimeNanos() - began) / 1e6); assertNull(network.activeNetwork) }
        }
        override fun close() = local.close()
    }
    @Test fun captureFrozenSourceUnitRouting(): Unit = runBlocking {
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("vipiDedicatedEmulator") == "true" && args.getString("vipiRoutingArm") == "candidate")
        check(android.os.Build.MODEL.contains("sdk_gphone") || android.os.Build.FINGERPRINT.contains("generic"))
        val run = args.getString("vipiRoutingRun") ?: "001"; require(run.matches(Regex("[0-9]{3}")))
        val context = instrumentation.targetContext
        val bytes = File(context.filesDir, "source-unit-routing-fixtures-r01.json").readBytes()
        assertEquals("1a2e1d5974df1053fbda0901fe268f98a2c6fde99c8076cb23bf34db667deb74", sha(bytes))
        val fixture = JSONObject(bytes.toString(Charsets.UTF_8))
        val catalogHash = context.assets.open("immersion/catalog.json").use { sha(it.readBytes()) }
        assertEquals(fixture.getString("catalog_sha256"), catalogHash)
        val input = fixture.getJSONArray("fixtures"); assertEquals(6, input.length())
        val output = File(context.filesDir, "source-unit-routing-candidate-$run.json"); check(!output.exists())
        val report = JSONObject().put("arm", "source_unit_candidate").put("complete", false).put("input_sha256", sha(bytes))
            .put("catalog_sha256", catalogHash).put("started_at", Instant.now().toString())
            .put("provider", "Google ML Kit17.0.3 actual installed local model").put("new_mappings", false)
            .put("counter_scope", "production LookupFirst function with the same actual native catalog/readings/lexical/provider callbacks; separate actual ConversationImmersion first/warm measurements")
        val rows = JSONArray(); report.put("cases", rows)
        fun save() = output.writeText(report.toString(2))
        val network = context.getSystemService(ConnectivityManager::class.java)
        val wifi = shell("settings get global wifi_on").trim(); val mobile = shell("settings get global mobile_data").trim()
        var changedNetwork = false
        save()
        try {
            val installed = RemoteModelManager.getInstance().isModelDownloaded(TranslateRemoteModel.Builder("sw").build()).await()
            report.put("sw_model_already_installed", installed); assertTrue(installed)
            changedNetwork = true; shell("svc wifi disable"); shell("svc data disable")
            withTimeout(15_000) { while (network.activeNetwork != null) delay(100) }
            assertNull(network.activeNetwork); report.put("network_observation", "Emulator Wi-Fi and mobile disabled; no activeNetwork at each actual provider call; original radio settings restored finally")
            withTimeout(600_000) { for (index in 0 until input.length()) {
                val item = input.getJSONObject(index); val text = item.getString("text"); val density = item.getDouble("density")
                assertEquals("en", item.getString("source")); assertEquals("sw", item.getString("target"))
                val row = JSONObject(item.toString()); rows.put(row); save()
                val catalog = BundledImmersionCatalog(context); val lexical = BundledLexicalCatalog(context); val readings = SentenceReadings(context)
                val direct = Tracking(network)
                try {
                    for (intent in listOf(ImmersionIntent.AUTOMATIC_IMMERSION, ImmersionIntent.FULL_TRANSLATION)) {
                        val events = JSONArray(); var readyCalls = 0; var aligns = 0; var partialCallbacks = 0
                        val beforeCalls = direct.calls.length(); val began = SystemClock.elapsedRealtimeNanos()
                        val probe = if (intent == ImmersionIntent.AUTOMATIC_IMMERSION) row else JSONObject().also { row.put("core_full_request_without_cache", it) }
                        fun event(name: String) { events.put(JSONObject().put("name", name).put("elapsed_ms", (SystemClock.elapsedRealtimeNanos() - began) / 1e6)) }
                        try {
                            val result = LookupFirst.resolve(LookupFirstRequest(text, "en", "sw", "en", intent), { true },
                                reference = { original, source, target -> withContext(Dispatchers.Default) { catalog.reference(original, source, target) } },
                                identify = { error("Explicit input should not call classifier") },
                                modelsReady = { readyCalls++; event("models_ready"); installed },
                                translate = { original, source, target -> direct.translate(original, source, target) },
                                align = { original, translated -> aligns++; event("heavy_align"); withContext(Dispatchers.IO) {
                                    catalog.result(original, translated, "en", "sw", density, lexical.entries(original, translated, "en", "sw"))
                                } },
                                partialReference = { original, source, target -> withContext(Dispatchers.Default) { catalog.partial(original, source, target, density, readings) } },
                                onPartial = { partial -> partialCallbacks++; event("partial"); probe.put("first_partial", presentation(partial)) })
                            probe.put("core_outcome", JSONObject().put("status", result.status.name).put("origin", result.origin?.name)
                                .put("fallback_status", result.fallbackStatus?.name).put("result", presentation(result.result)))
                        } catch (error: Exception) { probe.put("core_error", error.javaClass.simpleName); if (error is CancellationException) throw error }
                        finally { probe.put("core_elapsed_ms", (SystemClock.elapsedRealtimeNanos() - began) / 1e6)
                            .put("routing_readiness_calls", readyCalls).put("heavy_alignment_calls", aligns).put("partial_callbacks", partialCallbacks)
                            .put("core_events", events).put("core_provider_calls", JSONArray((beforeCalls until direct.calls.length()).map { direct.calls.getJSONObject(it) })); save() }
                    }
                } finally { direct.close() }
                val actual = Tracking(network)
                ConversationImmersion(context, "en", "sw", density, actual).use { engine ->
                    engine.checkDownloads(); row.put("app_models_ready", engine.ready)
                    val phases = JSONArray(); row.put("app_phases", phases)
                    val epoch = engine.newFullTranslationEpoch()
                    for (phase in listOf("automatic_first", "automatic_warm", "full_first", "full_repeat")) {
                        val at = SystemClock.elapsedRealtimeNanos(); val count = actual.calls.length(); val callbacks = JSONArray()
                        val observation = JSONObject().put("phase", phase); phases.put(observation)
                        try {
                            val value = if (phase.startsWith("full_")) engine.fullTranslation(text, "en", null, epoch).result
                            else engine.presentation(text, "en", onPartial = { partial -> callbacks.put(JSONObject()
                                .put("elapsed_ms", (SystemClock.elapsedRealtimeNanos() - at) / 1e6).put("result", presentation(partial))) })
                            observation.put("result", presentation(value)).put("status", engine.lastOutcome?.status?.name)
                                .put("cache_hit", engine.lastOutcome?.cacheHit).put("lexical_preparation", engine.lexicalPreparation)
                        } catch (error: Exception) { observation.put("error_class", error.javaClass.simpleName); if (error is CancellationException) throw error }
                        finally { observation.put("elapsed_ms", (SystemClock.elapsedRealtimeNanos() - at) / 1e6)
                            .put("provider_calls", actual.calls.length() - count).put("partial_callbacks", callbacks); save() }
                    }
                    row.put("app_provider_calls", actual.calls)
                }
                row.put("capture_complete", true); save()
            } }
            report.put("japanese_reading_diagnostic_only", JSONArray(listOf("または", "知っている", "何", "月").map { text ->
                JSONObject().put("original", text).put("speech_kana", JapaneseSpeechReading.convert(text))
                    .put("tokens", JSONArray(LocalImmersion.japaneseTokens(text).map { token -> JSONObject()
                        .put("surface", token.surface).put("position", token.position)
                        .put("reading", token.reading).put("pronunciation", token.pronunciation) }))
            }))
            report.put("complete", true).put("finished_at", Instant.now().toString()); save()
        } finally {
            if (changedNetwork) { shell("svc wifi ${if (wifi == "1") "enable" else "disable"}"); shell("svc data ${if (mobile == "1") "enable" else "disable"}") }
            report.put("wifi_before", wifi).put("mobile_before", mobile).put("wifi_after", shell("settings get global wifi_on").trim())
                .put("mobile_after", shell("settings get global mobile_data").trim()); save()
        }
    }
}
