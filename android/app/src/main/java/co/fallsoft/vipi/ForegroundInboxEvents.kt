package co.fallsoft.vipi

import java.util.concurrent.TimeUnit
import kotlin.random.Random
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.Channel
import okhttp3.*
import okhttp3.HttpUrl.Companion.toHttpUrl
import okio.ByteString
import org.json.JSONObject

/** Foreground wakeups only. Message contents still use the authenticated durable inbox. */
internal class ForegroundInboxEvents(
    private val scope: CoroutineScope,
    private val accessToken: suspend (rejected: String?) -> String,
    private val device: () -> DeviceCredential?,
    private val synchronize: suspend () -> Unit,
    endpoint: String = "https://api.mambovipi.app",
    private val sockets: WebSocket.Factory = http,
    private val retryPause: suspend (Long) -> Unit = { delay(it) },
    private val onDeviceRevoked: () -> Unit = {},
    private val onTyping: (java.util.UUID, Boolean) -> Unit = { _, _ -> },
    private val onReceipts: (java.util.UUID) -> Unit = {},
    private val onConnected: () -> Unit = {},
) : AutoCloseable {
    private val base =
        endpoint.toHttpUrl().also {
            require(
                it.encodedPath == "/" &&
                    it.query == null &&
                    it.fragment == null &&
                    it.username.isEmpty() &&
                    it.password.isEmpty()
            )
            require(
                it.isHttps || (BuildConfig.DEBUG && it.scheme == "http" && it.host == "127.0.0.1")
            )
        }
    private var job: Job? = null

    private data class End(val code: Int, val openedForMs: Long)

    fun start() {
        check(android.os.Looper.myLooper() == android.os.Looper.getMainLooper())
        if (job?.isActive == true) return
        job = scope.launch {
            coroutineScope {
                val signals = Channel<Unit>(Channel.CONFLATED)
                val receiver = launch {
                    for (signal in signals) {
                        for (attempt in 0..2) {
                            try {
                                synchronize()
                                break
                            } catch (error: CancellationException) {
                                throw error
                            } catch (_: Exception) {
                                // A transient inbox failure must not discard its only wakeup.
                                // The ordinary inbox path owns the user-visible error state.
                                if (attempt < 2) delay(1000L shl attempt)
                            }
                        }
                    }
                }
                var rejected: String? = null
                var failures = 0
                try {
                    while (isActive) {
                        val currentDevice = device() ?: break
                        val token =
                            try {
                                accessToken(rejected)
                            } catch (_: Authentication.SignInRequired) {
                                break
                            } catch (error: CancellationException) {
                                throw error
                            } catch (_: Exception) {
                                failures = (failures + 1).coerceAtMost(6)
                                retryPause(backoff(failures))
                                continue
                            }
                        rejected = null
                        val request =
                            Request.Builder()
                                .url(base.newBuilder().encodedPath("/v1/events").build())
                                .header("Authorization", "Bearer $token")
                                .header("X-Vipi-Device-ID", currentDevice.id.toString())
                                .header("X-Vipi-Device-Secret", currentDevice.secret)
                                .header("X-Vipi-Chat-Events", "1")
                                .build()
                        val ended = connection(request, signals)
                        if (ended.code in setOf(403, 4403)) {
                            onDeviceRevoked()
                            break
                        }
                        if (ended.code in setOf(1003, 1008)) break
                        if (ended.code in setOf(401, 4401)) rejected = token
                        failures =
                            if (ended.openedForMs >= 30_000) 0 else (failures + 1).coerceAtMost(6)
                        retryPause(backoff(failures))
                    }
                } finally {
                    signals.close()
                    receiver.cancelAndJoin()
                }
            }
        }
    }

    private suspend fun connection(request: Request, signals: Channel<Unit>): End {
        val done = CompletableDeferred<End>()
        var openedAt = 0L
        fun finish(code: Int) {
            done.complete(
                End(code, if (openedAt == 0L) 0 else (System.nanoTime() - openedAt) / 1_000_000)
            )
        }
        val socket =
            sockets.newWebSocket(
                request,
                object : WebSocketListener() {
                    override fun onOpen(webSocket: WebSocket, response: Response) {
                        openedAt = System.nanoTime()
                        if (done.isActive) {
                            signals.trySend(Unit)
                            scope.launch {
                                if (done.isActive && job?.isActive == true) onConnected()
                            }
                        }
                    }

                    override fun onMessage(webSocket: WebSocket, text: String) {
                        if (!done.isActive) return
                        try {
                            require(text.length <= 512)
                            val value = JSONObject(text)
                            when (value.getString("event")) {
                                "inbox_changed" -> {
                                    require(value.length() == 1)
                                    signals.trySend(Unit)
                                }
                                "typing",
                                "receipts_changed" -> {
                                    val raw = value.getString("peer")
                                    val peer = java.util.UUID.fromString(raw)
                                    require(peer.toString() == raw)
                                    if (value.getString("event") == "typing") {
                                        require(
                                            value.length() == 3 && value.get("active") is Boolean
                                        )
                                        val active = value.getBoolean("active")
                                        scope.launch {
                                            if (done.isActive && job?.isActive == true)
                                                onTyping(peer, active)
                                        }
                                    } else {
                                        require(value.length() == 2)
                                        scope.launch {
                                            if (done.isActive && job?.isActive == true)
                                                onReceipts(peer)
                                        }
                                    }
                                }
                                else -> throw IllegalArgumentException()
                            }
                        } catch (_: Exception) {
                            webSocket.close(1008, "Invalid event")
                            finish(1008)
                        }
                    }

                    override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                        webSocket.close(1003, "Text events required")
                        finish(1003)
                    }

                    override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                        webSocket.close(code, null)
                        finish(code)
                    }

                    override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                        finish(code)
                    }

                    override fun onFailure(
                        webSocket: WebSocket,
                        t: Throwable,
                        response: Response?,
                    ) {
                        finish(response?.code ?: 0)
                    }
                },
            )
        try {
            return done.await()
        } finally {
            done.cancel()
            socket.cancel()
        }
    }

    fun stop() {
        job?.cancel()
        job = null
    }

    override fun close() = stop()

    companion object {
        private val http =
            OkHttpClient.Builder()
                .followRedirects(false)
                .followSslRedirects(false)
                .retryOnConnectionFailure(false)
                .connectTimeout(15, TimeUnit.SECONDS)
                .callTimeout(20, TimeUnit.SECONDS)
                .readTimeout(0, TimeUnit.SECONDS)
                .writeTimeout(10, TimeUnit.SECONDS)
                .pingInterval(25, TimeUnit.SECONDS)
                .build()

        private fun backoff(failures: Int) =
            (1000L shl failures.coerceIn(0, 6)).coerceAtMost(60_000L) + Random.nextLong(0, 1000)
    }
}
