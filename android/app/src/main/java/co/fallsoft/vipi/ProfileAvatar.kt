package co.fallsoft.vipi

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Rect
import android.util.Base64
import java.io.ByteArrayOutputStream
import java.util.UUID
import org.json.JSONObject

internal data class ProfileAvatar(val revision: Long, val jpeg: ByteArray?) {
    fun json(): JSONObject =
        JSONObject()
            .put("revision", revision)
            .put(
                "jpeg",
                jpeg?.let { Base64.encodeToString(it, Base64.NO_WRAP) } ?: JSONObject.NULL,
            )

    companion object {
        fun parse(json: JSONObject?): ProfileAvatar? = runCatching {
            requireNotNull(json)
            val revision = json.get("revision")
            require(revision is Long || revision is Int)
            val stamp = (revision as Number).toLong()
            require(stamp > 0 && json.has("jpeg"))
            if (json.isNull("jpeg")) return@runCatching ProfileAvatar(stamp, null)
            val encoded = json.get("jpeg") as String
            require(encoded.length in 1..5464)
            val bytes = Base64.decode(encoded, Base64.NO_WRAP)
            require(bytes.size in 1..4096)
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
            require(
                bounds.outWidth == 96 &&
                    bounds.outHeight == 96 &&
                    bounds.outMimeType == "image/jpeg"
            )
            requireNotNull(BitmapFactory.decodeByteArray(bytes, 0, bytes.size)).recycle()
            ProfileAvatar(stamp, bytes)
        }
            .getOrNull()

        fun crop(input: Bitmap): ByteArray {
            val side = minOf(input.width, input.height)
            val x = (input.width - side) / 2
            val y = (input.height - side) / 2
            val out = Bitmap.createBitmap(96, 96, Bitmap.Config.ARGB_8888)
            try {
                Canvas(out).apply {
                    drawColor(android.graphics.Color.WHITE)
                    drawBitmap(
                        input,
                        Rect(x, y, x + side, y + side),
                        Rect(0, 0, 96, 96),
                        Paint(Paint.FILTER_BITMAP_FLAG),
                    )
                }
                for (quality in 88 downTo 8 step 8) {
                    val bytes =
                        ByteArrayOutputStream().use { stream ->
                            check(out.compress(Bitmap.CompressFormat.JPEG, quality, stream))
                            stream.toByteArray()
                        }
                    if (bytes.size <= 4096) return bytes
                }
                error("Cannot encode profile photo")
            } finally {
                out.recycle()
            }
        }
    }
}

internal fun MessageVault.avatar(peer: UUID): ProfileAvatar? =
    get("profile-avatar", peer.toString())?.let {
        ProfileAvatar.parse(JSONObject(it.toString(Charsets.UTF_8)))
    }

internal fun MessageVault.storeAvatar(peer: UUID, avatar: ProfileAvatar) {
    put("profile-avatar", peer.toString(), avatar.json().toString().toByteArray())
}

/** Called inside the same transaction as Signal encryption and the durable envelope. */
internal fun MessageVault.attachOwnAvatar(payload: JSONObject, peer: UUID, message: UUID) {
    val avatar = avatar(account) ?: return
    val device = get("peer-device", peer.toString())?.toString(Charsets.UTF_8) ?: return
    val contact = "$peer/$device"
    val delivered = get("avatar-delivered", contact)?.toString(Charsets.UTF_8)?.toLongOrNull() ?: 0
    if (delivered >= avatar.revision) return
    payload.put("profile_avatar", avatar.json())
    if (payload.toString().toByteArray().size > 60_000) {
        payload.remove("profile_avatar")
        return
    }
    put(
        "avatar-outgoing",
        message.toString(),
        JSONObject()
            .put("contact", contact)
            .put("revision", avatar.revision)
            .toString()
            .toByteArray(),
    )
}

internal fun MessageVault.avatarStatus(message: UUID, status: String) {
    if (status == "accepted") return
    val receipt = get("avatar-outgoing", message.toString()) ?: return
    if (status == "read" || status == "delivered") {
        val data = JSONObject(receipt.toString(Charsets.UTF_8))
        val contact = data.getString("contact")
        val revision = data.getLong("revision")
        if (
            revision >
                (get("avatar-delivered", contact)?.toString(Charsets.UTF_8)?.toLongOrNull() ?: 0)
        ) {
            put("avatar-delivered", contact, revision.toString().toByteArray())
        }
    }
    remove("avatar-outgoing", message.toString())
}
