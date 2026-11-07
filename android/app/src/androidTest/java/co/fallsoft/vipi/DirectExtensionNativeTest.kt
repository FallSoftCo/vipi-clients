package co.fallsoft.vipi

import android.net.ConnectivityManager
import android.util.AtomicFile
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.TranslationIntegrity
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.MessageDigest
import java.time.Instant

/** Evaluation only: direct native substring calls, without dictionary or production matcher prerequisites. */
class DirectExtensionNativeTest {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private fun shell(command: String) = instrumentation.uiAutomation.executeShellCommand(command).use {
        java.io.FileInputStream(it.fileDescriptor).bufferedReader().use { stream -> stream.readText() }
    }
    private fun write(file: File, value: JSONObject) {
        val atomic = AtomicFile(file); val stream = atomic.startWrite()
        try { stream.write(value.toString(2).toByteArray(Charsets.UTF_8)); atomic.finishWrite(stream) }
        catch (error: Throwable) { atomic.failWrite(stream); throw error }
    }
    private fun ranges(text: String, language: String) = JSONArray().apply {
        LocalImmersion.words(text, language).forEach { put(JSONArray(listOf(it.first, it.last + 1))) }
    }

    @Test fun captureFrozenDirectWordWindowAndRecursiveRequests(): Unit = runBlocking {
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("vipiDirectExtension") == "true")
        check(args.getString("vipiDedicatedEmulator") == "true")
        check(android.os.Build.FINGERPRINT.contains("generic") || android.os.Build.MODEL.contains("sdk_gphone"))
        val context = instrumentation.targetContext
        val input = File(context.filesDir, "direct-extension-native-protocol.json").readBytes()
        val expected = "00c9a1ef756427c069790ae86021e32e2624f3d883c8502025b6b04602d1b74e"
        val hash = MessageDigest.getInstance("SHA-256").digest(input).joinToString("") { "%02x".format(it) }
        assertEquals(expected, hash)
        val protocol = JSONObject(input.toString(Charsets.UTF_8))
        val array = protocol.getJSONArray("requests")
        val requests = (0 until array.length()).map(array::getJSONObject)
        assertEquals(4706, requests.size)
        assertEquals(4706, requests.map { it.getString("id") }.distinct().size)
        assertEquals(setOf("en" to "es", "en" to "sw"), requests.map { it.getString("source") to it.getString("target") }.toSet())
        val run = args.getString("vipiDirectRun") ?: "001"; require(run.matches(Regex("[0-9]{3}")))
        val directory = File(context.filesDir, "direct-extension-$run-cache").apply { mkdirs() }
        val output = File(context.filesDir, "direct-extension-$run.json")
        val cached = linkedMapOf<String, JSONObject>()
        for (request in requests) {
            val id = request.getString("id"); require(id.matches(Regex("[a-f0-9]{64}")))
            val file = File(directory, "$id.json")
            if (!file.exists()) continue
            val row = JSONObject(AtomicFile(file).openRead().bufferedReader().use { it.readText() })
            assertEquals(expected, row.getString("input_sha256"))
            for (key in listOf("id", "source", "target", "text")) assertEquals(request.getString(key), row.getString(key))
            require(row.getString("status") in setOf("translated", "failed", "timeout"))
            cached[id] = row
        }
        if (output.exists()) {
            val previous = JSONObject(output.readText()); assertEquals(expected, previous.getString("input_sha256"))
            check(!previous.getBoolean("complete")) { "Complete capture already exists; do not replay it" }
        }
        val report = JSONObject().put("schema", "vipi-direct-extension-native-capture-1")
            .put("input_sha256", expected).put("production", false).put("training_use", false)
            .put("provider", "Google ML Kit translate 17.0.3 on device")
            .put("build_fingerprint", android.os.Build.FINGERPRINT)
            .put("started_at", Instant.now().toString()).put("complete", false)
            .put("requested_count", requests.size).put("resumed_verified_results", cached.size)
            .put("cache_policy", "One persisted result per exact supplied request ID/source/target/text; failures retained without automatic retry")
            .put("models", JSONArray()).put("new_provider_calls", 0)
        fun save() { report.put("completed_count", cached.size).put("requests", JSONArray(cached.values.toList())); write(output, report) }
        save()
        val wifi = shell("settings get global wifi_on").trim() == "1"
        val mobile = shell("settings get global mobile_data").trim() == "1"
        val network = context.getSystemService(ConnectivityManager::class.java)
        val translators = linkedMapOf<Pair<String, String>, LocalTranslation>()
        val firstCalls = mutableSetOf<Pair<String, String>>()
        var changedNetwork = false
        var calls = 0
        try {
            val finished = withTimeoutOrNull(1_800_000) {
                for (pair in requests.map { it.getString("source") to it.getString("target") }.distinct()) {
                    val translator = LocalTranslation(); translators[pair] = translator
                    val began = android.os.SystemClock.elapsedRealtimeNanos()
                    withTimeout(300_000) { translator.prepare(pair.first, pair.second, true) }
                    report.getJSONArray("models").put(JSONObject().put("source", pair.first).put("target", pair.second)
                        .put("prepare_ms", (android.os.SystemClock.elapsedRealtimeNanos() - began) / 1e6))
                }
                changedNetwork = true
                shell("svc wifi disable"); shell("svc data disable")
                withTimeout(15_000) { while (network.activeNetwork != null) delay(100) }
                assertNull(network.activeNetwork)
                report.put("network_observation", "Emulator Wi-Fi and cellular data disabled after native model preparation; activeNetwork absent before and after each provider call")
                report.put("models_prepared_at", Instant.now().toString()); save()
                for (request in requests) {
                    ensureActive()
                    val id = request.getString("id"); if (id in cached) continue
                    val source = request.getString("source"); val target = request.getString("target"); val original = request.getString("text")
                    val pair = source to target
                    val row = JSONObject(request.toString()).put("input_sha256", expected)
                        .put("native_source_word_ranges", ranges(original, source)).put("started_at", Instant.now().toString())
                        .put("first_call_for_prepared_pair", firstCalls.add(pair))
                    assertNull(network.activeNetwork)
                    val began = android.os.SystemClock.elapsedRealtimeNanos()
                    calls++
                    var timedOut = false
                    try {
                        val translated = withTimeout(30_000) { translators.getValue(pair).translate(original, source, target) }
                        row.put("status", "translated").put("translation", translated)
                            .put("native_target_word_ranges", ranges(translated, target))
                            .put("identifiers_preserved", TranslationIntegrity.preservesIdentifiers(original, translated))
                    } catch (error: TimeoutCancellationException) {
                        currentCoroutineContext().ensureActive()
                        row.put("status", "timeout").put("error_class", error.javaClass.simpleName); timedOut = true
                    } catch (error: CancellationException) { throw error }
                    catch (error: Exception) { row.put("status", "failed").put("error_class", error.javaClass.simpleName) }
                    finally { row.put("elapsed_ms", (android.os.SystemClock.elapsedRealtimeNanos() - began) / 1e6) }
                    assertNull(network.activeNetwork)
                    row.put("active_network", "none")
                    write(File(directory, "$id.json"), row); cached[id] = row
                    report.put("new_provider_calls", calls)
                    if (cached.size % 25 == 0 || timedOut) save()
                    if (timedOut) { report.put("stopped_reason", "Single provider call exceeded 30 seconds; no overlapping retry"); return@withTimeoutOrNull false }
                }
                true
            }
            report.put("complete", finished == true && cached.size == requests.size)
            if (finished == null) report.put("stopped_reason", "Thirty minute run budget reached; verified cached results may resume")
        } finally {
            translators.values.forEach { it.close() }
            if (changedNetwork) { if (wifi) shell("svc wifi enable"); if (mobile) shell("svc data enable") }
            report.put("finished_at", Instant.now().toString()).put("new_provider_calls", calls)
                .put("restored_wifi_setting", shell("settings get global wifi_on").trim())
                .put("restored_mobile_data_setting", shell("settings get global mobile_data").trim())
            save()
        }
    }
}
