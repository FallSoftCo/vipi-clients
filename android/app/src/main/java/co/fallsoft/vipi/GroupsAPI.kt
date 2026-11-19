package co.fallsoft.vipi

import org.json.JSONObject
import java.util.UUID

internal class GroupsAPI(private val transport: ChatTransport, private val device: DeviceCredential) {
    data class Listing(val groups: List<GroupSnapshot>, val invitations: List<GroupInvitation>)
    suspend fun list(): Listing { val o = transport.request("GET", "/v1/groups", device = device); return Listing(o.getJSONArray("groups").objects().map(GroupSnapshot::parse), o.getJSONArray("invitations").objects().map(GroupInvitation::parse)) }
    suspend fun detail(group: UUID) = GroupSnapshot.parse(transport.request("GET", "/v1/groups/$group", device = device))
    suspend fun create(id: UUID, title: String) = GroupSnapshot.parse(transport.request("POST", "/v1/groups", JSONObject().put("id", id).put("title", title), device))
    suspend fun change(group: GroupSnapshot, method: String, suffix: String, request: UUID, fields: Map<String, String>): GroupSnapshot {
        val body = JSONObject(fields).put("request_id", request).put("expected_epoch", group.epoch)
        return GroupSnapshot.parse(transport.request(method, "/v1/groups/${group.id}$suffix", body, device))
    }
    suspend fun answer(invitation: GroupInvitation, accept: Boolean, request: UUID): GroupSnapshot? {
        val o = transport.request("POST", "/v1/groups/${invitation.group}/invitations/${invitation.id}/${if (accept) "accept" else "decline"}", JSONObject().put("request_id", request).put("expected_epoch", invitation.epoch), device)
        return if (accept) GroupSnapshot.parse(o) else null
    }
    suspend fun leave(group: GroupSnapshot, request: UUID) { transport.request("POST", "/v1/groups/${group.id}/leave", JSONObject().put("request_id", request).put("expected_epoch", group.epoch), device) }
    suspend fun sendControl(fanout: GroupFanout) = transport.request("POST", "/v1/groups/${fanout.group}/controls", JSONObject(fanout.body), device)
    suspend fun send(fanout: GroupFanout) = transport.request("POST", "/v1/groups/${fanout.group}/messages", JSONObject(fanout.body), device)
}
