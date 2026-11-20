package co.fallsoft.vipi

import org.json.JSONObject
import java.util.UUID

internal data class GroupMutationPlan(val group: GroupSnapshot, val request: UUID, val control: UUID, val method: String, val suffix: String,
    val fields: Map<String, String>, val previous: GroupApprovedRoster?, val originalDevice: UUID? = null) {
    fun transition(actor: UUID): GroupRosterTransition? {
        require(group.epoch < Int.MAX_VALUE && previous?.revision != Int.MAX_VALUE)
        val old = previous ?: return null
        if (suffix == "/leave") return GroupRosterTransition(actor, GroupControlAction.LEAVE, actor, old.revision, old.revision + 1, group.epoch + 1, old.members, old.members.filter { it.id != actor })
        if (!suffix.startsWith("/members/")) return null
        val target = UUID.fromString(suffix.removePrefix("/members/"))
        var newRole: GroupRole? = null
        val action: GroupControlAction
        val people = when {
            method == "DELETE" -> { action = GroupControlAction.REMOVE; old.members.filter { it.id != target } }
            fields["role"] == "owner" -> { action = GroupControlAction.TRANSFER; old.members.map { it.copy(role = if (it.id == target) GroupRole.OWNER else if (it.role == GroupRole.OWNER) GroupRole.ADMIN else it.role) } }
            else -> { action = GroupControlAction.ROLE; newRole = GroupRole.parse(requireNotNull(fields["role"])); old.members.map { if (it.id == target) it.copy(role = requireNotNull(newRole)) else it } }
        }
        return GroupRosterTransition(actor, action, target, old.revision, old.revision + 1, group.epoch + 1, old.members, people, newRole)
    }
    fun json() = JSONObject().put("group", group.json()).put("request", request).put("control", control).put("method", method).put("suffix", suffix).put("fields", JSONObject(fields)).put("previous", previous?.json() ?: JSONObject.NULL).put("original_device_id", originalDevice ?: JSONObject.NULL)
    companion object { fun parse(o: JSONObject): GroupMutationPlan { val fields = o.getJSONObject("fields"); return GroupMutationPlan(GroupSnapshot.parse(o.getJSONObject("group")), o.uuid("request"), o.uuid("control"), o.getString("method"), o.getString("suffix"), fields.keys().asSequence().associateWith(fields::getString), if (o.isNull("previous")) null else GroupApprovedRoster.parse(o.getJSONObject("previous")), if (o.isNull("original_device_id")) null else o.uuid("original_device_id")) } }
}

internal data class GroupJoinApprovalPlan(val id: UUID, val group: GroupSnapshot, val change: GroupRosterTransition, val originalDevice: UUID? = null) {
    fun json() = JSONObject().put("id", id).put("group", group.json()).put("change", change.json()).put("original_device_id", originalDevice ?: JSONObject.NULL)
    companion object { fun parse(o: JSONObject) = GroupJoinApprovalPlan(o.uuid("id"), GroupSnapshot.parse(o.getJSONObject("group")), GroupRosterTransition.parse(o.getJSONObject("change")), if (o.isNull("original_device_id")) null else o.uuid("original_device_id")) }
}
