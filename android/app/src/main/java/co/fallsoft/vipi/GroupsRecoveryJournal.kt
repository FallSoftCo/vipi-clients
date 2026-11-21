package co.fallsoft.vipi

import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest
import java.util.UUID

internal data class GroupRecoveryReview(val entry: GroupsRecoveryJournal.Entry, val current: GroupSnapshot)

/** Account-encrypted, immutable recovery records. No network call or Signal
 * rollback runs inside these transactions. Legacy plans have no descriptor and
 * remain exact-retry-only; a later login must never invent their original device. */
internal class GroupsRecoveryJournal(private val vault: MessageVault) {
    data class Link(val kind: String, val id: String, val hash: String) {
        fun json() = JSONObject().put("kind", kind).put("id", id).put("sha256", hash)
    }
    data class Entry(val original: PreparedGroupOperation, val links: List<Link>, val receipt: String?) {
        val cancelled get() = receipt?.let { original.resolution(JSONObject(it)) is GroupOperationResolution.Cancelled } == true
    }
    private fun key(value: PreparedGroupOperation) = "${value.group}/${value.request}"
    fun entries(group: UUID): List<Entry> = vault.transaction {
        vault.ids("group-recovery-descriptor").filter { it.startsWith("$group/") }.map(::loadInTransaction)
    }
    private fun loadInTransaction(recordKey: String): Entry {
        val original = PreparedGroupOperation.parse(GroupsStore.json(requireNotNull(vault.get("group-recovery-descriptor", recordKey))))
        require(key(original) == recordKey)
        val links = JSONArray(requireNotNull(vault.get("group-recovery-links", recordKey)).toString(Charsets.UTF_8)).objects().map {
            Link(it.getString("kind"), it.getString("id"), it.getString("sha256"))
        }
        require(links.size in 1..3 && links.map { it.kind to it.id }.distinct().size == links.size)
        return Entry(original, links, vault.get("group-recovery-receipt", recordKey)?.toString(Charsets.UTF_8))
    }
    fun remember(original: PreparedGroupOperation, planKind: String, planID: String, fanout: GroupFanout?) = vault.transaction {
        val key = key(original)
        require(vault.get("group-recovery-archive", key) == null) { "This saved change was already closed. Start a new change after reviewing the people." }
        require(planKind in setOf("group-mutation", "group-join-plan"))
        val refs = mutableListOf(planKind to planID)
        fanout?.let {
            require(it.group == original.group)
            refs += "group-control-outgoing" to "${it.group}/${it.message}"
            refs += "group-control-outgoing-change" to "${it.group}/${it.message}"
        }
        val links = refs.map { (kind, id) -> Link(kind, id, hash(requireNotNull(vault.get(kind, id)))) }
        if (vault.get("group-recovery-descriptor", key) != null) {
            val saved = loadInTransaction(key)
            require(canonical(JSONObject(saved.original.body)) == canonical(JSONObject(original.body)) && saved.links == links) { "The original saved change no longer matches. Keep it for review." }
            require(saved.receipt == null) { "Check the saved outcome before retrying this change." }
        } else {
            require(vault.ids("group-recovery-descriptor").size < 128) { "Too many group changes are waiting for review." }
            vault.put("group-recovery-descriptor", key, GroupsStore.bytes(original.json()))
            vault.put("group-recovery-links", key, JSONArray(links.map(Link::json)).toString().toByteArray(Charsets.UTF_8))
        }
    }
    fun record(entry: Entry, resolution: GroupOperationResolution) = vault.transaction {
        require(resolution.original.group == entry.original.group && resolution.original.request == entry.original.request && resolution.original.body == entry.original.body)
        val current = loadInTransaction(key(entry.original))
        require(current.original.body == entry.original.body && current.links == entry.links)
        // A resolved tombstone/outcome cannot change on a delayed retry.
        current.receipt?.let { require(canonical(JSONObject(it)) == canonical(JSONObject(resolution.receipt))) }
        current.original.resolution(JSONObject(resolution.receipt))
        vault.put("group-recovery-receipt", key(entry.original), resolution.receipt.toByteArray(Charsets.UTF_8))
    }
    /** Caller performs the exact admitted transition and removes its pending
     * plan/control in this SAME vault transaction, then reloads observable UI. */
    fun completedInTransaction(original: PreparedGroupOperation) = completedInTransaction(original.group, original.request)
    fun completedInTransaction(group: UUID, request: UUID) {
        val key = "$group/$request"
        for (kind in listOf("group-recovery-descriptor", "group-recovery-links", "group-recovery-receipt")) vault.remove(kind, key)
    }
    /** Only an authenticated cancelled receipt plus explicit current-people
     * confirmation reaches here. Preserve the old plan/ciphertext in the vault;
     * never restore or edit any ratchet/session/identity record. */
    fun archiveCancelled(entry: Entry, reviewed: GroupSnapshot, commitInTransaction: () -> Unit = {}) = vault.transaction {
        val key = key(entry.original); val current = loadInTransaction(key)
        require(current.original.body == entry.original.body && current.links == entry.links && current.cancelled)
        require(reviewed.id == entry.original.group && reviewed.epoch >= entry.original.expectedEpoch)
        reviewed.validate()
        require(vault.ids("group-recovery-archive").size < 128) { "Saved change history is full. Your original change is still retained." }
        val records = current.links.map { link ->
            require(link.kind in setOf("group-mutation", "group-join-plan", "group-control-outgoing", "group-control-outgoing-change"))
            val bytes = requireNotNull(vault.get(link.kind, link.id)); require(hash(bytes) == link.hash) { "The saved change changed while it was being reviewed." }
            link to bytes
        }
        val oldBytes = vault.ids("group-recovery-archived-record").sumOf { requireNotNull(vault.get("group-recovery-archived-record", it)).size.toLong() }
        require(oldBytes + records.sumOf { it.second.size.toLong() } <= 16L * 1024 * 1024) { "Saved change history is full. Your original change is still retained." }
        vault.put("group-recovery-archive", key, GroupsStore.bytes(JSONObject().put("original", current.original.json()).put("receipt", JSONObject(requireNotNull(current.receipt))).put("reviewed", reviewed.json()).put("links", JSONArray(current.links.map(Link::json)))))
        records.forEach { (link, bytes) -> vault.put("group-recovery-archived-record", "$key/${link.kind}", bytes) }
        records.filter { it.first.kind == "group-control-outgoing" }.forEach { (link, _) -> require(vault.get("group-control-logical", link.id) == null) { "An encrypted approval was already applied locally. Keep this change for reconciliation." } }
        commitInTransaction()
        records.forEach { (link, _) -> vault.remove(link.kind, link.id) }
        completedInTransaction(current.original)
    }
    companion object {
        private fun hash(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it.toInt() and 255) }
        private fun canonical(value: Any?): String = when (value) {
            is JSONObject -> value.keys().asSequence().sorted().joinToString(prefix = "{", postfix = "}") { JSONObject.quote(it) + ":" + canonical(value.get(it)) }
            is JSONArray -> (0 until value.length()).joinToString(prefix = "[", postfix = "]") { canonical(value.get(it)) }
            is String -> JSONObject.quote(value)
            else -> value.toString()
        }
    }
}
