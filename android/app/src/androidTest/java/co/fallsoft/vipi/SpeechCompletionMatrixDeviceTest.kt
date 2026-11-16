package co.fallsoft.vipi

import android.net.ConnectivityManager
import android.content.Intent
import androidx.test.core.app.ActivityScenario
import android.os.SystemClock
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.SpeechSpan
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File

/** Synthetic local controller completion; not pronunciation or acoustic acceptance. */
class SpeechCompletionMatrixDeviceTest {
 @Test fun allDirectedPairsReachPlaybackCompletionOffline() = runBlocking {
  val inst=InstrumentationRegistry.getInstrumentation();check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator")=="true")
  check(android.os.Build.FINGERPRINT.contains("generic") || android.os.Build.MODEL.contains("sdk_gphone"))
  val context=inst.targetContext;val scenario=ActivityScenario.launch<MainActivity>(Intent(context,MainActivity::class.java).putExtra("vipi_screen","welcome"));val fixture=JSONObject(File(context.filesDir,"immersion-qa/speech.json").readText())
  val languages=fixture.getJSONArray("languages").let{a->(0 until a.length()).map(a::getString)};assertEquals(initialLanguages.map{it.code}.toSet(),languages.toSet())
  val directory=File(context.filesDir,"speech-completion-110-20261116-r02");check(!directory.exists());check(directory.mkdirs())
  val rows=JSONArray();val report=JSONObject().put("scope","offline synthetic actual SpeechPlayback; not acoustic or meaning acceptance").put("directions",rows)
  fun shell(cmd:String)=inst.uiAutomation.executeShellCommand(cmd).use{java.io.FileInputStream(it.fileDescriptor).bufferedReader().use{f->f.readText()}}
  fun save(){File(directory,"report.json").writeText(report.toString(2))}
  val wifi=shell("settings get global wifi_on").trim()=="1";val mobile=shell("settings get global mobile_data").trim()=="1"
  try {
   shell("svc wifi disable");shell("svc data disable");withTimeout(15000){while(context.getSystemService(ConnectivityManager::class.java).activeNetwork!=null)delay(100)};report.put("activeNetwork","none")
   for(source in languages)for(target in languages.filter{it!=source}) {
    val row=JSONObject().put("source",source).put("target",target);val scope=CoroutineScope(SupervisorJob()+Dispatchers.Main.immediate)
    val controller=withContext(Dispatchers.Main){SpeechPlayback(context,source,target,scope)}
    suspend fun await(expected:SpeechState)=withTimeout(30000){while(withContext(Dispatchers.Main){controller.state}!=expected){check(withContext(Dispatchers.Main){controller.error}==null){controller.error.orEmpty()};delay(10)}}
    try {
     val start=SystemClock.elapsedRealtime();withContext(Dispatchers.Main){controller.prepare(mapOf(source to fixture.getJSONObject("warmup").getString(source),target to fixture.getJSONObject("warmup").getString(target)))};await(SpeechState.READY);row.put("prepare_ms",SystemClock.elapsedRealtime()-start)
     val spans=listOf(SpeechSpan(fixture.getJSONObject("coffee").getString(source),source),SpeechSpan(fixture.getJSONObject("tomorrow").getString(target),target))
     val play=SystemClock.elapsedRealtime();withContext(Dispatchers.Main){controller.toggle("matrix-$source-$target",spans)};await(SpeechState.PLAYING);row.put("playing_ms",SystemClock.elapsedRealtime()-play);await(SpeechState.READY)
     check(withContext(Dispatchers.Main){controller.error}==null);check(withContext(Dispatchers.Main){controller.activeMessage}==null)
     val feed=controller.outputUnderruns;row.put("feeding_underruns",feed).put("terminal_underruns",controller.endOfStreamUnderruns).put("completion_ms",SystemClock.elapsedRealtime()-play).put("status",if(feed==0)"completed" else "feeding_underrun")
    } catch(e:TimeoutCancellationException){row.put("status","failed").put("error","TimeoutCancellationException")} catch(e:CancellationException){throw e} catch(e:Exception){row.put("status","failed").put("error",e.javaClass.simpleName).put("message",e.message.orEmpty())}
    finally {withContext(Dispatchers.Main){controller.close()};scope.cancel();rows.put(row);save()}
   }
  } finally {if(wifi)shell("svc wifi enable");if(mobile)shell("svc data enable");scenario.close()}
  assertEquals(110,rows.length());assertEquals(110,(0 until rows.length()).count{rows.getJSONObject(it).getString("status")=="completed"})
 }
}
