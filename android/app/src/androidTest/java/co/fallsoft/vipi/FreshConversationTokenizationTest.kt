package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.MessageDigest

/** Freeze native boundaries before any forward/reverse provider evaluation. */
class FreshConversationTokenizationTest {
    @Test fun freezeEightyNativeSourceBoundariesWithoutTranslation() {
        check(InstrumentationRegistry.getArguments().getString("vipiFreshHoldoutTokenize") == "true")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val bytes = File(context.filesDir, "conversational-holdout-source-r01.json").readBytes()
        val sha = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
        assertEquals("76545660657732d09a98ac749cec9365292479c9d0a463563dfbe46e4e986586", sha)
        val cases = JSONObject(bytes.toString(Charsets.UTF_8)).getJSONArray("cases")
        assertEquals(80, cases.length())
        val rows = JSONArray()
        for (index in 0 until cases.length()) {
            val row = cases.getJSONObject(index)
            assertEquals("en", row.getString("source")); assertEquals("sw", row.getString("target"))
            val text = row.getString("text")
            rows.put(JSONObject().put("id", row.getString("id")).put("text", text)
                .put("native_source_word_ranges", JSONArray().apply {
                    LocalImmersion.words(text, "en").forEach { put(JSONArray().put(it.first).put(it.last + 1)) }
                }))
        }
        val output = File(context.filesDir, "conversational-tokenization-r01.json"); check(!output.exists())
        output.writeText(JSONObject().put("input_sha256", sha).put("complete", true).put("tokenize_only", true)
            .put("translation_calls", 0).put("cases", rows).toString(2))
    }
}
