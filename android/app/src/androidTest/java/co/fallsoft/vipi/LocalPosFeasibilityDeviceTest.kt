package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.TranslationIntegrity
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Test
import java.io.File

/** Research-only: native English POS is not semantic admission or a name detector. */
class LocalPosFeasibilityDeviceTest {
 @Test fun inspectEveryEnglishNounAndVerb() = runBlocking {
  val inst=InstrumentationRegistry.getInstrumentation();check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator")=="true");val dir=File(inst.targetContext.filesDir,"local-pos-feasibility-r01");val out=File(dir,"report.json");check(!out.exists());val cases=JSONObject(File(dir,"fixtures.json").readText()).getJSONArray("cases");val rows=JSONArray();val report=JSONObject().put("complete",false).put("cases",rows).put("scope","POS research only; POS/isolated translation do not establish sense, alignment or safe display; name detector unavailable")
  val provider=EnglishSourceRoleProvider(inst.targetContext.assets)
  for(i in 0 until cases.length()) {
   val f=cases.getJSONObject(i);if(f.getString("source_language")!="en")continue;val text=f.getString("original");val target=f.getString("target_language");val native=LocalImmersion.words(text,"en").map{FrozenContextTokenizer.Range(it.first,it.last+1)};val protection=TranslationIntegrity.protectedLiteralRanges(text).map{FrozenContextTokenizer.Range(it.first,it.last+1)};val result=provider.inspect(text,"en",native,protection);val tokens=JSONArray();val row=JSONObject().put("id",f.getString("id")).put("original",text).put("target",target).put("status",result.snapshot.status.name).put("name_protection",result.snapshot.namedProtection.name).put("native_words",JSONArray(native.map{JSONArray(listOf(it.start,it.end))})).put("tokens",tokens)
   val translator=LocalTranslation()
   try {val full=withTimeout(30000){translator.translate(text,"en",target)};row.put("full_translation",full)
    for(token in result.tokens) {
     val aligned=native.any{it==token.range};val masked=protection.any{it.start<token.range.end && token.range.start<it.end};val admitted=aligned && !masked && token.rawTag in setOf("NOUN","VERB")
     val item=JSONObject().put("surface",token.original).put("range",JSONArray(listOf(token.range.start,token.range.end))).put("tag",token.rawTag).put("tag_score",token.score).put("native_aligned",aligned).put("protected",masked).put("admitted_for_diagnostic",admitted)
     if(admitted)try {val began=System.nanoTime();val translated=withTimeout(30000){translator.translate(token.original,"en",target)};item.put("translation",translated).put("elapsed_ms",(System.nanoTime()-began)/1e6).put("reconstructed",text.replaceRange(token.range.start,token.range.end,translated));val m=Regex(Regex.escape(translated),RegexOption.IGNORE_CASE).findAll(full).toList();val targetWords=LocalImmersion.words(full,target);item.put("literal_occurrences",m.size).put("complete_target_word_occurrences",m.count{match->targetWords.any{it.first==match.range.first}&&targetWords.any{it.last==match.range.last}});if(target in setOf("ar","ja","ko","zh")){val reading=NativeFullReadings.resolve(translated,target,SentenceReadings(inst.targetContext),inst.targetContext);item.put("reading",reading?.text?:JSONObject.NULL)}} catch(e:Exception){item.put("translation_error",e.javaClass.simpleName)}
     tokens.put(item)
    }
   } catch(e:Exception){row.put("error",e.javaClass.simpleName)} finally {translator.close();rows.put(row);out.writeText(report.toString(2))}
  }
  report.put("complete",true);out.writeText(report.toString(2))
 }
}
