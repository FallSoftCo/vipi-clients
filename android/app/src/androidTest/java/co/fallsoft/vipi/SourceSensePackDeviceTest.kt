package co.fallsoft.vipi

import android.content.ContextWrapper
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.ImmersionEngine
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.json.JSONObject
import java.io.File
import java.util.UUID

@RunWith(AndroidJUnit4::class)
class SourceSensePackDeviceTest {
    @Test fun capturedProviderErrorsRemainNative() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val fixture = File(context.filesDir, "source-senses-regression")
        val regression = JSONObject(File(fixture, "regression.json").readText())
        val cases = regression.getJSONArray("cases")
        assertEquals(3, cases.length())
        assertEquals(64, regression.getString("capture_sha256").length)
        val root = File(context.cacheDir, "source-senses-regression-${UUID.randomUUID()}")
        val isolated = object : ContextWrapper(context) {
            override fun getFilesDir() = File(root, "files").apply { mkdirs() }
            override fun getNoBackupFilesDir() = File(root, "no-backup").apply { mkdirs() }
        }
        try {
            val store = VocabularyPackStore(isolated, mapOf("bilingual-qualification-007" to File(fixture, "signing-public-key.der").readBytes()))
            repeat(cases.length()) { index ->
                val item = cases.getJSONObject(index); val pair = item.getString("pair")
                val folder = File(fixture, pair)
                store.install(File(folder, "manifest.json").readBytes(), File(folder, "manifest.sig").readBytes(), File(folder, "vocabulary.sqlite").readBytes())
                val original = item.getString("original"); val rejected = item.getString("rejected_source")
                val entries = store.entries(pair, original)
                val languages = pair.split('-')
                val result = LocalImmersion.align(original, item.getString("translation"), entries, 0.3, languages[0], languages[1])
                assertFalse(pair, result.spans.any { it.original.lowercase() == rejected })
                if (rejected == "lectura") {
                    val meanings = entries.filter { it.source == "lectura" }
                    assertEquals(4, meanings.size)
                    assertEquals(3, meanings.count { it.targets.isEmpty() })
                }
                store.remove(pair)
            }
        } finally { root.deleteRecursively() }
    }

    @Test fun unmappedSensesSurviveSignedNativeLookup() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val fixture = File(context.filesDir, "source-senses-fixture")
        val root = File(context.cacheDir, "source-senses-${UUID.randomUUID()}")
        val isolated = object : ContextWrapper(context) {
            override fun getFilesDir() = File(root, "files").apply { mkdirs() }
            override fun getNoBackupFilesDir() = File(root, "no-backup").apply { mkdirs() }
        }
        try {
            val store = VocabularyPackStore(isolated, mapOf("source-senses-test" to File(fixture, "signing-public-key.der").readBytes()))
            store.install(File(fixture, "manifest.json").readBytes(), File(fixture, "manifest.sig").readBytes(), File(fixture, "vocabulary.sqlite").readBytes())
            val sentence = "Walk by the river bank."
            val entries = store.entries("en-es", sentence)
            val banks = entries.filter { it.source == "bank" }
            assertEquals(3, banks.size)
            assertEquals(2, banks.count { it.targets.isEmpty() })
            assertTrue(banks.all { it.requiresContext })
            assertTrue(banks.filter { it.targets.isEmpty() }.all { "river" in it.contextHints })
            assertTrue(ImmersionEngine().align(sentence, "Camina por el banco del río.", entries, 1.0).spans.isEmpty())
            val coffee = store.entries("en-es", "Coffee please.")
            assertEquals(listOf("Café"), ImmersionEngine().align("Coffee please.", "Café por favor.", coffee, 1.0).spans.map { it.translated })
            assertTrue(store.entries("en-es", "Don't move. Don’t stop.").isEmpty())
            store.remove("en-es")
        } finally { root.deleteRecursively() }
    }
}
