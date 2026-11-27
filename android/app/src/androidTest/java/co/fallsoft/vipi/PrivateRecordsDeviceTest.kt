package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PrivateRecordsDeviceTest {
    @Test
    fun survivesReopenRejectsTamperingAndBindsRecordName() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val records = PrivateRecords(context)
        val first = File(context.noBackupFilesDir, "private-records/test-one")
        val second = File(context.noBackupFilesDir, "private-records/test-two")
        try {
            records.write("test-one", JSONObject().put("token", "synthetic-secret"))
            assertEquals(
                "synthetic-secret",
                PrivateRecords(context).read("test-one")!!.getString("token"),
            )
            assertFalse(first.readBytes().toString(Charsets.UTF_8).contains("synthetic-secret"))
            second.writeBytes(first.readBytes())
            assertTrue(runCatching { records.read("test-two") }.isFailure)
            val bytes = first.readBytes()
            bytes[bytes.lastIndex] = (bytes.last().toInt() xor 1).toByte()
            first.writeBytes(bytes)
            assertTrue(runCatching { records.read("test-one") }.isFailure)
        } finally {
            records.remove("test-one")
            records.remove("test-two")
        }
    }
}
