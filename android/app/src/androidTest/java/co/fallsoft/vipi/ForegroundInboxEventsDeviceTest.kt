package co.fallsoft.vipi

import kotlinx.coroutines.*
import okhttp3.*
import okio.ByteString
import org.junit.Assert.*
import org.junit.Test
import java.util.UUID

class ForegroundInboxEventsDeviceTest {
    private class Socket(private val value: Request, val listener: WebSocketListener) : WebSocket {
        var cancelled = false
        override fun request() = value
        override fun queueSize() = 0L
        override fun send(text: String) = error("This receiver must never send application content")
        override fun send(bytes: ByteString) = error("This receiver must never send application content")
        override fun close(code: Int, reason: String?) = true
        override fun cancel() { cancelled = true }
        fun open() = listener.onOpen(this, Response.Builder().request(value).protocol(Protocol.HTTP_1_1).code(101).message("Switching Protocols").build())
    }
    @Test fun coalescesHintsRefreshesExpiredBearerAndStopsOnBackgroundOrRevokedDevice() = runBlocking {
        withContext(Dispatchers.Main) {
            val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
            val sockets = mutableListOf<Socket>()
            val refreshes = mutableListOf<String?>()
            val blocked = CompletableDeferred<Unit>(); val received = CompletableDeferred<Unit>()
            val retry = CompletableDeferred<Unit>(); val pause = CompletableDeferred<Unit>()
            var syncs = 0
            val device = DeviceCredential(UUID.randomUUID(), "isolated-qa-device-secret")
            val events = ForegroundInboxEvents(scope, { rejected ->
                refreshes.add(rejected); if (rejected == null) "isolated-qa-first-token" else "isolated-qa-refreshed-token"
            }, { device }, {
                syncs++; if (syncs == 1) { received.complete(Unit); blocked.await() }
            }, sockets = WebSocket.Factory { request, listener -> Socket(request, listener).also { sockets.add(it); it.open() } },
                retryPause = { wait -> assertTrue(wait >= 1000); pause.complete(Unit); retry.await() })
            try {
                events.start(); events.start()
                withTimeout(3000) { received.await() }
                assertEquals(1, sockets.size)
                val first = sockets.single()
                assertEquals("Bearer isolated-qa-first-token", first.request().header("Authorization"))
                assertEquals(device.id.toString(), first.request().header("X-Vipi-Device-ID"))
                repeat(100) { first.listener.onMessage(first, "{\"event\":\"inbox_changed\"}") }
                blocked.complete(Unit)
                withTimeout(3000) { while (syncs < 2) delay(10) }
                assertEquals(2, syncs)
                first.listener.onClosing(first, 4401, "Expired")
                withTimeout(3000) { pause.await() }; assertTrue(first.cancelled)
                retry.complete(Unit)
                withTimeout(3000) { while (sockets.size < 2 || syncs < 3) delay(10) }
                assertEquals(listOf(null, "isolated-qa-first-token"), refreshes)
                val second = sockets.last()
                assertEquals("Bearer isolated-qa-refreshed-token", second.request().header("Authorization"))
                second.listener.onClosing(second, 4403, "Device revoked")
                withTimeout(3000) { while (!second.cancelled) delay(10) }
                delay(50); assertEquals(2, sockets.size)
                events.stop(); events.start()
                withTimeout(3000) { while (sockets.size < 3) delay(10) }
                val third = sockets.last(); events.stop()
                withTimeout(3000) { while (!third.cancelled) delay(10) }
                val count = syncs
                third.listener.onMessage(third, "{\"event\":\"inbox_changed\"}")
                delay(50); assertEquals(count, syncs)
            } finally { events.close(); blocked.complete(Unit); retry.complete(Unit); scope.cancel() }
        }
    }
}
