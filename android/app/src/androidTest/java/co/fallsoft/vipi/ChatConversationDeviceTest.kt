package co.fallsoft.vipi

import android.content.Intent
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.regex.Pattern

@RunWith(AndroidJUnit4::class)
class ChatConversationDeviceTest {
    @Test fun reviewConversationThemes() {
        assumeTrue(InstrumentationRegistry.getArguments().getString("vipiLiveNetwork") == "true")
        val instrumentation = InstrumentationRegistry.getInstrumentation(); val context = instrumentation.targetContext
        val device = UiDevice.getInstance(instrumentation)
        val preferences = context.getSharedPreferences("preferences", 0); val previous = preferences.getString("appearance", "SYSTEM")
        val root = File(context.filesDir, "chat-qa").apply { mkdirs() }
        try {
            for (appearance in listOf("LIGHT", "DARK")) {
                preferences.edit().putString("appearance", appearance).commit()
                ActivityScenario.launch<MainActivity>(Intent(context, MainActivity::class.java)).use {
                    assertTrue(device.wait(Until.hasObject(By.text("Vipi iOS QA")), 30000))
                    device.takeScreenshot(File(root, "android-chat-list-${appearance.lowercase()}-review.png"))
                    device.findObject(By.text("Vipi iOS QA")).click()
                    assertTrue(device.wait(Until.hasObject(By.desc("Send message")), 15000))
                    device.takeScreenshot(File(root, "android-conversation-${appearance.lowercase()}-review.png"))
                }
            }
        } finally { preferences.edit().putString("appearance", previous).commit() }
    }
    @Test fun findFriendComposeAndSend() {
        val instrumentation = InstrumentationRegistry.getInstrumentation(); val context = instrumentation.targetContext
        assumeTrue(InstrumentationRegistry.getArguments().getString("vipiLiveNetwork") == "true")
        val peer = requireNotNull(InstrumentationRegistry.getArguments().getString("peer")); require(peer.startsWith("vqa_"))
        val device = UiDevice.getInstance(instrumentation)
        val preferences = context.getSharedPreferences("preferences", 0); val previous = preferences.getString("appearance", "SYSTEM")
        val root = File(context.filesDir, "chat-qa").apply { mkdirs() }
        try {
            preferences.edit().putString("appearance", "LIGHT").commit()
            ActivityScenario.launch<MainActivity>(Intent(context, MainActivity::class.java)).use {
                assertTrue(device.wait(Until.hasObject(By.desc("New chat")), 30000))
                device.takeScreenshot(File(root, "android-chat-list-light.png"))
                device.findObject(By.desc("New chat")).click()
                assertTrue(device.wait(Until.hasObject(By.clazz("android.widget.EditText")), 5000))
                device.findObject(By.clazz("android.widget.EditText")).text = peer
                device.takeScreenshot(File(root, "android-find-friend-light.png"))
                val username = normalizeLookupUsername(peer)
                val exact = By.text(context.getString(R.string.new_chat_lookup, username))
                val saved = By.text("@$username")
                (device.findObject(saved) ?: requireNotNull(device.wait(Until.findObject(exact), 5_000))).click()
                assertTrue(device.wait(Until.hasObject(By.desc("Send message")), 15000))
                device.findObject(By.clazz("android.widget.EditText")).text = "Coffee tomorrow? Sent from the Android conversation screen."
                device.takeScreenshot(File(root, "android-compose-light.png"))
                device.findObject(By.desc("Send message")).click()
                assertTrue(device.wait(Until.hasObject(By.text(Pattern.compile(".* · Sent"))), 20000))
                device.takeScreenshot(File(root, "android-conversation-light.png"))
            }
            preferences.edit().putString("appearance", "DARK").commit()
            ActivityScenario.launch<MainActivity>(Intent(context, MainActivity::class.java)).use {
                assertTrue(device.wait(Until.hasObject(By.text("Vipi iOS QA")), 30000))
                device.findObject(By.text("Vipi iOS QA")).click()
                assertTrue(device.wait(Until.hasObject(By.desc("Send message")), 15000))
                device.takeScreenshot(File(root, "android-conversation-dark.png"))
            }
        } finally { preferences.edit().putString("appearance", previous).commit() }
    }
}
