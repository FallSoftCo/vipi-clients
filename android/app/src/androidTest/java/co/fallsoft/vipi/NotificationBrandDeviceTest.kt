package co.fallsoft.vipi

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.graphics.Bitmap
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File

/** Posts only an owned local QA notification, never a push or friend message.
 * Host controller owns the exact runtime-permission baseline/restoration. */
class NotificationBrandDeviceTest {
    @get:Rule val compose=createComposeRule()
    @Test fun actualStatusBarAndShadeRenderApprovedTinyMarkInBothSystemAppearances(){
        val i=InstrumentationRegistry.getInstrumentation();val c=i.targetContext
        check(BuildConfig.DEBUG&&BuildConfig.APPLICATION_ID=="co.fallsoft.vipi.sourcecontextqa")
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator")=="true")
        val run=requireNotNull(InstrumentationRegistry.getArguments().getString("vipiJourneyRun"));require(run.matches(Regex("[0-9]{3}")))
        val out=File(c.filesDir,"journey-ui-$run/notification-brand");check(!out.exists());check(out.mkdirs())
        val device=UiDevice.getInstance(i);val nm=c.getSystemService(Context.NOTIFICATION_SERVICE)as NotificationManager
        check(nm.areNotificationsEnabled()){ "Host must explicitly admit/restore owned QA notification permission" }
        val channel="vipi-brand-review-$run";val id=591000+run.toInt();assertNull(nm.getNotificationChannel(channel))
        val prior=device.executeShellCommand("cmd uimode night").trim();val priorMode=prior.substringAfter(":").trim();check(priorMode in setOf("yes","no","auto","custom"))
        fun capture(name:String){
            val image=requireNotNull(i.uiAutomation.takeScreenshot());File(out,"$name.png").outputStream().use{image.compress(Bitmap.CompressFormat.PNG,100,it)};image.recycle()
            device.dumpWindowHierarchy(File(out,"$name.xml"))
        }
        compose.setContent{VipiTheme(Appearance.SYSTEM){Box(Modifier.fillMaxSize().background(vipiPalette().canvas))}}
        try{
            nm.createNotificationChannel(NotificationChannel(channel,"Vipi icon review",NotificationManager.IMPORTANCE_DEFAULT).apply{setSound(null,null);enableVibration(false)})
            for((mode,label)in listOf("no" to "light","yes" to "dark")){
                device.executeShellCommand("cmd uimode night $mode");compose.mainClock.advanceTimeBy(400);compose.waitForIdle()
                nm.notify(id,Notification.Builder(c,channel).setSmallIcon(R.drawable.vipi_notification).setContentTitle("Vipi").setContentText("Notification icon review").setOnlyAlertOnce(true).setShowWhen(false).build())
                val deadline=android.os.SystemClock.uptimeMillis()+5_000
                while(nm.activeNotifications.none{it.id==id&&it.notification.smallIcon.resId==R.drawable.vipi_notification}&&android.os.SystemClock.uptimeMillis()<deadline)android.os.SystemClock.sleep(50)
                check(nm.activeNotifications.any{it.id==id&&it.notification.smallIcon.resId==R.drawable.vipi_notification})
                device.waitForIdle();android.os.SystemClock.sleep(1000);capture("01-$label-statusbar")
                check(device.openNotification());check(device.wait(Until.hasObject(By.text("Notification icon review")),5_000));device.waitForIdle();android.os.SystemClock.sleep(1000);capture("02-$label-shade")
                device.pressBack();device.waitForIdle()
            }
        }finally{
            nm.cancel(id);nm.deleteNotificationChannel(channel);device.executeShellCommand("cmd uimode night $priorMode");device.waitForIdle()
            val after=device.executeShellCommand("cmd uimode night").trim();assertEquals(prior,after);assertFalse(nm.activeNotifications.any{it.id==id});assertNull(nm.getNotificationChannel(channel))
            File(out,"restoration.json").writeText(JSONObject().put("system_night_before",prior).put("system_night_after",after).put("owned_notification_cancelled",true).put("owned_channel_deleted",true).put("actual_push_sent",false).put("resource","vipi_notification").toString(2))
        }
    }
}
