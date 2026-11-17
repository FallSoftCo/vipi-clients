package co.fallsoft.vipi

import android.content.Context
import android.util.Base64
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.File
import java.security.KeyStore
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.UUID
import java.util.concurrent.TimeUnit

internal data class DeletionRecord(val account: UUID, val userID: String, val secret: String, val createdAt: Long,
                                   val phase: Phase = Phase.PREPARED, val localErased: Boolean = false) {
    enum class Phase { PREPARED, REQUESTED, COMPLETED }
    fun json() = JSONObject().put("account", account).put("userID", userID).put("secret", secret).put("createdAt", createdAt)
        .put("phase", phase.name).put("localErased", localErased)
    companion object {
        fun parse(value: JSONObject) = DeletionRecord(UUID.fromString(value.getString("account")), value.getString("userID"),
            value.getString("secret"), value.getLong("createdAt"), Phase.valueOf(value.getString("phase")), value.getBoolean("localErased"))
    }
}
internal interface DeletionStore {
    fun load(): DeletionRecord?
    fun save(record: DeletionRecord)
    fun remove()
}
internal class PrivateDeletionStore(context: Context) : DeletionStore {
    private val records = PrivateRecords(context)
    override fun load() = records.read("account-deletion")?.let(DeletionRecord::parse)
    override fun save(record: DeletionRecord) = records.write("account-deletion", record.json())
    override fun remove() = records.remove("account-deletion")
}
internal interface DeletionTransport {
    suspend fun submit(record: DeletionRecord): JSONObject
    suspend fun status(record: DeletionRecord): JSONObject
}
internal class AccountDeletionService(private val authentication: Authentication) : DeletionTransport {
    private val http = OkHttpClient.Builder().followRedirects(false).followSslRedirects(false)
        .retryOnConnectionFailure(false).callTimeout(25, TimeUnit.SECONDS).build()
    override suspend fun submit(record: DeletionRecord) = ServiceClient(authentication, record.userID).request("DELETE", "/v1/me",
        JSONObject().put("account_id", record.account).put("receipt_secret", record.secret))
    override suspend fun status(record: DeletionRecord): JSONObject = withContext(Dispatchers.IO) {
        val request = Request.Builder().url("https://api.mambovipi.app/v1/account-deletions/${record.account}")
            .header("Authorization", "Deletion ${record.secret}").header("Accept", "application/json").build()
        http.newCall(request).execute().use { response ->
            val source = requireNotNull(response.body).source()
            source.request(4097); check(source.buffer.size <= 4096)
            if (response.code != 200) throw ServiceFailure(response.code, "deletion_status_unavailable")
            JSONObject(source.readUtf8())
        }
    }
}

/** A persisted capability recovers a lost response without a usable sign-in.
 * Invoke on Main; close the chat before beginning and before any local erasure. */
internal class AccountDeletion(private val store: DeletionStore, private val service: DeletionTransport,
                               private val erase: (DeletionRecord) -> Unit, private val signOut: (String) -> Unit) {
    var pending by mutableStateOf<DeletionRecord?>(null); private set
    var busy by mutableStateOf(false); private set
    var loadFailed by mutableStateOf(false); private set
    var needsSignIn by mutableStateOf(false); private set
    var notice by mutableStateOf<Int?>(null); private set
    val active get() = pending != null || loadFailed
    init {
        try { pending = store.load() }
        catch (_: Exception) { loadFailed = true; notice = R.string.deletion_receipt_open_failed }
    }
    constructor(context: Context, authentication: Authentication) : this(PrivateDeletionStore(context), AccountDeletionService(authentication),
        { eraseLocal(context, it) }, { if (authentication.userID == it) authentication.signOutLocally() })
    fun begin(account: UUID, userID: String, closeChat: () -> Unit) {
        check(!active && !busy)
        val random = ByteArray(32).also { SecureRandom().nextBytes(it) }
        val secret = Base64.encodeToString(random, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
        closeChat()
        val record = DeletionRecord(account, userID, secret, System.currentTimeMillis())
        store.save(record); pending = record; notice = null
    }
    private fun accept(reply: JSONObject, record: DeletionRecord) {
        require(UUID.fromString(reply.getString("account_id")) == record.account)
        val phase = when (reply.getString("status")) {
            "deletion_requested" -> DeletionRecord.Phase.REQUESTED
            "deleted" -> DeletionRecord.Phase.COMPLETED
            else -> throw ServiceFailure(0, "invalid_deletion_response")
        }
        val next = record.copy(phase = phase)
        store.save(next); pending = next
    }
    private fun eraseIfConfirmed() {
        var record = pending ?: return
        if (record.phase == DeletionRecord.Phase.PREPARED) return
        if (!record.localErased) {
            erase(record); signOut(record.userID); record = record.copy(localErased = true)
            store.save(record); pending = record
        } else signOut(record.userID)
    }
    suspend fun resume() {
        if (busy || pending == null) return
        busy = true; notice = null; needsSignIn = false
        try {
            eraseIfConfirmed()
            val record = requireNotNull(pending)
            if (record.phase == DeletionRecord.Phase.COMPLETED) return
            try { accept(service.status(record), record) }
            catch (error: ServiceFailure) {
                if (error.status != 404 || record.phase != DeletionRecord.Phase.PREPARED || System.currentTimeMillis() - record.createdAt >= 7 * 86_400_000L) throw error
                accept(service.submit(record), record)
            }
            eraseIfConfirmed()
        } catch (error: CancellationException) {
            notice = R.string.deletion_interrupted; throw error
        } catch (error: Exception) {
            if (error is Authentication.SignInRequired || (error is ServiceFailure && error.code in setOf("recent_sign_in_required", "sign_in_required"))) {
                needsSignIn = true; notice = R.string.deletion_sign_in_again
            } else notice = if (pending?.phase == DeletionRecord.Phase.PREPARED)
                R.string.deletion_request_unconfirmed
            else R.string.deletion_check_failed
        } finally { busy = false }
    }
    fun finish() {
        val record = pending ?: return
        if (busy || record.phase != DeletionRecord.Phase.COMPLETED || !record.localErased) return
        try { store.remove(); pending = null; notice = null }
        catch (_: Exception) { notice = R.string.deletion_receipt_clear_failed }
    }
    companion object {
        fun eraseLocal(context: Context, record: DeletionRecord) {
            PrivateSpeechCache.erase(context)
            KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.${record.account}") }
            val folder = File(context.noBackupFilesDir, "messages/${record.account}")
            check(!folder.exists() || folder.deleteRecursively()) { "Local cleanup incomplete" }
            val digest = MessageDigest.getInstance("SHA-256").digest(record.userID.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
            PrivateRecords(context).remove("profile-$digest")
        }
    }
}
