package co.fallsoft.vipi

import android.content.Context
import android.net.Uri
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import androidx.browser.customtabs.CustomTabsIntent
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.workos.android.helpers.PublicClient
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.File
import java.security.KeyStore
import java.util.UUID
import java.util.concurrent.TimeUnit
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Atomic, authenticated local records. The wrapping key never leaves Android Keystore. */
internal class PrivateRecords(context: Context) {
    private val directory = File(context.noBackupFilesDir, "private-records").apply { mkdirs() }
    private val alias = "co.fallsoft.vipi.private.v1"
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setKeySize(256).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        }.generateKey()
    }
    private fun file(name: String): AtomicFile {
        require(name.matches(Regex("[a-z0-9-]{1,80}")))
        return AtomicFile(File(directory, name))
    }
    @Synchronized fun write(name: String, value: JSONObject) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()); updateAAD(name.toByteArray()) }
        val bytes = byteArrayOf(1) + cipher.iv + cipher.doFinal(value.toString().toByteArray(Charsets.UTF_8))
        val target = file(name)
        val stream = target.startWrite()
        try { stream.write(bytes); target.finishWrite(stream) }
        catch (error: Exception) { target.failWrite(stream); throw error }
    }
    @Synchronized fun read(name: String): JSONObject? {
        val target = file(name)
        if (!target.baseFile.exists()) return null
        val bytes = target.readFully()
        require(bytes.size in 30..65_536 && bytes[0] == 1.toByte())
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply {
            init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes.copyOfRange(1, 13)))
            updateAAD(name.toByteArray())
        }
        return JSONObject(cipher.doFinal(bytes.copyOfRange(13, bytes.size)).toString(Charsets.UTF_8))
    }
    @Synchronized fun remove(name: String) { file(name).delete() }
}

class Authentication(context: Context) {
    class SignInRequired : Exception("Sign-in required")
    private val records = PrivateRecords(context)
    private val callback = "co.fallsoft.vipi://auth/callback"
    private val client get() = PublicClient.create(BuildConfig.WORKOS_CLIENT_ID)
    private val refreshLock = Mutex()
    private var generation = UUID.randomUUID()
    private val refreshHTTP = OkHttpClient.Builder().followRedirects(false).followSslRedirects(false)
        .retryOnConnectionFailure(false).callTimeout(20, TimeUnit.SECONDS).build()
    var userID by mutableStateOf(runCatching { records.read("session")?.getString("userID") }.getOrNull())
        private set
    var busy by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
        private set

    fun signIn(context: Context) {
        if (busy) return
        error = null
        if (!BuildConfig.WORKOS_CLIENT_ID.startsWith("client_")) { error = "Sign-in isn’t available yet. Please try again shortly."; return }
        try {
            val start = client.getAuthorizationUrlWithPkce(callback)
            records.write("pending-sign-in", JSONObject().put("state", start.state).put("verifier", start.codeVerifier).put("createdAt", System.currentTimeMillis()))
            // WorkOS Android 0.4.0's public helper omits the connection selector.
            // AuthKit needs provider=authkit even for an application with no SSO.
            val url = Uri.parse(start.url).buildUpon().appendQueryParameter("provider", "authkit").build()
            CustomTabsIntent.Builder().setShowTitle(true).build().launchUrl(context, url)
        } catch (_: Exception) { records.remove("pending-sign-in"); error = "We couldn’t open secure sign-in. Please try again." }
    }
    suspend fun complete(uri: Uri) {
        if (uri.scheme != "co.fallsoft.vipi" || uri.host != "auth" || uri.path != "/callback" || uri.port != -1 || uri.userInfo != null || uri.fragment != null || busy) return
        busy = true; error = null
        try {
            val pending = records.read("pending-sign-in") ?: return
            // Consume before any suspension; a second callback cannot exchange the same verifier.
            records.remove("pending-sign-in")
            require(System.currentTimeMillis() - pending.getLong("createdAt") in 0 until 600_000)
            require(uri.getQueryParameters("state").singleOrNull() == pending.getString("state"))
            val code = requireNotNull(uri.getQueryParameters("code").singleOrNull()?.takeIf { it.isNotBlank() })
            val result = client.authenticateWithCode(code, pending.getString("verifier"))
            records.write("session", JSONObject().put("userID", result.user.id).put("accessToken", result.accessToken).put("refreshToken", result.refreshToken))
            generation = UUID.randomUUID()
            userID = result.user.id
        } catch (error: CancellationException) { throw error }
        catch (_: Exception) { error = "We couldn’t verify this sign-in. Please start again." }
        finally { busy = false }
    }
    suspend fun accessToken(expectedUser: String, rejected: String? = null): String = withContext(Dispatchers.Main.immediate) {
        refreshLock.withLock {
            val current = records.read("session") ?: throw SignInRequired()
            if (current.getString("userID") != expectedUser || userID != expectedUser) throw SignInRequired()
            val token = current.getString("accessToken")
            if (rejected == null || token != rejected) return@withLock token
            val started = generation
            // The pinned Android SDK has no public-client refresh helper. Use
            // WorkOS's public refresh endpoint without any client secret.
            val body = JSONObject().put("client_id", BuildConfig.WORKOS_CLIENT_ID).put("grant_type", "refresh_token")
                .put("refresh_token", current.getString("refreshToken")).toString().toRequestBody("application/json".toMediaType())
            val result = withContext(Dispatchers.IO) {
                refreshHTTP.newCall(Request.Builder().url("https://api.workos.com/user_management/authenticate").post(body).build()).execute().use { response ->
                    if (response.code in setOf(400, 401, 403)) throw SignInRequired()
                    if (!response.isSuccessful) throw java.io.IOException("Sign-in service unavailable")
                    val source = requireNotNull(response.body).source()
                    source.request(65_537); require(source.buffer.size <= 65_536)
                    JSONObject(source.readUtf8())
                }
            }
            if (generation != started || userID != expectedUser || result.getJSONObject("user").getString("id") != expectedUser) throw SignInRequired()
            val next = JSONObject().put("userID", expectedUser).put("accessToken", result.getString("access_token")).put("refreshToken", result.getString("refresh_token"))
            records.write("session", next)
            next.getString("accessToken")
        }
    }
    fun signOutLocally() { generation = UUID.randomUUID(); records.remove("session"); records.remove("pending-sign-in"); userID = null }
}
