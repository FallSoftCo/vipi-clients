package co.fallsoft.vipi

import android.graphics.Rect
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.view.inspector.WindowInspector
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.unit.dp
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.By
import co.fallsoft.vipi.core.ImmersionPresentation
import co.fallsoft.vipi.core.ImmersionSpan
import co.fallsoft.vipi.core.SpeechSpan
import com.google.mlkit.common.model.RemoteModelManager
import com.google.mlkit.nl.translate.TranslateRemoteModel
import kotlinx.coroutines.*
import kotlinx.coroutines.tasks.await
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.util.concurrent.CopyOnWriteArrayList

/** One real-provider native gesture case. Requires an already installed model;
 * no production profile/message writes and no acoustic-quality assertion. */
class ManualLookupActualGestureDeviceTest {
    @get:Rule val compose=createComposeRule()

    @Test fun uncoveredBookTapTranslatesContextSpeaksOnceStopsAndReusesCache() {
        val ins=InstrumentationRegistry.getInstrumentation();val args=InstrumentationRegistry.getArguments()
        check(args.getString("vipiDedicatedEmulator")=="true")
        val context=ins.targetContext;check(context.packageName=="co.fallsoft.vipi.uxqa")
        check(runBlocking {RemoteModelManager.getInstance().isModelDownloaded(TranslateRemoteModel.Builder("es").build()).await()}) {"Spanish model must already be installed; no download allowed"}
        val run=args.getString("vipiActualGestureRun")?:"001";check(run.matches(Regex("[0-9]{3}")))
        val output=File(context.filesDir,"manual-actual-gesture-$run");check(!output.exists());check(output.mkdirs())
        val originalText="Could you book a table for two tomorrow evening?"
        val id="actual-native-book"
        val fixture=object:ImmersionPresentation {
            override val original=originalText
            override val translation:String?=null
            override val spans=emptyList<ImmersionSpan>()
        }
        val calls=CopyOnWriteArrayList<JSONObject>();val accepted=CopyOnWriteArrayList<Pair<String,List<SpeechSpan>>>()
        val nativeTranslation=LocalTranslation()
        val provider=object:LanguageTranslation {
            override suspend fun prepare(source:String,target:String,cellularAllowed:Boolean)=error("No model download allowed")
            override suspend fun translate(text:String,source:String,target:String):String {
                check(text==originalText&&source=="en"&&target=="es")
                val start=SystemClock.elapsedRealtimeNanos()
                return nativeTranslation.translate(text,source,target).also {calls+=JSONObject().put("source",text).put("from",source).put("to",target).put("target",it).put("elapsedMs",(SystemClock.elapsedRealtimeNanos()-start)/1e6)}
            }
            override fun close()=nativeTranslation.close()
        }
        val scope=CoroutineScope(SupervisorJob()+Dispatchers.Main.immediate)
        lateinit var owner:ConversationImmersion;lateinit var speech:SpeechPlayback;lateinit var manual:ManualLookupInteraction
        val report=JSONObject().put("complete",false).put("provider","actual installed ML Kit Spanish model; no download")
            .put("scope","one actual native gesture/provider/SpeechPlayback path; no acoustic acceptance")
        fun save(){report.put("providerCalls",JSONArray(calls)).put("acceptedSpeechCount",accepted.size).put("speechInputs",JSONArray(accepted.map { (message, spans) -> JSONObject().put("message",message).put("spans",JSONArray(spans.map { JSONObject().put("text",it.text).put("language",it.language) })) }));File(output,"report.json").writeText(report.toString(2))}
        compose.runOnIdle {
            owner=ConversationImmersion(context,"en","es",0.0,translator=provider,sourceLookup=null)
            owner.selectInputLanguage(id,"en")
            speech=SpeechPlayback(context,"en","es",scope)
            speech.qualificationInput={message,spans->accepted+=message to spans.toList()}
            speech.prepare(mapOf("en" to "Hello.","es" to "Hola."))
            manual=ManualLookupInteraction(owner,speech,id,originalText,scope)
        }
        val device=UiDevice.getInstance(ins)
        fun paragraphs(view:View):List<StableImmersionText> = when(view){
            is StableImmersionText->listOf(view)
            is ViewGroup->(0 until view.childCount).flatMap{paragraphs(view.getChildAt(it))}
            else->emptyList()
        }
        fun native()=WindowInspector.getGlobalWindowViews().flatMap(::paragraphs).single()
        try {
            compose.waitUntil(30_000){speech.state!=SpeechState.PREPARING}
            compose.runOnIdle {assertEquals(speech.error.orEmpty(),SpeechState.READY,speech.state)}
            compose.setContent {VipiTheme(Appearance.LIGHT){
                Column(Modifier.fillMaxSize().safeDrawingPadding().padding(18.dp)){
                    ImmersionBubble(fixture,ReadingMode.IMMERSED,speech,"en","es",id,embedded=true,
                        originalMessage=originalText,rawSourceLanguage="en",metadata={Text("3:15 PM")},manual=manual)
                }
                ManualLookupPopup(manual)
            }}
            lateinit var word:Rect
            val start=originalText.indexOf("book");val end=start+4
            compose.runOnIdle {
                assertTrue(fixture.spans.none{start<it.end&&end>it.start})
                assertEquals(originalText,native().displayedOriginal)
                word=native().sourceRangeRect(start,end)
            }
            var expectedTarget=""
            val began=SystemClock.elapsedRealtime()
            assertTrue(device.click(word.centerX(),word.centerY()))
            compose.waitUntil(20_000){manual.outcome?.status==ManualTranslationStatus.READY&&accepted.size==1}
            compose.waitUntil(15_000){speech.state==SpeechState.PLAYING||speech.error!=null}
            compose.runOnIdle {
                assertEquals(SpeechState.PLAYING,speech.state);assertNull(speech.error)
                assertEquals(1,calls.size);assertEquals(1,accepted.size)
                assertEquals(start,manual.request?.startUTF16);assertEquals(end,manual.request?.endUTF16)
                val result=requireNotNull(manual.outcome?.result)
                assertEquals("book",result.originalSlice);assertEquals(originalText,result.sourceContextText)
                assertEquals(0,result.sourceContextStartUTF16);assertEquals(originalText.length,result.sourceContextEndUTF16)
                assertTrue(result.targetText.contains("reservar",ignoreCase=true))
                expectedTarget=result.targetText
                assertEquals(listOf(SpeechSpan(result.targetText,"es")),accepted.single().second)
                report.put("sourceContext",result.sourceContextText).put("target",result.targetText)
                    .put("actualSpeechInput",accepted.single().second.single().text).put("actualSpeechLanguage","es")
                    .put("tapToPlayingMs",SystemClock.elapsedRealtime()-began)
            }
            compose.onNodeWithText(expectedTarget).assertIsDisplayed()
            report.put("actualTargetVisible",true)
            device.takeScreenshot(File(output,"real-context-translation.png"));save()
            assertTrue(device.click(word.centerX(),word.centerY()))
            compose.waitUntil(3_000){manual.request==null&&!manual.visible&&speech.activeMessage==null}
            SystemClock.sleep(250)
            compose.runOnIdle {assertEquals(1,accepted.size);assertEquals(1,calls.size);assertNull(speech.activeMessage)}
            report.put("sameTapStop",true);save()

            // Start the same cached word again, then touch a different word
            // while its actual popup/audio are active: exactly one new play.
            assertTrue(device.click(word.centerX(),word.centerY()))
            compose.waitUntil(10_000){manual.outcome?.status==ManualTranslationStatus.READY&&accepted.size==2}
            compose.waitUntil(10_000){speech.state==SpeechState.PLAYING}
            lateinit var other:Rect
            val otherStart=originalText.indexOf("table");val otherEnd=otherStart+5
            compose.runOnIdle {other=native().sourceRangeRect(otherStart,otherEnd)}
            assertTrue(device.click(other.centerX(),other.centerY()))
            compose.waitUntil(10_000){manual.outcome?.status==ManualTranslationStatus.READY&&accepted.size==3}
            compose.waitUntil(10_000){speech.state==SpeechState.PLAYING}
            SystemClock.sleep(100)
            compose.runOnIdle {
                assertEquals(3,accepted.size);assertEquals(1,calls.size)
                assertEquals(otherStart,manual.request?.startUTF16);assertEquals(otherEnd,manual.request?.endUTF16)
                assertEquals(accepted[0].second,accepted[2].second)
            }
            report.put("differentWordStartsOnce",true);save()

            // The actual popup and footer each expose Stop. The footer is
            // above this below-anchor popup, and receives the outside touch.
            val stopLabel=context.getString(R.string.ui_cae7d57bc067)
            val stops=device.findObjects(By.desc(stopLabel))
            check(stops.size>=2){"Both popup and footer Stop controls must be present"}
            val footer=stops.minBy{it.visibleBounds.top}
            assertTrue(device.click(footer.visibleBounds.centerX(),footer.visibleBounds.centerY()))
            compose.waitUntil(3_000){manual.request==null&&!manual.visible&&speech.activeMessage==null}
            SystemClock.sleep(250)
            compose.runOnIdle {
                assertEquals(3,accepted.size);assertEquals(1,calls.size);assertNull(speech.activeMessage)
                assertTrue(accepted.all{it.first.startsWith("manual-")})
            }
            report.put("footerStopWithoutGenericReplay",true);save()
            var x=0;var y=0
            compose.runOnIdle {val view=native();val location=IntArray(2);view.getLocationOnScreen(location);x=location[0]+view.width-4;y=location[1]+view.height/2}
            assertTrue(device.click(x,y))
            compose.waitUntil(10_000){manual.outcome?.status==ManualTranslationStatus.READY&&accepted.size==4}
            compose.runOnIdle {
                assertEquals(1,calls.size);assertEquals(0,manual.request?.startUTF16);assertEquals(originalText.length,manual.request?.endUTF16)
                assertEquals(originalText,manual.outcome?.result?.sourceContextText)
                assertEquals(accepted[0].second,accepted[3].second)
                report.put("cachedWholeMessage",true).put("actualSpeechOncePerGesture",true)
                manual.cancel()
            }
            report.put("passed",true).put("complete",true);save()
        }catch(error:Throwable){report.put("passed",false).put("error",error.toString());save();device.takeScreenshot(File(output,"failure.png"));throw error}
        finally {compose.runOnIdle{manual.cancel();owner.close();speech.close()};scope.cancel();save()}
    }
}
