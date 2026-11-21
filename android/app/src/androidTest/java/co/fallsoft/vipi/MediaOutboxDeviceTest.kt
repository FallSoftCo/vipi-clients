package co.fallsoft.vipi

import android.content.ContextWrapper
import android.graphics.Bitmap
import android.net.Uri
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.io.IOException
import java.security.KeyStore
import java.util.UUID

/** Real vault/Signal/preparation with a controlled JSON transport: this proves
 * lifecycle ordering/retry, not HTTP upload or server admission. */
class MediaOutboxDeviceTest {
    @Test fun failedUploadAndLostAdmissionResumeTheSameDurableAttachment() = runBlocking { withContext(Dispatchers.Main) {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(base.cacheDir, "media-outbox-${UUID.randomUUID()}").apply { mkdirs() }
        val context = object : ContextWrapper(base) {
            override fun getFilesDir() = File(root, "files").apply { mkdirs() }
            override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() }
            override fun getCacheDir() = File(root, "cache").apply { mkdirs() }
        }
        val alice = UUID.randomUUID(); val bob = UUID.randomUUID()
        val subject = "user_localmedia_outbox_${UUID.randomUUID()}"
        val vaults = mutableListOf<MessageVault>()
        var chat: ChatSession? = null
        try {
            val aliceVault = MessageVault(context, alice).also { vaults += it }
            val bobVault = MessageVault(context, bob).also { vaults += it }
            val sender = MessagingCore(aliceVault); val receiver = MessagingCore(bobVault)
            val now = System.currentTimeMillis(); val publication = receiver.keys.publication(now, 2)
            receiver.keys.published(1)
            val claim = UUID.randomUUID()
            sender.keys.establish(bob, claim, JSONObject().put("request_id", claim).put("user_id", bob)
                .put("device_id", receiver.device.id).put("signal_device_id", 1)
                .put("registration_id", publication.getInt("registration_id")).put("identity_key", publication.getString("identity_key"))
                .put("signed", publication.getJSONObject("signed")).put("one_time", publication.getJSONArray("one_time").getJSONObject(0)))
            val image = File(root, "photo.jpg")
            val bitmap = Bitmap.createBitmap(48, 32, Bitmap.Config.ARGB_8888)
            bitmap.eraseColor(0xffd77566.toInt())
            image.outputStream().use { assertTrue(bitmap.compress(Bitmap.CompressFormat.JPEG, 90, it)) }; bitmap.recycle()
            val repository = AttachmentRepository(context, alice)
            val manifest = repository.prepare(Uri.fromFile(image), AttachmentKind.PHOTO)
            var uploadsReady = false; var loseAdmissionResult = true; var reservations = 0
            val sent = mutableListOf<JSONObject>()
            val unknownPeer = UUID.randomUUID()
            var capabilityOnline = false
            val api = object : ChatTransport {
                override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>): JSONObject = when {
                    path == "/v1/me" -> ChatProfile(alice, "media_outbox_qa", "Media outbox QA").json()
                    path == "/v1/devices" -> JSONObject().put("id", requireNotNull(body).getString("device_id")).put("active", true)
                    path == "/v1/keys" -> JSONObject().put("revision", 1).put("remaining", 20)
                    path == "/v1/messages/pending" -> JSONObject().put("messages", JSONArray()).put("next_cursor", JSONObject.NULL)
                    path == "/v1/media/capability" -> JSONObject().put("version", 1)
                    path == "/v1/media/capability/$bob" || path == "/v1/media/capability/$unknownPeer" -> {
                        if (!capabilityOnline) throw IOException("Synthetic offline capability")
                        JSONObject().put("version", 1).put("device_id", receiver.device.id)
                    }
                    path == "/v1/media/uploads" -> {
                        reservations++
                        if (!uploadsReady) throw ServiceFailure(503, "synthetic_upload_offline")
                        JSONObject(requireNotNull(body).toString()).put("state", "ready")
                    }
                    path == "/v1/messages" -> {
                        check(uploadsReady); sent += JSONObject(requireNotNull(body).toString())
                        if (loseAdmissionResult) { loseAdmissionResult = false; throw IOException("Synthetic lost acceptance response") }
                        JSONObject().put("state", "accepted")
                    }
                    else -> error("Unexpected controlled outbox route: $path")
                }
            }
            val bytes = CiphertextTransport("http://127.0.0.1:1") { "unused-explicit-fixture-token" }
            chat = ChatSession(context, api, subject, bytes); chat!!.start(); assertTrue(chat!!.ready)
            assertTrue(runCatching { chat!!.requirePeerMedia(unknownPeer) }.exceptionOrNull() is IOException)
            assertTrue(runCatching { chat!!.requirePeerMedia(bob) }.exceptionOrNull() is IOException)
            capabilityOnline = true
            chat!!.requirePeerMedia(bob)
            capabilityOnline = false
            chat!!.requirePeerMedia(bob)
            // A stale grant for another device may never qualify this peer offline.
            aliceVault.transaction { aliceVault.put("peer-media-device", bob.toString(), UUID.randomUUID().toString().toByteArray()) }
            assertTrue(runCatching { chat!!.requirePeerMedia(bob) }.exceptionOrNull() is IOException)
            capabilityOnline = true
            chat!!.requirePeerMedia(bob)
            assertEquals(0, reservations)
            val id = chat!!.sendAttachments("Photo", bob, listOf(manifest))
            chat!!.synchronize()
            assertTrue(sent.isEmpty()); assertNull(sender.journal.outgoing(id))
            assertEquals(listOf(manifest), sender.journal.draft(id)?.attachments)
            chat!!.close(); chat = null
            uploadsReady = true
            chat = ChatSession(context, api, subject, bytes); chat!!.start()
            assertEquals(1, sent.size); assertEquals("queued", sender.journal.outgoing(id)?.state)
            val sealed = requireNotNull(sender.journal.outgoing(id)).envelope.ciphertext.copyOf()
            chat!!.close(); chat = null
            chat = ChatSession(context, api, subject, bytes); chat!!.start()
            assertEquals(2, sent.size); assertEquals(sent[0].toString(), sent[1].toString())
            assertArrayEquals(sealed, sender.journal.outgoing(id)?.envelope?.ciphertext)
            assertEquals("accepted", sender.journal.outgoing(id)?.state)
            val routed = RoutedMessage.received(JSONObject(sent.last().toString()).put("sender_id", alice)
                .put("sender_device_id", sender.device.id), bob)
            assertEquals(listOf(manifest), receiver.receive(routed, System.currentTimeMillis()).attachments)
            val beforeText = reservations
            chat!!.send("Text still uses its existing outbox", bob); chat!!.synchronize()
            assertEquals(beforeText, reservations)
            assertEquals(2, sent.map { it.getString("id") }.distinct().size)
            assertFalse(sent.single { it.getString("id") != id.toString() }.has("attachment_ids"))
        } finally {
            chat?.close(); vaults.forEach { it.close() }; root.deleteRecursively()
            val keys = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
            for (id in listOf(alice, bob)) keys.deleteEntry("co.fallsoft.vipi.messages.$id")
        }
    } }
}
