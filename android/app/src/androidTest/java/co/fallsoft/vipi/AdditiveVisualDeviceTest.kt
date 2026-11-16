package co.fallsoft.vipi

import android.content.Intent
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Surface
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import co.fallsoft.vipi.core.*
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.KeyStore
import java.util.UUID
import java.util.concurrent.atomic.AtomicInteger

class AdditiveVisualDeviceTest {
 @Test fun visibleDwellThenLaterMessageAndSettings() = runBlocking {
  val inst=InstrumentationRegistry.getInstrumentation();check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator")=="true");val context=inst.targetContext;val dir=File(context.filesDir,"additive-visual-r04");check(!dir.exists());dir.mkdirs();val device=UiDevice.getInstance(inst);val account=UUID.randomUUID();val vault=MessageVault(context,account);val store=VocabularyFamiliarityStore(vault)
  val scenario=ActivityScenario.launch<MainActivity>(Intent(context,MainActivity::class.java).putExtra("vipi_screen","welcome"));val observed=AtomicInteger()
  fun unit(text:String,source:String,target:String,reading:String,id:String):SourceReferenceUnit {val start=text.indexOf(source);return SourceReferenceUnit(start,start+source.length,source,target,reading,"frame:${"a".repeat(64)}:$id","a".repeat(64),1,id,ApprovedLearningIdentity(id,"synthetic $id",reading))}
  fun show(content:@androidx.compose.runtime.Composable ()->Unit) {scenario.onActivity{it.setContent{VipiTheme(Appearance.LIGHT){Surface { content() }}}};inst.waitForIdleSync();Thread.sleep(1200);inst.waitForIdleSync()}
  fun capture(name:String){device.waitForIdle();assertTrue(device.takeScreenshot(File(dir,name)))}
  try {
   show { Column(Modifier.fillMaxSize().safeDrawingPadding().padding(24.dp)) { LanguageSettingsLink("Japanese") {}; NewWordsControl(.25) {} } };capture("settings-normal.png")
   show { CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density,2f)) { Column(Modifier.fillMaxSize().safeDrawingPadding().padding(24.dp)) { LanguageSettingsLink("Japanese") {}; NewWordsControl(.25) {} } } };capture("settings-large.png")
   val firstText="The book arrives today.";val book=unit(firstText,"book","本","hon","book");val first=requireNotNull(SourceReferencePresentation.create(firstText,"ja",listOf(book),.75,4));assertEquals(listOf("book"),first.spans.map{it.original})
   show { Column(Modifier.fillMaxSize().padding(24.dp)) { ImmersionBubble(first,ReadingMode.IMMERSED,source="en",target="ja",messageID="first",targetDwellMs=4500,meaningDwellMs=700,onExposure={ spans -> if(spans.isNotEmpty()){store.observeSourceUnits(first.references,"en","ja",100);observed.incrementAndGet()} }) } };capture("first-bubble.png")
   withTimeout(10000){while(observed.get()==0)delay(100)};assertTrue(store.sourceSeen(book,"en","ja",100).observed)
   val nextText="The book and water are here.";val book2=unit(nextText,"book","本","hon","book");val water=unit(nextText,"water","水","mizu","water");val units=listOf(book2,water);val flags=store.sourceSeenBatch(units,"en","ja",100);val chosen=AdditiveExposureSelection.select(units,6,.25){flags.getValue(it)};val next=requireNotNull(SourceReferencePresentation.create(nextText,"ja",chosen,.75,6));assertEquals(listOf("book","water"),next.spans.map{it.original});assertEquals(listOf("hon","mizu"),next.spans.map{it.romanization})
   show { Column(Modifier.fillMaxSize().padding(24.dp)) { ImmersionBubble(next,ReadingMode.IMMERSED,source="en",target="ja",messageID="second",targetDwellMs=4500,meaningDwellMs=3500) } };capture("later-bubble.png");delay(4800);assertEquals(listOf("book","water"),next.spans.map{it.original});capture("later-bubble-after-flips.png")
   val speech=next.speech("en","ja",emptySet());assertEquals(listOf("本","水"),speech.filter{it.language=="ja"}.map{it.text});val pair=withContext(Dispatchers.Main){LocalSpeechPair(context,"en","ja")}
   try {pair.prepare(mapOf("en" to "The book","ja" to "本"));val audio=pair.render(speech);assertTrue(audio.milliseconds>0)} finally {withContext(Dispatchers.Main){pair.close()}}
   File(dir,"receipt.json").writeText("""{"visible_dwell":true,"later_seen_plus_new":true,"stable_membership":true,"reading":["hon","mizu"],"displayed_target_speech_rendered":true,"synthetic_only":true}""")
  } finally {scenario.close();vault.close();vault.file.parentFile!!.deleteRecursively();KeyStore.getInstance("AndroidKeyStore").apply{load(null)}.deleteEntry("co.fallsoft.vipi.messages.$account")}
 }
}
