package co.fallsoft.vipi
import android.content.Intent
import android.os.SystemClock
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import org.junit.Assert.*
import org.junit.Test
import org.json.JSONObject
import org.json.JSONArray
import java.io.File
class StarterRouteDeviceTest {
    @Test fun japaneseDefaultRoute()=demonstrate("ja")
    @Test fun swahiliDefaultRoute()=demonstrate("sw")
    @Test fun japanesePackedDefaultRoute()=demonstrate("ja",true)
    @Test fun swahiliPackedDefaultRoute()=demonstrate("sw",true)
    @Test fun japaneseExpandedDefaultRoute()=demonstrate("ja",true,true)
    @Test fun swahiliExpandedDefaultRoute()=demonstrate("sw",true,true)
    private fun demonstrate(target:String,packed:Boolean=false,expanded:Boolean=false) {
        val args=InstrumentationRegistry.getArguments()
        org.junit.Assume.assumeTrue(args.getString(if(expanded) "vipiStarterExpandedUI" else if(packed) "vipiStarterPackedUI" else "vipiStarterRouteUI")=="true")
        check(args.getString("vipiDedicatedEmulator")=="true")
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val device=UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
        val out=File(context.filesDir,"starter-route-ui-${if(expanded) "expanded-" else if(packed) "packed-" else ""}$target");check(!out.exists());out.mkdirs()
        val original=if(expanded) "The coffee and bread are for lunch." else if(packed) "My family and my family enjoy pizza." else "Country music is fun!"
        val mixed=if(expanded) { if(target=="ja") "The kōhī and pan are for chuushoku." else "The kahawa na mkate are for chakula cha mchana." } else if(packed) { if(target=="ja") "My kazoku and my kazoku enjoy piza." else "My familia na my familia enjoy piza." } else if(target=="ja") "Country ongaku is fun!" else "Country muziki is fun!"
        val scenario=ActivityScenario.launch<StarterRouteQualificationActivity>(Intent(context,StarterRouteQualificationActivity::class.java).putExtra("target",target).putExtra("packed",packed).putExtra("expanded",expanded))
        val observations=JSONArray()
        try {
            checkNotNull(device.wait(Until.findObject(By.desc(mixed)),20_000));assertTrue(File(out,"proof.json").exists())
            var previous="";var transitions=0;val deadline=SystemClock.elapsedRealtime()+40_000;var first:android.graphics.Rect?=null
            while(SystemClock.elapsedRealtime()<deadline && transitions<6) {
                val node=device.findObject(By.desc(mixed)) ?: device.findObject(By.desc(original))
                if(node!=null) {
                    val label=node.contentDescription
                    if(label!=previous) {
                        if(previous.isNotEmpty())transitions++;previous=label
                        val bounds=node.visibleBounds;if(first==null)first=android.graphics.Rect(bounds) else assertEquals(first,bounds)
                        observations.put(JSONObject().put("label",label).put("elapsed_ms",SystemClock.elapsedRealtime()).put("bounds",bounds.toShortString()))
                    }
                }
                SystemClock.sleep(250)
            }
            assertTrue(transitions>=6);device.takeScreenshot(File(out,"continuous.png"))
            checkNotNull(device.findObject(By.desc("Reading options"))).click()
            if(target=="ja") {
                checkNotNull(device.wait(Until.findObject(By.text("Show original script")),5000)).click()
                assertNotNull(device.wait(Until.findObject(By.desc(if(expanded) "The コーヒー and パン are for 昼食." else if(packed) "My 家族 and my 家族 enjoy ピザ." else "Country 音楽 is fun!")),12_000));device.takeScreenshot(File(out,"native-script.png"))
                checkNotNull(device.findObject(By.desc("Reading options"))).click();checkNotNull(device.wait(Until.findObject(By.text("Show transliteration")),5000)).click()
            } else { assertFalse(device.hasObject(By.text("Show original script")));device.pressBack() }
            assertNotNull(device.wait(Until.findObject(By.desc(mixed)),12_000))
            checkNotNull(device.findObject(By.desc("Reading options"))).click();checkNotNull(device.wait(Until.findObject(By.text("Listen")),20_000)).click()
            val speechDeadline=SystemClock.elapsedRealtime()+10_000
            var speechStates=JSONArray()
            while(SystemClock.elapsedRealtime()<speechDeadline) {
                val f=File(out,"speech-events.json")
                if(f.exists()) speechStates=JSONObject(f.readText()).getJSONArray("states")
                if((0 until speechStates.length()).any{speechStates.getString(it)=="PLAYING"}) break
                SystemClock.sleep(100)
            }
            assertTrue((0 until speechStates.length()).any{speechStates.getString(it)=="PLAYING"})
            observations.put(JSONObject().put("observed_speech_states",speechStates).put("acoustic_correctness_claim",false))
            File(out,"observations.json").writeText(observations.toString())
        } finally {
            File(out,"observations.json").writeText(observations.toString())
            device.takeScreenshot(File(out,"final-state.png"));device.dumpWindowHierarchy(File(out,"final-hierarchy.xml"))
            scenario.close()
        }
    }
}
