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
class BilingualPackDeviceTest {
    @Test fun japaneseMixedScriptAndInflectionsKeepWholeMorphemes() {
        val mixed = "私の妹は銀行で働いています。 She will help me tomorrow."
        assertTrue(LocalImmersion.words(mixed, "ja").map { mixed.substring(it) }.contains("銀行"))
        val inflected = "18:30に会おう。生きています。"
        val words = LocalImmersion.words(inflected, "ja").map { inflected.substring(it) }
        assertFalse(words.contains("会")); assertFalse(words.contains("生"))
        assertTrue(words.contains("会お")); assertTrue(words.contains("生き"))
    }
    @Test fun signedBilingualSenseAndReadingRoundTrip() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val fixture = JSONObject(File(context.filesDir, "bilingual-lookup.json").readText())
        assertEquals("SYNTHETIC BILINGUAL QA ONLY", fixture.getString("purpose"))
        fun bytes(value: JSONObject, key: String) = Base64.decode(value.getString(key), Base64.DEFAULT)
        val store = VocabularyPackStore(context, mapOf("synthetic-bilingual-qa" to bytes(fixture, "public_key")))
        val records = PrivateRecords(context)
        val cases = fixture.getJSONArray("cases")
        repeat(cases.length()) { index ->
            val sample = cases.getJSONObject(index); val id = sample.getString("id"); val key = "pack-$id"
            assumeTrue("Preserve existing pack receipt", records.read(key) == null)
            assumeTrue("Preserve installed pack files", !File(context.filesDir, "language-packs/$id.json").exists())
            try {
                assertEquals(id, store.install(bytes(sample, "manifest"), bytes(sample, "signature"), bytes(sample, "database")))
                val source = sample.getString("source"); val target = sample.getString("target")
                val text = sample.getString("text"); val translation = sample.getString("translation")
                val entries = store.entries(id, text)
                val result = LocalImmersion.align(text, translation, entries, 1.0, source, target)
                assertEquals(id, 1, result.spans.size)
                assertEquals(sample.getString("expected"), result.spans.first().original)
                assertEquals(sample.getString("written"), result.spans.first().translated)
                assertEquals(if (sample.isNull("reading")) null else sample.getString("reading"), result.spans.first().romanization)
                assertTrue(result.speech(source, target).any { it.text == sample.getString("written") && it.language == target })
                if (target == "fr") {
                    assertEquals(2, entries.count { it.source == "bank" })
                    assertTrue(entries.any { "river" in it.contextHints })
                    assertTrue(entries.filter { it.source == "bank" }.all { it.requiresContext })
                    assertTrue(LocalImmersion.align("A bank.", "Une banque.", entries, 1.0, "en", "fr").spans.isEmpty())
                    assertTrue(LocalImmersion.align(text, "Une banque près du fleuve.", entries, 1.0, "en", "fr").spans.isEmpty())
                    assertTrue(LocalImmersion.align("A bank.", "Une banque et une rive.", entries, 1.0, "en", "fr").spans.isEmpty())
                }
                if (target == "ja") {
                    assertTrue(LocalImmersion.align("I read.", "読む。", store.entries(id, "I read."), 1.0, "en", "ja").spans.isEmpty())
                }
                if (target == "zh") {
                    assertTrue(LocalImmersion.align("It is missing.", "丢失。", store.entries(id, "It is missing."), 1.0, "en", "zh").spans.isEmpty())
                }
            } finally { store.remove(id); records.remove(key) }
        }
    }
}
