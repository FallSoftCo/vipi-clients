package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import java.util.UUID
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class GroupsRoutingTest {
    private fun packet() =
        JSONObject()
            .put("id", UUID.randomUUID())
            .put("sender_id", UUID.randomUUID())
            .put("sender_device_id", UUID.randomUUID())
            .put("recipient_device_id", UUID.randomUUID())
            .put("created_at", "2026-11-19T18:00:00.000Z")
            .put("cipher_type", 2)
            .put(
                "ciphertext",
                android.util.Base64.encodeToString(
                    ByteArray(64) { 7 },
                    android.util.Base64.NO_WRAP,
                ),
            )

    private fun group(kind: String = "message") =
        packet()
            .put("group_id", UUID.randomUUID())
            .put("group_epoch", 3)
            .put("group_message_id", UUID.randomUUID())
            .put("group_kind", kind)

    @Test
    fun directPacketHasNoGroupContext() {
        assertFalse(GroupIncoming.hasContext(packet()))
    }

    @Test
    fun partialAndUnknownMetadataNeverBecomeDirectText() {
        listOf("group_id", "group_epoch", "group_message_id", "group_kind").forEach { omitted ->
            val packet = group()
            packet.remove(omitted)
            assertTrue(GroupIncoming.hasContext(packet))
            assertThrows(Exception::class.java) { GroupIncoming.parse(packet, UUID.randomUUID()) }
        }
        assertThrows(Exception::class.java) {
            GroupIncoming.parse(group("other"), UUID.randomUUID())
        }
    }

    @Test
    fun controlAndTextRemainDistinct() {
        listOf("message", "control").forEach { kind ->
            assertEquals(kind, GroupIncoming.parse(group(kind), UUID.randomUUID()).kind)
        }
        assertThrows(Exception::class.java) {
            GroupIncoming.parse(group().put("group_epoch", 0), UUID.randomUUID())
        }
    }
}
