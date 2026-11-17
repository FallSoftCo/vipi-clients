package co.fallsoft.vipi

import android.graphics.Rect
import android.text.Spanned
import android.text.style.ReplacementSpan
import android.view.View
import android.view.ViewGroup
import android.view.inspector.WindowInspector
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import co.fallsoft.vipi.core.*
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.util.concurrent.atomic.AtomicInteger

/** Production owner/catalog/renderer, with no translation or download provider. */
class ArabicOrthographyUIDeviceTest {
    @get:Rule val compose = createComposeRule()
    @Test fun exactArabicTokensRemainJoinedOnBothNativeFaces() {
        val ins = InstrumentationRegistry.getInstrumentation()
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("vipiDedicatedEmulator") == "true")
        val context = ins.targetContext; check(context.packageName == "co.fallsoft.vipi.uxqa")
        val run = args.getString("vipiArabicRun") ?: "001"; check(run.matches(Regex("[0-9]{3}")))
        val out = File(context.filesDir,"arabic-orthography-$run"); check(!out.exists()); check(out.mkdirs())
        val source = listOf("أنا أشرب الماء الآن.","أنا أحب الموسيقى.","أين شاحن الهاتف؟")
        val attempts = AtomicInteger()
        val provider = object : LanguageTranslation {
            override suspend fun prepare(source:String,target:String,cellularAllowed:Boolean) = error("No model downloads")
            override suspend fun translate(text:String,source:String,target:String):String { attempts.incrementAndGet(); error("Only bundled local references allowed") }
            override fun close() { }
        }
        val scope = CoroutineScope(SupervisorJob()+Dispatchers.Main.immediate)
        lateinit var owner:ConversationImmersion; lateinit var speech:SpeechPlayback
        val results = mutableListOf<ImmersionPresentation>()
        val report = JSONObject().put("complete",false).put("provider","actual bundled catalogs and production owner; translator/downloads forbidden")
        fun descendants(view:View):List<StableImmersionText> = when(view) {
            is StableImmersionText -> listOf(view)
            is ViewGroup -> (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) }
            else -> emptyList()
        }
        fun natives() = WindowInspector.getGlobalWindowViews().flatMap(::descendants)
        fun save() = File(out,"report.json").writeText(report.put("translationAttempts",attempts.get()).toString(2))
        fun committedNativeFrame() {
            val commits=AtomicInteger()
            var expected=0
            compose.runOnIdle {
                val views=natives(); expected=views.size
                views.forEach { view ->
                    check(view.isHardwareAccelerated)
                    view.viewTreeObserver.registerFrameCommitCallback { commits.incrementAndGet() }
                    view.invalidate()
                }
            }
            compose.waitUntil(5_000) { commits.get()>=expected && expected==3 }
        }
        fun snapshot():JSONArray {
            lateinit var rows:JSONArray
            compose.runOnIdle {
                rows=JSONArray(natives().map { view ->
                    val text=view.text as Spanned
                    val slots=text.getSpans(0,text.length,ReplacementSpan::class.java).map { span ->
                        val a=text.getSpanStart(span);val b=text.getSpanEnd(span)
                        assertTrue("No attachment may split Arabic orthography",SourceOrthography.permitsReplacement(view.displayedOriginal,a,b))
                        JSONObject().put("start",a).put("end",b).put("source",view.displayedOriginal.substring(a,b))
                    }
                    val rect=Rect();view.getGlobalVisibleRect(rect)
                    JSONObject().put("original",view.displayedOriginal).put("visible",view.visibleText())
                        .put("slots",JSONArray(slots)).put("bounds",rect.toShortString()).put("bodySp",view.textSize/view.resources.displayMetrics.scaledDensity)
                })
            }
            return rows
        }
        compose.runOnIdle {
            owner=ConversationImmersion(context,"ar","en",.5,translator=provider,qaModelsReady=false)
            source.forEachIndexed { i,text -> owner.selectInputLanguage("arabic-row-$i","ar") }
            speech=SpeechPlayback(context,"ar","en",scope)
            speech.prepare(mapOf("ar" to source.first(),"en" to "I am drinking water now."))
        }
        try {
            for ((i,text) in source.withIndex()) {
                val value=runBlocking(Dispatchers.Default) { requireNotNull(owner.presentation(text,inputLanguage="ar",messageID="arabic-row-$i")) }
                assertEquals(text,value.original)
                assertTrue(value.spans.all { SourceOrthography.permitsReplacement(text,it.start,it.end) })
                if(i==0) assertTrue(value.spans.none { it.start==11&&it.end==14 })
                if(i==1) assertTrue(value.spans.none { it.start==10&&it.end==16 })
                results += value
            }
            assertEquals(0,attempts.get())
            assertTrue("Actual bundled charger slot remains eligible",results[2].spans.any { it.original=="شاحن" })
            val bare=LocalImmersion.align("شاحن","charger",listOf(VocabularyEntry("شاحن",listOf("charger"))),1.0,"ar","en")
            assertEquals(listOf("شاحن"),bare.spans.map { it.original })
            report.put("bareWholeTokenProbe",JSONObject().put("source","شاحن").put("mapping","explicit supplied charger mapping; eligibility only").put("start",0).put("end",4))
            report.put("results",JSONArray(results.map { value -> JSONObject().put("original",value.original)
                .put("translation",value.translation).put("spans",JSONArray(value.spans.map { span -> JSONObject().put("start",span.start).put("end",span.end).put("source",span.original).put("target",span.translated) })) }))
            compose.waitUntil(30_000) { speech.state!=SpeechState.PREPARING }
            report.put("voicePreparationState",speech.state.name).put("voicePreparationError",speech.error)
            compose.setContent { VipiTheme(Appearance.LIGHT) { CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl) {
                Surface(Modifier.fillMaxSize()) {
                    Column(Modifier.fillMaxSize().safeDrawingPadding().padding(18.dp),verticalArrangement=Arrangement.spacedBy(14.dp)) {
                        Text("Alex",style=MaterialTheme.typography.titleLarge)
                        results.forEachIndexed { i,value ->
                            Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant,RoundedCornerShape(18.dp))) {
                                ImmersionBubble(value,ReadingMode.IMMERSED,speech,"ar","en","arabic-row-$i",embedded=true,
                                    originalMessage=value.original,rawSourceLanguage="ar",onVoiceHelp={},
                                    metadata={Text("٣:١٥ م · في انتظار الإرسال",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)})
                            }
                        }
                    }
                }
            } } }
            compose.waitUntil(5_000) { var count=0;compose.runOnIdle { count=natives().size };count==3 }
            compose.waitUntil(5_000) { var target=false;compose.runOnIdle { target=natives().single { it.displayedOriginal==source[2] }.visibleText()!=source[2] };target }
            committedNativeFrame()
            report.put("learningFace",snapshot());save()
            val device=UiDevice.getInstance(ins);assertTrue(device.takeScreenshot(File(out,"learning-face.png")))
            compose.waitUntil(12_000) { var allOriginal=false;compose.runOnIdle { allOriginal=natives().all { it.visibleText()==it.displayedOriginal } };allOriginal }
            committedNativeFrame()
            report.put("sourceFaceWithNativeSlots",snapshot());save()
            assertTrue(device.takeScreenshot(File(out,"source-face.png")))
            compose.runOnIdle { assertEquals(0,attempts.get()) }
            report.put("complete",true).put("passed",true);save()
        } catch(error:Throwable) {
            report.put("passed",false).put("error",error.toString());save()
            UiDevice.getInstance(ins).takeScreenshot(File(out,"failure.png"));throw error
        } finally { compose.runOnIdle { owner.close();speech.close() };scope.cancel();save() }
    }
}
