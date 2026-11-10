package co.fallsoft.vipi
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.*
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test
import java.io.File

/** Mechanism-only synthetic lexical edge; no conversation recapture or provider calls. */
class ContextualSenseMaskTest {
 @Test fun retainedRecognitionBlocksSyntheticLegacyEdge()=runBlocking {
  val args=InstrumentationRegistry.getArguments();org.junit.Assume.assumeTrue(args.getString("vipiContextualSenseMask")=="true");check(args.getString("vipiDedicatedEmulator")=="true")
  val context=InstrumentationRegistry.getInstrumentation().targetContext
  val provider=SwahiliStarterLookup.bundledIfPromoted(context) ?: error("Missing held pack")
  val manifest=context.assets.open("immersion/starter-sw-catalog.json").use{it.readBytes()}
  val file=JSONObject(manifest.toString(Charsets.UTF_8)).getString("file");assertEquals("starter-en-sw-005.json",file)
  val bytes=context.assets.open("immersion/$file").use{it.readBytes()}
  val raw=SwahiliStarterLookup(bytes,manifest,packMultiple=true)
  val rows=JSONArray()
  for(text in listOf("hair","My hair is long.","The cat has hair.")) {
   val a=text.indexOf("hair");val b=a+4;val held=provider.lookup(text,"en","sw",.75)
   raw.resolve(text,"en","sw",.75)
   val hair=(0 until raw.trace.length()).map{raw.trace.getJSONObject(it)}.single{it.getString("source")=="hair"}
   assertEquals("unqualified_source_sense",hair.getString("reason"))
   assertFalse(held.allowsLegacy(a,b));assertTrue(held.partial?.spans.orEmpty().none{it.start<b && a<it.end})
   assertTrue(held.recognitions.any{it.mask?.let{m->m.start<=a && m.end>=b}==true && it.approvedOutputs.none{p->p.range.start<b && a<p.range.end}})
   rows.put(JSONObject().put("source",text).put("trace",hair).put("hair_scope",JSONArray(listOf(a,b))).put("mask_retained",true).put("deliberate_human_hair_omission",text=="My hair is long."))
  }
  val synthetic=listOf(VocabularyEntry("hair",listOf("nywele")))
  val unmasked=LocalImmersion.align("hair","nywele",synthetic,.75,"en","sw")
  assertEquals(1,unmasked.spans.size);assertEquals("hair",unmasked.spans.single().original);assertEquals("nywele",unmasked.spans.single().translated)
  val held=provider.lookup("hair","en","sw",.75)
  val masked=LocalImmersion.align("hair","nywele",synthetic,.75,"en","sw",sourceEvidence=held)
  assertTrue(masked.spans.isEmpty())
  File(context.filesDir,"android-controls.json").writeText(JSONObject().put("controls",rows).put("synthetic_lexical_entry_and_target",true).put("production_dictionary_mutated",false).put("unmasked_legacy_spans",unmasked.spans.size).put("masked_legacy_spans",masked.spans.size).put("translation_model_calls",0).toString())
  File(context.filesDir,"android-status.json").writeText(JSONObject().put("rows",0).put("control_cases",4).put("translation_calls",0).put("default_capture_replayed",false).toString())
 }
}
