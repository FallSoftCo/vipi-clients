package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import com.google.mlkit.common.model.RemoteModelManager
import com.google.mlkit.nl.translate.TranslateRemoteModel
import java.io.File
import kotlinx.coroutines.*
import kotlinx.coroutines.tasks.await
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Test

/** Explicitly authorized QA-only model download. No source text is translated. */
class PrepareLocalTranslationModelsDeviceTest {
    @Test
    fun prepareOfficialModels() = runBlocking {
        val inst = InstrumentationRegistry.getInstrumentation()
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val dir = File(inst.targetContext.filesDir, "local-model-preparation-r01")
        check(!dir.exists())
        dir.mkdirs()
        val rows = JSONArray()
        val report =
            JSONObject()
                .put("complete", false)
                .put("languages", rows)
                .put("scope", "official ML Kit models; no translation input")
        fun save() {
            File(dir, "report.json").writeText(report.toString(2))
        }
        val manager = RemoteModelManager.getInstance()
        val store = NativeLanguageDownloadStore()
        save()
        try {
            for (code in initialLanguages.map { it.code }.filter { it != "en" }) {
                val model = TranslateRemoteModel.Builder(code).build()
                val before = manager.isModelDownloaded(model).await()
                val row = JSONObject().put("language", code).put("installed_before", before)
                val t = System.nanoTime()
                try {
                    if (!before)
                        withTimeout(180_000) {
                            store.download(DownloadPair("en", code), cellular = true)
                        }
                    row.put("installed_after", manager.isModelDownloaded(model).await())
                        .put("status", "checked")
                } catch (e: Exception) {
                    row.put("status", "error").put("error_class", e.javaClass.simpleName)
                } finally {
                    row.put("elapsed_ms", (System.nanoTime() - t) / 1e6)
                    rows.put(row)
                    save()
                }
            }
            report.put("complete", true)
            save()
        } finally {
            store.close()
        }
    }
}
