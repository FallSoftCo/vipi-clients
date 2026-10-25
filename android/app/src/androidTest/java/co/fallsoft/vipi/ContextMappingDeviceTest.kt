package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.ContextMapping
import co.fallsoft.vipi.core.ContextMappingMatcher
import co.fallsoft.vipi.core.ContextPart
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class ContextMappingDeviceTest {
    @Test fun actualPhraseTranslationsPreservePersonAndPossession() = runBlocking {
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val inputs=File(context.filesDir,"immersion-qa/authored-everyday.jsonl").readLines().map(::JSONObject)
        val mappings=inputs.filter { it.getJSONObject("usage").has("context_pattern") }.map { row ->
            val pattern=row.getJSONObject("usage").getJSONArray("context_pattern")
            val parts=(0 until pattern.length()).map { index ->
                val part=pattern.getJSONObject(index)
                when {
                    part.has("literal") -> ContextPart.Literal(part.getString("literal"))
                    part.has("focus") -> ContextPart.Focus(part.getString("focus"))
                    else -> ContextPart.Slot(part.getJSONArray("slot").let { array -> (0 until array.length()).map(array::getString) })
                }
            }
            ContextMapping(row.getString("logical_id"),row.getString("meaning"),row.getString("source_language"),
                row.getString("target_language"),parts,listOf(row.getString("target")))
        }
        assertEquals(3,mappings.size)
        val report=JSONObject(File(context.filesDir,"phrase-observations-001.json").readText())
        assertTrue(report.getBoolean("complete")); assertTrue(report.getBoolean("network_absence_verified"))
        val captures=report.getJSONArray("results"); val results=JSONArray()
        repeat(captures.length()) { index ->
            val row=captures.getJSONObject(index)
            if (row.getString("source")!="en" || row.getString("target")!="es") return@repeat
            val original=row.getString("original")
            val entries=ContextMappingMatcher.entries(original,"en","es",mappings)
            if (entries.isEmpty()) return@repeat
            val aligned=LocalImmersion.align(original,row.getString("translation"),entries,1.0,"en","es")
            assertEquals(1,aligned.spans.size)
            val span=aligned.spans.single()
            assertEquals(row.getInt("start"),span.start); assertEquals(row.getInt("end"),span.end)
            assertEquals(if (span.original=="books") "libros" else "libro",span.translated)
            val visible=aligned.speech("en","es").joinToString("") { it.text }
            assertEquals(original.substring(0,span.start)+span.translated+original.substring(span.end),visible)
            results.put(JSONObject().put("original",original).put("translation",row.getString("translation")).put("visible",visible))
        }
        assertEquals(3,results.length())
        File(context.filesDir,"context-mapping-001.json").writeText(JSONObject().put("cases",3)
            .put("scope","native context matcher against retained actual offline ML Kit output")
            .put("general_chat_integration",false).put("broad_linguistic_acceptance",false).put("results",results).toString(2))
    }
}
