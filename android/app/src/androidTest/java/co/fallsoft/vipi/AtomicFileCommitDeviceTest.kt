package co.fallsoft.vipi

import android.system.Os
import android.util.AtomicFile
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.util.UUID
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Direct checks of the installed framework, not a reimplementation of AtomicFile. */
@RunWith(AndroidJUnit4::class)
class AtomicFileCommitDeviceTest {
    private fun probe(name: String, run: (File, AtomicFile) -> JSONObject) {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(context.cacheDir, "atomic-finish-${UUID.randomUUID()}").apply { mkdirs() }
        try {
            val base = File(root, "record")
            base.writeText("synthetic old value")
            val result =
                run(base, AtomicFile(base))
                    .put("sdk", android.os.Build.VERSION.SDK_INT)
                    .put("fingerprint", android.os.Build.FINGERPRINT)
                    .put("synthetic", true)
            val output = File(context.filesDir, "atomic-finish-control").apply { mkdirs() }
            File(output, "$name.json").writeText(result.toString(2))
        } finally {
            assertTrue(root.deleteRecursively())
        }
    }

    @Test
    fun runtimeFinishWriteCanSilentlyFailToRename() =
        probe("rename") { base, atomic ->
            val stream = atomic.startWrite()
            stream.write("synthetic new value".toByteArray())
            val moved = File(base.parentFile, "detached")
            assertTrue(File(base.path + ".new").renameTo(moved))
            val error = runCatching { atomic.finishWrite(stream) }.exceptionOrNull()
            assertNull("Actual runtime logs the failed rename rather than throwing", error)
            assertEquals("synthetic old value", base.readText())
            assertEquals("synthetic new value", moved.readText())
            JSONObject()
                .put("finish_threw", false)
                .put("base_still_old", true)
                .put("failure", "new pathname moved after startWrite, before finishWrite")
        }

    @Test
    fun runtimeFinishWriteCanSilentlyIgnoreSyncFailure() =
        probe("sync") { base, atomic ->
            val stream = atomic.startWrite()
            stream.write("synthetic unsynced value".toByteArray())
            Os.close(stream.fd)
            val error = runCatching { atomic.finishWrite(stream) }.exceptionOrNull()
            assertNull("Actual runtime logs closed-fd sync failure rather than throwing", error)
            assertEquals("synthetic unsynced value", base.readText())
            JSONObject()
                .put("finish_threw", false)
                .put("new_bytes_visible", true)
                .put("failure", "owned stream descriptor closed before finishWrite")
                .put("power_loss_durability_proven", false)
        }
}
