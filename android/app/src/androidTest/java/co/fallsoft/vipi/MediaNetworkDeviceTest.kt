package co.fallsoft.vipi

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.media.MediaMetadataRetriever
import android.media.MediaExtractor
import android.media.MediaCodec
import android.media.MediaFormat
import android.net.Uri
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.security.MessageDigest
import java.util.UUID

/** Explicit synthetic signed-authentication loopback lane. Normal backend,
 * production binary transfer/journal/Signal code; no WorkOS or real accounts. */
@RunWith(AndroidJUnit4::class)
class MediaNetworkDeviceTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private fun file(name: String) = File(context.filesDir, name)
    private fun config(): JSONObject {
        org.junit.Assume.assumeTrue("Explicit isolated media fixture required", InstrumentationRegistry.getArguments().getString("vipiIsolatedMedia") == "true")
        return JSONObject(file("media-network-config.json").readText()).also {
            val endpoint = java.net.URI(it.getString("endpoint"))
            require(endpoint.scheme == "http" && endpoint.host == "127.0.0.1" && endpoint.port > 0)
            for (name in listOf("android", "peer")) require(it.getJSONObject(name).getString("subject").startsWith("user_localmedia_"))
        }
    }
    private fun hash(file: File): String = file.inputStream().use { input ->
        val digest = MessageDigest.getInstance("SHA-256"); val buffer = ByteArray(65536)
        while (true) { val count = input.read(buffer); if (count < 0) break; digest.update(buffer, 0, count) }
        digest.digest().joinToString("") { "%02x".format(it) }
    }
    private fun decodeFirstFrameOrPCM(file: File, kind: AttachmentKind): Int {
        val extractor = MediaExtractor(); var decoder: MediaCodec? = null
        try {
            extractor.setDataSource(file.path)
            val prefix = if (kind == AttachmentKind.VIDEO) "video/" else "audio/"
            val track = (0 until extractor.trackCount).first { extractor.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith(prefix) == true }
            val format = extractor.getTrackFormat(track); extractor.selectTrack(track)
            val codec = MediaCodec.createDecoderByType(requireNotNull(format.getString(MediaFormat.KEY_MIME))); decoder = codec
            codec.configure(format, null, null, 0); codec.start()
            val info = MediaCodec.BufferInfo(); var ended = false; val deadline = System.nanoTime() + 5_000_000_000L
            while (System.nanoTime() < deadline) {
                if (!ended) {
                    val index = codec.dequeueInputBuffer(10_000)
                    if (index >= 0) {
                        val size = extractor.readSampleData(requireNotNull(codec.getInputBuffer(index)), 0)
                        if (size < 0) { codec.queueInputBuffer(index, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM); ended = true }
                        else { codec.queueInputBuffer(index, 0, size, extractor.sampleTime, 0); extractor.advance() }
                    }
                }
                val index = codec.dequeueOutputBuffer(info, 10_000)
                if (index >= 0) {
                    val count = info.size; codec.releaseOutputBuffer(index, false)
                    if (count > 0) return count
                    if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) break
                }
            }
            error("Native decoder produced no ${if (kind == AttachmentKind.VIDEO) "frame" else "PCM"} data")
        } finally { decoder?.let { runCatching { it.stop() }; it.release() }; extractor.release() }
    }
    @Test fun sendPhotoVideoAndVoiceToOfflineRecipient() = runBlocking { send(false) }
    @Test fun sendPhotoVideoAndVoiceToExistingAppleRecipient() = runBlocking { send(true) }
    private suspend fun send(existingApple: Boolean) {
        val config = config(); val endpoint = config.getString("endpoint")
        val accounts = mutableMapOf<String, UUID>()
        for (name in if (existingApple) listOf("android") else listOf("android", "peer")) {
            val identity = config.getJSONObject(name)
            val api = SignedLoopbackPairTransport(endpoint, identity.getString("access_token"))
            val profile = api.request("PUT", "/v1/me", JSONObject().put("username", identity.getString("username")).put("display_name", "Synthetic media $name"))
            val account = UUID.fromString(profile.getString("id")); accounts[name] = account
            MessageVault(context, account).use { vault ->
                val core = MessagingCore(vault)
                api.request("POST", "/v1/devices", JSONObject().put("device_id", core.device.id).put("secret", core.device.secret))
                check(api.request("PUT", "/v1/media/capability", JSONObject().put("version", 1), core.device).getInt("version") == 1)
                val published = api.request("PUT", "/v1/keys", core.keys.publication(System.currentTimeMillis()), core.device)
                core.keys.published(published.getInt("revision"))
            }
        }
        if (existingApple) {
            val sender = config.getJSONObject("android")
            val api = SignedLoopbackPairTransport(endpoint, sender.getString("access_token"))
            MessageVault(context, accounts.getValue("android")).use { vault ->
                val peer = api.request("GET", "/v1/people/${config.getJSONObject("peer").getString("username")}", device = MessagingCore(vault).device)
                accounts["peer"] = UUID.fromString(peer.getString("id"))
            }
        }
        val alice = accounts.getValue("android"); val bob = accounts.getValue("peer")
        val identity = config.getJSONObject("android"); val token = identity.getString("access_token")
        val api = SignedLoopbackPairTransport(endpoint, token); val bytes = CiphertextTransport(endpoint) { token }
        val repository = AttachmentRepository(context, alice)
        val photo = file("media-native-photo.jpg")
        val image = Bitmap.createBitmap(96, 72, Bitmap.Config.ARGB_8888); image.eraseColor(0xffd77566.toInt())
        photo.outputStream().use { assertTrue(image.compress(Bitmap.CompressFormat.JPEG, 90, it)) }; image.recycle()
        val inputs = listOf(AttachmentKind.PHOTO to photo, AttachmentKind.VIDEO to file("media-native-video.mp4"), AttachmentKind.VOICE to file("media-native-voice.m4a"))
        val sent = JSONArray()
        MessageVault(context, alice).use { vault ->
            val core = MessagingCore(vault); val request = UUID.randomUUID()
            val claim = api.request("POST", "/v1/people/$bob/keys", JSONObject().put("request_id", request), core.device)
            core.keys.establish(bob, request, claim)
            for ((kind, input) in inputs) {
                val manifest = repository.prepare(Uri.fromFile(input), kind)
                val id = UUID.randomUUID(); val now = System.currentTimeMillis(); val fallback = when (kind) {
                    AttachmentKind.PHOTO -> "Photo"; AttachmentKind.VIDEO -> "Video"; else -> "Voice message"
                }
                core.journal.saveDraft(id, bob, fallback, now, now, attachments = listOf(manifest))
                repository.ensureUploaded(manifest, api, bytes, core.device)
                repository.ensureUploaded(manifest, api, bytes, core.device) // lost-ready-response retry, no new key/blob
                val routed = core.queue(id, bob, fallback, now, now, listOf(manifest))
                assertEquals("accepted", api.request("POST", "/v1/messages", routed.sendJSON(), core.device).getString("state"))
                val retry = core.queue(id, bob, fallback, now, now, requireNotNull(core.journal.outgoing(id)).attachments)
                assertArrayEquals(routed.envelope.ciphertext, retry.envelope.ciphertext)
                assertEquals("accepted", api.request("POST", "/v1/messages", retry.sendJSON(), core.device).getString("state"))
                sent.put(JSONObject().put("id", id).put("kind", kind.name.lowercase(java.util.Locale.ROOT)).put("original_sha256", hash(input)))
            }
            // A mistaken text file is rejected before it becomes a draft or upload.
            val mistaken = file("not-a-photo.jpg"); mistaken.writeText("synthetic text, not a JPEG")
            assertTrue(runCatching { repository.prepare(Uri.fromFile(mistaken), AttachmentKind.PHOTO) }.isFailure); mistaken.delete()
            val cancelled = repository.prepare(Uri.fromFile(photo), AttachmentKind.PHOTO)
            repository.ensureUploaded(cancelled, api, bytes, core.device)
            repository.cancelUnsent(cancelled, api, core.device)
            assertTrue(runCatching { repository.ensureUploaded(cancelled, api, bytes, core.device) }.isFailure)
        }
        file("media-native-state.json").writeText(JSONObject().put("run", config.getString("run")).put("sender", alice).put("recipient", bob).put("messages", sent).toString())
        file("media-native-send-receipt.json").writeText(JSONObject().put("run", config.getString("run")).put("process_id", android.os.Process.myPid()).put("types", JSONArray(listOf("photo", "video", "voice")))
            .put("accepted", 3).put("exact_retry", true).put("mistaken_file_rejected", true).put("cancel_before_send", true)
            .put("recipient_active_socket", false).put("recipient_platform", if (existingApple) "Apple pending receive" else "Android")
            .put("proof", "synthetic signed auth, local PostgreSQL, actual Android crypto and HTTP; recipient proof is a separate stage").toString())
    }
    @Test fun queueAllMediaInRealSessionAndLoseOneAdmissionResult() = runBlocking {
        val config = config(); val endpoint = config.getString("endpoint")
        val accounts = mutableMapOf<String, UUID>()
        for (name in listOf("android", "peer")) {
            val identity = config.getJSONObject(name)
            val api = SignedLoopbackPairTransport(endpoint, identity.getString("access_token"))
            val profile = api.request("PUT", "/v1/me", JSONObject().put("username", identity.getString("username")).put("display_name", "Synthetic outbox $name"))
            val account = UUID.fromString(profile.getString("id")); accounts[name] = account
            MessageVault(context, account).use { vault ->
                val core = MessagingCore(vault)
                api.request("POST", "/v1/devices", JSONObject().put("device_id", core.device.id).put("secret", core.device.secret))
                check(api.request("PUT", "/v1/media/capability", JSONObject().put("version", 1), core.device).getInt("version") == 1)
                core.keys.published(api.request("PUT", "/v1/keys", core.keys.publication(System.currentTimeMillis()), core.device).getInt("revision"))
            }
        }
        val alice = accounts.getValue("android"); val bob = accounts.getValue("peer")
        val identity = config.getJSONObject("android"); val token = identity.getString("access_token")
        val api = SignedLoopbackPairTransport(endpoint, token); val bytes = CiphertextTransport(endpoint) { token }
        val repository = AttachmentRepository(context, alice)
        val photo = file("media-native-photo.jpg")
        val bitmap = Bitmap.createBitmap(96, 72, Bitmap.Config.ARGB_8888); bitmap.eraseColor(0xffd77566.toInt())
        photo.outputStream().use { assertTrue(bitmap.compress(Bitmap.CompressFormat.JPEG, 90, it)) }; bitmap.recycle()
        val inputs = listOf(AttachmentKind.PHOTO to photo, AttachmentKind.VIDEO to file("media-native-video.mp4"), AttachmentKind.VOICE to file("media-native-voice.m4a"))
        val messages = JSONArray()
        ChatSession(context, api, identity.getString("subject"), bytes).use { chat ->
            chat.start(); assertTrue(chat.ready)
            for ((kind, input) in inputs) {
                val manifest = repository.prepare(Uri.fromFile(input), kind)
                val id = chat.sendAttachments("${kind.name.lowercase(java.util.Locale.ROOT)} attachment", bob, listOf(manifest))
                messages.put(JSONObject().put("id", id).put("kind", kind.name.lowercase(java.util.Locale.ROOT)).put("original_sha256", hash(input)))
            }
            chat.synchronize()
            MessageVault(context, alice).use { vault ->
                val core = MessagingCore(vault)
                assertEquals(3, core.journal.pending(System.currentTimeMillis()).size)
                var actuallyAccepted = 0
                for (index in 0 until messages.length()) {
                    val expected = messages.getJSONObject(index); val id = UUID.fromString(expected.getString("id"))
                    val saved = requireNotNull(core.journal.outgoing(id)); assertEquals("queued", saved.state)
                    expected.put("ciphertext_sha256", MessageDigest.getInstance("SHA-256").digest(saved.envelope.ciphertext).joinToString("") { "%02x".format(it) })
                    if (runCatching { api.request("GET", "/v1/messages/$id", device = core.device).getString("state") }.getOrNull() == "accepted") actuallyAccepted++
                }
                assertEquals(1, actuallyAccepted) // fixture returns503 only AFTER a real commit
            }
        }
        file("media-native-state.json").writeText(JSONObject().put("run", config.getString("run")).put("sender", alice).put("recipient", bob).put("messages", messages).toString())
        file("media-native-outbox-first-receipt.json").writeText(JSONObject().put("run", config.getString("run")).put("process_id", android.os.Process.myPid())
            .put("queued_native_ciphertexts", 3).put("server_committed_before_injected_503", 1).put("local_acceptances_before_restart", 0).toString())
    }
    @Test fun reopenRealSessionOutboxAfterLostAdmissionResult() = runBlocking {
        val config = config(); val state = JSONObject(file("media-native-state.json").readText())
        assertEquals(config.getString("run"), state.getString("run"))
        val identity = config.getJSONObject("android"); val endpoint = config.getString("endpoint"); val token = identity.getString("access_token")
        val api = SignedLoopbackPairTransport(endpoint, token); val bytes = CiphertextTransport(endpoint) { token }
        val account = UUID.fromString(state.getString("sender"))
        ChatSession(context, api, identity.getString("subject"), bytes).use { chat ->
            chat.start(); assertTrue(chat.ready)
            MessageVault(context, account).use { vault ->
                val core = MessagingCore(vault); val expected = state.getJSONArray("messages")
                assertTrue(core.journal.pendingDrafts(System.currentTimeMillis()).isEmpty())
                for (index in 0 until expected.length()) {
                    val item = expected.getJSONObject(index); val id = UUID.fromString(item.getString("id")); val saved = requireNotNull(core.journal.outgoing(id))
                    assertEquals("accepted", saved.state)
                    assertEquals(item.getString("ciphertext_sha256"), MessageDigest.getInstance("SHA-256").digest(saved.envelope.ciphertext).joinToString("") { "%02x".format(it) })
                    assertEquals("accepted", api.request("GET", "/v1/messages/$id", device = core.device).getString("state"))
                }
            }
        }
        file("media-native-outbox-reopened-receipt.json").writeText(JSONObject().put("run", config.getString("run")).put("process_id", android.os.Process.myPid())
            .put("accepted", 3).put("same_ids_and_Signal_ciphertexts_after_process_restart", true).put("ordinary_ChatSession_outbox", true).toString())
    }
    @Test fun receiveApplePhotoAndAuthenticateOriginal() = runBlocking {
        val config = config(); val state = JSONObject(file("media-native-state.json").readText())
        val expected = JSONObject(file("media-apple-reply-state.json").readText())
        assertEquals(config.getString("run"), expected.getString("run"))
        val account = UUID.fromString(state.getString("sender")); val token = config.getJSONObject("android").getString("access_token")
        val endpoint = config.getString("endpoint"); val api = SignedLoopbackPairTransport(endpoint, token)
        val bytes = CiphertextTransport(endpoint) { token }; val repository = AttachmentRepository(context, account)
        MessageVault(context, account).use { vault ->
            val core = MessagingCore(vault)
            val messages = api.request("GET", "/v1/messages/pending", device = core.device).getJSONArray("messages")
            assertEquals(1, messages.length())
            val routed = RoutedMessage.received(messages.getJSONObject(0), account)
            assertEquals(expected.getString("id"), routed.envelope.id.toString())
            val manifest = core.receive(routed, System.currentTimeMillis()).attachments.single()
            assertEquals(AttachmentKind.PHOTO, manifest.kind)
            assertEquals("delivered", api.request("POST", "/v1/messages/${routed.envelope.id}/receipt", device = core.device).getString("state"))
            val original = repository.open(manifest, false, bytes, core.device)
            assertEquals(expected.getString("original_sha256"), hash(original))
            val decoded = BitmapFactory.decodeFile(original.path); assertNotNull(decoded); decoded.recycle()
            assertTrue(repository.open(manifest, true, bytes, core.device).length() > 0)
        }
        file("media-native-apple-reply-receipt.json").writeText(JSONObject().put("run", config.getString("run"))
            .put("apple_photo_decrypted_and_decoded", true).put("process_id", android.os.Process.myPid()).toString())
    }
    @Test fun receiveAfterSenderProcessEndsAndAuthenticateAllThreeOriginals() = runBlocking {
        val config = config(); val state = JSONObject(file("media-native-state.json").readText())
        assertEquals(config.getString("run"), state.getString("run"))
        val account = UUID.fromString(state.getString("recipient")); val token = config.getJSONObject("peer").getString("access_token")
        val endpoint = config.getString("endpoint"); val api = SignedLoopbackPairTransport(endpoint, token)
        val bytes = CiphertextTransport(endpoint) { token }; val repository = AttachmentRepository(context, account)
        val expected = state.getJSONArray("messages")
        MessageVault(context, account).use { vault ->
            val core = MessagingCore(vault)
            val pending = api.request("GET", "/v1/messages/pending", device = core.device).getJSONArray("messages")
            assertEquals(3, pending.length())
            for (index in 0 until pending.length()) {
                val routed = RoutedMessage.received(pending.getJSONObject(index), account)
                val received = core.receive(routed, System.currentTimeMillis()); val manifest = received.attachments.single()
                val match = (0 until expected.length()).map { expected.getJSONObject(it) }.single { it.getString("id") == routed.envelope.id.toString() }
                assertEquals(match.getString("kind"), manifest.kind.name.lowercase(java.util.Locale.ROOT))
                // Delivery ACK clears the Signal envelope on the server; media remains authorized.
                assertEquals("delivered", api.request("POST", "/v1/messages/${routed.envelope.id}/receipt", device = core.device).getString("state"))
                val original = repository.open(manifest, false, bytes, core.device)
                assertEquals(match.getString("original_sha256"), hash(original))
                if (manifest.thumbnail != null) assertTrue(repository.open(manifest, true, bytes, core.device).length() > 0)
                if (manifest.kind == AttachmentKind.PHOTO) {
                    val bitmap = BitmapFactory.decodeFile(original.path); assertNotNull(bitmap); assertEquals(96, bitmap.width); bitmap.recycle()
                } else {
                    val reader = MediaMetadataRetriever()
                    try { reader.setDataSource(original.path); assertTrue(reader.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)!!.toLong() > 0) }
                    finally { reader.release() }
                    assertTrue(decodeFirstFrameOrPCM(original, manifest.kind) > 0)
                }
            }
            assertEquals(0, api.request("GET", "/v1/messages/pending", device = core.device).getJSONArray("messages").length())
        }
        file("media-native-receive-receipt.json").writeText(JSONObject().put("run", config.getString("run")).put("process_id", android.os.Process.myPid()).put("decrypted_originals", 3)
            .put("native_photo_decode", true).put("native_video_frame_decode", true).put("native_audio_pcm_decode", true).put("after_delivery_ack", true).put("separate_instrumentation_process", true)
            .put("proof", "Android sender and distinct Android recipient; Apple proof and picker/record/playback UX remain separate").toString())
    }
}
