package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.ImmersionEngine
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class VocabularyPackDeviceTest {
    @Test fun signedPackInstallsAndMatchesContext() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val fixture = File(context.filesDir, "pack-fixture")
        val key = File(fixture, "signing-public-key.der").readBytes()
        val manifest = File(fixture, "manifest.json").readBytes()
        val signature = File(fixture, "manifest.sig").readBytes()
        val database = File(fixture, "vocabulary.sqlite").readBytes()
        val store = VocabularyPackStore(context, mapOf("development-2026-10" to key))
        assertEquals("en-es", store.install(manifest, signature, database))
        val original = "Coffee tomorrow? I know a little place by the river."
        val entries = store.entries("en-es", original)
        assertTrue(entries.any { it.source == "coffee" && "café" in it.targets })
        val result = ImmersionEngine().align(original, "¿Café mañana? Conozco un pequeño lugar junto al río.", entries, .3)
        assertTrue(result.spans.any { it.translated == "Café" })
        val damaged = database.copyOf(); damaged[damaged.lastIndex] = (damaged.last().toInt() xor 1).toByte()
        assertTrue(runCatching { store.install(manifest, signature, damaged) }.isFailure)
        val fakeSignature = signature.copyOf(); fakeSignature[fakeSignature.lastIndex] = (fakeSignature.last().toInt() xor 1).toByte()
        assertTrue(runCatching { store.install(manifest, fakeSignature, database) }.isFailure)
        assertTrue(runCatching { VocabularyPackStore(context, emptyMap()).install(manifest, signature, database) }.isFailure)
        assertEquals(entries, store.entries("en-es", original))
        store.remove("en-es")
        assertTrue(store.entries("en-es", original).isEmpty())
    }
}
