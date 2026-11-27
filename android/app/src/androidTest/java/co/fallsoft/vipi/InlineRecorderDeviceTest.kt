package co.fallsoft.vipi

import android.Manifest
import android.os.SystemClock
import android.view.MotionEvent
import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.StaleObjectException
import androidx.test.uiautomator.UiDevice
import java.util.UUID
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test

/**
 * Real framework pointer and recorder events. The paired lane separately verifies HTTP, Signal and
 * recipient playback.
 */
class InlineRecorderDeviceTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun holdCancelLockPreviewDiscardReleaseAndAccessibleControls() {
        val inst = InstrumentationRegistry.getInstrumentation()
        val context = inst.targetContext
        assumeTrue(
            context.packageName.endsWith(".sourcecontextqa") &&
                InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true"
        )
        inst.uiAutomation.grantRuntimePermission(
            context.packageName,
            Manifest.permission.RECORD_AUDIO,
        )
        val device = UiDevice.getInstance(inst)
        val account = UUID.randomUUID()
        val repo = AttachmentRepository(context, account)
        val vault = MessageVault(context, account)
        val peer = UUID.randomUUID()
        val local =
            object : ChatTransport {
                override suspend fun request(
                    method: String,
                    path: String,
                    body: org.json.JSONObject?,
                    device: DeviceCredential?,
                    query: Map<String, String>,
                ): org.json.JSONObject =
                    when (path) {
                        "/v1/me" -> ChatProfile(account, "voice_local", "Alex").json()
                        "/v1/devices" ->
                            org.json
                                .JSONObject()
                                .put("id", requireNotNull(body).getString("device_id"))
                                .put("active", true)
                        "/v1/keys" -> org.json.JSONObject().put("revision", 1).put("remaining", 20)
                        "/v1/media/capability" -> org.json.JSONObject().put("version", 1)
                        "/v1/messages/pending" ->
                            org.json
                                .JSONObject()
                                .put("messages", org.json.JSONArray())
                                .put("next_cursor", org.json.JSONObject.NULL)
                        else -> throw ServiceFailure(404, "fixture_route")
                    }
            }
        val chat =
            ChatSession(
                context,
                local,
                "user_localmedia_voice_$account",
                CiphertextTransport("http://127.0.0.1:1") { "unused" },
            )
        kotlinx.coroutines.runBlocking(kotlinx.coroutines.Dispatchers.Main) {
            chat.start()
            check(chat.ready)
        }
        val drafts = requireNotNull(chat.voiceDrafts)
        val accepted = java.util.concurrent.CopyOnWriteArrayList<AttachmentManifest>()
        val errors = java.util.concurrent.CopyOnWriteArrayList<Exception>()
        val visible = mutableStateOf(true)
        val transportAvailable = mutableStateOf(true)
        val offline = java.util.concurrent.atomic.AtomicBoolean(false)
        val slowCheck =
            java.util.concurrent.atomic.AtomicReference<
                kotlinx.coroutines.CompletableDeferred<Unit>?
            >(
                null
            )
        val checking = java.util.concurrent.atomic.AtomicBoolean(false)
        compose.setContent {
            var active by remember { mutableStateOf(false) }
            VipiTheme(Appearance.LIGHT) {
                Box(
                    Modifier.fillMaxSize().safeDrawingPadding().padding(16.dp),
                    contentAlignment = Alignment.BottomCenter,
                ) {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        if (!active) Spacer(Modifier.weight(1f).testTag("idle-composer"))
                        if (visible.value)
                            VoiceComposer(
                                drafts,
                                peer,
                                transportAvailable.value,
                                {
                                    slowCheck.get()?.let {
                                        checking.set(true)
                                        it.await()
                                    }
                                    if (offline.get())
                                        throw java.io.IOException(
                                            "Synthetic capability route offline"
                                        )
                                },
                                { manifest, commit ->
                                    check(
                                        manifest.kind == AttachmentKind.VOICE &&
                                            repo.ciphertext(manifest.original).isFile
                                    )
                                    chat.sendVoiceDraft("Voice message", peer, manifest, commit)
                                    accepted.add(manifest)
                                },
                                { active = it },
                                errors::add,
                            )
                    }
                }
            }
        }
        fun actionCenter(label: String): android.graphics.Point {
            var center: android.graphics.Point? = null
            compose.waitUntil(5000) {
                center =
                    try {
                        device.findObject(By.desc(label))?.visibleCenter
                    } catch (_: StaleObjectException) {
                        null
                    }
                center != null
            }
            return requireNotNull(center)
        }
        fun pointer(kind: Int, x: Float, y: Float, time: Long) {
            val event = MotionEvent.obtain(time, SystemClock.uptimeMillis(), kind, x, y, 0)
            try {
                check(inst.uiAutomation.injectInputEvent(event, true))
            } finally {
                event.recycle()
            }
        }
        fun press(
            dx: Float = 0f,
            dy: Float = 0f,
            milliseconds: Long = 1050,
            interrupt: Boolean = false,
        ) {
            val pos = actionCenter("Hold to record a voice message")
            val scale = context.resources.displayMetrics.density
            val down = SystemClock.uptimeMillis()
            pointer(MotionEvent.ACTION_DOWN, pos.x.toFloat(), pos.y.toFloat(), down)
            var released = false
            try {
                SystemClock.sleep(milliseconds)
                val x = pos.x + dx * scale
                val y = pos.y + dy * scale
                if (dx != 0f || dy != 0f) {
                    pointer(MotionEvent.ACTION_MOVE, x, y, down)
                    SystemClock.sleep(120)
                }
                if (interrupt) {
                    compose.runOnIdle { visible.value = false }
                    compose.onNodeWithTag("voice-action").assertDoesNotExist()
                }
                pointer(MotionEvent.ACTION_UP, x, y, down)
                released = true
            } finally {
                if (!released)
                    runCatching {
                        pointer(MotionEvent.ACTION_CANCEL, pos.x.toFloat(), pos.y.toFloat(), down)
                    }
            }
        }
        fun ax() =
            compose.onNodeWithTag("voice-action").performSemanticsAction(SemanticsActions.OnClick)
        fun waitFor(label: String) =
            compose.waitUntil(8000) {
                compose.onAllNodesWithContentDescription(label).fetchSemanticsNodes().isNotEmpty()
            }
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
            SystemClock.sleep(800)
            device.pressBack()
            waitFor("Send voice message")
            assertNotNull(drafts.current(peer))
            compose.runOnIdle { transportAvailable.value = false }
            compose.waitForIdle()
            compose.runOnIdle { transportAvailable.value = true }
            compose.waitForIdle()
            compose.onNodeWithTag("idle-composer").assertDoesNotExist()
            compose.onNodeWithTag("voice-discard").performClick()
            idle()
            assertTrue(accepted.isEmpty())
            press(interrupt = true)
            compose.waitUntil(6000) { drafts.current(peer) != null }
            drafts.finishPending()
            val interrupted = requireNotNull(drafts.current(peer))
            assertTrue(repo.ciphertext(interrupted.original).isFile)
            assertNull(drafts.current(UUID.randomUUID()))
            MessageVault(context, account).use { reopened ->
                assertEquals(interrupted, VoiceDrafts(reopened, repo).current(peer))
            }
            val otherAccount = UUID.randomUUID()
            MessageVault(context, otherAccount).use { other ->
                assertNull(
                    VoiceDrafts(other, AttachmentRepository(context, otherAccount)).current(peer)
                )
            }
            java.io.File(context.noBackupFilesDir, "messages/$otherAccount").deleteRecursively()
            java.security.KeyStore.getInstance("AndroidKeyStore").apply {
                load(null)
                deleteEntry("co.fallsoft.vipi.messages.$otherAccount")
            }
            assertTrue(
                java.io
                    .File(context.cacheDir, "media-capture/$account")
                    .listFiles()
                    .orEmpty()
                    .isEmpty()
            )
            compose.runOnIdle { visible.value = true }
            waitFor("Send voice message")
            assertTrue(accepted.isEmpty())
            compose.onNodeWithContentDescription("Play voice message").performClick()
            waitFor("Pause")
            compose.onNodeWithTag("voice-discard").performClick()
            idle()
            assertNull(drafts.current(peer))
            assertFalse(repo.ciphertext(interrupted.original).exists())
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
            val send = actionCenter("Send voice message")
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
            assertNull(drafts.current(peer))
            val count = vault.transaction { vault.ids("draft").size }
            assertEquals(4, count)
            val now = System.currentTimeMillis()
            assertTrue(
                runCatching {
                    MessageJournal(vault)
                        .saveDraft(
                            UUID.randomUUID(),
                            peer,
                            "Voice message",
                            now,
                            now,
                            attachments = listOf(accepted.last()),
                            consumeVoiceDraft = true,
                        )
                }
                    .isFailure
            )
            assertEquals(count, vault.transaction { vault.ids("draft").size })
            val previous = vault.transaction {
                DraftChat.parse(requireNotNull(vault.get("draft", vault.ids("draft").first())))
            }
            MessageJournal(vault)
                .saveDraft(
                    previous.id,
                    peer,
                    previous.text,
                    previous.createdAt,
                    now,
                    attachments = previous.attachments,
                    consumeVoiceDraft = true,
                )
            assertEquals(count, vault.transaction { vault.ids("draft").size })
            val gate = kotlinx.coroutines.CompletableDeferred<Unit>()
            slowCheck.set(gate)
            press()
            compose.waitUntil(6000) { checking.get() }
            compose.activityRule.scenario.moveToState(Lifecycle.State.STARTED)
            gate.complete(Unit)
            SystemClock.sleep(300)
            assertEquals(4, accepted.size)
            compose.activityRule.scenario.moveToState(Lifecycle.State.RESUMED)
            waitFor("Send voice message")
            assertNotNull(drafts.current(peer))
            compose.onNodeWithTag("voice-discard").performClick()
            assertNull(drafts.current(peer))
        } finally {
            compose.runOnIdle { visible.value = false }
            compose.waitForIdle()
            drafts.finishPending()
            accepted.forEach(repo::discard)
            kotlinx.coroutines.runBlocking(kotlinx.coroutines.Dispatchers.Main) { chat.close() }
            vault.close()
            java.io.File(context.noBackupFilesDir, "messages/$account").deleteRecursively()
            java.security.KeyStore.getInstance("AndroidKeyStore").apply {
                load(null)
                deleteEntry("co.fallsoft.vipi.messages.$account")
            }
        }
    }
}
