package co.fallsoft.vipi

import android.content.Context
import android.content.ContextWrapper
import android.database.sqlite.SQLiteDatabase
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.security.KeyPairGenerator
import java.security.MessageDigest
import java.security.Signature
import java.security.spec.ECGenParameterSpec
import java.util.UUID

/** Synthetic signed databases only; never touches live app pack state. */
@RunWith(AndroidJUnit4::class)
class VocabularyPackActivationDeviceTest {
    private class Fixture {
        val app = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(app.cacheDir, "pack-activation-${UUID.randomUUID()}").apply { mkdirs() }
        val context = object : ContextWrapper(app) {
            override fun getFilesDir() = File(root, "files").apply { mkdirs() }
            override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() }
        }
        val pair = KeyPairGenerator.getInstance("EC").apply { initialize(ECGenParameterSpec("secp256r1")) }.generateKeyPair()
        val keys = mapOf("atomic-activation-qa" to pair.public.encoded)
        val directory get() = File(context.filesDir, "language-packs")
        val records get() = PrivateRecords(context)
        fun store() = VocabularyPackStore(context, keys)
        data class Pack(val manifest: ByteArray, val signature: ByteArray, val database: ByteArray)
        fun pack(revision: Int, target: String): Pack {
            val file = File(root, "synthetic-${UUID.randomUUID()}.sqlite")
            SQLiteDatabase.openOrCreateDatabase(file, null).use { db ->
                db.execSQL("PRAGMA application_id=1447645257")
                db.execSQL("PRAGMA user_version=1")
                db.execSQL("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
                db.execSQL("INSERT INTO metadata VALUES('pack_id','en-es')")
                db.execSQL("CREATE TABLE vocabulary(source TEXT,target TEXT)")
                db.execSQL("INSERT INTO vocabulary VALUES(?,?)", arrayOf("water", target))
            }
            val bytes = file.readBytes(); check(file.delete())
            val manifest = JSONObject().put("key_id", "atomic-activation-qa")
                .put("signature_algorithm", "ECDSA-P256-SHA256").put("pack_id", "en-es")
                .put("revision", revision).put("schema_version", 1).put("source_language", "en")
                .put("target_language", "es").put("normalization", "unicode-nfc-lower")
                .put("file", "vocabulary.sqlite").put("bytes", bytes.size).put("sha256", digest(bytes))
                .toString().toByteArray()
            val signature = Signature.getInstance("SHA256withECDSA").run {
                initSign(pair.private); update(manifest); sign()
            }
            return Pack(manifest, signature, bytes)
        }
        fun install(store: VocabularyPackStore, pack: Pack) = store.install(pack.manifest, pack.signature, pack.database)
        fun target(store: VocabularyPackStore) = store.entries("en-es", "water").single().targets.single()
        fun retain(name: String, packs: List<Pack>, result: JSONObject) {
            val output = File(app.filesDir, "pack-activation/$name").apply { mkdirs() }
            File(output, "public-key.der").writeBytes(pair.public.encoded)
            packs.forEachIndexed { index, p ->
                File(output, "$index-manifest.json").writeBytes(p.manifest)
                File(output, "$index-manifest.sig").writeBytes(p.signature)
                File(output, "$index-database.sqlite").writeBytes(p.database)
            }
            File(output, "receipt.json").writeText(result.put("synthetic", true)
                .put("public_key_sha256", digest(pair.public.encoded)).toString(2))
        }
        fun close() { check(root.deleteRecursively()) }
        companion object { fun digest(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) } }
    }

    @Test fun installUpgradeFailureAndCancellationPreservePreviousActivation() {
        val f = Fixture()
        try {
            val one = f.pack(1, "agua"); val two = f.pack(2, "aguas")
            f.install(f.store(), one)
            assertEquals("agua", f.target(f.store()))
            val accepted = f.records.read("pack-en-es")!!.toString()
            for (stage in listOf(PackActivationCheckpoint.STAGED, PackActivationCheckpoint.BEFORE_COMMIT)) {
                val store = f.store(); var cancel = false
                store.qualificationCheckpoint = { if (it == stage) cancel = true }
                assertTrue(runCatching { store.install(two.manifest, two.signature, two.database) {
                    if (cancel) throw java.util.concurrent.CancellationException("synthetic cancellation")
                } }.exceptionOrNull() is java.util.concurrent.CancellationException)
                assertEquals(accepted, f.records.read("pack-en-es")!!.toString())
                assertEquals("agua", f.target(f.store()))
            }
            // A real owned filesystem failure at PrivateRecords.startWrite.
            val blocked = File(f.context.noBackupFilesDir, "private-records/pack-en-es.new")
            assertTrue(blocked.mkdir()); File(blocked, "keep").writeText("synthetic blocker")
            assertTrue(runCatching { f.install(f.store(), two) }.isFailure)
            assertEquals(accepted, f.records.read("pack-en-es")!!.toString())
            assertEquals("agua", f.target(f.store()))
            assertTrue(blocked.deleteRecursively())
            f.install(f.store(), two)
            assertEquals("aguas", f.target(f.store()))
            assertEquals(VocabularyPackState.ACTIVE, f.store().status("en-es").state)
            assertEquals(2, f.store().status("en-es").revision)
            assertFalse(f.store().status("en-es").cleanupPending)
            f.retain("precommit", listOf(one, two), JSONObject().put("passed", true)
                .put("cancel_stages", "staged,before_commit").put("write_failure", "owned AtomicFile new-path directory")
                .put("reopened_previous_after_each_failure", true))
        } finally { f.close() }
    }

    @Test fun committedUpgradeAndRemovalRemainAuthoritativeWhenCleanupFails() {
        val f = Fixture()
        try {
            val one = f.pack(1, "agua"); val two = f.pack(2, "aguas")
            f.install(f.store(), one)
            val store = f.store()
            store.qualificationCheckpoint = { if (it == PackActivationCheckpoint.BEFORE_DELETE) throw java.io.IOException("synthetic delete failure") }
            assertEquals("en-es", f.install(store, two))
            assertEquals("aguas", f.target(f.store()))
            assertTrue(f.store().status("en-es").cleanupPending)
            val removed = store.remove("en-es")
            assertEquals(VocabularyPackState.INACTIVE, removed.state)
            assertEquals(2, removed.revision); assertTrue(removed.cleanupPending)
            assertTrue(f.store().entries("en-es", "water").isEmpty())
            assertTrue(runCatching { f.install(f.store(), one) }.isFailure)
            // Same exact revision is a valid reinstall and completes deferred cleanup.
            f.install(f.store(), two)
            assertEquals("aguas", f.target(f.store()))
            assertFalse(f.store().status("en-es").cleanupPending)
            val committed = f.store()
            committed.qualificationCheckpoint = { if (it == PackActivationCheckpoint.AFTER_COMMIT) throw java.util.concurrent.CancellationException() }
            assertEquals("en-es", f.install(committed, two))
            assertEquals("aguas", f.target(f.store()))
            f.retain("postcommit-removal", listOf(one, two), JSONObject().put("passed", true)
                .put("cleanup_failure_visible", true).put("postcommit_cancellation_reported_as_success", true))
        } finally { f.close() }
    }

    @Test fun legacyMetadataCannotBecomeTrustedWithoutVerifiedReinstall() {
        val f = Fixture()
        try {
            val one = f.pack(1, "agua"); val two = f.pack(2, "aguas")
            val manifest = JSONObject(two.manifest.toString(Charsets.UTF_8))
            f.records.write("pack-en-es", JSONObject().put("revision", 2).put("hash", manifest.getString("sha256")))
            f.directory.mkdirs()
            val destination = File(f.directory, "en-es-2-${manifest.getString("sha256")}.sqlite")
            destination.writeBytes(two.database)
            // Deliberately fabricated metadata cannot override the highwater or
            // become an activation record, even with a legitimate payload.
            val pointer = File(f.directory, "en-es.json")
            pointer.writeText(JSONObject().put("file", destination.name)
                .put("manifest", manifest.put("source_language", "fr")).toString())
            val before = pointer.readBytes()
            assertEquals(VocabularyPackState.REINSTALL_REQUIRED, f.store().status("en-es").state)
            assertTrue(runCatching { f.target(f.store()) }.exceptionOrNull() is VocabularyPackReinstallRequired)
            assertTrue(runCatching { f.store().remove("en-es") }.exceptionOrNull() is VocabularyPackReinstallRequired)
            assertArrayEquals(before, pointer.readBytes())
            assertArrayEquals(two.database, destination.readBytes())
            assertEquals(2, f.records.read("pack-en-es")!!.getInt("revision"))
            assertTrue(runCatching { f.install(f.store(), one) }.isFailure)
            f.install(f.store(), two)
            assertEquals("aguas", f.target(f.store()))
            assertFalse(pointer.exists())
            f.retain("legacy-reinstall", listOf(one, two), JSONObject().put("passed", true)
                .put("fabricated_pointer_ignored", true).put("legacy_highwater_preserved", true))
        } finally { f.close() }
    }

    @Test fun missingCorruptAndUntrustedPacksNeverFallBackOrDowngrade() {
        val f = Fixture()
        try {
            val one = f.pack(1, "agua"); val two = f.pack(2, "aguas"); val conflict = f.pack(2, "conflict")
            f.install(f.store(), one)
            val store = f.store()
            store.qualificationCheckpoint = { if (it == PackActivationCheckpoint.BEFORE_DELETE) throw java.io.IOException() }
            f.install(store, two)
            val activeFile = File(f.directory, f.records.read("pack-en-es")!!.getJSONObject("active").getString("file"))
            val original = activeFile.readBytes()
            val damaged = original.copyOf(); damaged[damaged.lastIndex] = (damaged.last().toInt() xor 1).toByte()
            activeFile.writeBytes(damaged)
            assertEquals(VocabularyPackState.REINSTALL_REQUIRED, f.store().status("en-es").state)
            assertTrue(runCatching { f.target(f.store()) }.exceptionOrNull() is VocabularyPackReinstallRequired)
            assertTrue(activeFile.delete())
            assertTrue(runCatching { f.target(f.store()) }.exceptionOrNull() is VocabularyPackReinstallRequired)
            assertTrue(runCatching { f.install(f.store(), one) }.isFailure)
            f.install(f.store(), two)
            assertEquals("aguas", f.target(f.store()))
            assertTrue(runCatching { f.install(f.store(), conflict) }.isFailure)
            assertTrue(runCatching { f.store().install(two.manifest, two.signature, damaged) }.isFailure)
            val signature = two.signature.copyOf(); signature[signature.lastIndex] = (signature.last().toInt() xor 1).toByte()
            assertTrue(runCatching { f.store().install(two.manifest, signature, two.database) }.isFailure)
            assertTrue(runCatching { f.install(VocabularyPackStore(f.context, emptyMap()), two) }.isFailure)
            assertEquals("aguas", f.target(f.store()))
            val accepted = f.records.read("pack-en-es")!!.getJSONObject("active")
            assertArrayEquals(two.manifest, android.util.Base64.decode(accepted.getString("manifest_bytes"), android.util.Base64.NO_WRAP))
            assertArrayEquals(two.signature, android.util.Base64.decode(accepted.getString("signature"), android.util.Base64.NO_WRAP))
            f.retain("integrity", listOf(one, two, conflict), JSONObject().put("passed", true)
                .put("original_signed_manifest_preserved", true).put("older_leftover_never_selected", true))
        } finally { f.close() }
    }

    @Test fun concurrentHandlesSerializeRollbackAndRemovalCleanup() {
        val f = Fixture(); val executor = java.util.concurrent.Executors.newFixedThreadPool(2)
        try {
            val one = f.pack(1, "agua"); val two = f.pack(2, "aguas"); val three = f.pack(3, "third")
            f.install(f.store(), one)
            val staged = java.util.concurrent.CountDownLatch(1); val release = java.util.concurrent.CountDownLatch(1)
            val newer = f.store()
            newer.qualificationCheckpoint = { if (it == PackActivationCheckpoint.STAGED) {
                staged.countDown(); check(release.await(5, java.util.concurrent.TimeUnit.SECONDS))
            } }
            val newFuture = executor.submit<String> { f.install(newer, three) }
            assertTrue(staged.await(5, java.util.concurrent.TimeUnit.SECONDS))
            val oldStarted = java.util.concurrent.CountDownLatch(1)
            val oldFuture = executor.submit<Boolean> { oldStarted.countDown(); runCatching { f.install(f.store(), two) }.isFailure }
            assertTrue(oldStarted.await(5, java.util.concurrent.TimeUnit.SECONDS)); release.countDown()
            assertEquals("en-es", newFuture.get(5, java.util.concurrent.TimeUnit.SECONDS))
            assertTrue(oldFuture.get(5, java.util.concurrent.TimeUnit.SECONDS))
            assertEquals("third", f.target(f.store()))
            val deleting = java.util.concurrent.CountDownLatch(1); val finishDelete = java.util.concurrent.CountDownLatch(1)
            val remover = f.store()
            remover.qualificationCheckpoint = { if (it == PackActivationCheckpoint.BEFORE_DELETE) {
                deleting.countDown(); check(finishDelete.await(5, java.util.concurrent.TimeUnit.SECONDS))
            } }
            val removeFuture = executor.submit<VocabularyPackStatus> { remover.remove("en-es") }
            assertTrue(deleting.await(5, java.util.concurrent.TimeUnit.SECONDS))
            val reinstallStarted = java.util.concurrent.CountDownLatch(1)
            val reinstallFuture = executor.submit<String> { reinstallStarted.countDown(); f.install(f.store(), three) }
            assertTrue(reinstallStarted.await(5, java.util.concurrent.TimeUnit.SECONDS)); finishDelete.countDown()
            assertEquals(VocabularyPackState.INACTIVE, removeFuture.get(5, java.util.concurrent.TimeUnit.SECONDS).state)
            assertEquals("en-es", reinstallFuture.get(5, java.util.concurrent.TimeUnit.SECONDS))
            assertEquals("third", f.target(f.store()))
            f.retain("concurrent-handles", listOf(one, two, three), JSONObject().put("passed", true)
                .put("older_install_cannot_win", true).put("old_removal_cannot_delete_reinstalled_file", true))
        } finally { executor.shutdownNow(); f.close() }
    }

    @Test fun failedFinishRenameCannotTriggerOldDatabaseCleanup() {
        val f = Fixture()
        try {
            val one = f.pack(1, "agua"); val two = f.pack(2, "aguas")
            f.install(f.store(), one)
            val before = f.records.read("pack-en-es")!!
            val oldFile = File(f.directory, before.getJSONObject("active").getString("file"))
            val store = f.store()
            val base = File(f.context.noBackupFilesDir, "private-records/pack-en-es")
            val detached = File(f.root, "detached-encrypted-new")
            store.qualificationRecordWrite = { stage, _ ->
                if (stage == PrivateRecordWriteCheckpoint.BEFORE_FINISH) check(File(base.path + ".new").renameTo(detached))
            }
            val error = runCatching { f.install(store, two) }.exceptionOrNull() as? PrivateRecordWriteFailure
            assertNotNull(error); assertEquals(PrivateRecordCommitState.NOT_COMMITTED, error!!.commitState)
            assertTrue(oldFile.exists())
            assertEquals(before.toString(), f.records.read("pack-en-es")!!.toString())
            assertEquals("agua", f.target(f.store()))
            assertTrue(f.store().status("en-es").cleanupPending)
            f.install(f.store(), two)
            assertEquals("aguas", f.target(f.store()))
            assertFalse(oldFile.exists())
            f.retain("finish-rename", listOf(one, two), JSONObject().put("passed", true)
                .put("commit_state", error.commitState.name).put("old_database_preserved_on_failure", true)
                .put("failure", "new pathname moved after explicit file sync, before actual framework finishWrite"))
        } finally { f.close() }
    }

    @Test fun explicitFileAndDirectorySyncErrorsRemainObservable() {
        val f = Fixture()
        try {
            val one = f.pack(1, "agua"); val two = f.pack(2, "aguas")
            f.install(f.store(), one)
            val oldFile = File(f.directory, f.records.read("pack-en-es")!!.getJSONObject("active").getString("file"))
            val before = f.store()
            before.qualificationRecordWrite = { stage, fd ->
                if (stage == PrivateRecordWriteCheckpoint.BEFORE_FILE_SYNC) android.system.Os.close(checkNotNull(fd))
            }
            val first = runCatching { f.install(before, two) }.exceptionOrNull() as? PrivateRecordWriteFailure
            assertNotNull(first); assertEquals(PrivateRecordCommitState.NOT_COMMITTED, first!!.commitState)
            assertEquals("agua", f.target(f.store())); assertTrue(oldFile.exists())
            val after = f.store()
            after.qualificationRecordWrite = { stage, fd ->
                if (stage == PrivateRecordWriteCheckpoint.BEFORE_DIRECTORY_SYNC) android.system.Os.close(checkNotNull(fd))
            }
            val second = runCatching { f.install(after, two) }.exceptionOrNull() as? PrivateRecordWriteFailure
            assertNotNull(second); assertEquals(PrivateRecordCommitState.COMMITTED_DURABILITY_UNCERTAIN, second!!.commitState)
            assertEquals("aguas", f.target(f.store())); assertTrue(oldFile.exists())
            assertTrue(f.store().status("en-es").cleanupPending)
            f.install(f.store(), two)
            assertFalse(oldFile.exists())
            f.retain("explicit-sync", listOf(one, two), JSONObject().put("passed", true)
                .put("file_sync_failure", first.commitState.name).put("directory_sync_failure", second.commitState.name)
                .put("actual_closed_descriptors", true).put("power_loss_durability_proven", false))
        } finally { f.close() }
    }

    @Test fun unreadablePostcommitStateIsUnknownAndNeverCleansPreviousFiles() {
        val f = Fixture()
        val base = File(f.context.noBackupFilesDir, "private-records/pack-en-es")
        try {
            val one = f.pack(1, "agua"); val two = f.pack(2, "aguas")
            f.install(f.store(), one)
            val oldFile = File(f.directory, f.records.read("pack-en-es")!!.getJSONObject("active").getString("file"))
            val store = f.store()
            store.qualificationRecordWrite = { stage, _ ->
                if (stage == PrivateRecordWriteCheckpoint.AFTER_FINISH) check(base.setReadable(false, false))
            }
            val error = runCatching { f.install(store, two) }.exceptionOrNull() as? PrivateRecordWriteFailure
            assertNotNull(error); assertEquals(PrivateRecordCommitState.UNKNOWN, error!!.commitState)
            assertTrue(oldFile.exists())
            assertTrue(base.setReadable(true, true))
            assertEquals("aguas", f.target(f.store()))
            assertTrue(f.store().status("en-es").cleanupPending)
            f.retain("unknown-commit", listOf(one, two), JSONObject().put("passed", true)
                .put("commit_state", error.commitState.name).put("old_database_preserved", true)
                .put("failure", "owned encrypted record made unreadable after finishWrite; read permission restored after assertion"))
        } finally { base.setReadable(true, true); f.close() }
    }

    @Test fun versionedRecordMustExplicitlyDeclareItsActiveState() {
        val f = Fixture()
        try {
            val one = f.pack(1, "agua"); val two = f.pack(2, "aguas")
            f.install(f.store(), one)
            val original = f.records.read("pack-en-es")!!
            val malformed = JSONObject(original.toString()).apply { remove("active") }
            f.records.write("pack-en-es", malformed)
            assertTrue(runCatching { f.store().status("en-es") }.isFailure)
            assertTrue(runCatching { f.target(f.store()) }.isFailure)
            assertTrue(runCatching { f.store().remove("en-es") }.isFailure)
            assertTrue(runCatching { f.install(f.store(), two) }.isFailure)
            assertEquals(malformed.toString(), f.records.read("pack-en-es")!!.toString())
            f.records.write("pack-en-es", original)
            assertEquals("agua", f.target(f.store()))
            f.retain("missing-active", listOf(one), JSONObject().put("passed", true)
                .put("missing_active_fails_closed", true).put("no_silent_inactive_transition", true))
        } finally { f.close() }
    }

}
