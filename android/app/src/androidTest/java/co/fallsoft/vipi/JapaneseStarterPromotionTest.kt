package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.*
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import android.os.SystemClock

class JapaneseStarterPromotionTest {
    private class NoTranslation : LanguageTranslation {
        var calls=0
        override suspend fun prepare(source:String,target:String,cellularAllowed:Boolean)=error("No model preparation")
        override suspend fun translate(text:String,source:String,target:String):String { calls++;error("No new Translation call permitted") }
        override fun close() {}
    }
    private fun spans(value:ImmersionPresentation?)=JSONArray(value?.spans?.map { s -> JSONObject().put("source",s.original).put("target",s.translated)
        .put("reading",s.romanization ?: JSONObject.NULL).put("source_utf16",JSONArray(listOf(s.start,s.end))) } ?: emptyList<JSONObject>())
    @Test fun mechanismsAndCapture()=runBlocking {
        val args=InstrumentationRegistry.getArguments()
        org.junit.Assume.assumeTrue("Private starter capture is opt-in",args.containsKey("vipiJapaneseStarterCapture"))
        check(args.getString("vipiJapaneseStarterCapture")=="true")
        assertTrue(JapaneseStarterLookup.PROMOTION_ENABLED)
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        check(args.getString("vipiDedicatedEmulator")=="true")
        val input=File(context.filesDir,"japanese-starter-inputs-r01.json").readBytes()
        assertEquals("a4fe2868d2c341adb3360f5f80f535537ae1791ddbf0b7901fbbbc8ba63f03eb",JapaneseStarterLookup.sha(input))
        val data=context.assets.open("immersion/starter-en-ja-002.json").use{it.readBytes()}
        val manifest=context.assets.open("immersion/starter-catalog.json").use{it.readBytes()}
        val fixture=JSONObject(input.toString(Charsets.UTF_8));val cases=fixture.getJSONArray("cases");val states=fixture.getJSONArray("known_states")
        val allKnown=states.getJSONArray(2).let{a->(0 until a.length()).map{a.getString(it)}.toSet()}
        val known=JapaneseStarterLookup(data,manifest,allKnown).resolve("music","en","ja",.25)
        assertNull(known.partial);assertTrue(known.recognitions.isNotEmpty());assertFalse(known.allowsLegacy(0,5))
        val mechanism=JapaneseStarterLookup(data,manifest)
        assertEquals(mechanism.cacheIdentity,requireNotNull(JapaneseStarterLookup.bundledIfPromoted(context)).cacheIdentity)
        val masked=mechanism.resolve("music","en","ja",.25,sourceMasks=listOf(SourceLookupRange(0,5)))
        assertNull(masked.partial);assertFalse(masked.allowsLegacy(0,5))
        assertNull(mechanism.resolve("`music`","en","ja",.25).partial)
        assertNull(mechanism.resolve("I'm","en","ja",.25).partial)
        assertTrue(JapaneseStarterLookup.whitespaceGap(" "));assertTrue(JapaneseStarterLookup.whitespaceGap("\n\t"))
        assertFalse(JapaneseStarterLookup.whitespaceGap(". "));assertFalse(JapaneseStarterLookup.whitespaceGap(",\n"));assertFalse(JapaneseStarterLookup.whitespaceGap(""))
        mechanism.resolve("What. kind of music do you like?","en","ja",.25)
        assertTrue((0 until mechanism.trace.length()).any { mechanism.trace.getJSONObject(it).let { row -> row.getString("source")=="What. kind" && row.optString("reason")=="noncontiguous_source_unit" } })
        mechanism.resolve("What\nkind of music do you like?","en","ja",.25)
        assertFalse((0 until mechanism.trace.length()).any { mechanism.trace.getJSONObject(it).let { row -> row.getString("source")=="What\nkind" && row.optString("reason")=="noncontiguous_source_unit" } })
        val identities=(0 until states.length()).map { n -> val values=states.getJSONArray(n); JapaneseStarterLookup(data,manifest,(0 until values.length()).map { values.getString(it) }.toSet()).cacheIdentity }
        assertEquals(states.length(),identities.toSet().size)
        try { JapaneseStarterLookup(data.copyOf().also{it[0]=(it[0].toInt() xor 1).toByte()},manifest);fail("corrupt input accepted") } catch(_:IllegalArgumentException) {} catch(_:org.json.JSONException) {}
        val smokeRows=JSONArray()
        val smokeProvider=NoTranslation()
        ConversationImmersion(context,"en","ja",.25,translator=smokeProvider,qaModelsReady=false).use { smoke ->
            for ((label,text) in listOf("starter" to "music","reference" to "hello","literal" to "`music`")) {
                smoke.selectInputLanguage(label,"en")
                val value=smoke.presentation(text,"en",label);val outcome=requireNotNull(smoke.lastOutcome)
                assertNotEquals("STALE",outcome.status.name)
                when(label) {
                    "starter" -> { assertEquals("SOURCE_REFERENCE_PARTIAL",outcome.origin?.name);assertTrue(value?.spans?.any { it.translated=="音楽" }==true) }
                    "reference" -> { assertEquals("LOOKUP_REFERENCE",outcome.origin?.name);assertNotNull(value) }
                    "literal" -> assertTrue(value?.spans.isNullOrEmpty())
                }
                smokeRows.put(JSONObject().put("label",label).put("original",text).put("status",outcome.status.name).put("origin",outcome.origin?.name ?: JSONObject.NULL).put("spans",spans(value)))
            }
            assertEquals(0,smokeProvider.calls)
        }
        File(context.filesDir,"japanese-starter-route-smoke-r05.json").writeText(smokeRows.toString())
        val rows=JSONArray();val output=File(context.filesDir,"japanese-starter-output-r01.json");check(!output.exists())
        val report=JSONObject().put("schema",1).put("complete",false).put("platform","android").put("input_sha256",JapaneseStarterLookup.sha(input))
            .put("pack_sha256",JapaneseStarterLookup.sha(data)).put("activation",true).put("default_provider_path",true).put("model_policy","explicit unavailable injection; no Translation calls").put("cases",rows)
        fun save(){ val temporary=File(output.parentFile,output.name+".tmp");temporary.writeText(report.toString());check(temporary.length()<16*1024*1024);check(temporary.renameTo(output)) }
        save()
        for(stateIndex in 0 until states.length()) {
            val a=states.getJSONArray(stateIndex);val ids=(0 until a.length()).map{a.getString(it)}.toSet()
            val owner=JapaneseStarterLookup(data,manifest,ids);assertEquals(owner.cacheIdentity,requireNotNull(JapaneseStarterLookup.bundledIfPromoted(context,ids)).cacheIdentity);val provider=NoTranslation()
            ConversationImmersion(context,"en","ja",.25,translator=provider,qaModelsReady=false,sourceKnownConceptIDs=ids).use { engine ->
                for(n in 0 until cases.length()) {
                    val c=cases.getJSONObject(n);val id=c.getString("id");val text=c.getString("text")
                    engine.selectInputLanguage(id,"en")
                    val began=SystemClock.elapsedRealtimeNanos();val value=engine.presentation(text,"en",id);val elapsed=(SystemClock.elapsedRealtimeNanos()-began)/1e6
                    val outcome=requireNotNull(engine.lastOutcome);val counts=engine.lastInvocation;assertNotEquals("STALE",outcome.status.name);assertFalse(outcome.cacheHit);owner.resolve(text,"en","ja",.25);val trace=JSONArray(owner.trace.toString())
                    val direct=owner.resolve(text,"en","ja",.25)
                    assertTrue(direct.partial?.spans?.all { !it.romanization.isNullOrBlank() } ?: true)
                    value?.spans?.forEach{assertEquals(text.substring(it.start,it.end),it.original)}
                    val repeat=engine.presentation(text,"en",id);val repeatedOutcome=requireNotNull(engine.lastOutcome);if(value!=null) assertTrue(repeatedOutcome.cacheHit);assertEquals(0,provider.calls)
                    assertEquals(value?.spans,repeat?.spans)
                    val row=JSONObject().put("id",id).put("stratum",c.getString("stratum")).put("original",text).put("known_state",stateIndex).put("known_ids",a).put("density",.25)
                        .put("elapsed_ms",elapsed).put("status",outcome.status.name).put("origin",outcome.origin?.name ?: JSONObject.NULL)
                        .put("translation_calls",provider.calls).put("readiness_calls",counts.readiness).put("alignment_calls",counts.heavyAlignment)
                        .put("mixed",value?.let{ImmersionText.project(it)} ?: text).put("full_reference",value?.translation ?: JSONObject.NULL)
                        .put("cache_hit_on_repeat",repeatedOutcome.cacheHit).put("native_words",JSONArray(LocalImmersion.words(text,"en").map{JSONArray(listOf(it.first,it.last+1))}))
                        .put("trace",trace).put("spans",spans(value)).put("starter_spans",spans(direct.partial))
                        .put("recognitions",JSONArray(direct.recognitions.map{JSONObject().put("rule",it.ruleID).put("mask",it.mask?.let{r->JSONArray(listOf(r.start,r.end))} ?: JSONObject.NULL).put("approved",JSONArray(it.approvedOutputs.map{a->a.outputID}))}))
                    rows.put(row);save()
                }
            }
        }
        report.put("complete",true);save()
    }
}
