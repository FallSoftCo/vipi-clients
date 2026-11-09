package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.*
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test
import java.io.File

/** Actual default route; private QA opt-in, no injected presentation or translations. */
class StarterTechnicalLiteralRouteTest {
 private class NoTranslation:LanguageTranslation {
  override suspend fun prepare(source:String,target:String,cellularAllowed:Boolean)=error("No preparation")
  override suspend fun translate(text:String,source:String,target:String):String=error("No translation")
  override fun close() {}
 }
 @Test fun technicalLiteralsThroughDefaultConversation()=runBlocking {
  val args=InstrumentationRegistry.getArguments()
  org.junit.Assume.assumeTrue(args.getString("vipiContentExpansion")=="true")
  check(args.getString("vipiDedicatedEmulator")=="true")
  val context=InstrumentationRegistry.getInstrumentation().targetContext
  val records=JSONArray()
  for(target in listOf("ja","sw")) {
   val engine=ConversationImmersion(context,"en",target,.75,translator=NoTranslation(),qaModelsReady=false)
   try {
    for(token in listOf("music_notes.txt","music_notes","music.txt","music-notes.json","music.tar.gz","music.JPG","music.vipihistory","music_notes.custom","_music_notes","music__notes","music.txt_notes",".music_notes","music_notes_","music..notes_")) {
     val text="Send $token and enjoy music.";val start=text.indexOf(token);val end=start+token.length;val ordinary=text.lastIndexOf("music")
     engine.selectInputLanguage(token,"en");val result=requireNotNull(engine.presentation(text,"en",token));val outcome=requireNotNull(engine.lastOutcome)
     assertTrue("ordinary music remains available $target/$token",result.spans.any{it.start==ordinary && it.end==ordinary+5})
     assertFalse("literal changed $target/$token",result.spans.any{it.start<end && start<it.end})
     assertEquals(0,outcome.localTranslationCalls)
     records.put(JSONObject().put("pair","en-$target").put("source",text).put("token",token).put("mixed",ImmersionText.project(result)).put("origin",outcome.origin?.name).put("status",outcome.status.name).put("translation_calls",outcome.localTranslationCalls).put("spans",JSONArray(result.spans.map{JSONObject().put("source",it.original).put("target",it.translated).put("reading",it.romanization ?: JSONObject.NULL).put("source_utf16",JSONArray(listOf(it.start,it.end)))})))
    }
   } finally {engine.close()}
  }
  assertEquals(28,records.length())
  File(context.filesDir,"content-literal-controls.json").writeText(records.toString())
 }
}
