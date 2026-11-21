package co.fallsoft.vipi

import android.content.ContentValues
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.provider.MediaStore
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.security.KeyStore
import java.util.UUID
import java.util.regex.Pattern

/** The platform photo picker, real conversation, native Signal and encrypted
 * journal. Only the service responses use an isolated transport fixture. */
class PhotoPickerJourneyDeviceTest {
    @get:Rule val compose = createComposeRule()

    @Test fun cancelThenSendOnePhotoFromTheSystemPicker() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        assumeTrue(context.packageName.endsWith(".sourcecontextqa") &&
            InstrumentationRegistry.getArguments().getString("disposablePicker") == "true")
        val device = UiDevice.getInstance(instrumentation)
        val alice = UUID.randomUUID()
        val bob = UUID.randomUUID()
        val photo = requireNotNull(context.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            ContentValues().apply {
                put(MediaStore.Images.Media.DISPLAY_NAME, "Vipi-cafe-$alice.jpg")
                put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
                put(MediaStore.Images.Media.IS_PENDING, 1)
            }))
        val evidence = File(context.filesDir, "photo-picker-evidence").apply { mkdirs() }
        val vaults = mutableListOf<MessageVault>()
        var session: ChatSession? = null
        val visible = mutableStateOf(true)
        val recipientSession = mutableStateOf<ChatSession?>(null)
        fun capture(name: String) {
            compose.waitForIdle()
            android.os.SystemClock.sleep(500)
            check(device.takeScreenshot(File(evidence, "$name.png")))
        }
        fun choose() {
            compose.onNodeWithContentDescription("Attach media").performClick()
            compose.onNodeWithText("Photos and videos").performClick()
            val thumb = By.res(Pattern.compile(".*:id/(icon_thumbnail|thumbnail|item_thumbnail|image_thumbnail)"))
            val tile = device.wait(Until.findObject(thumb), 12000)
            if (tile == null) {
                device.dumpWindowHierarchy(File(evidence, "picker.xml"))
                capture("picker-inspect")
                error("System picker did not expose the synthetic photo")
            }
            capture("01-system-picker")
            tile.click()
            compose.waitUntil(10000) { compose.onAllNodesWithText("Photo for Maya").fetchSemanticsNodes().isNotEmpty() }
        }
        try {
            val art = Bitmap.createBitmap(640, 400, Bitmap.Config.ARGB_8888)
            val canvas = Canvas(art)
            val brush = Paint(Paint.ANTI_ALIAS_FLAG)
            canvas.drawColor(0xfff5a688.toInt())
            brush.color = 0xff553342.toInt(); canvas.drawOval(88f, 255f, 558f, 320f, brush)
            brush.color = 0xfffbd680.toInt(); canvas.drawOval(72f, 99f, 560f, 287f, brush)
            brush.color = 0xff427d70.toInt(); canvas.drawRoundRect(178f, 121f, 298f, 221f, 29f, 29f, brush)
            brush.color = 0xfffff1cb.toInt(); canvas.drawOval(177f, 108f, 299f, 148f, brush)
            brush.color = 0xff64433d.toInt(); canvas.drawOval(191f, 117f, 285f, 139f, brush)
            brush.color = 0xffbf6459.toInt(); canvas.drawRoundRect(342f, 102f, 440f, 184f, 24f, 24f, brush)
            brush.color = 0xfffff1cb.toInt(); canvas.drawOval(341f, 91f, 441f, 121f, brush)
            brush.color = 0xff64433d.toInt(); canvas.drawOval(354f, 98f, 428f, 115f, brush)
            requireNotNull(context.contentResolver.openOutputStream(photo)).use { check(art.compress(Bitmap.CompressFormat.JPEG, 87, it)) }
            art.recycle()
            context.contentResolver.update(photo, ContentValues().apply { put(MediaStore.Images.Media.IS_PENDING, 0) }, null, null)

            val sender = MessagingCore(MessageVault(context, alice).also(vaults::add))
            val receiver = MessagingCore(MessageVault(context, bob).also(vaults::add))
            val keys = receiver.keys.publication(System.currentTimeMillis(), 2)
            receiver.keys.published(1)
            val claim = UUID.randomUUID()
            sender.keys.establish(bob, claim, JSONObject().put("request_id", claim).put("user_id", bob)
                .put("device_id", receiver.device.id).put("signal_device_id", 1).put("registration_id", keys.getInt("registration_id"))
                .put("identity_key", keys.getString("identity_key")).put("signed", keys.getJSONObject("signed"))
                .put("one_time", keys.getJSONArray("one_time").getJSONObject(0)))
            vaults.first().transaction {
                vaults.first().put("contact", bob.toString(), ChatProfile(bob,"cafe_fixture","Maya").json().toString().toByteArray())
            }
            val posts = java.util.concurrent.CopyOnWriteArrayList<JSONObject>()
            val api = object : ChatTransport {
                override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String,String>): JSONObject = when {
                    path == "/v1/me" -> ChatProfile(alice, "photo_fixture", "Alex").json()
                    path == "/v1/devices" -> JSONObject().put("id", requireNotNull(body).getString("device_id")).put("active",true)
                    path == "/v1/keys" -> JSONObject().put("revision",1).put("remaining",20)
                    path == "/v1/messages/pending" -> JSONObject().put("messages",JSONArray()).put("next_cursor",JSONObject.NULL)
                    path == "/v1/media/capability" -> JSONObject().put("version", 1)
                    path == "/v1/media/capability/$bob" -> JSONObject().put("version", 1).put("device_id", receiver.device.id)
                    path == "/v1/media/uploads" -> JSONObject(requireNotNull(body).toString()).put("state","ready")
                    path.endsWith("/receipts") -> JSONObject().put("acknowledged", requireNotNull(body).getJSONArray("seen")).put("read", JSONArray())
                    path == "/v1/messages" -> JSONObject().put("state","accepted").also { posts.add(JSONObject(requireNotNull(body).toString())) }
                    path == "/v1/blocks/$bob" -> JSONObject().put("blocked",false)
                    else -> throw ServiceFailure(404,"fixture_unused_route")
                }
            }
            val chat = ChatSession(context, api, "user_localmedia_picker_$alice", CiphertextTransport("http://127.0.0.1:1") { "unused" })
            session = chat
            runBlocking { withContext(Dispatchers.Main) { chat.start(); check(chat.ready) } }
            compose.setContent {
                if (visible.value) VipiTheme(Appearance.LIGHT) {
                    val recipient = recipientSession.value
                    androidx.compose.runtime.key(recipient) {
                        if (recipient == null) FriendConversationScreen(chat, bob, back = {})
                        else FriendConversationScreen(recipient, alice, back = {})
                    }
                }
            }
            compose.waitUntil(8000) { compose.onAllNodesWithContentDescription("Attach media").fetchSemanticsNodes().any() }
            compose.onNodeWithContentDescription("Attach media").performClick()
            compose.onNodeWithText("Take a photo").performClick()
            val shutter = requireNotNull(device.wait(Until.findObject(By.res("com.android.camera2", "shutter_button")), 12_000)) {
                device.dumpWindowHierarchy(File(evidence, "camera-before.xml")); "Dedicated virtual camera shutter unavailable"
            }
            capture("00a-system-camera")
            shutter.click()
            val done = requireNotNull(device.wait(Until.findObject(By.res(Pattern.compile("com.android.camera2:id/(btn_done|done_button)"))), 12_000)) {
                device.dumpWindowHierarchy(File(evidence, "camera-after.xml")); "Dedicated virtual camera result unavailable"
            }
            done.click()
            compose.waitUntil(12_000) { compose.onAllNodesWithText("Photo for Maya").fetchSemanticsNodes().isNotEmpty() }
            capture("00b-camera-preview")
            compose.onNodeWithText("Cancel", ignoreCase = true).performClick()
            compose.waitForIdle()
            assertTrue(posts.isEmpty())
            choose()
            capture("02-photo-preview")
            val cipherDir = File(context.noBackupFilesDir,"attachments/$alice")
            assertTrue(cipherDir.listFiles().orEmpty().isEmpty())
            assertFalse(context.cacheDir.walkTopDown().any { it.name.startsWith("photo-selection-") })
            compose.onNodeWithText("Cancel", ignoreCase = true).performClick()
            compose.waitForIdle()
            assertTrue(posts.isEmpty()); assertTrue(cipherDir.listFiles().orEmpty().isEmpty())
            choose()
            compose.onNodeWithText("Send photo").performClick()
            compose.waitUntil(15000) { posts.size == 1 && compose.onAllNodesWithContentDescription("Photo").fetchSemanticsNodes().isNotEmpty() }
            capture("03-queued-photo")
            val routed = RoutedMessage.received(JSONObject(posts.single().toString()).put("sender_id",alice).put("sender_device_id",sender.device.id),bob)
            val attachment = receiver.receive(routed,System.currentTimeMillis()).attachments.single()
            assertEquals(640,attachment.width); assertEquals(400,attachment.height)
            assertTrue(cipherDir.listFiles().orEmpty().all { it.extension == "ciphertext" })
            assertEquals(2,cipherDir.listFiles().orEmpty().size)
            assertFalse(File(context.cacheDir,"attachments/$alice").walkTopDown().any { it.isFile })
            assertFalse(File("/proc/self/fd").listFiles().orEmpty().any {
                runCatching { android.system.Os.readlink(it.path).contains("photo-selection-") }.getOrDefault(false)
            })
            val original = attachment.original
            val payload = File(cipherDir, "${original.blobId}.ciphertext").readBytes()
            val listener = java.net.ServerSocket(0, 2, java.net.InetAddress.getByName("127.0.0.1"))
            val requests = java.util.concurrent.CopyOnWriteArrayList<String>()
            val fixtureFailure = java.util.concurrent.atomic.AtomicReference<Throwable?>()
            val http = kotlin.concurrent.thread(isDaemon = true) {
                try {
                    repeat(2) { index ->
                        listener.accept().use { socket ->
                            socket.soTimeout = 5000
                            val headers = socket.getInputStream().bufferedReader()
                            requests += requireNotNull(headers.readLine())
                            val fields = generateSequence { headers.readLine() }.takeWhile(String::isNotEmpty)
                                .map { it.substringBefore(':').lowercase() to it.substringAfter(':').trim() }.toMap()
                            check(fields["authorization"] == "Bearer photo-reader-fixture")
                            check(fields["x-vipi-device-id"] == receiver.device.id.toString())
                            check(fields["x-vipi-device-secret"] == receiver.device.secret)
                            val raw = payload.clone()
                            if (index == 0) raw[raw.lastIndex] = (raw.last().toInt() xor 1).toByte()
                            socket.getOutputStream().apply {
                                write(("HTTP/1.1 200 OK\r\nContent-Length: ${raw.size}\r\n" +
                                    "X-Ciphertext-SHA256: ${original.ciphertextSHA256}\r\nConnection: close\r\n\r\n").toByteArray())
                                write(raw); flush()
                            }
                        }
                    }
                } catch (failure: Exception) { fixtureFailure.set(failure) }
            }
            try {
                val otherApi = object : ChatTransport {
                    override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?,
                                                 query: Map<String,String>): JSONObject = when {
                        path == "/v1/me" -> ChatProfile(bob,"cafe_fixture","Maya").json()
                        path == "/v1/blocks/$alice" -> JSONObject().put("blocked",false)
                        path == "/v1/messages/${routed.envelope.id}/receipt" -> JSONObject().put("state", "delivered")
                        else -> api.request(method, path, body, device, query)
                    }
                }
                vaults.last().transaction {
                    vaults.last().put("contact", alice.toString(), ChatProfile(alice, "photo_fixture", "Alex").json().toString().toByteArray())
                }
                val other = ChatSession(context, otherApi, "user_localmedia_reader_$bob",
                    CiphertextTransport("http://127.0.0.1:${listener.localPort}") { "photo-reader-fixture" })
                runBlocking { withContext(Dispatchers.Main) { other.start(); check(other.ready); recipientSession.value = other } }
                fun waitForText(label: String) {
                    compose.waitUntil(20000) { compose.onAllNodesWithText(label).fetchSemanticsNodes().isNotEmpty() }
                }
                waitForText("Open photo")
                assertTrue(requests.isEmpty())
                compose.onNodeWithText("Open photo").performClick()
                waitForText("Couldn’t open this photo.")
                assertTrue(File(context.noBackupFilesDir, "attachments/$bob").listFiles().orEmpty().isEmpty())
                capture("04-recipient-retry")
                compose.onNodeWithText("Try again").performClick()
                compose.waitUntil(20000) { compose.onAllNodesWithContentDescription("Opened photo").fetchSemanticsNodes().isNotEmpty() }
                capture("05-recipient-opened")
                compose.onNodeWithText("Close").performClick()
                compose.onNodeWithText("Open photo").performClick()
                compose.waitUntil(10000) { compose.onAllNodesWithContentDescription("Opened photo").fetchSemanticsNodes().isNotEmpty() }
                compose.onNodeWithText("Close").performClick()
                assertEquals(List(2) { "GET /v1/media/${original.blobId}/ciphertext HTTP/1.1" }, requests)
                assertFalse(File(context.cacheDir,"attachments/$bob").walkTopDown().any { it.isFile })
                assertEquals(listOf("${original.blobId}.ciphertext"), File(context.noBackupFilesDir,"attachments/$bob").list().orEmpty().toList())
                assertNull(fixtureFailure.get())
                assertEquals(1,posts.size)
            } finally {
                listener.close()
                http.join(1500)
            }
        } finally {
            compose.runOnIdle { visible.value = false }
            compose.waitForIdle()
            instrumentation.runOnMainSync { recipientSession.value?.close(); session?.close() }
            vaults.forEach { it.close() }
            context.contentResolver.delete(photo,null,null)
            // Only this invocation's test accounts and synthetic photo are owned.
            for (owner in listOf(alice,bob)) {
                File(context.noBackupFilesDir,"attachments/$owner").deleteRecursively()
                File(context.cacheDir,"attachments/$owner").deleteRecursively()
                KeyStore.getInstance("AndroidKeyStore").apply { load(null) }.deleteEntry("co.fallsoft.vipi.messages.$owner")
            }
        }
    }
}
