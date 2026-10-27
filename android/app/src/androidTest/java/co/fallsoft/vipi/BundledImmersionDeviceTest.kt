package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.json.JSONObject
import java.io.File
import android.database.sqlite.SQLiteDatabase
import kotlinx.coroutines.runBlocking

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
        assertEquals(110, pairs.size); assertEquals(12575, rows.length()); assertTrue(selected > 10000)
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
        assertEquals("We are not sending an barua pepe tonight.", catalog.result("We are not sending an email tonight.", "Hatutumi barua pepe leo usiku.", "en", "sw", 1.0).speech("en","sw").joinToString(""){it.text})
        val pastNeed = catalog.result("We needed a phone charger before dinner.", "Tulihitaji chaja ya simu kabla ya chakula cha jioni.", "en", "sw", 1.0)
        assertEquals("We needed a chaja ya simu before chakula cha jioni.", pastNeed.speech("en", "sw").joinToString("") { it.text })
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
        assertEquals("Sihitaji water.",catalog.result("Sihitaji maji.", "I do not need water.", "sw", "en", 1.0).speech("sw","en").joinToString(""){it.text})
        var units=0;var unchanged=0
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
                            if(source.equals(target,ignoreCase=true) && targetLanguage !in setOf("ar","zh","ja","ko")) {
                                assertTrue("Identical written words need no artificial flip",result.spans.isEmpty())
                                assertEquals("$source.",result.speech(sourceLanguage,targetLanguage).joinToString(""){it.text})
                                unchanged++
                            } else {
                                assertEquals("$pair:$source",1,result.spans.size)
                                assertEquals(source,result.spans.single().original)
                                assertEquals("$target.",result.speech(sourceLanguage,targetLanguage).joinToString(""){it.text})
                            }
                            units++
                        }
                    }
                }
            } finally { check(temporary.delete()) }
        }
        assertEquals(28965,units)
        assertEquals(708,unchanged)
        val shared=catalog.result("Send the phone number.","Tuma nambari ya simu.","en","sw",1.0)
        assertEquals("Send the nambari ya simu.",shared.speech("en","sw").joinToString(""){it.text})
        for((left,right) in listOf("phone numbers." to "nambari ya simu.","phone number." to "ufunguo wa mlango.",
            "phone number; phone number." to "nambari ya simu.","phone number." to "nambari yangu ya simu."))
            assertTrue("No unsupported complete phone-number unit",catalog.result(left,right,"en","sw",1.0).spans.none { it.original.contains("number") })
        val existingPhone=catalog.result("What is your phone number?","Nambari ya simu yako ni ipi?","en","sw",1.0)
        assertEquals("What is your Nambari ya simu?",existingPhone.speech("en","sw").joinToString(""){it.text})
        for((left,right,expected) in listOf(
            Triple("Do you like this music?","Je, unapenda muziki huu?","Do you like this muziki?"),
            Triple("Hatuna pesa leo.","We have no money today.","Hatuna money today."),
            Triple("Muziki huu ni mzuri.","This music is good.","music huu ni mzuri."))) {
            val reverse=left.startsWith("Hatuna") || left.startsWith("Muziki")
            val source=if(reverse) "sw" else "en";val target=if(reverse) "en" else "sw"
            val result=catalog.result(left,right,source,target,1.0)
            assertEquals(expected,result.speech(source,target).joinToString(""){it.text})
            assertEquals(left,result.original)
        }
        assertNull("Lexical case examples cannot become whole translations",catalog.reference("music.","en","sw"))
        for((left,right) in listOf("music and music" to "muziki", "book the taxi" to "weka nafasi ya teksi",
            "music" to "filamu", "https://example.test/music" to "muziki"))
            assertTrue(catalog.result(left,right,"en","sw",1.0).spans.isEmpty())
        val output = File(context.filesDir, "bundled-immersion-017.json"); check(!output.exists())
        output.writeText(JSONObject().put("pairs", pairs.size).put("references", rows.length()).put("spans", selected)
            .put("lexical_units",units).put("unchanged_latin_forms",unchanged)
            .put("runtime_path", "app-bundled-native-catalog").put("independent_linguistic_acceptance", false).toString(2))
    }
    @Test fun peopleUnitsPreserveNumberAndExcludeAmbiguousSourceForms() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val catalog = BundledImmersionCatalog(context)
        val original = "I did not see the children."
        val value = catalog.result(original, "Sikuwaona watoto.", "en", "sw", 1.0)
        assertEquals(original, value.original)
        assertEquals("I did not see the watoto.", value.speech("en", "sw").joinToString("") { it.text })
        val reverse = catalog.result("Sikumwona mtoto.", "I did not see the child.", "sw", "en", 1.0)
        assertEquals("Sikumwona child.", reverse.speech("sw", "en").joinToString("") { it.text })
        for ((left, right, source, target) in listOf(
            listOf(original, "Sikumwona mtoto.", "en", "sw"),
            listOf("Mtoto.", "Children.", "sw", "en"),
            listOf("Personne.", "Hakuna mtu.", "fr", "sw"),
            listOf("هل هي أختها أم أمها؟", "Is she her sister or her mother?", "ar", "en"),
            listOf("عالم يدرس العالم.", "A scholar studies the world.", "ar", "en")
        )) {
            val rejected = catalog.result(left, right, source, target, 1.0)
            assertTrue("Do not borrow a different number or ambiguous source noun: $source:$left", rejected.spans.isEmpty())
        }
        assertNull("A noun carrier is not a whole-sentence translation", catalog.reference("children.", "en", "sw"))
        assertEquals("I met my marafiki.", catalog.result("I met my friends.", "Nilikutana na marafiki zangu.", "en", "sw", 1.0).speech("en", "sw").joinToString("") { it.text })
        assertEquals("books vyetu viko hapa.", catalog.result("Vitabu vyetu viko hapa.", "Our books are here.", "sw", "en", 1.0).speech("sw", "en").joinToString("") { it.text })
        assertTrue(catalog.result("Vitabu.", "Book.", "sw", "en", 1.0).spans.isEmpty())
        assertTrue(catalog.result("She books it.", "Anaweka nafasi; vitabu viko hapa.", "en", "sw", 1.0).spans.isEmpty())
    }
    @Test fun shortGreetingsAndNamesakeUseLocalReferencesInBothDirections() = runBlocking {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        ConversationImmersion(context, "en", "sw", 0.25).use { owner ->
            assertNull(owner.ready) // No translation-model preparation is performed.
            for ((original, expected) in listOf("hi" to "Hujambo.", "Thanks a lot." to "Asante sana.",
                "What's up?" to "Mambo vipi?")) {
                val value = requireNotNull(owner.result(original))
                assertEquals(original, value.original)
                assertEquals(expected, value.translation)
                assertEquals("Keep the complete conversational formula", 1, value.spans.size)
            }
            val reverse = requireNotNull(owner.result("Mambo vipi?"))
            assertEquals("What's up?", reverse.original)
            assertEquals("Mambo vipi?", reverse.translation)
            assertEquals("Mambo vipi?", reverse.speech("en", "sw").joinToString("") { it.text })
            assertNull(owner.ready)
        }
        val catalog = BundledImmersionCatalog(context)
        assertNull(catalog.reference("What's up there?", "en", "sw"))
        val preserved = catalog.result("I did not say Thanks.", "Sikusema Asante.", "en", "sw", 1.0)
        assertEquals("I did not say Asante.", preserved.speech("en", "sw").joinToString("") { it.text })
    }
}
