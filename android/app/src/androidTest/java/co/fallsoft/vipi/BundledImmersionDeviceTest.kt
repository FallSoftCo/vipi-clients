package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.json.JSONObject
import java.io.File
import android.database.sqlite.SQLiteDatabase

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
        assertEquals(110, pairs.size); assertEquals(10615, rows.length()); assertTrue(selected > 10000)
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
        val pastNeed = catalog.result("We needed a phone charger before dinner.", "Tulihitaji chaja ya simu kabla ya chakula cha jioni.", "en", "sw", 1.0)
        assertEquals("We needed a chaja ya simu before dinner.", pastNeed.speech("en", "sw").joinToString("") { it.text })
        val help = catalog.result("Nahitaji msaada sasa.", "I need help now.", "sw", "en", 1.0)
        assertEquals("Nahitaji help sasa.", help.speech("sw", "en").joinToString("") { it.text })
        assertTrue("A postal address is not a memory address", catalog.result("I need a memory address.", "Ninahitaji anwani ya kumbukumbu.", "en", "sw", 1.0).spans.isEmpty())
        assertTrue("Request grammar alone cannot align different nouns", catalog.result("I need food.", "Ninahitaji taarifa.", "en", "sw", 1.0).spans.isEmpty())
        val polite = catalog.result("Ningependa nambari ya simu sasa.", "I would like a phone number now.", "sw", "en", 1.0)
        assertEquals("Ningependa phone number sasa.", polite.speech("sw", "en").joinToString("") { it.text })
        val want = catalog.result("I want water now.", "Nataka maji sasa.", "en", "sw", 1.0)
        assertEquals("I want maji now.", want.speech("en", "sw").joinToString("") { it.text })
        assertNull("Never transplant a need reference into a want sentence", catalog.reference("I want water now.", "en", "sw"))
        val french = catalog.result("Je voudrais un numéro de téléphone.", "Ningependa nambari ya simu.", "fr", "sw", 1.0)
        assertEquals("Je voudrais un nambari ya simu.", french.speech("fr", "sw").joinToString("") { it.text })
        assertTrue(catalog.result("Sihitaji maji.", "I do not need water.", "sw", "en", 1.0).spans.isEmpty())
        var units=0
        for(pair in pairs.sorted()) {
            val (sourceLanguage,targetLanguage)=pair.split("-")
            val temporary=File.createTempFile("compound-qa-", ".sqlite",context.cacheDir)
            try {
                context.assets.open("immersion/$pair.sqlite").use { input -> temporary.outputStream().use { input.copyTo(it) } }
                SQLiteDatabase.openDatabase(temporary.path,null,SQLiteDatabase.OPEN_READONLY or SQLiteDatabase.NO_LOCALIZED_COLLATORS).use { db ->
                    db.rawQuery("SELECT payload FROM mappings",null).use { cursor ->
                        while(cursor.moveToNext()) {
                            val row=JSONObject(cursor.getString(0));if(!row.optBoolean("lexical_unit"))continue
                            val source=row.getString("source");val target=row.getString("target")
                            val result=catalog.result("$source.","$target.",sourceLanguage,targetLanguage,1.0)
                            assertEquals("$pair:$source",1,result.spans.size)
                            assertEquals(source,result.spans.single().original)
                            assertEquals("$target.",result.speech(sourceLanguage,targetLanguage).joinToString(""){it.text})
                            units++
                        }
                    }
                }
            } finally { check(temporary.delete()) }
        }
        assertEquals(660,units)
        val shared=catalog.result("Send the phone number.","Tuma nambari ya simu.","en","sw",1.0)
        assertEquals("Send the nambari ya simu.",shared.speech("en","sw").joinToString(""){it.text})
        for((left,right) in listOf("phone numbers." to "nambari ya simu.","phone number." to "ufunguo wa mlango.",
            "phone number; phone number." to "nambari ya simu.","phone number." to "nambari yangu ya simu."))
            assertTrue(catalog.result(left,right,"en","sw",1.0).spans.isEmpty())
        val existingPhone=catalog.result("What is your phone number?","Nambari ya simu yako ni ipi?","en","sw",1.0)
        assertEquals("What is your Nambari ya simu?",existingPhone.speech("en","sw").joinToString(""){it.text})
        val output = File(context.filesDir, "bundled-immersion-009.json"); check(!output.exists())
        output.writeText(JSONObject().put("pairs", pairs.size).put("references", rows.length()).put("spans", selected)
            .put("compound_units",units)
            .put("runtime_path", "app-bundled-native-catalog").put("independent_linguistic_acceptance", false).toString(2))
    }
}
