package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.json.JSONObject
import java.io.File

@RunWith(AndroidJUnit4::class)
class MessageLanguageDeviceTest {
    @Test fun inputLanguageChoiceBelongsToMessageAndSurvivesRowRecreation() = runBlocking {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        withContext(Dispatchers.Main) {
            val owner = ConversationImmersion(context, "en", "sw", 1.0)
            try {
                val text = "Ninapenda muziki."
                owner.selectInputLanguage("message-one", "sw")
                val value = owner.result(text, owner.inputLanguage("message-one"))
                assertNotNull(value)
                assertEquals(value, owner.cached(text, "message-one"))
                assertNull(owner.cached(text, "message-two"))
                assertNull(owner.inputLanguage("message-two"))
                owner.selectInputLanguage("message-one", "de")
                assertEquals("sw", owner.inputLanguage("message-one"))
                owner.selectInputLanguage("message-one", null)
                assertNull(owner.inputLanguage("message-one"))
                owner.selectInputLanguage("message-one", "sw")
            } finally { owner.close() }
            assertNull(owner.inputLanguage("message-one"))
            assertNull(owner.cached("Ninapenda muziki.", "message-one"))
        }
    }
    @Test fun bundledIdentificationRecognizesElevenNativeParagraphsAndAbstainsOnShortInput() = runBlocking {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val examples = JSONObject(context.assets.open("immersion-preview.json").bufferedReader().use { it.readText() }).getJSONObject("languages")
        val results = JSONObject()
        MessageLanguage().use { language ->
            for (code in initialLanguages.map { it.code }) {
                val guess = language.identify(examples.getJSONObject(code).getString("text"))
                results.put(code, guess ?: JSONObject.NULL)
                assertEquals(code, guess)
            }
            for (text in listOf("ok", "no", "42", "🙂")) assertNull(language.identify(text))
        }
        val output = File(context.filesDir, "message-language-001.json"); check(!output.exists())
        output.writeText(JSONObject().put("authored_paragraphs", results).put("independent_accuracy", false).toString(2))
    }

    @Test fun learningLanguageInputUsesNativeBaselineAndKeepsExactTarget() = runBlocking {
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        withContext(Dispatchers.Main) {
            ConversationImmersion(context, "en", "sw", 1.0).use { owner ->
                owner.checkDownloads(); assertEquals(true, owner.ready)
                val exact = requireNotNull(owner.result("Ninapenda muziki."))
                assertEquals("I like music.", exact.original)
                assertEquals("Ninapenda muziki.", exact.translation)
                assertEquals("I like muziki.", exact.speech("en", "sw").joinToString("") { it.text })
                val unseen = requireNotNull(owner.result("Tunakunywa maji sasa."))
                assertEquals("Tunakunywa maji sasa.", unseen.translation)
                assertTrue(unseen.spans.any { it.original.equals("water", ignoreCase = true) && it.translated == "maji" })
                assertNull(owner.result("ok"))
                assertNull(owner.result("Das ist ein langer deutscher Satz über unsere gemeinsame Reise."))
                assertNull(owner.result("Ninapenda muziki.", "de"))
                assertEquals(exact, owner.result("Ninapenda muziki.", "sw"))
                assertEquals(exact, owner.result("Ninapenda muziki."))
            }
        }
    }
}
