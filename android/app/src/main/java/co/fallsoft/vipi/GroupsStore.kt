package co.fallsoft.vipi

import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/** Account-bound encrypted storage. All calls execute on the native coordinator;
 * no network/suspension occurs inside vault transactions. */
internal class GroupsStore(val vault: MessageVault) {
    fun snapshots() = vault.transaction { vault.ids("group-roster").map { GroupSnapshot.parse(json(requireNotNull(vault.get("group-roster", it)))) } }
    fun activeIDs(): Set<UUID>? = vault.transaction { vault.get("group-active", "ids")?.let { bytes -> val values = JSONArray(bytes.toString(Charsets.UTF_8)); (0 until values.length()).map { UUID.fromString(values.getString(it)) }.toSet() } }
    fun saveActiveIDs(ids: Set<UUID>) = vault.transaction { vault.put("group-active", "ids", JSONArray(ids.map(UUID::toString)).toString().toByteArray(Charsets.UTF_8)) }
    fun save(group: GroupSnapshot) { group.validate(); vault.transaction {
        vault.get("group-roster", group.id.toString())?.let { require(GroupSnapshot.parse(json(it)).epoch <= group.epoch) { "The group changed. Refresh and review the people." } }
        vault.put("group-roster", group.id.toString(), bytes(group.json()))
    } }
    fun preferences(group: UUID) = vault.transaction { preferencesInTransaction(group) }
    private fun preferencesInTransaction(group: UUID): GroupPreferences = vault.get("group-preferences", group.toString())?.let { data ->
        val o = json(data); val read = o.getJSONArray("read")
        GroupPreferences(o.getBoolean("muted"), (0 until read.length()).map { UUID.fromString(read.getString(it)) }.toSet(), o.getString("draft"))
    } ?: GroupPreferences()
    fun preferences(group: UUID, change: (GroupPreferences) -> GroupPreferences) = vault.transaction {
        val value = change(preferencesInTransaction(group))
        vault.put("group-preferences", group.toString(), bytes(JSONObject().put("muted", value.muted).put("read", JSONArray(value.read.map(UUID::toString))).put("draft", value.draft)))
    }
    fun messages(group: UUID) = vault.transaction { messagesInTransaction(group) }
    fun messagesInTransaction(group: UUID) = vault.ids("group-message").filter { it.startsWith("$group/") }.map { GroupMessage.parse(json(requireNotNull(vault.get("group-message", it)))) }.sortedWith(compareBy({ it.createdAt }, { it.id.toString() }))
    fun saveMessage(value: GroupMessage) = vault.transaction { saveMessageInTransaction(value) }
    fun saveMessageInTransaction(value: GroupMessage) {
        val key = "${value.group}/${value.id}"
        vault.get("group-message", key)?.let { bytes -> val old = GroupMessage.parse(json(bytes)); require(old.copy(delivery = value.delivery, withheldReason = value.withheldReason) == value) { "Group message context changed" } }
        vault.put("group-message", key, bytes(value.json()))
    }
    fun unread(group: UUID, account: UUID): Int { val read = preferences(group).read; return messages(group).count { it.sender != account && it.delivery == GroupDelivery.RECEIVED && it.id !in read } }
    companion object {
        fun json(bytes: ByteArray) = JSONObject(bytes.toString(Charsets.UTF_8))
        fun bytes(json: JSONObject) = json.toString().toByteArray(Charsets.UTF_8)
    }
}
