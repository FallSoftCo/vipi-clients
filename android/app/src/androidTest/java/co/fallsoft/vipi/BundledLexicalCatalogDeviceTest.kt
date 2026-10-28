package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.UUID

@RunWith(AndroidJUnit4::class)
class BundledLexicalCatalogDeviceTest {
    @Test fun selectedPairRepairsDamageAndRejectsInvalidStreams() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val root = File(instrumentation.targetContext.cacheDir, "lexical-fixture-" + UUID.randomUUID())
        val store = BundledLexicalCatalog(instrumentation.context, "lexical-fixture", root)
        try {
            assertTrue(store.prepare("en", "es"))
            assertEquals(3, root.listFiles().orEmpty().size)
            assertFalse(root.listFiles().orEmpty().any { it.name.startsWith("d-pt-") })
            val entries = store.entries("An apple.", "Una manzana.", "en", "es")
            assertTrue(entries.any { it.source == "apple" && "manzana" in it.targets })
            val file = root.listFiles()!!.single { it.name.startsWith("d-en-") }
            val expected = file.readBytes()
            val initial = file.lastModified()
            assertTrue(store.prepare("es", "en"))
            assertEquals(initial, file.lastModified())
            file.writeBytes(byteArrayOf(0, 1))
            assertTrue(store.prepare("en", "es"))
            assertArrayEquals(expected, file.readBytes())
            for (target in listOf("fr", "de")) {
                var rejected = false
                try { store.prepare("en", target) } catch (_: Exception) { rejected = true }
                assertTrue("Invalid $target fixture must be rejected", rejected)
                assertEquals(3, root.listFiles().orEmpty().size)
                assertFalse(root.listFiles().orEmpty().any { it.name.startsWith("prepare-") })
            }
            assertTrue(store.entries("An apple.", "Una manzana.", "en", "es").any { it.source == "apple" })
        } finally { root.deleteRecursively() }
    }
}
