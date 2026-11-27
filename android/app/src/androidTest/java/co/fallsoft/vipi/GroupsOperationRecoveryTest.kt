package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import java.util.UUID
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class GroupsOperationRecoveryTest {
    @Test
    fun restartPreservesOriginalDeviceAndDescriptor() {
        val device = UUID.randomUUID()
        val group = UUID.randomUUID()
        val request = UUID.randomUUID()
        val saved =
            PreparedGroupOperation.capture(
                group,
                request,
                "rename",
                4,
                device,
                mapOf("title" to "Coffee friends"),
            )
        val restored = PreparedGroupOperation.parse(JSONObject(saved.json().toString()))
        assertEquals(saved.body, restored.body)
        assertEquals(device, restored.originalDevice)
        assertThrows(IllegalArgumentException::class.java) {
            PreparedGroupOperation.parse(saved.json().put("current_device", UUID.randomUUID()))
        }
        assertThrows(IllegalArgumentException::class.java) {
            PreparedGroupOperation.capture(group, request, "remove", 4, device)
        }
        assertThrows(IllegalArgumentException::class.java) {
            PreparedGroupOperation.capture(
                group,
                request,
                "leave",
                4,
                device,
                mapOf("target_id" to UUID.randomUUID().toString()),
            )
        }
    }

    @Test
    fun mismatchedOrAmbiguousReceiptNeverMeansCancelled() {
        val original =
            PreparedGroupOperation.capture(
                UUID.randomUUID(),
                UUID.randomUUID(),
                "leave",
                3,
                UUID.randomUUID(),
            )
        fun receipt() =
            JSONObject()
                .put("group_id", original.group)
                .put("request_id", original.request)
                .put("status", "cancelled")
                .put("expected_epoch", 3)
        assertTrue(original.resolution(receipt()) is GroupOperationResolution.Cancelled)
        assertThrows(IllegalArgumentException::class.java) {
            original.resolution(receipt().put("request_id", UUID.randomUUID()))
        }
        assertThrows(IllegalArgumentException::class.java) {
            original.resolution(receipt().put("group_id", UUID.randomUUID()))
        }
        assertThrows(IllegalArgumentException::class.java) {
            original.resolution(receipt().put("expected_epoch", 4))
        }
        assertThrows(IllegalStateException::class.java) {
            original.resolution(receipt().put("status", "unknown"))
        }
        assertThrows(Exception::class.java) {
            original.resolution(receipt().put("status", "admitted"))
        }
        val admitted =
            original.resolution(
                receipt().put("status", "admitted").put("result", JSONObject().put("left", true))
            ) as GroupOperationResolution.Admitted
        assertTrue(JSONObject(admitted.originalResult).getBoolean("left"))
        assertEquals(original.body, admitted.original.body)
    }
}
