package co.fallsoft.vipi

import android.graphics.Bitmap
import android.net.Uri
import android.os.SystemClock
import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.unit.LayoutDirection
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.UUID

/** Normal conversation renderer, encrypted local history and Android media decoder. */
class VoiceBubbleBoundsDeviceTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    @Test fun bothVoiceDirectionsRetainInsetsAndControlsAtEveryPlaybackState() {
        val inst = InstrumentationRegistry.getInstrumentation()
        val ctx = inst.targetContext.applicationContext
        val args = InstrumentationRegistry.getArguments()
        assumeTrue(ctx.packageName.endsWith(".sourcecontextqa") && args.getString("vipiDedicatedEmulator") == "true")
        val rtl = args.getString("rtl") == "true"
        val output = File(ctx.filesDir, "voice-bounds-" + args.getString("vipiJourneyRun", "001"))
        check(output.mkdir())
        val account = UUID.randomUUID()
        val peer = UUID.randomUUID()
        val ids = List(2) { UUID.randomUUID() }
        val labels = ids.mapIndexed { i, id -> (if (i == 0) "incoming-" else "outgoing-") + id }
        val proof = JSONArray()
        val repository = AttachmentRepository(ctx, account)
        val durations = listOf(93, 8)
        val clips = durations.map { seconds ->
            val samples = seconds * 8000
            val bytes = ByteBuffer.allocate(44 + samples * 2).order(ByteOrder.LITTLE_ENDIAN)
            bytes.put("RIFF".toByteArray()).putInt(36 + samples * 2).put("WAVEfmt ".toByteArray())
                .putInt(16).putShort(1).putShort(1).putInt(8000).putInt(16000)
                .putShort(2).putShort(16).put("data".toByteArray()).putInt(samples * 2)
            val file = File.createTempFile("silent-", ".wav", ctx.cacheDir)
            try {
                file.writeBytes(bytes.array())
                runBlocking { repository.prepare(Uri.fromFile(file), AttachmentKind.VOICE) }
            } finally { file.delete() }
        }
        val now = System.currentTimeMillis()
        MessageVault(ctx, account).use { vault ->
            ConversationHistory(vault)
            vault.transaction {
                vault.put("contact", peer.toString(), ChatProfile(peer, "maya", "Maya").json().toString().toByteArray())
                ids.forEachIndexed { i, id ->
                    val outgoing = i == 1
                    val kind = if (outgoing) "outgoing" else "incoming"
                    val time = now - (2 - i) * 60_000
                    val envelope = ChatEnvelope(id, if (outgoing) account else peer, if (outgoing) peer else account, time, 1, byteArrayOf(1))
                    vault.put(kind, id.toString(), StoredChat(envelope, "Voice message", "delivered", true, listOf(clips[i])).encode())
                    ConversationHistory.record(vault, kind, id, peer, time)
                }
            }
        }
        val local = object : ChatTransport {
            override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?,
                                         query: Map<String, String>): JSONObject = when (path) {
                "/v1/me" -> ChatProfile(account, "alex", "Alex").json()
                "/v1/devices" -> JSONObject().put("id", requireNotNull(body).getString("device_id")).put("active", true)
                "/v1/keys" -> JSONObject().put("revision", 1).put("remaining", 20)
                "/v1/media/capability" -> JSONObject().put("version", 1)
                "/v1/blocks/$peer" -> JSONObject().put("blocked", false)
                "/v1/messages/pending" -> JSONObject().put("messages", JSONArray()).put("next_cursor", JSONObject.NULL)
                "/v1/conversations/$peer/receipts" -> JSONObject().put("accepted", true)
                else -> throw ServiceFailure(404, "fixture_route")
            }
        }
        val chat = ChatSession(ctx, local, "user_localvoice_$account", CiphertextTransport("http://127.0.0.1:1") { "unused" })
        val density = ctx.resources.displayMetrics.density
        fun element(index: Int, matcher: SemanticsMatcher) = compose.onNode(
            matcher and hasAnyAncestor(hasTestTag("message-row-" + ids[index])), useUnmergedTree = true)
        fun frame(index: Int) = compose.onNodeWithTag("message-row-" + ids[index]).fetchSemanticsNode().boundsInWindow
        fun checkBounds(index: Int, state: String, action: Int) {
            val bubble = frame(index)
            val track = element(index, hasTestTag("voice-playback-track")).fetchSemanticsNode().boundsInWindow
            val duration = element(index, hasTestTag("voice-playback-position")).fetchSemanticsNode()
            val control = element(index, hasClickAction()).fetchSemanticsNode().boundsInWindow
            val receipt = element(index, hasTestTag("message-meta-" + ids[index])).fetchSemanticsNode().boundsInWindow
            fun inside(r: Rect) = r.width > 0 && r.height > 0 && r.left >= bubble.left - 1 &&
                r.top >= bubble.top - 1 && r.right <= bubble.right + 1 && r.bottom <= bubble.bottom + 1
            for (r in listOf(track, duration.boundsInWindow, control, receipt)) assertTrue("$state $r inside $bubble", inside(r))
            assertTrue("Start and end of track have visible padding", track.left - bubble.left >= 11.5f*density && bubble.right - track.right >= 11.5f*density)
            val endInset = if (rtl) track.left - bubble.left else bubble.right - track.right
            assertTrue("Trailing rail should follow the bubble's 12dp text inset", endInset >= 11.5f*density)
            assertTrue("Touch target $control density $density", control.width >= 48*density-1 && control.height >= 48*density-1)
            assertTrue("Receipt below playback time", receipt.top >= duration.boundsInWindow.bottom - 1)
            element(index, hasContentDescription(ctx.getString(action))).assertIsDisplayed()
            val layouts = mutableListOf<TextLayoutResult>()
            element(index,hasTestTag("voice-playback-position")).performSemanticsAction(SemanticsActions.GetTextLayoutResult) { it(layouts) }
            val text = duration.config[SemanticsProperties.Text].single().text
            val layout = layouts.single()
            assertEquals("Every time character was laid out", text.length, layout.getLineEnd(layout.lineCount-1, visibleEnd=true))
            for (line in 0 until layout.lineCount) {
                assertFalse("Time must never ellipsize", layout.isLineEllipsized(line))
                val left = duration.boundsInWindow.left + layout.getLineLeft(line)
                val right = duration.boundsInWindow.left + layout.getLineRight(line)
                assertTrue("Actual clock ink [$left,$right] must fit inside $bubble", left >= bubble.left+11*density && right <= bubble.right-11*density)
            }
            val total = text.substringAfter(" / ").split(':').fold(0) { time, part -> time * 60 + part.toInt() }
            assertEquals(durations[index], total)
            proof.put(JSONObject().put("row", labels[index]).put("state", state).put("rtl",rtl)
                .put("screen_width_dp",ctx.resources.configuration.screenWidthDp).put("font_scale",ctx.resources.configuration.fontScale)
                .put("bubble",bubble).put("track",track).put("control",control).put("time",text)
                .put("time_bounds",duration.boundsInWindow).put("receipt",receipt).put("trailing_inset_dp",endInset/density))
        }
        fun awaitPlayback(index: Int, seconds: Int) = compose.waitUntil(12_000) {
            val clock = element(index, hasTestTag("voice-playback-position")).fetchSemanticsNode().config[SemanticsProperties.Text].single().text
            clock.substringBefore(" / ").split(':').fold(0) { time, part -> time * 60 + part.toInt() } >= seconds
        }
        fun capture(name: String) {
            compose.waitForIdle()
            SystemClock.sleep(350)
            val screenshot = inst.uiAutomation.takeScreenshot()
            File(output, "$name.png").outputStream().use { check(screenshot.compress(Bitmap.CompressFormat.PNG,100,it)) }
            screenshot.recycle()
        }
        try {
            runBlocking(Dispatchers.Main) { chat.start(); check(chat.ready); chat.configureTranslations("en","es",{ NoJourneyModelTranslation }) }
            compose.setContent {
                CompositionLocalProvider(LocalLayoutDirection provides if (rtl) LayoutDirection.Rtl else LayoutDirection.Ltr) {
                    VipiTheme(if (args.getString("dark")=="true") Appearance.DARK else Appearance.LIGHT) {
                        Box(Modifier.fillMaxSize().safeDrawingPadding()) {
                            FriendConversationScreen(chat,peer,animateBackground=false, back={})
                        }
                    }
                }
            }
            compose.waitUntil(10000) { compose.onAllNodesWithTag("voice-playback-track").fetchSemanticsNodes().size == 2 }
            checkBounds(0,"idle",R.string.media_open_voice)
            checkBounds(1,"idle",R.string.media_open_voice)
            capture("01-both-directions")
            element(0,hasContentDescription(ctx.getString(R.string.media_open_voice))).performClick()
            val pause = hasContentDescription(ctx.getString(R.string.media_pause))
            compose.waitUntil(6000) { element(0,pause).isDisplayed() }
            awaitPlayback(0,2)
            checkBounds(0,"playing",R.string.media_pause)
            capture("incoming-playing")
            element(0,pause).performClick()
            checkBounds(0,"paused",R.string.media_open_voice)
            capture("incoming-paused")
            element(1,hasContentDescription(ctx.getString(R.string.media_open_voice))).performClick()
            compose.waitUntil(6000) { element(1,pause).isDisplayed() }
            awaitPlayback(1,2)
            checkBounds(1,"playing",R.string.media_pause)
            capture("02-playing")
            element(1,pause).performClick()
            checkBounds(1,"paused",R.string.media_open_voice)
            capture("outgoing-paused")
            compose.runOnIdle { stopInlineVoicePlayback() }
            // Re-open the paused incoming row only after its decoder was released by the outgoing row.
            val ciphertext = repository.ciphertext(clips[0].original)
            java.io.RandomAccessFile(ciphertext,"rw").use { it.seek(0); val first=it.read(); it.seek(0); it.write(first xor 1) }
            element(0,hasContentDescription(ctx.getString(R.string.media_open_voice))).performClick()
            val error = element(0,hasText(ctx.getString(R.string.media_open_error)))
            compose.waitUntil(6000) { error.isDisplayed() }
            checkBounds(0,"error",R.string.try_again)
            val err = error.fetchSemanticsNode().boundsInWindow
            assertTrue("Readable error is inset", err.left >= frame(0).left + 11*density && err.right <= frame(0).right - 11*density)
            capture("03-readable-error")
            File(output,"bounds.json").writeText(proof.toString(2))
        } finally {
            compose.runOnIdle { stopInlineVoicePlayback(); chat.close() }
            File(ctx.noBackupFilesDir,"attachments/$account").deleteRecursively()
            File(ctx.noBackupFilesDir,"messages/$account").deleteRecursively()
            java.security.KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
        }
    }
}
