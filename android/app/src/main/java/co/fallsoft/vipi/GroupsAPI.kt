package co.fallsoft.vipi

import java.util.UUID
import org.json.JSONObject

internal class GroupsAPI(
    private val transport: ChatTransport,
    private val device: DeviceCredential,
) {
    val originalDeviceID: UUID
        get() = device.id

    data class Listing(val groups: List<GroupSnapshot>, val invitations: List<GroupInvitation>)

    suspend fun list(): Listing {
        val o = transport.request("GET", "/v1/groups", device = device)
        return Listing(
            o.getJSONArray("groups").objects().map(GroupSnapshot::parse),
            o.getJSONArray("invitations").objects().map(GroupInvitation::parse),
        )
    }

    suspend fun detail(group: UUID) =
        GroupSnapshot.parse(transport.request("GET", "/v1/groups/$group", device = device))

    suspend fun create(id: UUID, title: String) =
        GroupSnapshot.parse(
            transport.request(
                "POST",
                "/v1/groups",
                JSONObject().put("id", id).put("title", title),
                device,
            )
        )

    data class Changed(val snapshot: GroupSnapshot, val control: JSONObject?)

    suspend fun change(
        group: GroupSnapshot,
        method: String,
        suffix: String,
        request: UUID,
        fields: Map<String, String>,
        control: GroupFanout? = null,
    ): Changed {
        val body = JSONObject(fields).put("request_id", request).put("expected_epoch", group.epoch)
        control?.let { body.put("control", JSONObject(it.body)) }
        val response = transport.request(method, "/v1/groups/${group.id}$suffix", body, device)
        return Changed(GroupSnapshot.parse(response), response.optJSONObject("control_acceptance"))
    }

    suspend fun answer(
        invitation: GroupInvitation,
        accept: Boolean,
        request: UUID,
    ): GroupSnapshot? {
        val o =
            transport.request(
                "POST",
                "/v1/groups/${invitation.group}/invitations/${invitation.id}/${if (accept) "accept" else "decline"}",
                JSONObject().put("request_id", request).put("expected_epoch", invitation.epoch),
                device,
            )
        return if (accept) GroupSnapshot.parse(o) else null
    }

    suspend fun leave(group: GroupSnapshot, request: UUID, control: GroupFanout): JSONObject {
        val response =
            transport.request(
                "POST",
                "/v1/groups/${group.id}/leave",
                JSONObject()
                    .put("request_id", request)
                    .put("expected_epoch", group.epoch)
                    .put("control", JSONObject(control.body)),
                device,
            )
        require(response.getBoolean("left"))
        return response.getJSONObject("control_acceptance")
    }

    suspend fun sendControl(fanout: GroupFanout) =
        transport.request(
            "POST",
            "/v1/groups/${fanout.group}/controls",
            JSONObject(fanout.body),
            device,
        )

    suspend fun send(fanout: GroupFanout) =
        transport.request(
            "POST",
            "/v1/groups/${fanout.group}/messages",
            JSONObject(fanout.body),
            device,
        )

    suspend fun resolve(original: PreparedGroupOperation): GroupOperationResolution {
        val result =
            transport.request(
                "POST",
                "/v1/groups/${original.group}/operations/${original.request}/cancel",
                JSONObject(original.body),
                device,
            )
        return original.resolution(result)
    }
}
