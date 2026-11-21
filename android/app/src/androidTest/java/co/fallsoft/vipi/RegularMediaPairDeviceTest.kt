package co.fallsoft.vipi

import android.app.Application
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.SystemClock
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.v2.createEmptyComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.net.InetSocketAddress
import java.net.Socket
import java.util.UUID

/** Ephemeral test overlay. Uses native UI, service and Signal stores and real private HTTP. */
class RegularMediaPairDeviceTest {
    @get:Rule val compose = createEmptyComposeRule()
    private val inst get() = InstrumentationRegistry.getInstrumentation()
    private val app get() = inst.targetContext.applicationContext as Application
    private val config get() = JSONObject(File(app.filesDir, "media-ui-config.json").readText())
    private val runID get() = config.getString("run").also { require(it.matches(Regex("[a-zA-Z0-9-]{1,96}"))) }
    private val stateFile get() = File(app.filesDir, "regular-media-ui-$runID-state.json")
    private fun readState() = JSONObject(stateFile.readText())
    private fun model(): VipiModel {
        val c = config
        require(c.getBoolean("isolated_signed_authentication"))
        val endpoint = c.getString("endpoint")
        require(java.net.URI(endpoint).host == "127.0.0.1")
        val subject = c.getString("expected_subject")
        require(subject.startsWith("user_localpair_"))
        val records = PrivateRecords(app)
        check(records.read("session") == null)
        records.write("session", IdentityAuthority.FALLSOFT_VIPI_PRODUCTION.tag(JSONObject()
            .put("userID", subject).put("accessToken", c.getString("access_token")).put("refreshToken", "inert-local-no-refresh")))
        val boundary = object : VipiWorkflowBoundary {
            override fun transport(authentication: Authentication, userID: String): ChatTransport {
                check(userID == subject)
                return ServiceClient(authentication, userID, endpoint)
            }
            override fun requestPush(context: Context, registration: Boolean) {}
            override fun cancelPush(context: Context) {}
            override fun foregroundEvents(scope: CoroutineScope, authentication: Authentication, chat: ChatSession) =
                ForegroundInboxEvents(scope, { c.getString("access_token") }, chat::eventDevice, { chat.synchronize() },
                    endpoint = endpoint, onTyping = chat::peerTypingEvent, onReceipts = chat::receiptEvent, onConnected = chat::eventConnected)
            override fun translationClient(): LanguageTranslation = NoJourneyModelTranslation
        }
        return VipiModel(app, NoJourneyModelTranslation, boundary).also { it.changeConversationAnimation(false) }
    }
    private fun stage(label: String, action: (MainActivityJourneyFixture) -> Unit) {
        org.junit.Assume.assumeTrue(InstrumentationRegistry.getArguments().getString("vipiRegularMediaPair") == "true")
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val c = config
        if (!c.getString("username").startsWith("vma")) error("Dedicated media identity required")
        val owner = PrivateRecords(app)
        val marker = File(app.filesDir, "regular-media-ui-$runID-${label}.json")
        check(!marker.exists() && owner.read("session") == null)
        try {
            MainActivityJourneyFixture("regular-media-ui-$label", { model() }).use { f ->
                action(f)
                marker.writeText(JSONObject().put("run", c.getString("run")).put("stage", label)
                    .put("pid", android.os.Process.myPid()).put("terminal", "passed").toString())
            }
        } finally {
            val current = owner.read("session")
            if (current != null) {
                check(current.getString("userID") == c.getString("expected_subject"))
                owner.remove("session")
            }
        }
    }
    private fun capture(f: MainActivityJourneyFixture, name: String) {
        compose.waitForIdle()
        SystemClock.sleep(650)
        f.capture(name)
    }

    @Test fun playExistingVoiceNotesInTheTimeline() = stage("voice-playback") { f ->
        val before = readState()
        val peer = UUID.fromString(before.getString("peer"))
        val arguments = InstrumentationRegistry.getArguments()
        val comparison = arguments.getString("otherIncomingVoiceID")?.let(UUID::fromString)
        val ids = if (comparison != null) listOf(comparison, UUID.fromString(before.getString("sent_voice")))
            else listOf("voice", "locked").sortedByDescending { before.getLong("${it}_duration_ms") }
                .map { UUID.fromString(before.getString("sent_$it")) }
        check(ids.distinct().size == 2)
        f.launch()
        compose.waitUntil(25_000) { f.model.chat?.ready == true && f.model.screen == Screen.HOME }
        val chat = requireNotNull(f.model.chat)
        if (comparison != null) compose.waitUntil(25_000) { chat.messages(peer).any { it.id == comparison && !it.outgoing } }
        val incomingID = arguments.getString("incomingVoiceID")?.let(UUID::fromString)
        val expectedHash = arguments.getString("incomingVoiceSHA256")
        if (incomingID != null) {
            require(expectedHash != null && expectedHash.matches(Regex("[a-f0-9]{64}")))
            compose.waitUntil(25_000) { chat.messages(peer).any { it.id == incomingID && !it.outgoing } }
        }
        val voiceIDs = chat.messages(peer).filter { it.attachments.any { a -> a.kind == AttachmentKind.VOICE } }.map { it.id }.toSet()
        check(ids.all { it in voiceIDs })
        compose.onNodeWithTag("inbox-row-$peer").performClick()
        compose.waitUntil { f.model.screen == Screen.CONVERSATION }
        val play = app.getString(R.string.media_open_voice)
        val pause = app.getString(R.string.media_pause)
        fun inRow(id: UUID) = hasAnyAncestor(hasTestTag("message-row-$id"))
        fun button(id: UUID, action: String) = compose.onNode(hasContentDescription(action) and inRow(id))
        fun seconds(id: UUID): Int {
            val value = compose.onNode(hasTestTag("voice-playback-position") and inRow(id), useUnmergedTree = true)
                .fetchSemanticsNode().config[androidx.compose.ui.semantics.SemanticsProperties.Text].single().text
            return value.substringBefore(" / ").split(':').fold(0) { acc, part -> acc * 60 + part.toInt() }
        }
        val first = ids[0]; val second = ids[1]
        compose.onNodeWithTag("conversation-timeline").performScrollToNode(hasTestTag("message-row-$first"))
        button(first, play).performClick()
        compose.waitUntil(12_000) { runCatching { seconds(first) > 0 }.getOrDefault(false) }
        button(first, pause).performClick()
        val paused = seconds(first)
        SystemClock.sleep(500)
        check(seconds(first) == paused)
        capture(f, "01-note-paused-inline")
        button(first, play).performClick()
        button(first, pause).assertExists()
        compose.onNodeWithTag("conversation-timeline").performScrollToNode(hasTestTag("message-row-$second"))
        button(second, play).performClick()
        compose.waitUntil(8_000) { runCatching { button(second, pause).assertExists(); true }.getOrDefault(false) }
        button(first, play).assertExists()
        capture(f, "02-second-note-playing-inline")
        compose.waitUntil(24_000) { runCatching { button(second, play).assertExists(); true }.getOrDefault(false) }
        val secondCompletedSeconds = seconds(second)
        check(secondCompletedSeconds > 0)
        check(f.model.screen == Screen.CONVERSATION)
        val after = chat.messages(peer).filter { it.attachments.any { a -> a.kind == AttachmentKind.VOICE } }.map { it.id }.toSet()
        check(after == voiceIDs)
        var incomingHash: String? = null
        if (incomingID != null) {
            val incoming = chat.messages(peer).single { it.id == incomingID && !it.outgoing }
            val manifest = incoming.attachments.single { it.kind == AttachmentKind.VOICE }
            compose.onNodeWithTag("conversation-timeline").performScrollToNode(hasTestTag("message-row-$incomingID"))
            button(incomingID, play).performClick()
            compose.waitUntil(8_000) { runCatching { button(incomingID, pause).assertExists(); true }.getOrDefault(false) }
            capture(f, "03-incoming-iPhone-note-inline")
            compose.waitUntil(24_000) { runCatching { button(incomingID, play).assertExists(); true }.getOrDefault(false) }
            check(seconds(incomingID) > 0)
            val clear = runBlocking { chat.openMedia(peer, manifest, AttachmentRepository(app, requireNotNull(chat.profile).id)) }
            incomingHash = try { java.security.MessageDigest.getInstance("SHA-256").digest(clear.readBytes()).joinToString("") { "%02x".format(it) } }
            finally { clear.delete() }
            check(incomingHash == expectedHash)
        }
        File(f.output, "playback.json").writeText(JSONObject().put("sourceRun", config.getString("run"))
            .put("first", first).put("second", second).put("pausedSeconds", paused)
            .put("secondCompletedSeconds", secondCompletedSeconds).put("exactNoteIDsPreserved", true)
            .put("otherNotePaused", true).put("incomingVoiceID", incomingID).put("incomingOpenedSHA256", incomingHash)
            .put("fixtureSubmittedMessages", 0).toString(2))
    }

    @Test fun register() = stage("register") { f ->
        val username = config.getString("username")
        check(username.matches(Regex("vma[a-z0-9]+")))
        runBlocking {
            val api = SignedLoopbackPairTransport(config.getString("endpoint"), config.getString("access_token"))
            val profile = api.request("PUT", "/v1/me", JSONObject().put("username", username).put("display_name", "Maya Android"))
            withContext(Dispatchers.Main) { f.model.activateChats() }
            val chat = requireNotNull(f.model.chat)
            check(chat.ready && chat.profile!!.id.toString() == profile.getString("id"))
            val own = requireNotNull(chat.eventDevice())
            var observed = JSONObject()
            withTimeout(8000) {
                while (observed.optInt("version") != 1) {
                    observed = api.request("GET", "/v1/media/capability/" + profile.getString("id"), device = own)
                    if (observed.optInt("version") != 1) delay(200)
                }
            }
            check(observed.getString("device_id") == own.id.toString())
            stateFile.writeText(JSONObject().put("run", config.getString("run")).put("account", profile.getString("id"))
                .put("device", own.id).put("media_version", 1).toString())
        }
    }
    @Test fun profileAndCameraControls() = stage("controls") { f ->
        val peer = UUID.fromString(readState().getString("peer"))
        val uri = requireNotNull(app.contentResolver.insert(android.provider.MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            android.content.ContentValues().apply {
                put(android.provider.MediaStore.Images.Media.DISPLAY_NAME, "Vipi-review-profile.jpg")
                put(android.provider.MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
                put(android.provider.MediaStore.Images.Media.IS_PENDING, 1)
            }))
        try {
            val art = android.graphics.Bitmap.createBitmap(192, 120, android.graphics.Bitmap.Config.ARGB_8888)
            art.eraseColor(0xff4b675b.toInt())
            val canvas = android.graphics.Canvas(art)
            val paint = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply { color = 0xffe7b381.toInt() }
            canvas.drawCircle(96f, 50f, 32f, paint); canvas.drawRoundRect(48f, 78f, 144f, 144f, 14f, 14f, paint)
            requireNotNull(app.contentResolver.openOutputStream(uri)).use { check(art.compress(android.graphics.Bitmap.CompressFormat.JPEG, 92, it)) }
            art.recycle()
            app.contentResolver.update(uri, android.content.ContentValues().apply { put(android.provider.MediaStore.Images.Media.IS_PENDING, 0) }, null, null)
            f.launch()
            compose.waitUntil(20_000) { f.model.screen == Screen.HOME && f.model.chat?.ready == true }
            val chat = requireNotNull(f.model.chat)
            val existing = chat.messages(peer).filter { it.outgoing }.map { it.id }.toSet()
            val me = requireNotNull(chat.profile).id
            compose.onNodeWithContentDescription(app.getString(R.string.nav_settings)).performClick()
            fun choose(label: String) {
                compose.onNodeWithText(label).performScrollTo().performClick()
                val tile = requireNotNull(f.device.wait(Until.findObject(By.res(java.util.regex.Pattern.compile(".*:id/(icon_thumbnail|thumbnail|item_thumbnail|image_thumbnail)"))), 12_000))
                tile.click()
                compose.waitUntil(8000) { compose.onAllNodesWithText("Use this photo").fetchSemanticsNodes().isNotEmpty() }
                compose.onNodeWithText("Use this photo").performClick()
                compose.waitUntil(5000) { compose.onAllNodesWithText("Use this photo").fetchSemanticsNodes().isEmpty() }
            }
            if (chat.avatar(me)?.jpeg == null) choose("Set profile photo") else choose("Change profile photo")
            val first = requireNotNull(chat.avatar(me))
            check(first.jpeg != null)
            capture(f, "05-settings-avatar")
            choose("Change profile photo")
            val changed = requireNotNull(chat.avatar(me))
            check(changed.revision > first.revision)
            compose.onNodeWithText("Remove profile photo").performClick()
            compose.onAllNodesWithText("Remove profile photo").onLast().performClick()
            compose.waitUntil(5000) { chat.avatar(me)?.jpeg == null }
            val removed = requireNotNull(chat.avatar(me))
            check(removed.revision > changed.revision)
            choose("Set profile photo")
            val finalAvatar = requireNotNull(chat.avatar(me))
            check(finalAvatar.revision > removed.revision)
            compose.onNodeWithContentDescription(app.getString(R.string.nav_back)).performClick()
            compose.waitUntil(5000) { compose.onAllNodesWithTag("inbox-row-$peer").fetchSemanticsNodes().isNotEmpty() }
            compose.onNodeWithTag("inbox-row-$peer").performClick()
            compose.onNodeWithContentDescription("Attach media").performClick()
            capture(f, "06-camera-and-gallery")
            compose.onNodeWithText("Take a photo").performClick()
            compose.waitUntil(8000) { f.device.currentPackageName != app.packageName }
            val cameraPackage = f.device.currentPackageName
            f.device.pressBack()
            compose.waitUntil(8000) { f.device.currentPackageName == app.packageName }
            val values = readState().put("camera_launch_package",cameraPackage).put("camera_cancel",true).put("android_avatar_revision",finalAvatar.revision)
            check(chat.messages(peer).filter { it.outgoing }.map { it.id }.toSet() == existing)
            stateFile.writeText(values.toString())
        } finally { app.contentResolver.delete(uri, null, null) }
    }
    @Test fun receivePhotoAndAvatar() = stage("receive") { f ->
        f.launch()
        compose.waitUntil(35_000) { f.model.chat?.threads?.isNotEmpty() == true }
        val chat = requireNotNull(f.model.chat)
        val peer = chat.threads.single().peer
        compose.onNodeWithTag("inbox-row-$peer").performClick()
        val row = chat.messages(peer).single { !it.outgoing && it.attachments.singleOrNull()?.kind == AttachmentKind.PHOTO }
        val item = row.attachments.single()
        val avatar = requireNotNull(chat.avatar(peer))
        val jpeg = requireNotNull(avatar.jpeg)
        check(jpeg.size in 1..4096 && android.graphics.BitmapFactory.decodeByteArray(jpeg, 0, jpeg.size).width == 96)
        compose.onNodeWithText("Open photo").performClick()
        compose.waitUntil(15_000) { compose.onAllNodesWithContentDescription("Opened photo").fetchSemanticsNodes().isNotEmpty() }
        capture(f, "01-swift-photo")
        compose.onNodeWithText("Close").performClick()
        val store = AttachmentRepository(app, requireNotNull(chat.profile).id)
        val clear = runBlocking { store.openLocal(item) }
        fun digest(bytes: ByteArray) = java.security.MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
        val hash = try { digest(clear.readBytes()) } finally { clear.delete() }
        stateFile.writeText(readState().put("received", row.id).put("peer", peer).put("photo_original", hash)
            .put("photo_width", item.width).put("photo_height", item.height).put("avatar_sha256", digest(jpeg))
            .put("avatar_revision", avatar.revision).put("avatar_bytes", jpeg.size).toString())
        capture(f, "02-avatar-and-photo-in-chat")
    }
    @Test fun sendVideoFromGallery() = stage("sendvideo") { f ->
        val state = readState()
        val peer = UUID.fromString(state.getString("peer"))
        val source = File(app.filesDir, "regular-media-fixture.mp4")
        check(source.length() in 500..1_000_000)
        val uri = requireNotNull(app.contentResolver.insert(android.provider.MediaStore.Video.Media.EXTERNAL_CONTENT_URI,
            android.content.ContentValues().apply {
                put(android.provider.MediaStore.MediaColumns.DISPLAY_NAME, "Vipi-pair-video.mp4")
                put(android.provider.MediaStore.MediaColumns.MIME_TYPE, "video/mp4")
                put(android.provider.MediaStore.MediaColumns.IS_PENDING, 1)
            }))
        try {
            requireNotNull(app.contentResolver.openOutputStream(uri)).use { out -> source.inputStream().use { it.copyTo(out) } }
            app.contentResolver.update(uri, android.content.ContentValues().apply { put(android.provider.MediaStore.MediaColumns.IS_PENDING, 0) }, null, null)
            f.launch()
            compose.waitUntil(20_000) { f.model.screen == Screen.HOME && f.model.chat?.ready == true }
            val chat = requireNotNull(f.model.chat)
            check(chat.messages(peer).none { row -> row.outgoing && row.attachments.any { it.kind == AttachmentKind.VIDEO } })
            compose.onNodeWithTag("inbox-row-$peer").performClick()
            compose.onNodeWithContentDescription("Attach media").performClick()
            compose.onNodeWithText("Photos and videos").performClick()
            val tile = requireNotNull(f.device.wait(Until.findObject(By.res(java.util.regex.Pattern.compile(".*:id/(icon_thumbnail|thumbnail|item_thumbnail|image_thumbnail)"))), 12_000))
            tile.click()
            compose.waitUntil(12_000) { compose.onAllNodesWithText("Open video").fetchSemanticsNodes().isNotEmpty() }
            capture(f, "09-video-picker-review")
            compose.onNodeWithText("Send").performClick()
            compose.waitUntil(30_000) { chat.messages(peer).any { row ->
                row.outgoing && row.attachments.any { it.kind == AttachmentKind.VIDEO } && row.state in setOf("accepted","delivered","read")
            } }
            val row = chat.messages(peer).single { it.outgoing && it.attachments.any { a -> a.kind == AttachmentKind.VIDEO } }
            val item = row.attachments.single()
            val hash = java.security.MessageDigest.getInstance("SHA-256").digest(source.readBytes()).joinToString("") { "%02x".format(it) }
            stateFile.writeText(state.put("sent_video",row.id).put("sent_video_sha256",hash).put("sent_video_width",item.width)
                .put("sent_video_height",item.height).put("sent_video_duration_ms",item.durationMillis).toString())
        } finally { app.contentResolver.delete(uri, null, null) }
    }
    @Test fun receiveVideoAndRemovedAvatar() = stage("video") { f ->
        val state = readState()
        val peer = UUID.fromString(state.getString("peer"))
        f.launch()
        compose.waitUntil(30_000) { f.model.chat?.messages(peer)?.any { row ->
            !row.outgoing && row.attachments.any { it.kind == AttachmentKind.VIDEO }
        } == true }
        val chat = requireNotNull(f.model.chat)
        val avatar = requireNotNull(chat.avatar(peer))
        check(avatar.jpeg == null && avatar.revision > state.getLong("avatar_revision"))
        val row = chat.messages(peer).single { !it.outgoing && it.attachments.any { item -> item.kind == AttachmentKind.VIDEO } }
        val item = row.attachments.single()
        compose.onNodeWithTag("inbox-row-$peer").performClick()
        compose.onNode(hasText("Open video") and hasAnyAncestor(hasTestTag("message-row-${row.id}"))).performClick()
        compose.waitUntil(15_000) { compose.onAllNodesWithText("Pause").fetchSemanticsNodes().isNotEmpty() ||
            compose.onAllNodesWithText("Play").fetchSemanticsNodes().isNotEmpty() }
        capture(f, "07-swift-video-player")
        compose.onNodeWithText("Close").performClick()
        val clear = runBlocking { AttachmentRepository(app, requireNotNull(chat.profile).id).openLocal(item) }
        try {
            val media = android.media.MediaMetadataRetriever()
            try {
                media.setDataSource(clear.path)
                val frame = requireNotNull(media.getFrameAtTime(0, android.media.MediaMetadataRetriever.OPTION_CLOSEST_SYNC))
                check(frame.width > 0 && frame.height > 0)
                val digest = java.security.MessageDigest.getInstance("SHA-256").digest(clear.readBytes()).joinToString("") { "%02x".format(it) }
                stateFile.writeText(state.put("video_id",row.id).put("video_sha256",digest).put("video_frame_width",frame.width)
                    .put("video_frame_height",frame.height).put("video_duration_ms",item.durationMillis)
                    .put("removed_avatar_revision",avatar.revision).toString())
                frame.recycle()
            } finally { media.release() }
        } finally { clear.delete() }
        capture(f, "08-initials-after-removal")
    }
    @Test fun deniedMicLeavesChatAndDraftUsable() = stage("deny") { f ->
        val peer = UUID.fromString(readState().getString("peer"))
        check(app.checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) != android.content.pm.PackageManager.PERMISSION_GRANTED)
        f.launch()
        compose.waitUntil(20_000) { f.model.chat?.ready == true && f.model.screen == Screen.HOME }
        compose.onNodeWithTag("inbox-row-$peer").performClick()
        val chat = requireNotNull(f.model.chat)
        val before = chat.messages(peer).filter { it.outgoing }.map { it.id }.toSet()
        compose.onNodeWithContentDescription("Hold to record a voice message").performClick()
        val request = By.res(java.util.regex.Pattern.compile(".*:id/permission_deny_button"))
        requireNotNull(f.device.wait(Until.findObject(request), 8000)).click()
        compose.onNodeWithText("Allow microphone access to record a voice message.").assertIsDisplayed()
        compose.onNodeWithTag("message-input").performTextInput("Draft after denial")
        compose.onNodeWithTag("message-input").assertTextContains("Draft after denial")
        compose.onNodeWithTag("message-input").performTextClearance()
        check(chat.messages(peer).filter { it.outgoing }.map { it.id }.toSet() == before)
        capture(f, "10-mic-denied-text-available")
    }
    @Test fun sendRecordedVoice() = sendInlineVoice("voice", locked = false)
    @Test fun sendLockedVoice() = sendInlineVoice("locked", locked = true)

    private fun sendInlineVoice(stageName: String, locked: Boolean) = stage(stageName) { f ->
        f.launch()
        compose.waitUntil(25_000) { f.model.chat?.ready == true && f.model.screen == Screen.HOME }
        val state = readState()
        val chat = requireNotNull(f.model.chat)
        val peer = if (state.has("peer")) {
            val known = UUID.fromString(state.getString("peer"))
            if (compose.onAllNodesWithTag("inbox-row-$known").fetchSemanticsNodes().isNotEmpty())
                compose.onNodeWithTag("inbox-row-$known").performClick()
            else { compose.runOnIdle { f.model.openConversation(known) } }
            known
        } else {
            compose.onNodeWithTag("inbox-compose").performClick()
            val lookup = compose.onNodeWithTag("new-chat-search")
            lookup.performTextInput(config.getString("peer_username"))
            lookup.performImeAction()
            compose.waitUntil(12_000) { f.model.screen == Screen.CONVERSATION && f.model.selectedPeer != null }
            requireNotNull(f.model.selectedPeer)
        }
        val idField = "sent_${stageName}"
        check(!state.has(idField))
        val existing = chat.messages(peer).filter { it.outgoing && it.attachments.any { a -> a.kind == AttachmentKind.VOICE } }.map { it.id }.toSet()
        runBlocking(Dispatchers.Main) { chat.requirePeerMedia(peer) }
        if (app.checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            compose.onNodeWithContentDescription("Hold to record a voice message").performClick()
            val allow = By.res(java.util.regex.Pattern.compile(".*:id/permission_allow_foreground_only_button"))
            requireNotNull(f.device.wait(Until.findObject(allow), 8000)).click()
            compose.waitUntil(5000) { app.checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) == android.content.pm.PackageManager.PERMISSION_GRANTED }
        }
        val mic = requireNotNull(f.device.wait(Until.findObject(By.desc("Hold to record a voice message")), 6000)).visibleCenter
        val down = SystemClock.uptimeMillis()
        fun pointer(action: Int, y: Float) {
            val event = android.view.MotionEvent.obtain(down, SystemClock.uptimeMillis(), action, mic.x.toFloat(), y, 0)
            try { check(inst.uiAutomation.injectInputEvent(event, true)) } finally { event.recycle() }
        }
        val holdMillis = InstrumentationRegistry.getArguments().getString("voiceHoldMillis")?.toLongOrNull()?.coerceIn(1700L,12_000L) ?: 4500L
        pointer(android.view.MotionEvent.ACTION_DOWN, mic.y.toFloat())
        var released = false
        try {
            SystemClock.sleep(1000)
            check(f.device.takeScreenshot(File(f.output, "01-${stageName}-live.png")))
            val y = if (locked) mic.y - 90 * app.resources.displayMetrics.density else mic.y.toFloat()
            if (locked) { pointer(android.view.MotionEvent.ACTION_MOVE, y); SystemClock.sleep(200) }
            SystemClock.sleep(holdMillis - 1000)
            pointer(android.view.MotionEvent.ACTION_UP, y)
            released = true
        } finally { if (!released) runCatching { pointer(android.view.MotionEvent.ACTION_CANCEL, mic.y.toFloat()) } }
        if (locked) {
            compose.onNodeWithContentDescription("Finish recording").performClick()
            compose.waitUntil(6000) { compose.onAllNodesWithContentDescription("Send voice message").fetchSemanticsNodes().isNotEmpty() }
            check(chat.messages(peer).none { it.outgoing && it.id !in existing && it.attachments.any { a -> a.kind == AttachmentKind.VOICE } })
            val draft = hasAnyAncestor(hasTestTag("voice-composer-active"))
            compose.onNode(hasContentDescription("Play voice message") and draft).performClick()
            compose.waitUntil(4000) { compose.onAllNodes(hasContentDescription("Pause") and draft).fetchSemanticsNodes().isNotEmpty() }
            compose.onNode(hasContentDescription("Pause") and draft).performClick()
            capture(f, "02-locked-inline-review")
            compose.onNodeWithContentDescription("Send voice message").performClick()
        }
        compose.waitUntil(35_000) { chat.messages(peer).any { row -> row.outgoing && row.id !in existing &&
            row.attachments.any { it.kind == AttachmentKind.VOICE } && row.state in setOf("accepted","delivered","read") } }
        val row = chat.messages(peer).single { it.outgoing && it.id !in existing && it.attachments.any { a -> a.kind == AttachmentKind.VOICE } }
        val voice = row.attachments.single()
        check((voice.durationMillis ?: 0L) in 500L..20_000L)
        val clear = runBlocking { AttachmentRepository(app, requireNotNull(chat.profile).id).openLocal(voice) }
        val hash = try {
            clear.copyTo(File(app.filesDir, "regular-media-$runID-${stageName}.m4a"), overwrite = false)
            java.security.MessageDigest.getInstance("SHA-256").digest(clear.readBytes()).joinToString("") { "%02x".format(it) }
        } finally { clear.delete() }
        stateFile.writeText(state.put("peer",peer).put(idField, row.id).put("${stageName}_sha256", hash)
            .put("${stageName}_duration_ms", voice.durationMillis).put("${stageName}_state", row.state).toString())
        capture(f, "03-${stageName}-sent")
    }
}
