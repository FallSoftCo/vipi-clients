package co.fallsoft.vipi

import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.security.MessageDigest
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.suspendCancellableCoroutine
import okhttp3.Call
import okhttp3.Callback
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.Response
import okio.BufferedSink
import org.json.JSONObject

/**
 * Streaming opaque bytes only. Authentication remains bound to the caller's immutable account; keys
 * and descriptive metadata never enter this transport.
 */
internal class CiphertextTransport(
    endpoint: String,
    private val authorize: suspend (rejected: String?) -> String,
) {
    private val base = endpoint.toHttpUrl()
    private val http =
        OkHttpClient.Builder()
            .followRedirects(false)
            .followSslRedirects(false)
            .retryOnConnectionFailure(false)
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .callTimeout(120, TimeUnit.SECONDS)
            .build()

    init {
        require(
            base.encodedPath == "/" &&
                base.query == null &&
                base.fragment == null &&
                base.username.isEmpty() &&
                base.password.isEmpty()
        )
        require(
            base.isHttps || (BuildConfig.DEBUG && base.scheme == "http" && base.host == "127.0.0.1")
        )
    }

    private fun request(
        method: String,
        part: MediaPart,
        device: DeviceCredential,
        token: String,
        body: RequestBody? = null,
    ): Request =
        Request.Builder()
            .url(base.newBuilder().encodedPath("/v1/media/${part.blobId}/ciphertext").build())
            .method(method, body)
            .header("Authorization", "Bearer $token")
            .header("X-Vipi-Device-ID", device.id.toString())
            .header("X-Vipi-Device-Secret", device.secret)
            .header(
                "Accept",
                if (method == "GET") "application/octet-stream" else "application/json",
            )
            .build()

    private fun json(response: Response): JSONObject {
        val source = response.body?.source() ?: throw IOException("Empty media response")
        source.request(8193)
        if (source.buffer.size > 8192) throw IOException("Media response is too large")
        return JSONObject(source.readUtf8())
    }

    private fun checked(response: Response) {
        if (!response.isSuccessful) {
            val body = runCatching { json(response) }.getOrNull()
            throw ServiceFailure(
                response.code,
                body?.optString("error", "media_unavailable") ?: "media_unavailable",
            )
        }
    }

    private suspend fun <T> execute(request: Request, consume: (Response, () -> Unit) -> T): T =
        suspendCancellableCoroutine { continuation ->
            val call = http.newCall(request)
            continuation.invokeOnCancellation { call.cancel() }
            call.enqueue(
                object : Callback {
                    override fun onFailure(call: Call, e: IOException) {
                        if (continuation.isActive) continuation.resumeWithException(e)
                    }

                    override fun onResponse(call: Call, response: Response) {
                        try {
                            val value = response.use {
                                consume(it) {
                                    if (!continuation.isActive)
                                        throw CancellationException("Media transfer cancelled")
                                }
                            }
                            if (continuation.isActive) continuation.resume(value)
                        } catch (error: Exception) {
                            if (continuation.isActive) continuation.resumeWithException(error)
                        }
                    }
                }
            )
        }

    private suspend fun <T> authenticated(operation: suspend (String) -> T): T {
        var token = authorize(null)
        for (attempt in 0..1) {
            try {
                return operation(token)
            } catch (error: ServiceFailure) {
                if (attempt == 0 && error.status == 401 && error.code == "sign_in_required")
                    token = authorize(token)
                else throw error
            }
        }
        throw ServiceFailure(401, "sign_in_required")
    }

    suspend fun upload(part: MediaPart, source: File, device: DeviceCredential): JSONObject {
        part.validate()
        require(source.isFile && source.length() == part.ciphertextBytes) {
            "Encrypted attachment is missing or incomplete"
        }
        val body =
            object : RequestBody() {
                override fun contentType() = "application/octet-stream".toMediaType()

                override fun contentLength() = part.ciphertextBytes

                override fun writeTo(sink: BufferedSink) {
                    source.inputStream().use { input ->
                        val buffer = ByteArray(65536)
                        var count = 0L
                        while (true) {
                            val size = input.read(buffer)
                            if (size < 0) break
                            count += size
                            if (count > part.ciphertextBytes)
                                throw IOException("Encrypted attachment changed during upload")
                            sink.write(buffer, 0, size)
                        }
                        if (count != part.ciphertextBytes)
                            throw IOException("Encrypted attachment changed during upload")
                    }
                }
            }
        return authenticated { token ->
            execute(request("PUT", part, device, token, body)) { response, active ->
                active()
                checked(response)
                json(response).also {
                    require(
                        it.getString("id") == part.blobId.toString() &&
                            it.getString("state") == "ready" &&
                            it.getLong("ciphertext_bytes") == part.ciphertextBytes &&
                            it.getString("ciphertext_sha256") == part.ciphertextSHA256
                    )
                }
            }
        }
    }

    suspend fun download(part: MediaPart, destination: File, device: DeviceCredential): File {
        part.validate()
        require(destination.parentFile?.isDirectory == true)
        return authenticated { token ->
            execute(request("GET", part, device, token)) { response, active ->
                checked(response)
                require(response.header("Content-Length")?.toLongOrNull() == part.ciphertextBytes)
                require(response.header("X-Ciphertext-SHA256") == part.ciphertextSHA256)
                val temporary = File.createTempFile("download-", ".partial", destination.parentFile)
                try {
                    val digest = MessageDigest.getInstance("SHA-256")
                    var count = 0L
                    response.body!!.byteStream().use { input ->
                        FileOutputStream(temporary).use { output ->
                            val buffer = ByteArray(65536)
                            while (true) {
                                active()
                                val size = input.read(buffer)
                                if (size < 0) break
                                count += size
                                require(count <= part.ciphertextBytes) {
                                    "Attachment download is too large"
                                }
                                digest.update(buffer, 0, size)
                                output.write(buffer, 0, size)
                            }
                            require(
                                count == part.ciphertextBytes &&
                                    digest.digest().joinToString("") { "%02x".format(it) } ==
                                        part.ciphertextSHA256
                            ) {
                                "Attachment download is incomplete or corrupt"
                            }
                            output.flush()
                            output.fd.sync()
                        }
                    }
                    active()
                    MediaCryptography.publish(temporary, destination)
                    destination
                } finally {
                    temporary.delete()
                }
            }
        }
    }
}
