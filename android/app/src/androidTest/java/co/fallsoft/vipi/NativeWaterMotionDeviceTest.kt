package co.fallsoft.vipi

import android.graphics.Bitmap
import android.os.ParcelFileDescriptor
import android.os.SystemClock
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test

/**
 * Production Choreographer clock and Activity. The fixture controls only the local account and
 * service.
 */
class NativeWaterMotionDeviceTest {
    @Test
    fun captureFriendCrossingOnTheNativeFrameClock() {
        val service =
            JourneyServices(
                profileRequired = false,
                accountDisplayName = "Alex",
                peerDisplayName = "Maya",
                translationFactory = {
                    object : LanguageTranslation {
                        override suspend fun prepare(
                            source: String,
                            target: String,
                            cellularAllowed: Boolean,
                        ) = Unit

                        override suspend fun isReady(source: String, target: String) = true

                        override suspend fun translate(
                            text: String,
                            source: String,
                            target: String,
                        ) = "¿Nos vemos a las seis?"

                        override fun close() = Unit
                    }
                },
            )
        MainActivityJourneyFixture("native-friend-water", service::model).use { f ->
            val run =
                requireNotNull(InstrumentationRegistry.getArguments().getString("vipiJourneyRun"))
            try {
                f.instrumentation.runOnMainSync {
                    f.model.selectTarget("es")
                    f.model.selectImmersionMode(ImmersionMode.FULL_MESSAGES)
                }
                f.launch()
                val deadline = SystemClock.elapsedRealtime() + 12_000
                while (
                    f.model.chat?.ready != true && SystemClock.elapsedRealtime() < deadline
                ) SystemClock.sleep(50)
                runBlocking(Dispatchers.Main) {
                    val chat = requireNotNull(f.model.chat)
                    chat.find("journey_friend")
                    chat.send("Can we meet at six?", service.peer)
                    chat.synchronize()
                    f.model.openConversation(service.peer)
                }
                assertNotNull(f.device.wait(Until.findObject(By.text("Maya")), 8_000))
                val record = "/data/local/tmp/vipi-friend-swim-$run.mp4"
                check(
                    f.device
                        .executeShellCommand("test ! -e $record || echo exists")
                        .trim()
                        .isEmpty()
                )
                val command = "dumpsys gfxinfo ${f.base.packageName}"
                f.device.executeShellCommand("$command reset")
                val start = SystemClock.elapsedRealtimeNanos()
                val stream =
                    f.instrumentation.uiAutomation.executeShellCommand(
                        "screenrecord --size 720x1600 --bit-rate 4500000 --time-limit 11 $record"
                    )
                check(
                    ParcelFileDescriptor.AutoCloseInputStream(stream)
                        .use { it.readBytes() }
                        .isEmpty()
                )
                val end = SystemClock.elapsedRealtimeNanos()
                File(f.output, "recorded.txt")
                    .writeText(f.device.executeShellCommand("$command framestats"))
                f.device.executeShellCommand("$command reset")
                val idleStart = SystemClock.elapsedRealtimeNanos()
                SystemClock.sleep(4000)
                val idleEnd = SystemClock.elapsedRealtimeNanos()
                File(f.output, "unrecorded.txt")
                    .writeText(f.device.executeShellCommand("$command framestats"))
                File(f.output, "intervals-ns.txt").writeText("$start $end $idleStart $idleEnd")
                f.capture("friend")
            } finally {
                f.stopActivity()
                service.close()
            }
        }
    }

    @Test
    fun inboxAndConversationShareMovingAndStaticWater() {
        val service =
            JourneyServices(
                profileRequired = false,
                accountDisplayName = "Alex",
                peerDisplayName = "Maya",
            )
        MainActivityJourneyFixture("native-water", service::model).use { f ->
            val device = f.device
            val run =
                requireNotNull(InstrumentationRegistry.getArguments().getString("vipiJourneyRun"))
            val originalScale =
                device.executeShellCommand("settings get global animator_duration_scale").trim()
            fun shell(cmd: String) = device.executeShellCommand(cmd)
            fun sample(name: String): IntArray {
                val bitmap = requireNotNull(f.instrumentation.uiAutomation.takeScreenshot())
                val pixels =
                    Bitmap.createBitmap(
                        bitmap,
                        bitmap.width / 10,
                        bitmap.height * 37 / 100,
                        bitmap.width * 7 / 10,
                        bitmap.height * 46 / 100,
                    )
                val data = IntArray(pixels.width * pixels.height)
                pixels.getPixels(data, 0, pixels.width, 0, 0, pixels.width, pixels.height)
                File(f.output, "$name.png").outputStream().use { stream ->
                    check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, stream))
                }
                pixels.recycle()
                bitmap.recycle()
                return data
            }
            fun screen(s: Screen) {
                val end = SystemClock.elapsedRealtime() + 12_000
                while (
                    (f.model.screen != s || f.model.chat?.ready != true) &&
                        SystemClock.elapsedRealtime() < end
                ) SystemClock.sleep(50)
                assertEquals(s, f.model.screen)
                assertTrue(f.model.chat?.ready == true)
            }
            try {
                shell("settings put global animator_duration_scale 1")
                f.launch()
                screen(Screen.HOME)
                runBlocking(Dispatchers.Main) {
                    val chat = requireNotNull(f.model.chat)
                    chat.find("journey_friend")
                    chat.send("See you at six?", service.peer)
                    chat.synchronize()
                }
                assertNotNull(device.wait(Until.findObject(By.text("Maya")), 8_000))
                val remote = "/data/local/tmp/vipi-swim-$run.mp4"
                assertEquals("", shell("test ! -e $remote || echo exists").trim())
                shell("dumpsys gfxinfo ${f.base.packageName} reset")
                val appBefore = android.os.SystemClock.elapsedRealtimeNanos()
                val record =
                    f.instrumentation.uiAutomation.executeShellCommand(
                        "screenrecord --size 720x1600 --bit-rate 4500000 --time-limit 12 $remote"
                    )
                val one = sample("01-moving")
                SystemClock.sleep(2500)
                val two = sample("02-moving")
                assertTrue(
                    "Actual Choreographer motion",
                    one.indices.count { one[it] != two[it] } > 1_000,
                )
                val recordOutput =
                    ParcelFileDescriptor.AutoCloseInputStream(record).use { it.readBytes() }
                check(recordOutput.isEmpty()) { recordOutput.toString(Charsets.UTF_8) }
                val appAfter = android.os.SystemClock.elapsedRealtimeNanos()
                File(f.output, "gfxinfo.txt")
                    .writeText(shell("dumpsys gfxinfo ${f.base.packageName} framestats"))
                File(f.output, "measured-interval-ns.txt").writeText("$appBefore $appAfter")
                shell("settings put global animator_duration_scale 0")
                SystemClock.sleep(650)
                val quiet = sample("03-system-motion-off")
                SystemClock.sleep(800)
                assertArrayEquals(
                    "System reduced motion freezes the decorated layer",
                    quiet,
                    sample("04-system-still"),
                )
                shell("settings put global animator_duration_scale 1")
                SystemClock.sleep(800)
                assertFalse(
                    "Allowed system motion resumes",
                    quiet.contentEquals(sample("05-resumed")),
                )
                val settings =
                    requireNotNull(
                        device.wait(
                            Until.findObject(By.desc(f.base.getString(R.string.nav_settings))),
                            5_000,
                        )
                    )
                settings.click()
                screen(Screen.SETTINGS)
                val label = By.text(f.base.getString(R.string.animate_conversation_background))
                val scroller = device.findObject(By.scrollable(true))
                if (!device.hasObject(label))
                    scroller.scrollUntil(
                        androidx.test.uiautomator.Direction.DOWN,
                        Until.hasObject(label),
                    )
                requireNotNull(device.findObject(label)).click()
                assertFalse(f.model.animateConversationBackground)
                device.pressBack()
                screen(Screen.HOME)
                SystemClock.sleep(600)
                val paused = sample("06-settings-off")
                SystemClock.sleep(900)
                assertArrayEquals(paused, sample("07-settings-still"))
                requireNotNull(device.findObject(By.text("Maya"))).click()
                screen(Screen.CONVERSATION)
                SystemClock.sleep(550)
                device.pressBack()
                screen(Screen.HOME)
                SystemClock.sleep(550)
                assertArrayEquals(
                    "Chat navigation preserves the exact frozen scene",
                    paused,
                    sample("08-same-water-after-chat"),
                )
            } finally {
                if (originalScale == "null") shell("settings delete global animator_duration_scale")
                else shell("settings put global animator_duration_scale $originalScale")
                f.stopActivity()
                service.close()
            }
        }
    }
}
