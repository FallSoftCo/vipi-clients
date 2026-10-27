package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest

/** Authored reference diagnostics only; never reads private messages or evaluation corpora. */
@RunWith(AndroidJUnit4::class)
class CatalogParityDeviceTest {
    @Test fun captureActualReferenceSelectionsForNativeComparison() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val revision = requireNotNull(InstrumentationRegistry.getArguments().getString("vipiCatalogParityRun"))
        check(revision.matches(Regex("[0-9]{3}")))
        val context = instrumentation.targetContext
        val bytes = context.assets.open("immersion/catalog.json").use { it.readBytes() }
        val rows = JSONObject(String(bytes, Charsets.UTF_8)).getJSONArray("references")
        val catalog = BundledImmersionCatalog(context)
        val cases = JSONArray()
        for (i in 0 until rows.length()) {
            val row = rows.getJSONObject(i)
            val (source,target) = row.getString("pair").split("-")
            val original = row.getString("original"); val translation = row.getString("translation")
            val result = catalog.result(original,translation,source,target,1.0)
            assertEquals(original,result.original); assertEquals(translation,result.translation)
            val spans = JSONArray()
            for (s in result.spans) spans.put(JSONObject().put("start",s.start).put("end",s.end)
                .put("target_start",s.targetStart).put("target_end",s.targetEnd)
                .put("original",s.original).put("translated",s.translated).put("reading",s.romanization ?: JSONObject.NULL))
            cases.put(JSONObject().put("index",i).put("pair",row.getString("pair")).put("original",original)
                .put("translation",translation).put("spans",spans))
        }
        val output = File(context.filesDir,"catalog-parity-$revision.json"); check(!output.exists())
        output.writeText(JSONObject().put("schema","vipi-native-catalog-parity-1")
            .put("catalog_sha256",MessageDigest.getInstance("SHA-256").digest(bytes).joinToString(""){"%02x".format(it)})
            .put("cases",cases).put("semantic_acceptance",false).toString())
    }
}
