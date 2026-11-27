package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Runs only on Vipi's dedicated emulator. Disables its network, never the host's. */
@RunWith(AndroidJUnit4::class)
class LocalTranslationDeviceTest {
    private val instrumentation
        get() = InstrumentationRegistry.getInstrumentation()

    private fun shell(command: String): String =
        instrumentation.uiAutomation.executeShellCommand(command).use { descriptor ->
            java.io.FileInputStream(descriptor.fileDescriptor).bufferedReader().use {
                it.readText()
            }
        }

    @Test
    fun downloadedModelsTranslateWithAllEmulatorRadiosOff() = runBlocking {
        // Require an explicit runner argument before changing this emulator's network.
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        check(
            android.os.Build.FINGERPRINT.contains("generic") ||
                android.os.Build.MODEL.contains("sdk_gphone")
        )
        val wifi = shell("settings get global wifi_on").trim() == "1"
        val data = shell("settings get global mobile_data").trim() == "1"
        val target = InstrumentationRegistry.getArguments().getString("vipiOfflineTarget") ?: "es"
        val tokens =
            when (target) {
                "es" -> listOf("café", "río", "banco")
                "ru" -> listOf("кофе", "рек", "банк")
                else -> error("No fixture for $target")
            }
        LocalTranslation().use { translation ->
            withTimeout(180_000) { translation.prepare("en", target, cellularAllowed = true) }
            try {
                shell("svc wifi disable")
                shell("svc data disable")
                val manager =
                    instrumentation.targetContext.getSystemService(
                        android.net.ConnectivityManager::class.java
                    )
                withTimeout(15_000) {
                    while (manager.activeNetwork != null) kotlinx.coroutines.delay(100)
                }
                assertNull("Network still active", manager.activeNetwork)
                val samples =
                    listOf(
                        "Coffee tomorrow?",
                        "The river flows past the village.",
                        "My sister works at a bank.",
                    )
                val output =
                    withTimeout(30_000) { samples.map { translation.translate(it, "en", target) } }
                output.zip(samples).forEach { (translated, original) ->
                    assertTrue(translated.isNotBlank())
                    assertNotEquals(original, translated)
                }
                tokens.zip(output).forEach { (token, text) ->
                    assertTrue(text, text.contains(token, ignoreCase = true))
                }
                if (target == "ru") {
                    val native = output.first()
                    val reading =
                        FullMessageReadings.read(instrumentation.targetContext, native, target)
                    assertEquals(FullMessageReadingStatus.AVAILABLE, reading.status)
                    val wav =
                        java.io.File.createTempFile(
                            "translated-",
                            ".wav",
                            instrumentation.targetContext.cacheDir,
                        )
                    val voice =
                        kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) {
                            LocalVoice(instrumentation.targetContext, target)
                        }
                    try {
                        voice.render(native, wav)
                        assertTrue(PcmWave.read(wav).samples.any { it != 0.toByte() })
                    } finally {
                        voice.close()
                        wav.delete()
                    }
                }
                // Synthetic fixtures only, useful for reviewing the actual provider output.
                val receipt =
                    org.json
                        .JSONObject()
                        .put("provider", "MLKit 17.0.3")
                        .put("activeNetwork", "none")
                        .put("target", target)
                        .put("source", org.json.JSONArray(samples))
                        .put("translation", org.json.JSONArray(output))
                val filename =
                    if (target == "es") "offline-translation-receipt.json"
                    else "offline-translation-$target.json"
                java.io
                    .File(instrumentation.targetContext.filesDir, filename)
                    .writeText(receipt.toString(2))
            } finally {
                if (wifi) shell("svc wifi enable")
                if (data) shell("svc data enable")
            }
        }
    }
}
