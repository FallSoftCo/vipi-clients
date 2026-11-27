package co.fallsoft.vipi

import java.util.UUID
import org.json.JSONObject

/**
 * Capture this WITH the original journal before dispatch. Never reconstruct its device from a later
 * login/roster, or its control from newly encrypted bytes. Older pending records without this
 * descriptor remain frozen/retry-only.
 */
internal class PreparedGroupOperation
private constructor(val group: UUID, val request: UUID, val body: String) {
    val expectedEpoch: Int
        get() = JSONObject(body).strictInt("expected_epoch")

    val originalDevice: UUID
        get() = JSONObject(body).uuid("original_device_id")

    fun json() =
        JSONObject()
            .put("version", 1)
            .put("group_id", group)
            .put("request_id", request)
            .put("body", body)

    fun resolution(response: JSONObject): GroupOperationResolution {
        require(response.uuid("group_id") == group && response.uuid("request_id") == request) {
            "Group recovery response belongs to another operation"
        }
        return when (response.getString("status")) {
            "cancelled" -> {
                require(
                    response.strictInt("expected_epoch") == expectedEpoch && !response.has("result")
                )
                GroupOperationResolution.Cancelled(this, response.toString())
            }
            "admitted" ->
                GroupOperationResolution.Admitted(
                    this,
                    response.getJSONObject("result").toString(),
                    response.toString(),
                )
            else ->
                error("Unrecognized group recovery response; preserve the original pending journal")
        }
    }

    companion object {
        private val needs =
            mapOf(
                "rename" to setOf("title"),
                "invite" to setOf("target_id"),
                "accept" to setOf("invite_id"),
                "decline" to setOf("invite_id"),
                "cancel-invite" to setOf("invite_id"),
                "role" to setOf("target_id", "role"),
                "remove" to setOf("target_id"),
                "leave" to emptySet(),
                "control" to emptySet(),
            )

        fun capture(
            group: UUID,
            request: UUID,
            action: String,
            expectedEpoch: Int,
            originalDevice: UUID,
            fields: Map<String, String> = emptyMap(),
            originalControl: GroupFanout? = null,
        ): PreparedGroupOperation {
            require(expectedEpoch > 0 && needs[action] == fields.keys) {
                "Incomplete original group operation descriptor"
            }
            fields["title"]?.let {
                require(
                    it.codePointCount(0, it.length) in 1..80 &&
                        it.isNotBlank() &&
                        it.none(Char::isISOControl)
                )
            }
            fields["role"]?.let { GroupRole.parse(it) }
            fields.filterKeys { it.endsWith("_id") }.values.forEach(UUID::fromString)
            val body =
                JSONObject(fields)
                    .put("action", action)
                    .put("expected_epoch", expectedEpoch)
                    .put("original_device_id", originalDevice)
            originalControl?.let {
                require(
                    action in setOf("control", "role", "remove", "leave") &&
                        it.group == group &&
                        it.epoch == expectedEpoch
                )
                if (action == "control") require(it.message == request)
                val wire = JSONObject(it.body)
                require(wire.uuid("id") == it.message && wire.strictInt("epoch") == expectedEpoch)
                require(action == "control" || !wire.has("invited_user_id"))
                body.put("control", wire)
            }
            require(action != "control" || originalControl != null)
            return PreparedGroupOperation(group, request, body.toString())
        }

        fun parse(value: JSONObject): PreparedGroupOperation {
            require(
                value.keys().asSequence().toSet() ==
                    setOf("version", "group_id", "request_id", "body") &&
                    value.strictInt("version") == 1
            )
            val group = value.uuid("group_id")
            val request = value.uuid("request_id")
            val raw = value.getString("body")
            val body = JSONObject(raw)
            val action = body.getString("action")
            val fields = requireNotNull(needs[action])
            val keys =
                setOf("action", "expected_epoch", "original_device_id") +
                    fields +
                    if (body.has("control")) setOf("control") else emptySet()
            require(body.keys().asSequence().toSet() == keys)
            val control =
                body.optJSONObject("control")?.let {
                    GroupFanout(group, it.uuid("id"), it.strictInt("epoch"), it.toString())
                }
            capture(
                group,
                request,
                action,
                body.strictInt("expected_epoch"),
                body.uuid("original_device_id"),
                fields.associateWith(body::getString),
                control,
            )
            return PreparedGroupOperation(
                group,
                request,
                raw,
            ) // Preserve the original body, including ciphertext bytes.
        }
    }
}

/**
 * A cancellation RECEIPT still requires explicit people review and an atomic archive of the
 * original journal/fanout before a new request may be prepared. An admission reconciles its saved
 * original outcome; never current roster. These types deliberately provide no implicit discard or
 * ratchet rollback.
 */
internal sealed interface GroupOperationResolution {
    val original: PreparedGroupOperation
    val receipt: String

    data class Cancelled(
        override val original: PreparedGroupOperation,
        override val receipt: String,
    ) : GroupOperationResolution

    data class Admitted(
        override val original: PreparedGroupOperation,
        val originalResult: String,
        override val receipt: String,
    ) : GroupOperationResolution
}
