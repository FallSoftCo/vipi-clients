package co.fallsoft.vipi

import android.net.ConnectivityManager
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.security.MessageDigest

/** Research-only: no changes to real messages, installed packs, or app behavior. */
@RunWith(AndroidJUnit4::class)
class TranslationMarkerDeviceTest {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private fun shell(command: String) = instrumentation.uiAutomation.executeShellCommand(command).use {
        java.io.FileInputStream(it.fileDescriptor).bufferedReader().use { reader -> reader.readText() }
    }

    @Test fun recordTwoMarkerCorrespondenceOffline() = runBlocking {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        check(android.os.Build.FINGERPRINT.contains("generic") || android.os.Build.MODEL.contains("sdk_gphone"))
        val context = instrumentation.targetContext
        val bytes = File(context.filesDir, "immersion-qa/marker-protocol.json").readBytes()
        val protocol = JSONObject(bytes.toString(Charsets.UTF_8))
        val markers = protocol.getJSONArray("markers").let { a -> (0 until a.length()).map { a.getString(it) } }
        require(markers == listOf("ZXQ9129", "QXZ7281"))
        val samples = protocol.getJSONArray("samples")
        require(samples.length() == 360)
        val rows = JSONArray()
        val report = JSONObject().put("provider", "MLKit 17.0.3").put("scope", "exploratory_not_linguistic_acceptance")
            .put("protocol_sha256", MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) })
            .put("results", rows)
        val receipt = File(context.filesDir, "context-marker-001.json")
        fun save() { receipt.writeText(report.toString(2)) }
        val wifi = shell("settings get global wifi_on").trim() == "1"
        val mobile = shell("settings get global mobile_data").trim() == "1"
        try {
            shell("svc wifi disable"); shell("svc data disable")
            val network = context.getSystemService(ConnectivityManager::class.java)
            withTimeout(15_000) { while (network.activeNetwork != null) delay(100) }
            assertNull(network.activeNetwork); report.put("network_absence_verified", true)
            LocalTranslation().use { translator ->
                val baselines = mutableMapOf<Triple<String, String, String>, String>()
                for (index in 0 until samples.length()) {
                    val item = samples.getJSONObject(index)
                    val row = JSONObject(item.toString())
                    val source = item.getString("source"); val target = item.getString("target")
                    val original = item.getString("original")
                    val started = SystemClock.elapsedRealtimeNanos()
                    try {
                        val key = Triple(source, target, original)
                        val baseline = baselines[key] ?: withTimeout(45_000) { translator.translate(original, source, target) }.also { baselines[key] = it }
                        row.put("translation", baseline)
                        val perturbations = JSONArray()
                        val candidates = mutableListOf<Pair<Int, Int>?>()
                        for (marker in markers) {
                            require(!original.contains(marker) && !baseline.contains(marker))
                            val altered = original.replaceRange(item.getInt("start"), item.getInt("end"), marker)
                            val translated = withTimeout(45_000) { translator.translate(altered, source, target) }
                            perturbations.put(JSONObject().put("marker", marker).put("translation", translated))
                            val at = translated.indexOf(marker)
                            val once = at >= 0 && translated.indexOf(marker, at + marker.length) < 0
                            val prefix = if (once) translated.substring(0, at) else ""
                            val suffix = if (once) translated.substring(at + marker.length) else ""
                            val end = baseline.length - suffix.length
                            val valid = once && end > prefix.length && baseline.startsWith(prefix) && baseline.endsWith(suffix)
                            candidates += if (valid) prefix.length to end else null
                        }
                        row.put("perturbations", perturbations)
                        val candidate = candidates.firstOrNull()
                        val words = LocalImmersion.words(baseline, target)
                        val selected = candidate != null && candidates.all { it == candidate } &&
                            words.any { it.first == candidate.first } && words.any { it.last + 1 == candidate.second }
                        row.put("selected", selected)
                        if (selected) {
                            row.put("selected_start", candidate!!.first).put("selected_end", candidate.second)
                                .put("selected_target", baseline.substring(candidate.first, candidate.second))
                        }
                        row.put("status", "executed")
                    } catch (cancelled: CancellationException) { throw cancelled }
                    catch (failure: Exception) { row.put("status", "failed").put("error_type", failure.javaClass.simpleName) }
                    row.put("latency_ms", (SystemClock.elapsedRealtimeNanos() - started) / 1_000_000.0)
                    rows.put(row); save()
                }
            }
        } finally {
            if (wifi) shell("svc wifi enable")
            if (mobile) shell("svc data enable")
        }
        assertEquals(360, rows.length())
    }
}
