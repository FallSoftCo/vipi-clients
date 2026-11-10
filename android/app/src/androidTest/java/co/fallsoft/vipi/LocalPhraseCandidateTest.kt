package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

class LocalPhraseCandidateTest {
    @Test fun actualLocalRoutes() = runBlocking {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(context.filesDir,"local-phrase-input")
        assumeTrue("Explicit private candidate input required", File(root,"fixtures.json").exists())
        fun bytes(name: String) = File(root,name).readBytes()
        val cases = JSONObject(bytes("fixtures.json").toString(Charsets.UTF_8)).getJSONArray("cases")
        val jaManifest = bytes("starter-catalog.json")
        val ja = JapaneseStarterLookup(bytes(JSONObject(jaManifest.toString(Charsets.UTF_8)).getString("file")),jaManifest,packMultiple=true)
        val swManifest = bytes("starter-sw-catalog.json")
        val sw = SwahiliStarterLookup(bytes(JSONObject(swManifest.toString(Charsets.UTF_8)).getString("file")),swManifest,packMultiple=true)
        val candidate = requireNotNull(BundledStarterLookup.compose(
            SourceFrameLookup.bundled(context,"ja",ja,emptySet()) { ja.rawCandidates },
            SourceFrameLookup.bundled(context,"sw",sw,emptySet()) { sw.rawCandidates }))
        val rows = JSONArray()
        for ((variant, provider) in listOf("baseline" to requireNotNull(BundledStarterLookup.provider(context)), "candidate" to candidate)) {
            for (i in 0 until cases.length()) {
                val c = cases.getJSONObject(i); val source = c.getString("source"); val target = c.getString("pair").takeLast(2)
                for (density in listOf(.25,.75)) {
                    val owner = ConversationImmersion(context,"en",target,density,qaModelsReady=false,sourceLookup=provider)
                    try {
                        val result = owner.presentation(source,inputLanguage="en")
                        val outcome = requireNotNull(owner.lastOutcome); assertEquals(0,outcome.localTranslationCalls)
                        assertTrue("Lookup must succeed or explicitly miss: ${c.getString("id")} / $variant / ${outcome.status}",
                            outcome.status in setOf(co.fallsoft.vipi.core.ImmersionStatus.PARTIAL, co.fallsoft.vipi.core.ImmersionStatus.NO_LOCAL_MATCH))
                        val spans = result?.spans.orEmpty(); val mixed = StringBuilder(source)
                        for (span in spans.reversed()) mixed.replace(span.start,span.end,span.translated)
                        rows.put(JSONObject().put("id",c.getString("id")).put("variant",variant).put("target",target)
                            .put("density",density).put("source",source).put("mixed",mixed.toString())
                            .put("status",outcome.status.name).put("translation_calls",outcome.localTranslationCalls)
                            .put("spans",JSONArray(spans.map { JSONObject().put("start",it.start).put("end",it.end)
                                .put("source",it.original).put("target",it.translated).put("reading",it.romanization ?: "") })))
                    } finally { owner.close() }
                }
            }
        }
        assertEquals(cases.length()*4, rows.length())
        for (variant in listOf("baseline","candidate")) for (target in listOf("ja","sw")) {
            assertTrue("The fixture must demonstrate actual output for $variant/$target", (0 until rows.length()).any {
                val row=rows.getJSONObject(it); row.getString("variant")==variant && row.getString("target")==target && row.getJSONArray("spans").length()>0
            })
        }
        File(root,"android-results.json").writeText(rows.toString())
    }
}
