package co.fallsoft.vipi

import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

internal data class GroupCreationDraft(val title: String, val people: Set<UUID>, val createdGroup: UUID? = null)

/** Account-bound encrypted storage. All calls execute on the native coordinator;
 * no network/suspension occurs inside vault transactions. */
internal class GroupsStore(val vault: MessageVault) {
    fun creationDraft(): GroupCreationDraft? = vault.transaction {
        vault.get("group-compose", "draft")?.let { data ->
            val fields = json(data)
            val people = fields.getJSONArray("people")
            GroupCreationDraft(fields.getString("title"), (0 until people.length()).map { UUID.fromString(people.getString(it)) }.toSet(),
                fields.optString("created_group").takeIf(String::isNotEmpty)?.let(UUID::fromString))
        }
    }
    fun saveCreationDraft(draft: GroupCreationDraft) = vault.transaction { saveCreationDraftInTransaction(draft) }
    fun saveCreationDraftInTransaction(draft: GroupCreationDraft) {
        require(draft.people.size <= 15 && vault.account !in draft.people)
        val fields = JSONObject().put("title", draft.title).put("people", JSONArray(draft.people.map(UUID::toString)))
        draft.createdGroup?.let { fields.put("created_group", it) }
        vault.put("group-compose", "draft", bytes(fields))
    }
    fun clearCreationDraft() = vault.transaction { vault.remove("group-compose", "draft") }
    fun snapshots() = vault.transaction { snapshotsInTransaction() }
    fun snapshotsInTransaction() = vault.ids("group-roster").map { GroupSnapshot.parse(json(requireNotNull(vault.get("group-roster", it)))) }
    fun activeIDs(): Set<UUID>? = vault.transaction { vault.get("group-active", "ids")?.let { bytes -> val values = JSONArray(bytes.toString(Charsets.UTF_8)); (0 until values.length()).map { UUID.fromString(values.getString(it)) }.toSet() } }
    fun saveActiveIDs(ids: Set<UUID>) = vault.transaction { saveActiveIDsInTransaction(ids) }
    fun saveActiveIDsInTransaction(ids: Set<UUID>) { vault.put("group-active", "ids", JSONArray(ids.map(UUID::toString)).toString().toByteArray(Charsets.UTF_8)) }
    fun save(group: GroupSnapshot) = vault.transaction { saveInTransaction(group) }
    fun saveInTransaction(group: GroupSnapshot) { group.validate()
        vault.get("group-roster", group.id.toString())?.let { require(GroupSnapshot.parse(json(it)).epoch <= group.epoch) { "The group changed. Refresh and review the people." } }
        vault.put("group-roster", group.id.toString(), bytes(group.json()))
        group.members.forEach { person -> vault.put("group-member", "${group.id}/${person.id}", bytes(JSONObject().put("id", person.id).put("name", person.name).put("username", person.username))) }
    }
    fun cachedName(group: UUID, person: UUID): String? = vault.transaction { vault.get("group-member", "$group/$person")?.let { json(it).getString("name") } }
    fun preferences(group: UUID) = vault.transaction { preferencesInTransaction(group) }
    private fun preferencesInTransaction(group: UUID): GroupPreferences = vault.get("group-preferences", group.toString())?.let { data ->
        val o = json(data); val read = o.getJSONArray("read")
        GroupPreferences(o.getBoolean("muted"), (0 until read.length()).map { UUID.fromString(read.getString(it)) }.toSet(), o.getString("draft"))
    } ?: GroupPreferences()
    fun preferences(group: UUID, change: (GroupPreferences) -> GroupPreferences) = vault.transaction {
        val old = preferencesInTransaction(group)
        val value = change(old)
        if (value.read != old.read) {
            vault.get("group-inbox", group.toString())?.let { data ->
                val index = json(data)
                fun received(id: UUID): Boolean = vault.get("group-message", "$group/$id")?.let {
                    val message = GroupMessage.parse(json(it))
                    message.delivery == GroupDelivery.RECEIVED && message.features.reaction == null && message.sender != vault.account
                } == true
                val newlyRead = (value.read - old.read).count(::received)
                val newlyUnread = (old.read - value.read).count(::received)
                index.put("unread", index.getInt("unread") - newlyRead + newlyUnread)
                vault.put("group-inbox", group.toString(), bytes(index))
            }
        }
        vault.put("group-preferences", group.toString(), bytes(JSONObject().put("muted", value.muted).put("read", JSONArray(value.read.map(UUID::toString))).put("draft", value.draft)))
    }
    fun messages(group: UUID) = vault.transaction { messagesInTransaction(group).filter { it.features.reaction == null } }
    fun messagesInTransaction(group: UUID) = vault.ids("group-message").filter { it.startsWith("$group/") }.map { GroupMessage.parse(json(requireNotNull(vault.get("group-message", it)))) }.sortedWith(compareBy({ it.createdAt }, { it.id.toString() }))
    fun saveMessage(value: GroupMessage) = vault.transaction { saveMessageInTransaction(value) }
    fun saveMessageInTransaction(value: GroupMessage) {
        val key = "${value.group}/${value.id}"
        val previous = vault.get("group-message", key)?.let { GroupMessage.parse(json(it)) }
        if (previous != null) require(previous.copy(delivery = value.delivery, withheldReason = value.withheldReason) == value) { "Group message context changed" }
        ConversationStreaks.group(vault, value)
        vault.put("group-message", key, bytes(value.json()))
        if (previous?.delivery != value.delivery && value.features.reaction == null) {
            updateInboxInTransaction(value, previous)
        }
        if (value.delivery in setOf(GroupDelivery.ACCEPTED, GroupDelivery.RECEIVED)) {
            val ref = ConversationRef.Group(value.group)
            val ledger = ConversationReactions(vault)
            val change = value.features.reaction
            if (change == null) ledger.resolve(ref, value.id, value.sender)
            else ledger.record(ref, change, value.sender, requireNotNull(value.actionDevice), value.id)
        }
    }
    private fun eligible(message: GroupMessage) = message.features.reaction == null &&
        message.delivery in setOf(GroupDelivery.ACCEPTED, GroupDelivery.RECEIVED)

    private fun updateInboxInTransaction(value: GroupMessage, previous: GroupMessage?) {
        val group = value.group.toString()
        val saved = vault.get("group-inbox", group)?.let(::json) ?: return
        if (previous != null && eligible(previous)) {
            vault.remove("group-inbox", group)
            return
        }
        if (!eligible(value)) return
        if (value.createdAt > saved.optLong("time", Long.MIN_VALUE) ||
            value.createdAt == saved.optLong("time") && value.id.toString() > saved.optString("latest")) {
            saved.put("latest", value.id).put("time", value.createdAt)
        }
        if (value.delivery == GroupDelivery.RECEIVED && value.sender != vault.account &&
            value.id !in preferencesInTransaction(value.group).read) saved.put("unread", saved.getInt("unread") + 1)
        vault.put("group-inbox", group, bytes(saved))
    }

    fun inboxSummary(group: UUID): Pair<GroupMessage?, Int> = vault.transaction {
        val key = group.toString()
        val cached = vault.get("group-inbox", key)?.let(::json)
        if (cached != null) {
            val latest = cached.optString("latest").takeIf(String::isNotEmpty)?.let { id ->
                vault.get("group-message", "$group/$id")?.let { GroupMessage.parse(json(it)) }
            }
            return@transaction latest to cached.getInt("unread")
        }
        val history = messagesInTransaction(group).filter(::eligible)
        val latest = history.lastOrNull()
        val read = preferencesInTransaction(group).read
        val unread = history.count { it.delivery == GroupDelivery.RECEIVED && it.sender != vault.account && it.id !in read }
        val summary = JSONObject().put("unread", unread)
        if (latest != null) summary.put("latest", latest.id).put("time", latest.createdAt)
        vault.put("group-inbox", key, bytes(summary))
        latest to unread
    }

    fun unread(group: UUID, account: UUID): Int { val read = preferences(group).read; return messages(group).count { it.sender != account && it.delivery == GroupDelivery.RECEIVED && it.id !in read } }
    companion object {
        fun json(bytes: ByteArray) = JSONObject(bytes.toString(Charsets.UTF_8))
        fun bytes(json: JSONObject) = json.toString().toByteArray(Charsets.UTF_8)
    }
}
