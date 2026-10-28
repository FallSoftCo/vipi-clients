package co.fallsoft.vipi

import android.net.ConnectivityManager
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.MessageDigest

/** Captures actual offline provider output for pinned public development prompts.
 * Source-labelled public samples include human assistant-style requests.
 * This small development cohort does not represent private chat populations.
 * Outputs are evidence for review, never training labels or accuracy assertions. */
class HumanPromptTranslationDeviceTest {
    @Test fun translatePublicDevelopmentPromptsOffline() = runBlocking {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("vipiDedicatedEmulator") == "true")
        check(android.os.Build.FINGERPRINT.contains("generic") || android.os.Build.MODEL.contains("sdk_gphone"))
        val run = requireNotNull(args.getString("vipiPromptRun"))
        require(run.matches(Regex("[0-9]{3}")))
        val expected = requireNotNull(args.getString("vipiPromptsSha"))
        require(expected.matches(Regex("[a-f0-9]{64}")))
        val context = instrumentation.targetContext
        val bytes = File(context.filesDir, "human-development-prompts.json").readBytes()
        assertEquals(expected, MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) })
        val prompts = JSONArray(bytes.toString(Charsets.UTF_8))
        val languages = listOf("ar","de","en","es","fr","it","ja","ko","pt","sw","zh")
        val onlyTarget = args.getString("vipiTargetLanguage")
        require(onlyTarget == null || onlyTarget in languages)
        val output = File(context.filesDir, "human-prompt-translations-$run.json")
        check(!output.exists())
        val rows = JSONArray()
        val errors = JSONArray()
        fun save(complete: Boolean) {
            output.writeText(JSONObject().put("schema", "vipi-human-prompt-translations-1")
                .put("complete", complete).put("input_sha256", expected).put("provider", "MLKit 17.0.3")
                .put("network", "none").put("development_only", true)
                .put("independent_semantic_acceptance", false).put("population_coverage_claim", false)
                .put("outcomes", rows).put("errors", errors).toString())
        }
        fun shell(command: String) = instrumentation.uiAutomation.executeShellCommand(command).use { descriptor ->
            java.io.FileInputStream(descriptor.fileDescriptor).bufferedReader().use { it.readText() }
        }
        val wifi = shell("settings get global wifi_on").trim() == "1"
        val data = shell("settings get global mobile_data").trim() == "1"
        val manager = context.getSystemService(ConnectivityManager::class.java)
        try {
            shell("svc wifi disable"); shell("svc data disable")
            withTimeout(15_000) { while (manager.activeNetwork != null) delay(100) }
            assertNull(manager.activeNetwork)
            LocalTranslation().use { translator ->
                for (source in languages) for (target in languages.filter { it != source && (onlyTarget == null || it == onlyTarget) }) {
                    for (i in 0 until prompts.length()) {
                        val row = prompts.getJSONObject(i)
                        if (row.getString("source") != source) continue
                        assertNull("Network unexpectedly restored", manager.activeNetwork)
                        val id = row.getString("id") + ":" + target
                        val start = System.nanoTime()
                        try {
                            // No prepare/download call: models must already be installed.
                            val translation = withTimeout(45_000) { translator.translate(row.getString("original"),source,target) }
                            check(translation.isNotBlank())
                            rows.put(JSONObject().put("id",id).put("dataset",row.optString("dataset","oasst1-human-development"))
                                .put("source",source).put("target",target).put("original",row.getString("original"))
                                .put("translation",translation).put("elapsed_ms",(System.nanoTime()-start)/1e6))
                        } catch (failure: Exception) {
                            errors.put(JSONObject().put("id",id).put("error",failure.javaClass.simpleName)
                                .put("message",failure.message))
                        }
                        save(false)
                    }
                }
            }
            save(true)
            assertEquals(errors.toString(),0,errors.length())
            val expectedRows = (0 until prompts.length()).sumOf { i ->
                languages.count { it != prompts.getJSONObject(i).getString("source") && (onlyTarget == null || it == onlyTarget) }
            }
            assertEquals(expectedRows,rows.length())
        } finally {
            if (wifi) shell("svc wifi enable")
            if (data) shell("svc data enable")
        }
    }
}
