package co.fallsoft.vipi

import android.util.Base64
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class SignedLanguageLookupDeviceTest {
    @Test fun nativeReadingFormatKeepsToneMarksAndRejectsIPA() {
        for ((reading, accepted) in listOf("kāfēi" to true, "ɡa" to false, "..." to false)) {
            val entries = listOf(co.fallsoft.vipi.core.VocabularyEntry("coffee", listOf("咖啡"), mapOf("咖啡" to listOf(reading))))
            val result = LocalImmersion.align("Want coffee?", "明天喝咖啡。", entries, 1.0, "en", "zh")
            assertEquals(accepted, result.spans.isNotEmpty())
            if (accepted) {
                assertEquals(reading, result.spans.first().displayedTarget)
                assertTrue(result.speech("en", "zh").any { it.text == "咖啡" })
            }
        }
    }
    @Test fun signedDictionaryLookupUsesNativeBoundaries() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val fixture = JSONObject(File(context.filesDir, "signed-lookup.json").readText())
        assertEquals("SYNTHETIC NATIVE WORD LOOKUP QA ONLY", fixture.getString("purpose"))
        fun bytes(value: JSONObject, key: String) = Base64.decode(value.getString(key), Base64.DEFAULT)
        val store = VocabularyPackStore(context, mapOf("synthetic-lookup-qa" to bytes(fixture, "public_key")))
        val records = PrivateRecords(context)
        val cases = fixture.getJSONArray("cases")
        repeat(cases.length()) { index ->
            val sample = cases.getJSONObject(index); val id = sample.getString("id"); val key = "pack-$id"
            assumeTrue("Preserve existing pack receipts", records.read(key) == null)
            assumeTrue("Preserve existing pack files", !File(context.filesDir, "language-packs/$id.json").exists())
            try {
                assertEquals(id, store.install(bytes(sample, "manifest"), bytes(sample, "signature"), bytes(sample, "database")))
                val entries = store.entries(id, sample.getString("text"))
                assertTrue(id, entries.any { it.source == sample.getString("expected") && "coffee" in it.targets })
                assertFalse(id, entries.any { it.source == sample.getString("partial") })
            } finally { store.remove(id); records.remove(key) }
        }
    }
}
