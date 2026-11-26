package co.fallsoft.vipi

import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

internal object GroupsUpgrade { const val maximumPeople = 16; const val muteDeliveryQualified = false }
internal enum class GroupRole(val wire: String) { OWNER("owner"), ADMIN("admin"), MEMBER("member"); companion object { fun parse(value: String) = entries.single { it.wire == value } } }
internal data class GroupMember(val id: UUID, val name: String, val username: String, val role: GroupRole, val joinedEpoch: Int, val device: UUID?, val chatFeaturesVersion: Int = 0)
internal data class GroupPendingInvitation(val id: UUID, val user: UUID, val invitedBy: UUID, val expiresAt: String, val state: String)
internal data class GroupInvitation(val id: UUID, val group: UUID, val title: String, val invitedBy: UUID, val expiresAt: String, val epoch: Int) {
    companion object { fun parse(o: JSONObject) = GroupInvitation(o.uuid("id"), o.uuid("group_id"), o.getString("title"), o.uuid("invited_by"), o.getString("expires_at"), o.getInt("epoch")) }
}
internal data class GroupSnapshot(val id: UUID, val title: String, val epoch: Int, val state: String, val members: List<GroupMember>, val invitations: List<GroupPendingInvitation>) {
    fun role(user: UUID) = members.firstOrNull { it.id == user }?.role
    fun manages(user: UUID) = role(user) in setOf(GroupRole.OWNER, GroupRole.ADMIN)
    fun removes(actor: UUID, subject: UUID) = actor != subject && role(subject) != null && (role(actor) == GroupRole.OWNER || (role(actor) == GroupRole.ADMIN && role(subject) == GroupRole.MEMBER))
    fun validate() {
        require(epoch > 0 && title.isNotBlank() && title.codePointCount(0, title.length) <= 80 && members.size <= 16)
        require(members.map { it.id }.distinct().size == members.size && members.count { it.role == GroupRole.OWNER } == 1)
    }
    fun json() = JSONObject().put("id", id).put("title", title).put("epoch", epoch).put("state", state)
        .put("members", JSONArray().apply { members.forEach { put(JSONObject().put("user_id", it.id).put("display_name", it.name).put("username", it.username).put("role", it.role.wire).put("chat_features_version", it.chatFeaturesVersion).put("joined_epoch", it.joinedEpoch).put("device_id", it.device ?: JSONObject.NULL)) } })
        .put("invitations", JSONArray().apply { invitations.forEach { put(JSONObject().put("id", it.id).put("user_id", it.user).put("invited_by", it.invitedBy).put("expires_at", it.expiresAt).put("state", it.state)) } })
    companion object { fun parse(o: JSONObject): GroupSnapshot {
        val value = GroupSnapshot(o.uuid("id"), o.getString("title"), o.getInt("epoch"), o.getString("state"), o.getJSONArray("members").objects().map {
            GroupMember(it.uuid("user_id"), it.getString("display_name"), it.getString("username"), GroupRole.parse(it.getString("role")), it.getInt("joined_epoch"), if (it.isNull("device_id")) null else it.uuid("device_id"), it.optInt("chat_features_version", 0))
        }, o.getJSONArray("invitations").objects().map { GroupPendingInvitation(it.uuid("id"), it.uuid("user_id"), it.uuid("invited_by"), it.getString("expires_at"), it.getString("state")) })
        value.validate(); return value
    } }
}
internal enum class GroupDelivery { QUEUED, ACCEPTED, FAILED, EXPIRED, MEMBERSHIP_CHANGED, IDENTITY_CHANGED, RECEIVED, WITHHELD }
internal data class GroupMessage(val id: UUID, val group: UUID, val epoch: Int, val membershipRevision: Int, val sender: UUID, val text: String, val createdAt: Long, val delivery: GroupDelivery, val withheldReason: String? = null, val features: ChatFeatures = ChatFeatures.EMPTY, val actionDevice: UUID? = null) {
    val renderID get() = "group:$group:$id"
    fun json() = JSONObject().put("id", id).put("group", group).put("epoch", epoch).put("membershipRevision", membershipRevision).put("sender", sender).put("text", text).put("createdAt", createdAt).put("delivery", delivery.name).put("withheldReason", withheldReason ?: JSONObject.NULL).also { features.write(it); actionDevice?.let { device -> it.put("action_device", device) } }
    companion object { fun parse(o: JSONObject) = GroupMessage(o.uuid("id"), o.uuid("group"), o.getInt("epoch"), o.getInt("membershipRevision"), o.uuid("sender"), o.getString("text"), o.getLong("createdAt"), GroupDelivery.valueOf(o.getString("delivery")), if (o.isNull("withheldReason")) null else o.getString("withheldReason"), ChatFeatures.parse(o, o.getString("text")), if (o.isNull("action_device")) null else o.uuid("action_device")) }
}
internal data class GroupPreferences(val muted: Boolean = false, val read: Set<UUID> = emptySet(), val draft: String = "")
internal object GroupSelection {
    fun name(text: String): String = text.trim().also { require(it.isNotEmpty() && it.codePointCount(0, it.length) <= 80 && it.none(Char::isISOControl)) { "Give your group a name with 1–80 characters." } }
    fun toggle(person: UUID, selected: Set<UUID>, account: UUID, occupied: Set<UUID> = emptySet()): Set<UUID> {
        require(person != account && person !in occupied)
        if (person in selected) return selected - person
        require(selected.size + occupied.size + 1 < 16) { "Choose up to 15 other people. The limit of 16 includes you." }
        return selected + person
    }
}
internal fun JSONObject.uuid(name: String): UUID = UUID.fromString(getString(name))
internal fun JSONArray.objects(): List<JSONObject> = (0 until length()).map(::getJSONObject)
