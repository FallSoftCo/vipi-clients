package co.fallsoft.vipi

import android.net.Uri
import android.os.ParcelFileDescriptor
import java.io.File
import java.util.UUID
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.joinAll
import kotlinx.coroutines.runBlocking
import org.json.JSONObject

/**
 * An unsent review belongs to exactly one account and conversation. Only a stopped recording enters
 * this store. The encrypted original transfers to the outbox on Send.
 */
internal class VoiceDrafts(private val vault: MessageVault, val repository: AttachmentRepository) {
    init {
        require(vault.account == repository.account)
    }

    private val saves = mutableMapOf<UUID, Deferred<AttachmentManifest>>()

    fun current(peer: UUID): AttachmentManifest? = vault.transaction {
        vault.get(RECORD, peer.toString())?.let {
            AttachmentManifest.parse(JSONObject(it.toString(Charsets.UTF_8)))
        }
    }

    @Synchronized fun pending(peer: UUID): Deferred<AttachmentManifest>? = saves[peer]

    @Synchronized
    fun save(peer: UUID, recording: File): Deferred<AttachmentManifest> {
        check(peer !in saves && current(peer) == null)
        val task =
            CoroutineScope(Dispatchers.IO).async(start = CoroutineStart.LAZY) {
                var prepared: AttachmentManifest? = null
                try {
                    val item = repository.prepare(Uri.fromFile(recording), AttachmentKind.VOICE)
                    prepared = item
                    vault.transaction {
                        check(vault.get(RECORD, peer.toString()) == null)
                        vault.put(
                            RECORD,
                            peer.toString(),
                            item.json().toString().toByteArray(Charsets.UTF_8),
                        )
                    }
                    prepared = null
                    item
                } finally {
                    prepared?.let(repository::discard)
                    recording.delete()
                }
            }
        saves[peer] = task
        task.invokeOnCompletion {
            synchronized(this) { if (saves[peer] === task) saves.remove(peer) }
        }
        task.start()
        return task
    }

    fun discard(peer: UUID, expected: AttachmentManifest) {
        vault.transaction {
            val bytes = requireNotNull(vault.get(RECORD, peer.toString()))
            check(AttachmentManifest.parse(JSONObject(bytes.toString(Charsets.UTF_8))) == expected)
            vault.remove(RECORD, peer.toString())
        }
        repository.discard(expected)
    }

    suspend fun open(item: AttachmentManifest): ParcelFileDescriptor {
        val clear = repository.openLocal(item)
        return try {
            ParcelFileDescriptor.open(clear, ParcelFileDescriptor.MODE_READ_ONLY)
        } finally {
            clear.delete()
        }
    }

    // Closing a session may close its SQLite handle. Drain only this account's finite
    // already-stopped encoder outputs; their complete IO path never waits for the UI thread.
    fun finishPending() {
        val active = synchronized(this) { saves.values.toList() }
        if (active.isNotEmpty()) runBlocking { active.joinAll() }
    }

    companion object {
        const val RECORD = "voice-preview"
    }
}
