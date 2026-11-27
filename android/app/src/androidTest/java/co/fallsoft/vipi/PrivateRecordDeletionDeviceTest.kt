package co.fallsoft.vipi

import android.content.ContextWrapper
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.util.UUID
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PrivateRecordDeletionDeviceTest {
    @Test
    fun accountDeletionDoesNotClaimCompletionWithEncryptedSidecarResidue() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val app = instrumentation.targetContext
        val legacyControl =
            InstrumentationRegistry.getArguments().getString("legacyDeleteControl") == "true"
        val root = File(app.cacheDir, "private-delete-${UUID.randomUUID()}").apply { mkdirs() }
        val context =
            object : ContextWrapper(app) {
                override fun getNoBackupFilesDir() = root
            }
        val store = PrivateDeletionStore(context)
        val transport =
            object : DeletionTransport {
                override suspend fun submit(record: DeletionRecord): JSONObject =
                    error("No network in native deletion fixture")

                override suspend fun status(record: DeletionRecord): JSONObject =
                    error("No network in native deletion fixture")
            }
        fun coordinator() =
            AccountDeletion(store, transport, { error("Already locally erased fixture") }, {})
        try {
            val record =
                DeletionRecord(
                    UUID.randomUUID(),
                    "user_synthetic_deletion_qa",
                    "synthetic-receipt-only",
                    1,
                    DeletionRecord.Phase.COMPLETED,
                    localErased = true,
                )
            store.save(record)
            val deletion = coordinator()
            val base = File(root, "private-records/account-deletion")
            val pending = File(base.path + ".new")
            val backup = File(base.path + ".bak")
            assertTrue(pending.mkdir())
            File(pending, "synthetic-encrypted-residue").writeBytes(base.readBytes())
            backup.writeBytes(base.readBytes())
            deletion.finish()
            assertTrue("Real nonempty-directory deletion must fail", pending.exists())
            val result =
                JSONObject()
                    .put("synthetic", true)
                    .put("control", legacyControl)
                    .put(
                        "failure",
                        "nonempty owned .new directory containing synthetic encrypted receipt",
                    )
                    .put("not_a_session_resurrection_claim", true)
            if (legacyControl) {
                assertFalse("Old remove incorrectly reports completion", deletion.active)
                assertNull(deletion.notice)
                assertFalse(base.exists())
                assertFalse(backup.exists())
                result.put("old_reported_completion_with_residue", true)
            } else {
                assertTrue(deletion.active)
                assertNotNull(deletion.notice)
                assertTrue("Authoritative receipt remains available for retry", base.exists())
                val reopened = coordinator()
                assertTrue(reopened.active)
                assertEquals(record, reopened.pending)
                assertTrue(pending.deleteRecursively()) // Clear only this test's owned blocker.
                reopened.finish()
                assertFalse(reopened.active)
                assertNull(reopened.notice)
                for (file in listOf(base, pending, backup)) assertFalse(file.exists())
                assertNull(store.load())
                result
                    .put("retry_survives_coordinator_reopen", true)
                    .put("retry_clears_all_three_paths", true)
            }
            val out = File(app.filesDir, "private-delete-qualification").apply { mkdirs() }
            File(out, if (legacyControl) "legacy-control.json" else "candidate.json")
                .writeText(result.toString(2))
        } finally {
            assertTrue(root.deleteRecursively())
        }
    }
}
