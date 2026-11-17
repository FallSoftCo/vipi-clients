package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.ImmersionOrigin
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

class FrozenRouteQualificationTest {
 @Test fun realAutomaticProviderAndExactReferenceFull()=runBlocking {
  val context=InstrumentationRegistry.getInstrumentation().targetContext
  assertEquals("co.fallsoft.vipi.frozenrouteqa",context.packageName)
  val rows=JSONArray(); val provider=requireNotNull(BundledStarterLookup.provider(context))
  for(target in listOf("ja","sw")) {
   val owner=ConversationImmersion(context,"en",target,.75,sourceLookup=provider,qaModelsReady=false)
   try {
    val text="I love music."; val result=requireNotNull(owner.presentation(text))
    val span=requireNotNull(result.spans.singleOrNull{it.original=="music"})
    assertEquals(if(target=="ja") "音楽" else "muziki",span.translated)
    if(target=="ja") assertEquals("ongaku",span.romanization)
    assertEquals(0,requireNotNull(owner.lastOutcome).localTranslationCalls)
    val exact="I like music."; val expected=requireNotNull(BundledImmersionCatalog(context).reference(exact,"en",target))
    val full=owner.fullTranslation(exact,null,null,1L)
    assertEquals(ImmersionOrigin.LOOKUP_REFERENCE,full.origin);assertEquals(expected,full.result?.translation)
    assertEquals(0,full.localTranslationCalls)
    rows.put(JSONObject().put("target",target).put("status",owner.lastOutcome?.status?.name).put("source",span.original).put("translated",span.translated).put("reading",span.romanization?:JSONObject.NULL).put("exact_reference",true).put("full_calls",full.localTranslationCalls))
   } finally {owner.close()}
  }
  File(context.filesDir,"frozen-route-result.json").writeText(JSONObject().put("synthetic",true).put("revision","a52a806").put("cases",rows).toString(2))
 }
}
