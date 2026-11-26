package co.fallsoft.vipi

import android.os.SystemClock
import androidx.compose.runtime.mutableStateMapOf
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.Channel
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/** Conversation metadata only. A typing transition never includes the draft.
 * Read intents are recorded on device before sending, independently of scrolling. */
internal class ChatActivityEvents(
    private val store: MessageVault,
    private val journal: MessageJournal,
    private val eligible: (UUID) -> Boolean,
    private val post: suspend (UUID, String, JSONObject) -> JSONObject,
    private val changed: () -> Unit
) : AutoCloseable {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val writer = Dispatchers.IO.limitedParallelism(1)
    private val remote = mutableStateMapOf<UUID, Job>()
    private val typing = linkedMapOf<UUID,Boolean>()
    private val typingWake = Channel<Unit>(Channel.CONFLATED)
    private val readWake = Channel<Unit>(Channel.CONFLATED)
    private var typer: UUID? = null
    private var activeAt = 0L
    private var idle: Job? = null
    private var viewed: UUID? = null
    private var incoming = emptyList<UUID>()
    private var outgoing = emptyList<UUID>()

    init {
        scope.launch {
            for (signal in typingWake) while (typing.isNotEmpty()) {
                val (peer, active) = typing.entries.first().toPair()
                typing.remove(peer)
                if (eligible(peer)) try { post(peer, "typing", JSONObject().put("active", active)) }
                    catch (e: CancellationException) { throw e } catch (_: Exception) { /* Expires on the receiving device. */ }
            }
        }
        scope.launch {
            for (signal in readWake) {
                delay(175)
                while (readWake.tryReceive().isSuccess) { /* coalesce viewport changes */ }
                try { flush() } catch (e: CancellationException) { throw e }
                catch (_: Exception) { /* Durable intents retry on the next view or foreground reconnect. */ }
            }
        }
    }
    fun isTyping(peer: UUID) = remote.containsKey(peer) && eligible(peer)
    fun remoteTyping(peer: UUID, active: Boolean) {
        remote.remove(peer)?.cancel()
        if (active && peer == viewed && eligible(peer)) remote[peer] = scope.launch {
            delay(7_000)
            remote.remove(peer)
        }
    }
    fun composer(peer: UUID, active: Boolean) {
        if (!active && typer != peer) return
        if (active && !eligible(peer)) return
        val now = SystemClock.elapsedRealtime()
        if (active && typer == peer) {
            if (now - activeAt >= 4_000) { typing[peer] = true; activeAt = now; typingWake.trySend(Unit) }
        } else {
            typer?.let { typing[it] = false }
            typer = peer.takeIf { active }
            if (active) { typing[peer] = true; activeAt = now }
            typingWake.trySend(Unit)
        }
        idle?.cancel()
        if (active) idle = scope.launch { delay(2_500); composer(peer, false) }
    }
    fun visible(peer: UUID, seen: List<UUID>, check: List<UUID>) {
        val ids = seen.distinct().take(64)
        val candidates = check.distinct().take(64)
        if (viewed == peer && ids == incoming && candidates == outgoing) return
        if (viewed != peer) { remote.values.toList().forEach { it.cancel() }; remote.clear() }
        val newlyVisible = if (viewed == peer) ids - incoming.toSet() else ids
        viewed = peer; incoming = ids; outgoing = candidates
        if (!eligible(peer)) return
        scope.launch(writer) {
            try {
                store.transaction {
                    for (id in newlyVisible) {
                        val bytes = store.get("incoming", id.toString()) ?: continue
                        val message = StoredChat.parse(bytes)
                        if (message.features.reaction == null && !message.seen && message.envelope.sender == peer) {
                            store.put("incoming", id.toString(), message.copy(seen = true).encode())
                            store.put("read-pending", "q.$id", peer.toString().toByteArray(Charsets.UTF_8))
                        }
                    }
                }
                if (ids.isNotEmpty() || candidates.isNotEmpty()) readWake.trySend(Unit)
            } catch (e: CancellationException) { throw e }
            catch (_: Exception) { /* An unavailable vault cannot establish a shared receipt. */ }
        }
    }
    fun receiptsChanged(peer: UUID) { if (viewed == peer) readWake.trySend(Unit) }
    fun outgoingAccepted(id: UUID, peer: UUID) {
        if (peer == viewed && id in outgoing) readWake.trySend(Unit)
    }
    fun reconnected() { readWake.trySend(Unit) }
    private suspend fun flush() {
        var check = viewed?.takeIf(eligible)?.let { peer -> outgoing.filter { id ->
            journal.outgoing(id)?.let { it.envelope.recipient == peer && it.state in setOf("accepted", "delivered") } == true
        }.takeIf { it.isNotEmpty() }?.let { peer to it } }
        var before: String? = null
        do {
            val page = store.transaction { store.pageIDs("read-pending", "q.", before, 64).associateWith { key ->
                UUID.fromString(requireNotNull(store.get("read-pending", key)).toString(Charsets.UTF_8))
            } }
            before = page.keys.lastOrNull()
            val seenByPeer = page.entries.groupBy({ it.value }, { UUID.fromString(it.key.removePrefix("q.")) })
            val peers = seenByPeer.keys + listOfNotNull(check?.first)
            for (peer in peers) {
                if (!eligible(peer)) continue
                val seen = seenByPeer[peer].orEmpty()
                val checking = check?.takeIf { it.first == peer }?.second.orEmpty()
                val response = post(peer, "receipts", JSONObject().put("seen", JSONArray(seen.map(UUID::toString))).put("check", JSONArray(checking.map(UUID::toString))))
                fun ids(key: String) = response.getJSONArray(key).let { array -> (0 until array.length()).map { UUID.fromString(array.getString(it)) } }
                val ack = ids("acknowledged"); val read = ids("read")
                require(ack.all { it in seen } && read.all { it in checking })
                store.transaction {
                    for (id in ack) store.remove("read-pending", "q.$id")
                }
                for (id in read) journal.applyStatus(id, "read")
                if (read.isNotEmpty()) changed()
            }
            check = null
        } while (page.size == 64)
    }
    override fun close() { scope.cancel(); typingWake.close(); readWake.close(); remote.clear() }
}
