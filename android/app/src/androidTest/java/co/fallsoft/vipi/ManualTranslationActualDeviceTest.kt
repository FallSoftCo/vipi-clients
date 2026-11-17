package co.fallsoft.vipi

import android.os.SystemClock
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.SpeechSpan
import com.google.mlkit.common.model.RemoteModelManager
import com.google.mlkit.nl.translate.TranslateRemoteModel
import kotlinx.coroutines.*
import kotlinx.coroutines.tasks.await
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Test
import java.io.File

/** Actual installed ML Kit, native reading producers and SpeechPlayback.
 * Explicit owned-emulator qualification; never invoked by ordinary app flows. */
class ManualTranslationActualDeviceTest {
    @Test fun actualContextTranslationReadingAndLearningScriptSpeech() = runBlocking {
        val ins=InstrumentationRegistry.getInstrumentation();val args=InstrumentationRegistry.getArguments()
        check(args.getString("vipiDedicatedEmulator")=="true")
        val context=ins.targetContext;check(context.packageName=="co.fallsoft.vipi.uxqa")
        val run=args.getString("vipiActualRun")?:"001";check(run.matches(Regex("[0-9]{3}")))
        val out=File(context.filesDir,"manual-actual-$run");check(!out.exists());check(out.mkdirs())
        val rows=JSONArray();val report=JSONObject().put("complete",false).put("provider","actual Google ML Kit local model")
            .put("scope","production manual resolver/readers/SpeechPlayback; no gesture or acoustic acceptance").put("cases",rows)
        fun save()=File(out,"report.json").writeText(report.toString(2))
        data class Sample(val id:String,val text:String,val word:String,val learning:String,val input:String)
        val samples=listOf(
            Sample("book-verb","Could you book a table for two tomorrow evening?","book","es","en"),
            Sample("water-vessels","Please bring two glasses of water to the balcony.","glasses","es","en"),
            Sample("forward-zh","My younger cousin enjoys quiet music after lunch.","music","zh","en"),
            Sample("reverse-zh","我喜欢音乐，也想去银行。","音乐","zh","zh"))
        val prepared=mutableSetOf<String>();val failures=mutableListOf<String>();save()
        for(sample in samples){
            val row=JSONObject().put("id",sample.id).put("raw",sample.text).put("learning",sample.learning).put("explicitInput",sample.input)
            rows.put(row);save()
            val native=LocalTranslation();val calls=JSONArray()
            val translator=object:LanguageTranslation {
                override suspend fun prepare(source:String,target:String,cellularAllowed:Boolean)=native.prepare(source,target,cellularAllowed)
                override suspend fun translate(text:String,source:String,target:String):String {
                    val start=SystemClock.elapsedRealtimeNanos()
                    return native.translate(text,source,target).also {calls.put(JSONObject().put("text",text).put("source",source).put("target",target).put("output",it).put("elapsedMs",(SystemClock.elapsedRealtimeNanos()-start)/1e6))}
                }
                override fun close()=native.close()
            }
            val scope=CoroutineScope(SupervisorJob()+Dispatchers.Main.immediate)
            var owner:ConversationImmersion?=null;var speech:SpeechPlayback?=null
            try {
                val model=TranslateRemoteModel.Builder(sample.learning).build()
                val installed=RemoteModelManager.getInstance().isModelDownloaded(model).await()
                row.put("modelInitiallyInstalled",installed);save()
                if(!installed&&sample.learning !in prepared){
                    check(args.getString("allowModelDownload")=="true"){"Explicit bounded model download not authorized"}
                    val start=SystemClock.elapsedRealtime()
                    withTimeout(90_000){native.prepare("en",sample.learning,true)}
                    row.put("modelPrepareMs",SystemClock.elapsedRealtime()-start);prepared+=sample.learning;save()
                }
                owner=ConversationImmersion(context,"en",sample.learning,0.0,translator=translator,sourceLookup=null)
                val start=sample.text.indexOf(sample.word);check(start>=0)
                val request=owner.makeManualRequest("actual-${sample.id}",sample.text,start,start+sample.word.length,1,inputLanguage=sample.input)
                val before=SystemClock.elapsedRealtimeNanos();val value=owner.manualTranslation(request)
                row.put("status",value.status.name).put("resolverMs",(SystemClock.elapsedRealtimeNanos()-before)/1e6).put("calls",calls);save()
                val result=checkNotNull(value.result){"Manual result ${value.status}"}
                check(value.status==ManualTranslationStatus.READY&&calls.length()==1)
                check(calls.getJSONObject(0).getString("text")==sample.text){"Isolated substring bypassed context"}
                check(result.sourceContextText==sample.text&&result.originalSlice==sample.word)
                row.put("sourceContext",result.sourceContextText).put("sourceContextStartUTF16",result.sourceContextStartUTF16).put("sourceContextEndUTF16",result.sourceContextEndUTF16)
                    .put("target",result.targetText).put("sourceLanguage",result.sourceLanguage).put("targetLanguage",result.targetLanguage)
                    .put("targetReading",result.reading?.text?:JSONObject.NULL).put("sourceReading",result.sourceReading?.text?:JSONObject.NULL)
                if(sample.learning=="zh"){
                    val guide=if(sample.input=="zh")result.sourceReading else result.reading
                    check(guide!=null&&Regex("[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]").containsMatchIn(guide.text)){"Marked Chinese guide missing"}
                    if(sample.input=="zh"){check(result.reading==null);check(guide.text.contains("yīnyuè")&&guide.text.contains("yínháng"))}
                }
                save()
                val spoken=if(result.sourceLanguage==sample.learning)result.sourceContextText else result.targetText
                val received=java.util.concurrent.CopyOnWriteArrayList<List<SpeechSpan>>()
                withContext(Dispatchers.Main){speech=SpeechPlayback(context,"en",sample.learning,scope).also {it.qualificationInput={_,spans->received+=spans.toList()};it.prepare(mapOf("en" to "Hello.",sample.learning to if(sample.learning=="zh")"你好。" else "Hola."))}}
                suspend fun waitFor(label:String,timeout:Long=30_000,condition:()->Boolean){withTimeout(timeout){while(!withContext(Dispatchers.Main){condition()})delay(10)}}
                waitFor("voice preparation"){speech!!.state!=SpeechState.PREPARING}
                row.put("voiceState",speech!!.state.name).put("voiceError",speech!!.error?:JSONObject.NULL);save()
                check(speech!!.state==SpeechState.READY){"Voice unavailable: ${speech!!.error}"}
                val playback=SystemClock.elapsedRealtime()
                withContext(Dispatchers.Main){speech!!.toggle("actual-${sample.id}",listOf(SpeechSpan(spoken,sample.learning)))}
                waitFor("actual playback") {speech!!.state==SpeechState.PLAYING||speech!!.error!=null}
                check(speech!!.state==SpeechState.PLAYING){speech!!.error.orEmpty()}
                row.put("playbackStartMs",SystemClock.elapsedRealtime()-playback)
                check(received.single()==listOf(SpeechSpan(spoken,sample.learning)))
                row.put("actualSpeechInput",spoken).put("actualSpeechLanguage",sample.learning)
                waitFor("actual completion"){speech!!.state==SpeechState.READY}
                row.put("playbackCompleteMs",SystemClock.elapsedRealtime()-playback).put("playbackError",speech!!.error?:JSONObject.NULL)
                check(speech!!.error==null);row.put("passed",true)
            }catch(error:Exception){row.put("error",error.toString());failures+="${sample.id}: $error"}
            finally {withContext(Dispatchers.Main){speech?.close();owner?.close()};scope.cancel();native.close();save()}
        }
        report.put("complete",true).put("passed",failures.isEmpty()).put("errors",JSONArray(failures));save()
        check(failures.isEmpty()){failures.joinToString("\n")}
    }
}
