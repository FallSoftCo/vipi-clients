package co.fallsoft.vipi

import androidx.compose.runtime.*
import androidx.compose.material3.Text
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File

class SentenceReadingsDeviceTest {
    @get:Rule val compose = createComposeRule()
    @Test fun exactReadingsPreserveParagraphsAndAbstainOnUnknownClauses() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val rows = JSONObject(context.assets.open("sentence-readings.json").bufferedReader().use { it.readText() }).getJSONArray("entries")
        val readings = SentenceReadings(context)
        assertEquals(410, rows.length())
        for (i in 0 until rows.length()) {
            val row = rows.getJSONObject(i); val language = row.getString("language")
            val native = row.getString("text"); val reading = row.getString("latin")
            assertEquals(reading, readings.reading(native, language))
            assertEquals("$reading\n$reading", readings.reading("$native\n$native", language))
            assertNull(readings.reading("$native\nUnknown new sentence.", language))
            assertNull(readings.reading(native, "sw"))
            assertTrue(reading.matches(Regex("^[\\p{IsLatin}\\p{M}\\p{N}\\s.,?!'’\\-]+$")))
            assertFalse(reading.codePoints().anyMatch { it in 0x0250..0x02FF || it in 0x1D00..0x1DBF })
        }
        assertEquals("Watashi wa ongaku ga suki desu. Eki wa doko desu ka.", readings.reading("私は音楽が好きです。駅はどこですか。", "ja"))
        assertNull(readings.reading("私は新しい音楽が好きです。", "ja"))
        assertNull(readings.reading("أنا أحب هذه الموسيقى.", "ar"))
        val file = File(context.filesDir, "sentence-readings-006.json"); check(!file.exists())
        file.writeText(JSONObject().put("exact_readings", rows.length()).put("languages", 4)
            .put("unknown_clause_abstention", true).put("independent_linguistic_acceptance", false).toString(2))
    }
    @Test fun japaneseChatRowOffersWholeReadingScriptAndNativeLanguageViews() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
        val preferences = context.getSharedPreferences("preferences", 0)
        val previousPace = preferences.getString("readingPace", null)
        val visible = mutableStateOf(true)
        compose.setContent {
            if (visible.value) VipiTheme(Appearance.LIGHT) {
                val scope = rememberCoroutineScope()
                val owner = remember { ConversationImmersion(context, "en", "ja", 1.0) }
                val speech = remember { SpeechPlayback(context, "en", "ja", scope) }
                DisposableEffect(Unit) { onDispose { owner.close(); speech.close() } }
                ConversationImmersionText("I like music.", "reading-qa", owner, speech, false, {}, { Text("A message") })
            }
        }
        try {
            compose.waitUntil(20_000) { device.hasObject(By.desc("I like ongaku.")) }
            compose.onNodeWithContentDescription("Reading options").performClick()
            compose.onNodeWithText("Japanese").performClick()
            compose.onNodeWithText("Watashi wa ongaku ga suki desu.").assertIsDisplayed()
            compose.onNodeWithContentDescription("Reading options").performClick()
            compose.onNodeWithText("Pause word switching").assertDoesNotExist()
            compose.onNodeWithText("Switching pace").assertDoesNotExist()
            compose.onNodeWithText("Show original script").performClick()
            compose.onNodeWithText("私は音楽が好きです。").assertIsDisplayed()
            compose.onNodeWithContentDescription("Reading options").performClick()
            compose.onNodeWithText("Show transliteration").performClick()
            compose.onNodeWithText("Watashi wa ongaku ga suki desu.").assertIsDisplayed()
            compose.onNodeWithContentDescription("Reading options").performClick()
            compose.onNodeWithText("English").performClick()
            compose.onNodeWithText("I like music.").assertIsDisplayed()
            compose.onNodeWithContentDescription("Reading options").performClick()
            compose.onNodeWithText("Show original script").assertDoesNotExist()
            device.pressBack()
            compose.onNodeWithContentDescription("Reading options").performClick()
            compose.onNodeWithText("Immersed").performClick()
            compose.onNodeWithContentDescription("Reading options").performClick()
            compose.onNodeWithText("Switching pace").performClick()
            compose.onNodeWithText("Relaxed").performClick()
            assertEquals("relaxed", preferences.getString("readingPace", null))
            compose.onNodeWithContentDescription("Reading options").performClick()
            compose.onNodeWithText("Switching pace").performClick()
            compose.onNodeWithText("Balanced").performClick()
            assertEquals("balanced", preferences.getString("readingPace", null))
        } finally {
            compose.runOnIdle { visible.value = false }; compose.waitForIdle()
            preferences.edit().apply { if (previousPace == null) remove("readingPace") else putString("readingPace", previousPace) }.commit()
        }
    }
}
