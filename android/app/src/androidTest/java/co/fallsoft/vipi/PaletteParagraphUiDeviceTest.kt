package co.fallsoft.vipi

import android.graphics.Rect
import android.text.Spanned
import android.text.style.BackgroundColorSpan
import android.text.style.ForegroundColorSpan
import android.view.View
import android.view.ViewGroup
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.dp
import androidx.core.graphics.ColorUtils
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import co.fallsoft.vipi.core.SpeechSpan
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** Actual production incremental owner/bubbles/native spans, supplied word
 * translation and controlled playback position. No acoustic/provider claim. */
class PaletteParagraphUiDeviceTest {
    @get:Rule val compose = createComposeRule()
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrumentation.targetContext
    @Test fun incomingAndOutgoingPracticeAndPlayingInkKeepNativeContrast(): Unit = runBlocking {
        check(BuildConfig.DEBUG && BuildConfig.APPLICATION_ID == "co.fallsoft.vipi.sourcecontextqa")
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val run = requireNotNull(InstrumentationRegistry.getArguments().getString("vipiJourneyRun")); require(run.matches(Regex("[0-9]{3}")))
        val output = File(context.filesDir,"journey-ui-$run/palette-paragraphs");check(!output.exists());check(output.mkdirs())
        val original = "☕ water 8:00"; val incoming=UUID.randomUUID().toString();val outgoing=UUID.randomUUID().toString()
        val scope=CoroutineScope(SupervisorJob()+Dispatchers.Main.immediate)
        val model=object:LanguageTranslation {
            override suspend fun prepare(source:String,target:String,cellularAllowed:Boolean)=Unit
            override suspend fun isReady(source:String,target:String)=true
            override suspend fun translate(text:String,source:String,target:String):String { check(text=="water");return "agua" }
            override fun close()=Unit
        }
        val owner=ConversationTranslation(context,"en","es",translator=model,language=object:MessageTranslationLanguage {
            override suspend fun identify(text:String)="en"
            override fun close()=Unit
        })
        val speech=object:ConversationSpeech {
            override val state=SpeechState.READY;override val error:String?=null;override val interruption=0L
            override var activeMessage by mutableStateOf<String?>(null)
            override var playingWord by mutableStateOf<PlayingWord?>(null)
            override fun toggle(message:String,spans:List<SpeechSpan>)=error("Translation-aware playback required")
            override fun toggleTranslation(message:String,value:FullMessageTranslation) {
                val range=WordReplacement.ranges(requireNotNull(value.words),reading=false).single()
                activeMessage=message;playingWord=PlayingWord(range,null)
            }
            override fun stop(){activeMessage=null;playingWord=null}
            override fun showMutedVolumeControl()=Unit
            override fun failureMessage()="Unexpected controlled playback failure"
        }
        val audio=withContext(Dispatchers.Main){ConversationAutoplay(owner,speech,scope){error("No voice setup in visual fixture")}}
        val gestures=FullMessageGestures();val appearance=mutableStateOf(Appearance.LIGHT);val mounted=mutableStateOf(true)
        val proof=JSONArray()
        fun views():List<FullMessageTextView> {
            val found=mutableListOf<FullMessageTextView>()
            fun visit(view:View){if(view is FullMessageTextView&&view.originalMessage==original)found+=view;if(view is ViewGroup)for(i in 0 until view.childCount)visit(view.getChildAt(i))}
            ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).forEach{visit(it.window.decorView)}
            check(found.size==2);return found
        }
        fun capture(name:String,palette:VipiPalette,active:Int?) {
            compose.mainClock.advanceTimeBy(250);compose.waitForIdle()
            repeat(2){val latch=CountDownLatch(1);instrumentation.runOnMainSync {
                val root=ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).single().window.decorView
                root.viewTreeObserver.registerFrameCommitCallback{latch.countDown()};root.invalidate()
            };check(latch.await(3,TimeUnit.SECONDS))}
            val bitmap=requireNotNull(instrumentation.uiAutomation.takeScreenshot())
            val rows=JSONArray()
            instrumentation.runOnMainSync {
                views().forEachIndexed{index,view->
                    val p=if(index==1)palette.onOutgoing()else palette
                    val fill=(if(index==1)palette.outgoing else palette.incoming).toArgb()
                    assertEquals("Native original segments use context-specific ink",p.ink.toArgb(),view.currentTextColor)
                    assertEquals("☕ agua 8:00",view.text.toString())
                    val styled=view.text as Spanned
                    val backgrounds=styled.getSpans(0,styled.length,BackgroundColorSpan::class.java).map{it.backgroundColor}
                    val inks=styled.getSpans(0,styled.length,ForegroundColorSpan::class.java).map{it.foregroundColor}
                    assertTrue(backgrounds.contains(p.practiceFill.toArgb()));assertTrue(inks.contains(p.practiceInk.toArgb()))
                    if(active==index){assertNotNull(view.highlightedWord);assertEquals(p.spokenFill.toArgb(),backgrounds.last());assertEquals(p.spokenInk.toArgb(),inks.last())}
                    else assertNull(view.highlightedWord)
                    assertTrue(ColorUtils.calculateContrast(p.ink.toArgb(),fill)>=4.5)
                    assertTrue(ColorUtils.calculateContrast(p.practiceInk.toArgb(),p.practiceFill.toArgb())>=4.5)
                    assertTrue(ColorUtils.calculateContrast(p.spokenInk.toArgb(),p.spokenFill.toArgb())>=4.5)
                    val at=IntArray(2);view.getLocationOnScreen(at);val sampled=bitmap.getPixel(at[0]-4,at[1]+view.height/2)
                    assertEquals("Actual opaque native bubble fill",fill,sampled)
                    rows.put(JSONObject().put("direction",if(index==1)"outgoing"else"incoming").put("text",view.text.toString())
                        .put("body_ink",view.currentTextColor).put("sampled_bubble_fill",sampled).put("practice_fill",p.practiceFill.toArgb())
                        .put("practice_ink",p.practiceInk.toArgb()).put("background_spans",JSONArray(backgrounds)).put("foreground_spans",JSONArray(inks))
                        .put("active_word",view.highlightedWord?.toString()?:JSONObject.NULL).put("bounds",Rect(at[0],at[1],at[0]+view.width,at[1]+view.height).toShortString()))
                }
            }
            File(output,"$name.png").outputStream().use{bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG,100,it)};bitmap.recycle()
            proof.put(JSONObject().put("capture",name).put("rows",rows));File(output,"proof.json").writeText(JSONObject().put("controlled_playback_position",true).put("actual_tts_claim",false).put("captures",proof).toString(2))
        }
        try {
            val first=owner.resolve(incoming,original);val second=owner.resolve(outgoing,original)
            assertEquals(1,first.words!!.size);assertEquals(first.practiceText,second.practiceText)
            compose.setContent {if(mounted.value)VipiTheme(appearance.value){Column(Modifier.fillMaxSize().background(vipiPalette().canvas).padding(24.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
                Text("Maya");ChatBubbleFrame(false){FullMessageBubble(original,incoming,owner,gestures,audio,accessibilityContext="Received"){}}
                Text("Alex");ChatBubbleFrame(true){FullMessageBubble(original,outgoing,owner,gestures,audio,accessibilityContext=context.getString(R.string.delivery_read)){}}
            }}}
            for((mode,label)in listOf(Appearance.LIGHT to "light",Appearance.DARK to "dark")){
                compose.runOnIdle{audio.background();appearance.value=mode};compose.waitForIdle()
                val increased=android.os.Build.VERSION.SDK_INT>=34&&context.getSystemService(android.app.UiModeManager::class.java).contrast>0f
                val palette=if(mode==Appearance.LIGHT){if(increased)VipiPalettes.IncreasedContrastLight else VipiPalettes.Light}else{if(increased)VipiPalettes.IncreasedContrastDark else VipiPalettes.Dark}
                capture("$label-01-practice",palette,null)
                for(index in 0..1){
                    compose.runOnIdle{assertTrue(views()[index].performAccessibilityAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK,null))}
                    compose.waitUntil(5_000){speech.activeMessage==(if(index==0)incoming else outgoing)}
                    capture("$label-0${index+2}-playing",palette,index)
                }
            }
        } finally {withContext(Dispatchers.Main){mounted.value=false;audio.close();owner.close();scope.cancel()}}
    }
}
