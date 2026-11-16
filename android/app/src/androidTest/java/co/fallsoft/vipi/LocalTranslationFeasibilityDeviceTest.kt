package co.fallsoft.vipi

import androidx.test.platform.app.InstrumentationRegistry
import com.google.mlkit.common.model.RemoteModelManager
import com.google.mlkit.nl.translate.TranslateRemoteModel
import kotlinx.coroutines.*
import kotlinx.coroutines.tasks.await
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Test
import java.io.File

/** Offline, model-preserving diagnostic; no downloads and no automatic immersion. */
class LocalTranslationFeasibilityDeviceTest {
 @Test fun compareContextAndFocusedPhrases() = runBlocking {
  val inst=InstrumentationRegistry.getInstrumentation();check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator")=="true")
  val dir=File(inst.targetContext.filesDir,"local-translation-feasibility-r01");val out=File(dir,InstrumentationRegistry.getArguments().getString("vipiReport") ?: "report.json");check(!out.exists())
  val cases=JSONObject(File(dir,"fixtures.json").readText()).getJSONArray("cases");val rows=JSONArray();val report=JSONObject().put("complete",false).put("cases",rows)
  fun save(){out.writeText(report.toString(2))};val manager=RemoteModelManager.getInstance()
  for(i in 0 until cases.length()) {
   val f=cases.getJSONObject(i);val text=f.getString("original");val source=f.getString("source_language");val target=f.getString("target_language");val bounds=f.getJSONArray("focus_utf16");val a=bounds.getInt(0);val b=bounds.getInt(1);check(text.substring(a,b)==f.getString("focus"))
   val row=JSONObject().put("id",f.getString("id")).put("source",source).put("target",target).put("original",text).put("focus",text.substring(a,b)).put("focus_utf16",bounds)
   val models=setOf(source,target)-"en";val available=models.associateWith { manager.isModelDownloaded(TranslateRemoteModel.Builder(it).build()).await() };row.put("model_installed",JSONObject(available))
   if(available.values.any{!it}){row.put("status","model_unavailable");rows.put(row);save();continue}
   val translator=LocalTranslation();val outputs=JSONArray();row.put("outputs",outputs)
   suspend fun measure(kind:String,input:String):String {val t=System.nanoTime();val translated=withTimeout(30_000){translator.translate(input,source,target)};outputs.put(JSONObject().put("kind",kind).put("input",input).put("translation",translated).put("elapsed_ms",(System.nanoTime()-t)/1e6));return translated}
   try {
    val full=measure("full_cold",text);measure("full_warm",text);val focus=measure("focus_cold",text.substring(a,b));measure("focus_warm",text.substring(a,b));val occurrences=if(focus.isEmpty())emptyList() else Regex(Regex.escape(focus),RegexOption.IGNORE_CASE).findAll(full).toList()
    row.put("focus_literal_occurrences_in_full",occurrences.size)
    val targetWords=LocalImmersion.words(full,target);row.put("focus_complete_word_occurrences_in_full",occurrences.count { m -> targetWords.any{it.first==m.range.first} && targetWords.any{it.last==m.range.last} })
    if(target in setOf("ar","zh","ja","ko")) {
     val reading=NativeFullReadings.resolve(focus,target,SentenceReadings(inst.targetContext),inst.targetContext)
     row.put("focus_reading",reading?.text ?: JSONObject.NULL).put("reading_provenance",reading?.provenance?.name ?: JSONObject.NULL)
    }
    val words=LocalImmersion.words(text,source);val start=words.indexOfFirst{it.last+1>a};val end=words.indexOfLast{it.first<b}
    if(start>=0 && end>=start)for(radius in 1..2){val l=words[maxOf(0,start-radius)].first;val r=words[minOf(words.lastIndex,end+radius)].last+1;val phrase=text.substring(l,r);if(phrase!=text && phrase!=text.substring(a,b))measure("window_$radius",phrase)}
    row.put("status","translated")
   } catch(e:Exception){row.put("status","error").put("error_class",e.javaClass.simpleName)} finally{translator.close();rows.put(row);save()}
  }
  report.put("complete",true).put("scope","local model translations only; literal occurrence is not alignment; no download");save()
 }
}
