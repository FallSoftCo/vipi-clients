package co.fallsoft.vipi

import android.content.Context
import android.net.Uri
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import android.system.Os
import android.system.OsConstants
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
import java.io.FileDescriptor
import java.io.IOException
import java.nio.file.Files
import java.nio.file.LinkOption.NOFOLLOW_LINKS
import java.security.KeyStore
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.TimeUnit
import java.util.concurrent.ConcurrentHashMap
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

internal enum class PrivateRecordCommitState { NOT_COMMITTED, COMMITTED_DURABILITY_UNCERTAIN, UNKNOWN }
internal class PrivateRecordWriteFailure(val commitState: PrivateRecordCommitState, cause: Exception) :
    IOException("Private record write could not be confirmed: $commitState", cause)
internal enum class PrivateRecordWriteCheckpoint { BEFORE_FILE_SYNC, BEFORE_FINISH, AFTER_FINISH, BEFORE_DIRECTORY_SYNC }

/** Authenticated local records. Success requires explicit sync and exact ciphertext readback.
 * The wrapping key never leaves Android Keystore. */
internal class PrivateRecords(context: Context) {
    private val directory = File(context.noBackupFilesDir, "private-records").apply { mkdirs() }
    private val alias = "co.fallsoft.vipi.private.v1"
    private val recordLock = locks.getOrPut(directory.canonicalPath) { Any() }
    companion object { private val locks = ConcurrentHashMap<String, Any>() }
    internal var qualificationWriteCheckpoint: ((PrivateRecordWriteCheckpoint, FileDescriptor?) -> Unit)? = null
        set(value) { check(BuildConfig.DEBUG); field = value }
    private fun currentBytes(target: AtomicFile): ByteArray? {
        if (!target.baseFile.exists()) return null
        require(target.baseFile.length() <= 65_536)
        return target.baseFile.readBytes()
    }
    private fun syncDirectory() {
        val descriptor = Os.open(directory.path, OsConstants.O_RDONLY, 0)
        try {
            qualificationWriteCheckpoint?.invoke(PrivateRecordWriteCheckpoint.BEFORE_DIRECTORY_SYNC, descriptor)
            Os.fsync(descriptor)
        } catch (failure: Exception) {
            runCatching { Os.close(descriptor) }.exceptionOrNull()?.let(failure::addSuppressed)
            throw failure
        }
        Os.close(descriptor)
    }
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
    fun write(name: String, value: JSONObject): Unit = synchronized(recordLock) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()); updateAAD(name.toByteArray()) }
        val bytes = byteArrayOf(1) + cipher.iv + cipher.doFinal(value.toString().toByteArray(Charsets.UTF_8))
        require(bytes.size in 30..65_536)
        val target = file(name)
        val previous = currentBytes(target)
        var stream: java.io.FileOutputStream? = null
        var finishStarted = false
        try {
            stream = target.startWrite()
            stream.write(bytes)
            qualificationWriteCheckpoint?.invoke(PrivateRecordWriteCheckpoint.BEFORE_FILE_SYNC, stream.fd)
            // AtomicFile.finishWrite logs sync/rename failures rather than throwing.
            // Our explicit sync must succeed before it may attempt activation.
            stream.fd.sync()
            qualificationWriteCheckpoint?.invoke(PrivateRecordWriteCheckpoint.BEFORE_FINISH, stream.fd)
            finishStarted = true
            target.finishWrite(stream)
            qualificationWriteCheckpoint?.invoke(PrivateRecordWriteCheckpoint.AFTER_FINISH, null)
            syncDirectory()
            check(currentBytes(target)?.contentEquals(bytes) == true) { "Private record activation readback failed" }
        } catch (failure: Exception) {
            if (!finishStarted && stream != null) runCatching { target.failWrite(stream) }
            val observation = runCatching { currentBytes(target) }
            val current = observation.getOrNull()
            val state = when {
                observation.isFailure -> PrivateRecordCommitState.UNKNOWN
                current?.contentEquals(bytes) == true -> PrivateRecordCommitState.COMMITTED_DURABILITY_UNCERTAIN
                (current == null && previous == null) || (current != null && previous != null && current.contentEquals(previous)) -> PrivateRecordCommitState.NOT_COMMITTED
                else -> PrivateRecordCommitState.UNKNOWN
            }
            throw PrivateRecordWriteFailure(state, failure)
        }
    }
    fun read(name: String): JSONObject? = synchronized(recordLock) {
        val target = file(name)
        if (!target.baseFile.exists()) return@synchronized null
        val bytes = target.readFully()
        require(bytes.size in 30..65_536 && bytes[0] == 1.toByte())
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply {
            init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes.copyOfRange(1, 13)))
            updateAAD(name.toByteArray())
        }
        JSONObject(cipher.doFinal(bytes.copyOfRange(13, bytes.size)).toString(Charsets.UTF_8))
    }
    fun remove(name: String): Unit = synchronized(recordLock) {
        val base = file(name).baseFile
        // A failed sidecar deletion must leave the authoritative record available
        // to a newly opened account-deletion coordinator so it can retry.
        val paths = listOf(File(base.path + ".new"), File(base.path + ".bak"), base).map { it.toPath() }
        for (path in paths) {
            Files.deleteIfExists(path)
            check(!Files.exists(path, NOFOLLOW_LINKS)) { "Private record could not be removed" }
        }
        syncDirectory()
        check(paths.none { Files.exists(it, NOFOLLOW_LINKS) }) { "Private record removal could not be confirmed" }
    }
}

/** EMAIL opens hosted AuthKit, which also offers the environment's enabled providers. */
enum class SignInProvider(internal val workosProvider: String) {
    EMAIL("authkit"), GOOGLE("GoogleOAuth"), APPLE("AppleOAuth")
}

/** Only reviewed authorities may receive a stored verifier or refresh token. */
internal enum class IdentityAuthority(val recordID: String, val clientID: String) {
    VIPI_PRODUCTION("vipi-production", "client_01M6VYVQQ9GWVNS95DFGABXEW9"),
    VIPI_STAGING("vipi-staging", "client_01M5S2CDSQ8F7FEX26G3CY9VS1"),
    FALLSOFT_VIPI_PRODUCTION("fallsoft-vipi-production", "client_01M7N9Y2DGSJJVT1ZV6TY7DTZ4");

    fun tag(record: JSONObject): JSONObject = record.put("formatVersion", 2).put("authority", recordID).put("clientID", clientID)
    companion object {
        // Older encrypted records contain no authority metadata. A future build
        // must not reinterpret those records as its newly configured authority.
        val legacy: IdentityAuthority get() = if (BuildConfig.DEBUG && BuildConfig.WORKOS_CLIENT_ID == VIPI_STAGING.clientID) VIPI_STAGING else VIPI_PRODUCTION
        fun configured(clientID: String): IdentityAuthority = entries.singleOrNull { it.clientID == clientID }
            ?: throw IOException("Unknown sign-in authority")
        fun forSignIn(saved: IdentityAuthority?, hasExpectedUser: Boolean, configuredClientID: String): IdentityAuthority =
            saved ?: if (hasExpectedUser) legacy else configured(configuredClientID)
        fun read(record: JSONObject, legacyAuthority: IdentityAuthority = legacy): IdentityAuthority {
            if (!record.has("formatVersion") && !record.has("authority") && !record.has("clientID")) return legacyAuthority
            require(record.get("formatVersion") == 2) { "Unsupported sign-in record" }
            val authority = entries.singleOrNull { it.recordID == record.getString("authority") }
                ?: throw IOException("Unknown sign-in authority")
            require(record.getString("clientID") == authority.clientID) { "Sign-in authority mismatch" }
            return authority
        }
    }
}

internal data class IdentityLinkIntent(val accountID: String, val requestID: String, val oldUserID: String,
                                      val deviceID: String, val deviceSecret: String, val expectedSharedUser: String? = null) {
    fun json() = JSONObject().put("accountID", accountID).put("requestID", requestID).put("oldUserID", oldUserID)
        .put("deviceID", deviceID).put("deviceSecret", deviceSecret).put("expectedSharedUser", expectedSharedUser)
    companion object {
        fun parse(value: JSONObject): IdentityLinkIntent {
            fun uuid(key: String) = value.getString(key).also { require(UUID.fromString(it).toString() == it) }
            return IdentityLinkIntent(uuid("accountID"), uuid("requestID"), value.getString("oldUserID").also { require(it.startsWith("user_") && it.length <= 128) },
                uuid("deviceID"), value.getString("deviceSecret").also { require(it.matches(Regex("[A-Za-z0-9_-]{43}"))) },
                value.optString("expectedSharedUser", "").takeIf { it.isNotEmpty() }?.also { require(it.startsWith("user_") && it.length <= 128) })
        }
    }
}

internal data class IdentityLinkJournal(val intent: IdentityLinkIntent, val candidate: JSONObject, val verifiedProfile: JSONObject? = null) {
    fun json() = JSONObject().put("linkFormatVersion", 1).put("intent", intent.json()).put("candidate", candidate).put("verifiedProfile", verifiedProfile)
    companion object {
        fun parse(value: JSONObject): IdentityLinkJournal {
            require(value.get("linkFormatVersion") == 1)
            val intent = IdentityLinkIntent.parse(value.getJSONObject("intent"))
            val candidate = value.getJSONObject("candidate")
            require(IdentityAuthority.read(candidate) == IdentityAuthority.FALLSOFT_VIPI_PRODUCTION)
            require(candidate.getString("userID").startsWith("user_") && candidate.getString("userID").length <= 128)
            require(candidate.getString("accessToken").length in 1..32_768 && candidate.getString("refreshToken").length in 1..16_384)
            require(intent.expectedSharedUser == null || intent.expectedSharedUser == candidate.getString("userID"))
            val profile = value.optJSONObject("verifiedProfile")
            if (profile != null) require(profile.getString("id") == intent.accountID)
            return IdentityLinkJournal(intent, candidate, profile)
        }
    }
}

internal fun signInAuthorizationURL(start: String, provider: SignInProvider, reauthenticate: Boolean): Uri {
    val original = Uri.parse(start)
    val builder = original.buildUpon().clearQuery()
    for (name in original.queryParameterNames) {
        if (name !in setOf("provider", "max_age", "screen_hint")) {
            for (value in original.getQueryParameters(name)) builder.appendQueryParameter(name, value)
        }
    }
    // Fresh same-account authentication must go through AuthKit's factor selection.
    // A direct upstream OAuth session is not proof of recent authentication.
    builder.appendQueryParameter("provider", if (reauthenticate) "authkit" else provider.workosProvider)
    if (reauthenticate) builder.appendQueryParameter("max_age", "0").appendQueryParameter("screen_hint", "sign-in")
    return builder.build()
}

class Authentication(context: Context) {
    private val appContext = context.applicationContext
    private val application = context.applicationContext
    class SignInRequired : Exception("Sign-in required")
    private val records = PrivateRecords(context)
    private val callback = "co.fallsoft.vipi://auth/callback"
    private val refreshLock = Mutex()
    private var generation = UUID.randomUUID()
    private class ExchangeFailure(val status: Int) : java.io.IOException("Sign-in service unavailable")
    private val publicHTTP = OkHttpClient.Builder().followRedirects(false).followSslRedirects(false)
        .retryOnConnectionFailure(false).callTimeout(20, TimeUnit.SECONDS).build()
    var userID by mutableStateOf(runCatching { records.read("session")?.let { IdentityAuthority.read(it); it.getString("userID") } }.getOrNull())
        private set
    var busy by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
        private set
    var signInRevision by mutableStateOf(0)
        private set

    internal val canLinkFallsoft: Boolean get() {
        // Observe successful same-user reauthentication/activation as well.
        signInRevision
        return runCatching { records.read("session")?.let { IdentityAuthority.read(it) == IdentityAuthority.VIPI_PRODUCTION && it.getString("userID") == userID } == true }.getOrDefault(false)
    }
    internal var qualificationSignInLaunch: ((Uri) -> Unit)? = null
        set(value) { check(BuildConfig.DEBUG); field = value }
    private fun launchSignIn(context: Context, authority: IdentityAuthority, expectedUser: String?, provider: SignInProvider,
                             link: IdentityLinkIntent? = null, sourceLink: IdentityLinkIntent? = null) {
        val start = PublicClient.create(authority.clientID).getAuthorizationUrlWithPkce(callback)
        val pending = authority.tag(JSONObject().put("state", start.state).put("verifier", start.codeVerifier)
            .put("createdAt", System.currentTimeMillis()).put("expectedUser", expectedUser))
        link?.let { pending.put("link", it.json()) }
        sourceLink?.let { pending.put("sourceLink", it.json()) }
        records.write("pending-sign-in", pending)
        val url = signInAuthorizationURL(start.url, provider, reauthenticate = expectedUser != null || link != null)
        qualificationSignInLaunch?.let { check(BuildConfig.DEBUG); it(url); return }
        val tab = CustomTabsIntent.Builder().setShowTitle(true).build()
        if (context !is android.app.Activity) tab.intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
        tab.launchUrl(context, url)
    }
    fun signIn(context: Context, expectedUser: String? = null, provider: SignInProvider = SignInProvider.EMAIL) {
        if (busy) return
        error = null
        try {
            val saved = records.read("session")
            val authority = IdentityAuthority.forSignIn(saved?.let { IdentityAuthority.read(it) }, expectedUser != null, BuildConfig.WORKOS_CLIENT_ID)
            if (saved != null) require(saved.getString("userID") == userID)
            val boundUser = expectedUser ?: userID
            launchSignIn(context, authority, boundUser, provider)
        } catch (_: Exception) { records.remove("pending-sign-in"); error = appContext.getString(R.string.ui_79290727c58b) }
    }
    /** Explicit migration only; ordinary sign-in never links or replaces accounts. */
    internal fun beginFallsoftLink(context: Context, accountID: UUID, device: DeviceCredential) {
        if (busy) return
        error = null
        try {
            val current = requireNotNull(records.read("session"))
            require(IdentityAuthority.read(current) == IdentityAuthority.VIPI_PRODUCTION && current.getString("userID") == userID)
            val previous = records.read("pending-identity-link")?.let(IdentityLinkJournal::parse)
            val intent = previous?.intent?.copy(expectedSharedUser = previous.candidate.getString("userID"))
                ?: IdentityLinkIntent(accountID.toString(), UUID.randomUUID().toString(), current.getString("userID"), device.id.toString(), device.secret)
            require(intent.accountID == accountID.toString() && intent.deviceID == device.id.toString() && intent.deviceSecret == device.secret && intent.oldUserID == userID)
            // Refresh cannot satisfy the backend's recent legacy auth_time.
            // The explicit action obtains both fresh proofs in order.
            launchSignIn(context, IdentityAuthority.VIPI_PRODUCTION, intent.oldUserID, SignInProvider.EMAIL, sourceLink = intent)
        } catch (_: Exception) { records.remove("pending-sign-in"); error = appContext.getString(R.string.ui_79290727c58b) }
    }
    suspend fun complete(uri: Uri) {
        val intent = consumeSignIn(uri) ?: return
        try {
            val current = requireNotNull(records.read("session"))
            require(IdentityAuthority.read(current) == IdentityAuthority.VIPI_PRODUCTION && current.getString("userID") == intent.oldUserID && userID == intent.oldUserID)
            launchSignIn(appContext, IdentityAuthority.FALLSOFT_VIPI_PRODUCTION, null, SignInProvider.EMAIL, link = intent)
        } catch (_: Exception) { records.remove("pending-sign-in"); error = appContext.getString(R.string.ui_79290727c58b) }
    }
    private suspend fun consumeSignIn(uri: Uri): IdentityLinkIntent? {
        if (uri.scheme != "co.fallsoft.vipi" || uri.host != "auth" || uri.path != "/callback" || uri.port != -1 || uri.userInfo != null || uri.fragment != null || busy) return null
        busy = true; error = null
        var stage = "pending-state"
        try {
            val pending = records.read("pending-sign-in") ?: return null
            // Consume before any suspension; a second callback cannot exchange the same verifier.
            records.remove("pending-sign-in")
            val authority = IdentityAuthority.read(pending)
            val sourceLink = pending.optJSONObject("sourceLink")?.let(IdentityLinkIntent::parse)
            require(sourceLink == null || (!pending.has("link") && authority == IdentityAuthority.VIPI_PRODUCTION && pending.optString("expectedUser") == sourceLink.oldUserID))
            stage = "callback-age"
            val ageMs = System.currentTimeMillis() - pending.getLong("createdAt")
            if (ageMs >= 600_000) {
                error = appContext.getString(R.string.sign_in_attempt_expired)
                return null
            }
            require(ageMs >= 0)
            stage = "callback-state"
            require(uri.getQueryParameters("state").singleOrNull() == pending.getString("state"))
            stage = "callback-code"
            val code = requireNotNull(uri.getQueryParameters("code").singleOrNull()?.takeIf { it.isNotBlank() })
            val started = generation
            stage = "public-pkce-exchange"
            // WorkOS Android 0.4.0's PublicClient serializes client_secret="".
            // Public PKCE must omit that field; the provider rejects it with 422.
            // Exchange once, using the original browser flow's saved verifier.
            val result = exchange(JSONObject().put("client_id", authority.clientID)
                .put("grant_type", "authorization_code").put("code", code)
                .put("code_verifier", pending.getString("verifier")))
            val resultUser = result.getJSONObject("user").getString("id")
            stage = "account-binding"
            if (started != generation) throw SignInRequired()
            pending.optJSONObject("link")?.let { link ->
                require(authority == IdentityAuthority.FALLSOFT_VIPI_PRODUCTION)
                val intent = IdentityLinkIntent.parse(link)
                require(intent.expectedSharedUser == null || intent.expectedSharedUser == resultUser)
                val current = requireNotNull(records.read("session"))
                require(IdentityAuthority.read(current) == IdentityAuthority.VIPI_PRODUCTION && current.getString("userID") == intent.oldUserID && userID == intent.oldUserID)
                val journal = IdentityLinkJournal(intent, sessionRecord(result, resultUser, authority))
                records.write("pending-identity-link", journal.json())
                finishFallsoftLink(journal, started)
                return null
            }
            if (pending.has("expectedUser") && pending.getString("expectedUser") != resultUser) {
                error = appContext.getString(R.string.ui_94455044f130); return null
            }
            val existing = records.read("session")
            if (existing != null && (IdentityAuthority.read(existing) != authority || existing.getString("userID") != resultUser)) {
                error = appContext.getString(R.string.ui_94455044f130); return null
            }
            stage = "private-session-save"
            if (userID != resultUser) PrivateSpeechCache.erase(application)
            records.write("session", sessionRecord(result, resultUser, authority))
            generation = UUID.randomUUID()
            userID = resultUser
            signInRevision++
            if (sourceLink != null) return sourceLink
        } catch (error: CancellationException) { throw error }
        catch (failure: Exception) {
            // Debug qualification gets a bounded category, never exception text,
            // callback URLs, authorization codes, tokens or provider payloads.
            if (BuildConfig.DEBUG) android.util.Log.w("VipiAuth", "Sign-in failed at $stage (${failure.javaClass.simpleName}, HTTP ${(failure as? ExchangeFailure)?.status ?: 0})")
            error = appContext.getString(R.string.ui_1afc1c2532c4)
        }
        finally { busy = false }
        return null
    }
    internal suspend fun resumeFallsoftLink() {
        if (busy) return
        busy = true; error = null
        try { finishFallsoftLink(IdentityLinkJournal.parse(requireNotNull(records.read("pending-identity-link"))), generation) }
        catch (failure: CancellationException) { throw failure }
        catch (_: Exception) { error = appContext.getString(R.string.ui_1afc1c2532c4) }
        finally { busy = false }
    }
    private suspend fun finishFallsoftLink(journal: IdentityLinkJournal, started: UUID) {
        val current = requireNotNull(records.read("session"))
        val nextUser = journal.candidate.getString("userID")
        // Recovery after an uncertain local activation never replays OAuth.
        if (journal.verifiedProfile != null && IdentityAuthority.read(current) == IdentityAuthority.FALLSOFT_VIPI_PRODUCTION && current.getString("userID") == nextUser) {
            require(records.read(profileKey(nextUser))?.getString("id") == journal.intent.accountID)
            if (started != generation) throw SignInRequired()
            if (userID != nextUser) { generation = UUID.randomUUID(); userID = nextUser; signInRevision++ }
            removeObsoleteLegacyProfile(journal)
            records.remove("pending-identity-link")
            return
        }
        require(IdentityAuthority.read(current) == IdentityAuthority.VIPI_PRODUCTION && current.getString("userID") == journal.intent.oldUserID && userID == journal.intent.oldUserID)
        val device = DeviceCredential(UUID.fromString(journal.intent.deviceID), journal.intent.deviceSecret)
        var oldToken = accessToken(journal.intent.oldUserID)
        val body = JSONObject().put("request_id", journal.intent.requestID).put("expected_account_id", journal.intent.accountID)
            .put("fallsoft_access_token", journal.candidate.getString("accessToken"))
        val receipt = try { linkRequest("POST", "/v1/identity-links/fallsoft", body, oldToken, device) }
        catch (failure: ServiceFailure) {
            if (failure.status != 401 || failure.code != "sign_in_required") throw failure
            oldToken = accessToken(journal.intent.oldUserID, oldToken)
            linkRequest("POST", "/v1/identity-links/fallsoft", body, oldToken, device)
        }
        require(receipt.getString("request_id") == journal.intent.requestID && receipt.getString("account_id") == journal.intent.accountID
            && receipt.getString("authority_id") == IdentityAuthority.FALLSOFT_VIPI_PRODUCTION.recordID && receipt.getString("authentication_subject") == nextUser
            && receipt.getInt("binding_revision") == 1)
        val profile = linkRequest("GET", "/v1/me", null, journal.candidate.getString("accessToken"), device)
        require(profile.getString("id") == journal.intent.accountID)
        if (started != generation || userID != journal.intent.oldUserID) throw SignInRequired()
        // Journal the successful UUID readback before any session activation.
        records.write("pending-identity-link", journal.copy(verifiedProfile = profile).json())
        records.write(profileKey(nextUser), profile)
        records.write("session", journal.candidate)
        val saved = requireNotNull(records.read("session"))
        require(IdentityAuthority.read(saved) == IdentityAuthority.FALLSOFT_VIPI_PRODUCTION && saved.getString("userID") == nextUser
            && saved.getString("accessToken") == journal.candidate.getString("accessToken") && saved.getString("refreshToken") == journal.candidate.getString("refreshToken"))
        generation = UUID.randomUUID(); userID = nextUser; signInRevision++
        removeObsoleteLegacyProfile(journal)
        records.remove("pending-identity-link")
    }
    private fun removeObsoleteLegacyProfile(journal: IdentityLinkJournal) {
        // Stable UUID vault/storage is unchanged; only the obsolete subject
        // cache can be discarded after durable shared activation.
        if (journal.intent.oldUserID != journal.candidate.getString("userID")) records.remove(profileKey(journal.intent.oldUserID))
    }
    private fun profileKey(subject: String) = "profile-" + MessageDigest.getInstance("SHA-256").digest(subject.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
    internal var qualificationLinkRequest: (suspend (String, String, JSONObject?, String, DeviceCredential) -> JSONObject)? = null
        set(value) { check(BuildConfig.DEBUG); field = value }
    private suspend fun linkRequest(method: String, path: String, fields: JSONObject?, token: String, device: DeviceCredential): JSONObject = withContext(Dispatchers.IO) {
        qualificationLinkRequest?.let { check(BuildConfig.DEBUG); return@withContext it(method, path, fields, token, device) }
        require(path in setOf("/v1/identity-links/fallsoft", "/v1/me"))
        val body = fields?.toString()?.toRequestBody("application/json".toMediaType())
        publicHTTP.newCall(Request.Builder().url("https://api.mambovipi.app$path").method(method, body)
            .header("Authorization", "Bearer $token").header("X-Vipi-Device-ID", device.id.toString()).header("X-Vipi-Device-Secret", device.secret).build()).execute().use { response ->
            val source = requireNotNull(response.body).source(); source.request(65_537); require(source.buffer.size <= 65_536)
            val result = JSONObject(source.readUtf8())
            if (!response.isSuccessful) throw ServiceFailure(response.code, result.optString("error", "service_unavailable"))
            result
        }
    }
    suspend fun accessToken(expectedUser: String, rejected: String? = null): String = withContext(Dispatchers.Main.immediate) {
        refreshLock.withLock {
            val current = records.read("session") ?: throw SignInRequired()
            val authority = IdentityAuthority.read(current)
            if (current.getString("userID") != expectedUser || userID != expectedUser) throw SignInRequired()
            val token = current.getString("accessToken")
            if (rejected == null || token != rejected) return@withLock token
            val started = generation
            // The pinned Android SDK has no public-client refresh helper. Use
            // WorkOS's public refresh endpoint without any client secret.
            val result = exchange(JSONObject().put("client_id", authority.clientID).put("grant_type", "refresh_token")
                .put("refresh_token", current.getString("refreshToken")))
            if (generation != started || userID != expectedUser || result.getJSONObject("user").getString("id") != expectedUser) throw SignInRequired()
            val next = sessionRecord(result, expectedUser, authority)
            records.write("session", next)
            next.getString("accessToken")
        }
    }
    internal var qualificationExchange: (suspend (JSONObject) -> JSONObject)? = null
        set(value) { check(BuildConfig.DEBUG); field = value }

    private suspend fun exchange(fields: JSONObject): JSONObject = withContext(Dispatchers.IO) {
        qualificationExchange?.let { check(BuildConfig.DEBUG); return@withContext it(fields) }
        val body = fields.toString().toRequestBody("application/json".toMediaType())
        publicHTTP.newCall(Request.Builder().url("https://api.workos.com/user_management/authenticate").post(body).build()).execute().use { response ->
            if (response.code in setOf(400, 401, 403)) throw SignInRequired()
            if (!response.isSuccessful) throw ExchangeFailure(response.code)
            val source = requireNotNull(response.body).source()
            source.request(65_537); require(source.buffer.size <= 65_536)
            JSONObject(source.readUtf8())
        }
    }
    private fun sessionRecord(result: JSONObject, subject: String, authority: IdentityAuthority): JSONObject {
        require(subject.startsWith("user_") && subject.length <= 128)
        val access = result.getString("access_token").also { require(it.isNotBlank() && it.length <= 32_768) }
        val refresh = result.getString("refresh_token").also { require(it.isNotBlank() && it.length <= 16_384) }
        return authority.tag(JSONObject().put("userID", subject).put("accessToken", access).put("refreshToken", refresh))
    }
    internal fun isCurrentAccount(expected: String): Boolean = runCatching {
        records.read("session")?.let { IdentityAuthority.read(it); it.getString("userID") == expected } == true
    }.getOrDefault(false)

    fun signOutLocally() { PushDelivery.clearPosted(application); generation = UUID.randomUUID(); PrivateSpeechCache.erase(application); records.remove("session"); records.remove("pending-sign-in"); records.remove("pending-identity-link"); userID = null; signInRevision++ }
}
