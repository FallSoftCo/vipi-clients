package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.json.JSONObject
import java.io.File

@RunWith(AndroidJUnit4::class)
class BundledImmersionDeviceTest {
    @Test fun appCatalogCoversAll110DirectionsAndPreservesOriginalText() {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val index = JSONObject(context.assets.open("immersion/catalog.json").bufferedReader().use { it.readText() })
        val rows = index.getJSONArray("references")
        val catalog = BundledImmersionCatalog(context)
        val pairs = mutableSetOf<String>(); var selected = 0
        for (i in 0 until rows.length()) {
            val row = rows.getJSONObject(i); val pair = row.getString("pair")
            val (source, target) = pair.split("-")
            val original = row.getString("original"); val translation = row.getString("translation")
            assertEquals(translation, catalog.reference(original, source, target))
            val result = catalog.result(original, translation, source, target, 1.0)
            assertEquals(original, result.original); assertEquals(translation, result.translation)
            assertEquals(original, result.speech(source, target, result.spans.map { it.id }.toSet()).joinToString("") { it.text })
            if (target in setOf("ar", "zh", "ja", "ko")) assertTrue(result.spans.all { !it.romanization.isNullOrBlank() })
            pairs += pair; selected += result.spans.size
        }
        assertEquals(110, pairs.size); assertEquals(9073, rows.length()); assertTrue(selected > 8600)
        assertEquals("Ninakunywa maji sasa.", catalog.reference("I am drinking water now.", "en", "sw"))
        assertNull(catalog.reference("We are drinking water now.", "en", "sw"))
        val embedded = catalog.result("We are drinking water now.", "Tunakunywa maji sasa.", "en", "sw", 1.0)
        assertEquals(1, embedded.spans.size)
        assertEquals("We are drinking maji now.", embedded.speech("en", "sw").joinToString("") { it.text })
        assertTrue(catalog.result("Book a room for us.", "Tuwekee chumba.", "en", "sw", 1.0).spans.isEmpty())
        assertEquals("Ninapenda muziki.\nNinakunywa maji sasa.", catalog.reference("I like music.\nI am drinking water now.", "en", "sw"))
        assertNull(catalog.reference("I like music.\nDo not guess this sentence.", "en", "sw"))
        val owned = catalog.result("Can they bring our book?", "¿Pueden traer nuestro libro?", "en", "es", 1.0)
        assertEquals("Can they bring our libro?", owned.speech("en", "es").joinToString("") { it.text })
        val office = catalog.result("Niko ofisini.", "I’m at the office.", "sw", "en", 1.0)
        assertEquals("Niko officeni.", office.speech("sw", "en").joinToString("") { it.text })
        val money = catalog.result("I don’t have enough money.", "Sina pesa za kutosha.", "en", "sw", 1.0)
        assertEquals("I don’t have enough pesa.", money.speech("en", "sw").joinToString("") { it.text })
        val request = catalog.result("Natafuta hoteli karibu.", "I am looking for a hotel nearby.", "sw", "en", 1.0)
        assertEquals("Natafuta hotel karibu.", request.speech("sw", "en").joinToString("") { it.text })
        val plural = catalog.result("We are looking for a hotel nearby.", "Tunatafuta hoteli karibu.", "en", "sw", 1.0)
        assertEquals("We are looking for a hoteli nearby.", plural.speech("en", "sw").joinToString("") { it.text })
        val ticket = catalog.result("I need a train ticket.", "Ninahitaji tiketi ya treni.", "en", "sw", 0.25)
        assertEquals("I need a tiketi ya treni.", ticket.speech("en", "sw").joinToString("") { it.text })
        assertTrue(catalog.result("We are not sending an email tonight.", "Hatutumi barua pepe leo usiku.", "en", "sw", 1.0).spans.isEmpty())
        val output = File(context.filesDir, "bundled-immersion-004.json"); check(!output.exists())
        output.writeText(JSONObject().put("pairs", pairs.size).put("references", rows.length()).put("spans", selected)
            .put("runtime_path", "app-bundled-native-catalog").put("independent_linguistic_acceptance", false).toString(2))
    }
}
