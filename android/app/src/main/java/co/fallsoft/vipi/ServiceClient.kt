package co.fallsoft.vipi

import android.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.security.SecureRandom
import java.util.UUID
import java.util.concurrent.TimeUnit

internal data class DeviceCredential(val id: UUID, val secret: String) {
    companion object {
        fun registered(vault: MessageVault): DeviceCredential? = vault.transaction {
            vault.get("local", "service-device")?.let {
                val item = JSONObject(it.toString(Charsets.UTF_8))
                val device = DeviceCredential(UUID.fromString(item.getString("id")), item.getString("secret"))
                device.takeIf { vault.get("local", "registered-device")?.toString(Charsets.UTF_8) == device.id.toString() }
            }
        }
        fun load(vault: MessageVault): DeviceCredential = vault.transaction {
            vault.get("local", "service-device")?.let {
                val item = JSONObject(it.toString(Charsets.UTF_8))
                return@transaction DeviceCredential(UUID.fromString(item.getString("id")), item.getString("secret"))
            }
            val random = ByteArray(32).also { SecureRandom().nextBytes(it) }
            val value = DeviceCredential(UUID.randomUUID(), Base64.encodeToString(random, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING))
            vault.put("local", "service-device", JSONObject().put("id", value.id).put("secret", value.secret).toString().toByteArray())
            value
        }
    }
}

internal class ServiceFailure(val status: Int, val code: String) : IOException(code)

/** HTTPS only in production, no redirects, response cache or plaintext logs.
 * The caller's immutable account binding prevents cross-account retry. */
internal object GroupInboxProtocol {
    private val message = Regex("/v1/messages/[0-9a-fA-F-]{36}")
    private val receipt = Regex("/v1/messages/[0-9a-fA-F-]{36}/receipt")
    fun supports(method: String, path: String) = method == "GET" && (path == "/v1/messages/pending" || message.matches(path)) ||
        method == "POST" && receipt.matches(path)
}
internal interface ChatTransport {
    suspend fun groupInboxRequest(method: String, path: String, body: JSONObject?, device: DeviceCredential, query: Map<String, String>): JSONObject =
        request(method, path, body, device, query)
    suspend fun request(method: String, path: String, body: JSONObject? = null, device: DeviceCredential? = null, query: Map<String, String> = emptyMap()): JSONObject
}
internal class ServiceClient(private val authentication: Authentication, val userID: String,
                             endpoint: String = "https://api.mambovipi.app") : ChatTransport {
    val media = CiphertextTransport(endpoint) { rejected -> authentication.accessToken(userID, rejected) }
    private val base = endpoint.toHttpUrl()
    private val http = OkHttpClient.Builder().followRedirects(false).followSslRedirects(false)
        .retryOnConnectionFailure(false).callTimeout(25, TimeUnit.SECONDS).build()
    init {
        require(base.encodedPath == "/" && base.query == null && base.fragment == null && base.username.isEmpty() && base.password.isEmpty())
        require(base.isHttps || (BuildConfig.DEBUG && base.scheme == "http" && base.host == "127.0.0.1"))
    }
    override suspend fun request(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>) =
        exchange(method, path, body, device, query, groupProtocol = false)

    override suspend fun groupInboxRequest(method: String, path: String, body: JSONObject?, device: DeviceCredential, query: Map<String, String>): JSONObject {
        require(GroupInboxProtocol.supports(method, path))
        return exchange(method, path, body, device, query, groupProtocol = true)
    }

    private suspend fun exchange(method: String, path: String, body: JSONObject?, device: DeviceCredential?, query: Map<String, String>, groupProtocol: Boolean): JSONObject {
        require(path.startsWith("/v1/") && !path.contains("..") && !path.contains('?') && !path.contains('#'))
        var token = authentication.accessToken(userID)
        for (attempt in 0..1) {
            val result = withContext(Dispatchers.IO) {
                val content = body?.toString()?.toRequestBody("application/json".toMediaType())
                    ?: if (method in setOf("POST", "PUT")) ByteArray(0).toRequestBody(null) else null
                val url = base.newBuilder().encodedPath(path).apply { query.forEach { (key, value) -> addQueryParameter(key, value) } }.build()
                val builder = Request.Builder().url(url).method(method, content)
                    .header("Authorization", "Bearer $token").header("Accept", "application/json")
                if (groupProtocol) builder.header("X-Vipi-Group-Protocol", "1")
                device?.let { builder.header("X-Vipi-Device-ID", it.id.toString()).header("X-Vipi-Device-Secret", it.secret) }
                http.newCall(builder.build()).execute().use { response ->
                    val source = requireNotNull(response.body).source()
                    source.request(12_000_001); if (source.buffer.size > 12_000_000) throw IOException("Response too large")
                    response.code to if (response.code == 204) JSONObject() else JSONObject(source.readUtf8())
                }
            }
            if (result.first in 200..299) return result.second
            val error = result.second.optString("error", "service_unavailable")
            if (attempt == 0 && result.first == 401 && error == "sign_in_required") token = authentication.accessToken(userID, token)
            else throw ServiceFailure(result.first, error)
        }
        throw Authentication.SignInRequired()
    }
}
