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
import org.json.JSONObject
import java.io.File
import java.security.KeyStore
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
        require(name.matches(Regex("[a-z-]{1,40}")))
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
    private val records = PrivateRecords(context)
    private val callback = "co.fallsoft.vipi://auth/callback"
    private val client get() = PublicClient.create(BuildConfig.WORKOS_CLIENT_ID)
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
            userID = result.user.id
        } catch (error: CancellationException) { throw error }
        catch (_: Exception) { error = "We couldn’t verify this sign-in. Please start again." }
        finally { busy = false }
    }
    fun signOutLocally() { records.remove("session"); records.remove("pending-sign-in"); userID = null }
}
