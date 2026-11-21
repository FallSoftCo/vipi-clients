package co.fallsoft.vipi

import android.Manifest
import android.os.SystemClock
import android.view.MotionEvent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import java.util.UUID

/** Real framework pointer and recorder events. The paired lane separately verifies HTTP, Signal and recipient playback. */
class InlineRecorderDeviceTest {
    @get:Rule val compose = createComposeRule()
    @Test fun holdCancelLockPreviewDiscardReleaseAndAccessibleControls() {
        val inst = InstrumentationRegistry.getInstrumentation()
        val context = inst.targetContext
        assumeTrue(context.packageName.endsWith(".sourcecontextqa") && InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        inst.uiAutomation.grantRuntimePermission(context.packageName, Manifest.permission.RECORD_AUDIO)
        val device = UiDevice.getInstance(inst)
        val account = UUID.randomUUID()
        val repo = AttachmentRepository(context, account)
        val accepted = java.util.concurrent.CopyOnWriteArrayList<AttachmentManifest>()
        val errors = java.util.concurrent.CopyOnWriteArrayList<Exception>()
        val visible = mutableStateOf(true)
        val offline = java.util.concurrent.atomic.AtomicBoolean(false)
        compose.setContent {
            var active by remember { mutableStateOf(false) }
            VipiTheme(Appearance.LIGHT) {
                Box(Modifier.fillMaxSize().safeDrawingPadding().padding(16.dp), contentAlignment = Alignment.BottomCenter) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    if (!active) Spacer(Modifier.weight(1f))
                    if (visible.value) VoiceComposer(repo, true, {
                        if (offline.get()) throw java.io.IOException("Synthetic capability route offline")
                    }, { manifest, commit ->
                        check(manifest.kind == AttachmentKind.VOICE && repo.ciphertext(manifest.original).isFile)
                        accepted.add(manifest); commit()
                    }, { active = it }, errors::add)
                }
                }
            }
        }
        fun anchor() = requireNotNull(device.wait(Until.findObject(By.desc("Hold to record a voice message")), 5000)).visibleCenter
        fun pointer(kind: Int, x: Float, y: Float, time: Long) {
            val event = MotionEvent.obtain(time, SystemClock.uptimeMillis(), kind, x, y, 0)
            try { check(inst.uiAutomation.injectInputEvent(event, true)) } finally { event.recycle() }
        }
        fun press(dx: Float = 0f, dy: Float = 0f, milliseconds: Long = 1050, interrupt: Boolean = false) {
            val pos = anchor()
            val scale = context.resources.displayMetrics.density
            val down = SystemClock.uptimeMillis()
            pointer(MotionEvent.ACTION_DOWN, pos.x.toFloat(), pos.y.toFloat(), down)
            var released = false
            try {
                SystemClock.sleep(milliseconds)
                val x = pos.x + dx * scale
                val y = pos.y + dy * scale
                if (dx != 0f || dy != 0f) { pointer(MotionEvent.ACTION_MOVE, x, y, down); SystemClock.sleep(120) }
                if (interrupt) {
                    compose.runOnIdle { visible.value = false }
                    compose.onNodeWithTag("voice-action").assertDoesNotExist()
                }
                pointer(MotionEvent.ACTION_UP, x, y, down)
                released = true
            } finally { if (!released) runCatching { pointer(MotionEvent.ACTION_CANCEL, pos.x.toFloat(), pos.y.toFloat(), down) } }
        }
        fun ax() = compose.onNodeWithTag("voice-action").performSemanticsAction(SemanticsActions.OnClick)
        fun waitFor(label: String) = compose.waitUntil(8000) { compose.onAllNodesWithContentDescription(label).fetchSemanticsNodes().isNotEmpty() }
        fun idle() = waitFor("Hold to record a voice message")
        try {
            press(milliseconds = 65)
            waitFor("Record hands-free")
            compose.onNodeWithTag("voice-discard").performClick()
            idle()
            assertTrue(accepted.isEmpty())
            press(dx = -92f)
            idle()
            assertTrue(accepted.isEmpty())
            // The fixture places its composer at the bottom so an upward motion is fully on screen.
            ax()
            waitFor("Finish recording")
            SystemClock.sleep(1000)
            compose.onNodeWithTag("voice-stop").performSemanticsAction(SemanticsActions.OnClick)
            waitFor("Send voice message")
            compose.onNodeWithTag("inline-voice-player").assertExists()
            compose.onNodeWithContentDescription("Play voice message").performClick()
            waitFor("Pause")
            compose.onNodeWithContentDescription("Pause").performClick()
            compose.onNodeWithTag("voice-discard").performClick()
            idle()
            assertTrue(accepted.isEmpty())
            ax()
            waitFor("Finish recording")
            device.pressBack()
            idle()
            assertTrue(accepted.isEmpty())
            press(interrupt = true)
            compose.runOnIdle { visible.value = true }
            idle()
            assertTrue(accepted.isEmpty())
            press(dy = -84f)
            waitFor("Finish recording")
            SystemClock.sleep(450)
            compose.onNodeWithContentDescription("Finish recording").performClick()
            waitFor("Send voice message")
            compose.onNodeWithContentDescription("Send voice message").performClick()
            compose.waitUntil(8000) { accepted.size == 1 }
            idle()
            press()
            compose.waitUntil(8000) { accepted.size == 2 }
            idle()
            // Lifting the finger after locking must not activate the Send button now under it.
            press(dy = -84f)
            waitFor("Finish recording")
            SystemClock.sleep(600)
            assertEquals(2, accepted.size)
            val send = requireNotNull(device.findObject(By.desc("Send voice message"))).visibleCenter
            assertTrue(device.click(send.x, send.y))
            compose.waitUntil(8000) { accepted.size == 3 }
            idle()
            SystemClock.sleep(450)
            assertEquals(3, accepted.size)
            assertEquals(3, accepted.map { it.id }.distinct().size)
            assertTrue(errors.toString(), errors.isEmpty())
            offline.set(true)
            ax()
            waitFor("Finish recording")
            SystemClock.sleep(750)
            compose.onNodeWithContentDescription("Send voice message").performClick()
            compose.waitUntil(5000) { errors.size == 1 }
            compose.onNodeWithTag("inline-voice-player").assertIsDisplayed()
            assertEquals(3, accepted.size)
            offline.set(false)
            compose.onNodeWithContentDescription("Send voice message").performClick()
            compose.waitUntil(8000) { accepted.size == 4 }
            idle()
            assertEquals(4, accepted.map { it.id }.distinct().size)
            assertEquals("Synthetic capability route offline", errors.single().message)
        } finally {
            compose.runOnIdle { visible.value = false }
            accepted.forEach(repo::discard)
        }
    }
}
