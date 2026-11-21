package co.fallsoft.vipi

import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/** A relay roster is only a proposal. These revisions are authorized by pinned
 * pairwise Signal identities; server epochs alone never authorize members. */
internal data class GroupApprovedPerson(val id: UUID, val role: GroupRole) {
    fun json() = JSONObject().put("user_id", id).put("role", role.wire)
    companion object { fun parse(o: JSONObject): GroupApprovedPerson { require(o.keys().asSequence().toSet() == setOf("user_id", "role")); return GroupApprovedPerson(o.uuid("user_id"), GroupRole.parse(o.getString("role"))) } }
}
internal data class GroupApprovedRoster(val group: UUID, val revision: Int, val members: List<GroupApprovedPerson>) {
    fun contains(user: UUID) = members.any { it.id == user }
    fun matches(snapshot: GroupSnapshot) = snapshot.id == group && members.toSet() == snapshot.members.map { GroupApprovedPerson(it.id, it.role) }.toSet()
    fun validate(allowEmpty: Boolean = false) {
        require(revision > 0 && members.size <= 16 && members.map { it.id }.distinct().size == members.size)
        require(members.count { it.role == GroupRole.OWNER } == if (allowEmpty && members.isEmpty()) 0 else 1)
    }
    fun json() = JSONObject().put("group_id", group).put("revision", revision).put("members", JSONArray(members.map { it.json() }))
    companion object { fun parse(o: JSONObject) = GroupApprovedRoster(o.uuid("group_id"), o.strictInt("revision"), o.getJSONArray("members").objects().map(GroupApprovedPerson::parse)) }
}
internal enum class GroupControlAction(val wire: String) { ADD("add"), REMOVE("remove"), ROLE("role"), TRANSFER("transfer"), LEAVE("leave") }
internal data class GroupRosterTransition(val actor: UUID, val action: GroupControlAction, val target: UUID, val fromRevision: Int, val toRevision: Int,
    val serverEpoch: Int, val previousMembers: List<GroupApprovedPerson>, val members: List<GroupApprovedPerson>, val newRole: GroupRole? = null) {
    fun validated(group: UUID, previous: GroupApprovedRoster, authenticatedSender: UUID): GroupApprovedRoster {
        previous.validate()
        require(actor == authenticatedSender && previous.group == group && fromRevision == previous.revision && fromRevision < Int.MAX_VALUE && toRevision == fromRevision + 1 && serverEpoch > 0)
        require(action == GroupControlAction.ROLE || newRole == null)
        require(previousMembers.toSet() == previous.members.toSet() && previousMembers.size == previous.members.size)
        val next = GroupApprovedRoster(group, toRevision, members); next.validate(action == GroupControlAction.LEAVE)
        val before = previous.members.associate { it.id to it.role }; val after = members.associate { it.id to it.role }
        val role = requireNotNull(before[actor]); val expected = before.toMutableMap()
        when (action) {
            GroupControlAction.ADD -> { require(role in setOf(GroupRole.OWNER, GroupRole.ADMIN) && target !in before && after[target] == GroupRole.MEMBER); expected[target] = GroupRole.MEMBER }
            GroupControlAction.REMOVE -> { val old = requireNotNull(before[target]); require(target != actor && old != GroupRole.OWNER && (role == GroupRole.OWNER || (role == GroupRole.ADMIN && old == GroupRole.MEMBER))); expected.remove(target) }
            GroupControlAction.ROLE -> { val old = requireNotNull(before[target]); val new = requireNotNull(after[target]); require(role == GroupRole.OWNER && target != actor && old != GroupRole.OWNER && new == newRole && new in setOf(GroupRole.MEMBER, GroupRole.ADMIN) && old != new); expected[target] = new }
            GroupControlAction.TRANSFER -> { require(role == GroupRole.OWNER && target != actor && target in before); expected[actor] = GroupRole.ADMIN; expected[target] = GroupRole.OWNER }
            GroupControlAction.LEAVE -> { require(target == actor && (role != GroupRole.OWNER || before.size == 1)); expected.remove(actor) }
        }
        require(expected == after) { "Authenticated group change modified extra people or roles" }; return next
    }
    fun json() = JSONObject().put("actor_id", actor).put("action", action.wire).put("target_id", target).put("from_revision", fromRevision).put("to_revision", toRevision).put("server_epoch", serverEpoch)
        .put("previous_members", JSONArray(previousMembers.map { it.json() })).put("members", JSONArray(members.map { it.json() })).apply { newRole?.let { put("role", it.wire) } }
    companion object { fun parse(o: JSONObject): GroupRosterTransition {
        val required = setOf("actor_id", "action", "target_id", "from_revision", "to_revision", "server_epoch", "previous_members", "members") + if (o.getString("action") == "role") setOf("role") else emptySet()
        val base = setOf("version", "kind", "id", "sender", "recipient", "sender_device_id", "createdAt", "group_id", "group_epoch", "group_message_id")
        val keys = o.keys().asSequence().toSet(); require(keys == required || keys == required + base)
        return GroupRosterTransition(o.uuid("actor_id"), GroupControlAction.entries.single { it.wire == o.getString("action") }, o.uuid("target_id"), o.strictInt("from_revision"), o.strictInt("to_revision"), o.strictInt("server_epoch"), o.getJSONArray("previous_members").objects().map(GroupApprovedPerson::parse), o.getJSONArray("members").objects().map(GroupApprovedPerson::parse), if (o.has("role")) GroupRole.parse(o.getString("role")) else null) } }
}
internal class GroupsMembership(private val vault: MessageVault) {
    fun current(group: UUID) = vault.transaction { currentInTransaction(group) }
    fun currentInTransaction(group: UUID) = vault.get("group-approved", group.toString())?.let { GroupApprovedRoster.parse(GroupsStore.json(it)) }
    fun historyInTransaction(group: UUID, revision: Int) = vault.get("group-approved-history", "$group/$revision")?.let { GroupApprovedRoster.parse(GroupsStore.json(it)) }
    private fun putInTransaction(roster: GroupApprovedRoster) {
        roster.validate(true); val key = "${roster.group}/${roster.revision}"
        vault.get("group-approved-history", key)?.let { require(GroupApprovedRoster.parse(GroupsStore.json(it)) == roster) { "Conflicting authenticated group history" } }
        val bytes = GroupsStore.bytes(roster.json()); vault.put("group-approved-history", key, bytes); vault.put("group-approved", roster.group.toString(), bytes)
    }
    fun createdLocally(snapshot: GroupSnapshot, expectedID: UUID) {
        require(snapshot.id == expectedID && snapshot.members.size == 1 && snapshot.members.single().id == vault.account && snapshot.members.single().role == GroupRole.OWNER)
        vault.transaction { if (currentInTransaction(snapshot.id) == null) putInTransaction(GroupApprovedRoster(snapshot.id, 1, listOf(GroupApprovedPerson(vault.account, GroupRole.OWNER)))) }
    }
    fun applyInTransaction(change: GroupRosterTransition, group: UUID, authenticatedSender: UUID) {
        val current = requireNotNull(currentInTransaction(group)) { "Authenticated group history is missing. Review the inviter’s encryption details." }
        val previous = requireNotNull(historyInTransaction(group, change.fromRevision)) { "An earlier authenticated group approval is missing." }
        val next = change.validated(group, previous, authenticatedSender)
        historyInTransaction(group, next.revision)?.let { require(it.members.toSet() == next.members.toSet()) { "Conflicting authenticated group approvals" }; return }
        require(current.revision == change.fromRevision); putInTransaction(next)
    }
    /** UI consent must bind to the full decrypted control and the pinned inviter
     * identity. A server invitation or snapshot can never call this alone. */
    fun bootstrapInTransaction(change: GroupRosterTransition, group: UUID, authenticatedSender: UUID, confirmedInviter: UUID) {
        require(currentInTransaction(group) == null && authenticatedSender == confirmedInviter && change.action == GroupControlAction.ADD && change.target == vault.account)
        val previous = GroupApprovedRoster(group, change.fromRevision, change.previousMembers)
        val next = change.validated(group, previous, authenticatedSender)
        putInTransaction(previous); putInTransaction(next)
    }
}

internal fun JSONObject.strictInt(name: String): Int { val value = get(name); require(value is Int || value is Long); val number = (value as Number).toLong(); require(number in Int.MIN_VALUE..Int.MAX_VALUE); return number.toInt() }

internal fun JSONObject.strictLong(name: String): Long { val value = get(name); require(value is Int || value is Long); return (value as Number).toLong() }
