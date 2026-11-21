package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.Closeable
import java.io.File
import java.net.InetAddress
import java.net.ServerSocket
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** A deliberately faulty local HTTP peer qualifies transport failure behavior.
 * It is not the signed-authentication/PostgreSQL/native API proof. */
@RunWith(AndroidJUnit4::class)
class CiphertextTransferFailureDeviceTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private class Reply(private val body: ByteArray, private val part: MediaPart, private val pause: Boolean = false) : Closeable {
        private val listener = ServerSocket(0, 1, InetAddress.getByName("127.0.0.1"))
        val endpoint = "http://127.0.0.1:${listener.localPort}"
        val started = CountDownLatch(1); private val release = CountDownLatch(1)
        private val worker = Thread {
            runCatching {
                listener.soTimeout = 5000
                listener.accept().use { socket ->
                    socket.soTimeout = 5000
                    val input = socket.getInputStream().bufferedReader()
                    var lines = 0
                    while (!input.readLine().isNullOrEmpty()) { check(++lines <= 32) }
                    val output = socket.getOutputStream()
                    output.write(("HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\n" +
                        "Content-Length: ${part.ciphertextBytes}\r\nX-Ciphertext-SHA256: ${part.ciphertextSHA256}\r\nConnection: close\r\n\r\n").toByteArray())
                    output.write(if (pause) body.copyOfRange(0, 64) else body); output.flush(); started.countDown()
                    if (pause) release.await(5, TimeUnit.SECONDS)
                }
            }
        }.apply { isDaemon = true; start() }
        override fun close() { release.countDown(); listener.close(); worker.join(1000) }
    }
    @Test fun truncatedAndCorruptBodiesRejectThenExactRetryAuthenticates() = runBlocking {
        val root = File(context.noBackupFilesDir, "media-wire-${UUID.randomUUID()}").also { check(it.mkdir()) }
        try {
            val content = ByteArray(4096) { (it % 251).toByte() }; val key = MediaCryptography.freshKey(); val attachment = UUID.randomUUID()
            val (part, encrypted) = MediaCryptography.seal(content.inputStream(), root, key, attachment, "original")
            val destination = File(root, "download.ciphertext"); val device = DeviceCredential(UUID.randomUUID(), "synthetic-no-authority")
            val bytes = encrypted.readBytes()
            Reply(bytes.copyOf(bytes.size - 1), part).use { reply ->
                val transport = CiphertextTransport(reply.endpoint) { "synthetic-transfer-failure-fixture" }
                val error = runCatching { withTimeout(7000) { transport.download(part, destination, device) } }.exceptionOrNull()
                assertTrue("Must reject an incomplete HTTP body", error is java.io.IOException)
                assertFalse(destination.exists())
            }
            val corrupt = bytes.copyOf(); corrupt[corrupt.lastIndex] = (corrupt.last().toInt() xor 1).toByte()
            Reply(corrupt, part).use { reply ->
                val transport = CiphertextTransport(reply.endpoint) { "synthetic-transfer-failure-fixture" }
                val error = runCatching { withTimeout(7000) { transport.download(part, destination, device) } }.exceptionOrNull()
                assertTrue("Must reject corrupted bytes using authenticated manifest hash", error is IllegalArgumentException)
                assertFalse(destination.exists())
            }
            assertFalse(root.listFiles().orEmpty().any { it.name.endsWith(".partial") })
            Reply(bytes, part).use { reply ->
                CiphertextTransport(reply.endpoint) { "synthetic-transfer-failure-fixture" }.download(part, destination, device)
            }
            val clear = File(root, "verified.bin")
            MediaCryptography.open(destination, clear, key, attachment, part)
            assertArrayEquals(content, clear.readBytes())
            File(context.filesDir, "media-wire-failure-receipt.json").writeText(JSONObject()
                .put("proof", "faulty local HTTP fixture plus production CiphertextTransport, not API authentication proof")
                .put("truncated_body_rejected", true).put("corrupt_body_rejected", true).put("no_published_partial", true)
                .put("same_ciphertext_retry_gcm_authenticated", true).toString())
        } finally { root.deleteRecursively() }
    }
    @Test fun cancellationClosesBlockedSocketAndRemovesPrivatePartial() = runBlocking {
        val root = File(context.noBackupFilesDir, "media-wire-cancel-${UUID.randomUUID()}").also { check(it.mkdir()) }
        try {
            val (part, encrypted) = MediaCryptography.seal(ByteArray(4096) { 11 }.inputStream(), root,
                MediaCryptography.freshKey(), UUID.randomUUID(), "original")
            val destination = File(root, "must-not-publish.ciphertext")
            Reply(encrypted.readBytes(), part, pause = true).use { reply ->
                val job = launch(Dispatchers.IO) {
                    CiphertextTransport(reply.endpoint) { "synthetic-transfer-failure-fixture" }
                        .download(part, destination, DeviceCredential(UUID.randomUUID(), "synthetic-no-authority"))
                }
                assertTrue(withContext(Dispatchers.IO) { reply.started.await(2, TimeUnit.SECONDS) })
                withTimeout(1000) { job.cancelAndJoin() }
                withTimeout(1000) { while (root.listFiles().orEmpty().any { it.name.endsWith(".partial") }) delay(10) }
                assertFalse(destination.exists())
            }
        } finally { root.deleteRecursively() }
    }
}
