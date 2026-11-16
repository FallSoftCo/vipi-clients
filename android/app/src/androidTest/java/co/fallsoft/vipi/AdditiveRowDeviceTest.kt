package co.fallsoft.vipi

import android.content.Intent
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
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

class AdditiveRowDeviceTest {
 @Test fun actualVisibleRowRemainsFrozenAcrossExposureAndReadiness() = runBlocking {
  val inst=InstrumentationRegistry.getInstrumentation();check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator")=="true");val context=inst.targetContext;val dir=File(context.filesDir,"additive-row-r02");check(!dir.exists());dir.mkdirs();val account=UUID.randomUUID();val vault=MessageVault(context,account);val store=VocabularyFamiliarityStore(vault);val calls=AtomicInteger()
  val text="The train and bank are near the house.";val pairs=listOf("train" to "tren","bank" to "banco","house" to "casa");val units=pairs.mapIndexed{i,(src,tgt)->val a=text.indexOf(src);SourceReferenceUnit(a,a+src.length,src,tgt,null,"frame:${"a".repeat(64)}:row-$i","a".repeat(64),1,"row-$i",ApprovedLearningIdentity("row-$i","synthetic $i",""))}
  val provider=object:SourceLookupProvider {override val cacheIdentity="row-test-v1";override suspend fun lookup(original:String,source:String,target:String,density:Double):SourceLookupEvidence {calls.incrementAndGet();val n=if(original==text)8 else 9;val partial=SourceReferencePresentation.create(original,target,units,density,n);return SourceLookupEvidence(original,source,target,cacheIdentity,partial,emptyList(),units,n)}}
  val owner=ConversationImmersion(context,"en","es",.25,sourceLookup=provider,familiarity=store,qaModelsReady=true);owner.selectInputLanguage("row","en");val scope=CoroutineScope(SupervisorJob()+Dispatchers.Main.immediate);val speech=withContext(Dispatchers.Main){SpeechPlayback(context,"en","es",scope)};val refresh=mutableIntStateOf(0);val scenario=ActivityScenario.launch<MainActivity>(Intent(context,MainActivity::class.java).putExtra("vipi_screen","welcome"));val device=UiDevice.getInstance(inst)
  try {
   scenario.onActivity{it.setContent {VipiTheme(Appearance.LIGHT){Surface{Column(Modifier.fillMaxSize().safeDrawingPadding().padding(24.dp)){Text("Synthetic chat ${refresh.intValue}");ConversationImmersionText(text,"row",owner,speech,false,onVoiceHelp={},metadata={})}}}}}
   withTimeout(15000){while(calls.get()==0)delay(100)};delay(900);assertTrue(device.takeScreenshot(File(dir,"row-before.png")));val beforeCalls=calls.get()
   withTimeout(15000){while(!store.sourceSeen(units[0],"en","es",(System.currentTimeMillis()/86400000L).toInt()).observed && !store.sourceSeen(units[1],"en","es",(System.currentTimeMillis()/86400000L).toInt()).observed)delay(100)}
   assertNull("readiness begins unresolved",owner.ready)
   withContext(Dispatchers.Main){owner.checkDownloads();refresh.intValue++};assertEquals(true,owner.ready);delay(1200);assertEquals("readiness/recomposition must not re-request visible row",beforeCalls,calls.get());assertTrue(device.takeScreenshot(File(dir,"row-after-exposure-readiness.png")))
   val next=requireNotNull(owner.presentation(text+" Tomorrow.","en"));assertTrue("future request should include previously seen and new",next.spans.size>=3)
   File(dir,"receipt.json").writeText("""{"actual_row_path":true,"visible_dwell_observed":true,"readiness_recomposition_no_rerequest":true,"future_request_adds_seen":true,"synthetic_only":true}""")
  } finally {scenario.close();withContext(Dispatchers.Main){speech.close();scope.cancel()};owner.close();vault.close();vault.file.parentFile!!.deleteRecursively();KeyStore.getInstance("AndroidKeyStore").apply{load(null)}.deleteEntry("co.fallsoft.vipi.messages.$account")}
 }
}
