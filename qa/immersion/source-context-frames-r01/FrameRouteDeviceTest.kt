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
class FrameRouteDeviceTest {
    @Test fun japaneseFrameRoute()=demonstrate("ja")
    @Test fun swahiliFrameRoute()=demonstrate("sw")
    private fun demonstrate(target:String) {
        val args=InstrumentationRegistry.getArguments()
        org.junit.Assume.assumeTrue(args.getString("vipiFrameRouteUI")=="true")
        check(args.getString("vipiDedicatedEmulator")=="true")
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val device=UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
        val out=File(context.filesDir,"frame-route-ui-$target");check(!out.exists());out.mkdirs()
        val original="We need a phone charger and your phone number."
        val mixed=if(target=="ja") "watashitachi need a keitai denwa no jūdenki and your denwa bangō." else "sisi need a chaja ya simu na your Nambari ya simu."
        val scenario=ActivityScenario.launch<FrameRouteQualificationActivity>(Intent(context,FrameRouteQualificationActivity::class.java).putExtra("target",target))
        val observations=JSONArray()
        try {
            checkNotNull(device.wait(Until.findObject(By.desc(mixed)),20_000));assertTrue(File(out,"proof.json").exists())
            val proof=JSONObject(File(out,"proof.json").readText());assertEquals(original,proof.getString("original"));assertEquals(.75,proof.getDouble("density"),0.0);assertEquals(if(target=="ja")3 else 4,proof.getJSONArray("spans").length());assertEquals("reference_miss_frame_evidence",proof.getString("routing_branch"));assertFalse(proof.getBoolean("supplied_target_or_span"))
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
                assertNotNull(device.wait(Until.findObject(By.desc("私たち need a 携帯電話の充電器 and your 電話番号.")),12_000));device.takeScreenshot(File(out,"native-script.png"))
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
