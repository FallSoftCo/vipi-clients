package co.fallsoft.vipi

import android.content.ContextWrapper
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.io.IOException
import java.security.KeyStore
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

class AccountDeletionDeviceTest {
    private class Store : DeletionStore {
        var record: DeletionRecord? = null; var failSave = false; var failLoad = false
        override fun load(): DeletionRecord? { if (failLoad) throw IOException(); return record }
        override fun save(record: DeletionRecord) { if (failSave) { failSave = false; throw IOException() }; this.record = record }
        override fun remove() { record = null }
    }
    private class Transport : DeletionTransport {
        var submitCount = 0; var statusCount = 0
        var submitBlock: (DeletionRecord) -> JSONObject = { error("Unexpected submit") }
        var statusBlock: (DeletionRecord) -> JSONObject = { throw ServiceFailure(404, "deletion_receipt_unavailable") }
        override suspend fun submit(record: DeletionRecord): JSONObject { submitCount++; return submitBlock(record) }
        override suspend fun status(record: DeletionRecord): JSONObject { statusCount++; return statusBlock(record) }
    }
    private fun reply(account: UUID, status: String = "deleted") = JSONObject().put("account_id", account).put("status", status)
    @Test fun lostResponseRecoversAfterRestartWithoutResubmission() = runBlocking { withContext(Dispatchers.Main) {
        val store = Store(); val api = Transport(); val account = UUID.randomUUID()
        var closed = false; var erased = 0; val signedOut = mutableListOf<String>()
        val first = AccountDeletion(store, api, { erased++ }, { signedOut += it })
        first.begin(account, "user_deletion_qa") { closed = true }
        val saved = requireNotNull(store.record); assertTrue(closed); assertEquals(43, saved.secret.length)
        api.submitBlock = { record ->
            assertEquals(store.record?.secret, record.secret)
            api.statusBlock = { receipt -> assertEquals(saved.secret, receipt.secret); reply(account) }
            throw IOException("Lost response")
        }
        first.resume(); assertEquals(0, erased); assertEquals(DeletionRecord.Phase.PREPARED, first.pending?.phase); assertNotNull(first.notice)
        val restarted = AccountDeletion(store, api, { erased++ }, { signedOut += it })
        restarted.resume()
        assertEquals(1, api.submitCount); assertEquals(1, erased); assertEquals(DeletionRecord.Phase.COMPLETED, restarted.pending?.phase)
        assertEquals(listOf("user_deletion_qa"), signedOut)
        restarted.finish(); assertNull(store.record); assertFalse(restarted.active)
    } }
    @Test fun mismatchAndExpiredReceiptNeverEraseOrInventSuccess() = runBlocking { withContext(Dispatchers.Main) {
        val store = Store(); val api = Transport()
        val manager = AccountDeletion(store, api, { fail("Unconfirmed deletion erased local data") }, { fail() })
        manager.begin(UUID.randomUUID(), "user_qa") {}
        api.submitBlock = { reply(UUID.randomUUID()) }
        manager.resume(); assertEquals(DeletionRecord.Phase.PREPARED, manager.pending?.phase); assertNotNull(manager.notice)
        val secret = store.record!!.secret
        api.submitBlock = { throw ServiceFailure(401, "recent_sign_in_required") }
        manager.resume(); assertTrue(manager.needsSignIn); assertEquals(secret, store.record?.secret)
        store.record = store.record!!.copy(createdAt = System.currentTimeMillis() - 8 * 86_400_000L)
        val restart = AccountDeletion(store, api, { fail() }, { fail() })
        val count = api.submitCount; restart.resume()
        assertEquals(count, api.submitCount); assertTrue(restart.active); assertNotNull(restart.notice)
    } }
    @Test fun receiptWriteAndCleanupFailuresRemainRecoverable() = runBlocking { withContext(Dispatchers.Main) {
        val store = Store(); val api = Transport(); var attempts = 0
        val manager = AccountDeletion(store, api, { attempts++; if (attempts == 1) throw IOException() }, {})
        manager.begin(UUID.randomUUID(), "user_qa") {}
        api.statusBlock = { reply(it.account) }; store.failSave = true
        manager.resume(); assertEquals(0, attempts); assertEquals(DeletionRecord.Phase.PREPARED, manager.pending?.phase)
        manager.resume(); assertEquals(1, attempts); assertEquals(DeletionRecord.Phase.COMPLETED, manager.pending?.phase)
        assertFalse(manager.pending!!.localErased); manager.finish(); assertTrue(manager.active)
        val checks = api.statusCount
        manager.resume(); assertEquals(2, attempts); assertEquals(checks, api.statusCount)
        assertTrue(manager.pending!!.localErased); manager.finish(); assertFalse(manager.active)
        store.failLoad = true
        val unreadable = AccountDeletion(store, api, { fail() }, { fail() })
        assertTrue(unreadable.active); assertTrue(unreadable.loadFailed)
    } }
    @Test fun eraseOnlyConfirmedAccountsFilesAndKeys() {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(base.cacheDir, "delete-${UUID.randomUUID()}").apply { mkdirs() }
        val context = object : ContextWrapper(base) { override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() } }
        val account = UUID.randomUUID(); val other = UUID.randomUUID(); val user = "delete-fixture-${UUID.randomUUID()}"
        val digest = MessageDigest.getInstance("SHA-256").digest(user.toByteArray()).joinToString("") { "%02x".format(it) }
        val password = "synthetic backup password only"
        val ownerStaging = HistoryTransferFiles.temporary(context, account)
        val otherStaging = HistoryTransferFiles.temporary(context, other)
        val externalExport = File(root, "user-selected/Documents/keep.vipihistory").apply { parentFile!!.mkdirs() }
        val legacyUnscoped = File(context.noBackupFilesDir, "history-transfer/unattributed-legacy.vipihistory")
        try {
            MessageVault(context, account).use { target ->
                target.transaction { target.put("test", "body", "secret".toByteArray()) }
                HistoryBackupStore(target).export(ownerStaging, password)
            }
            // This export outlives its transfer model, as after process death.
            ownerStaging.copyTo(externalExport)
            ownerStaging.copyTo(legacyUnscoped)
            val externalBytes = externalExport.readBytes()
            MessageVault(context, other).use { preserved ->
                preserved.transaction { preserved.put("test", "body", "keep".toByteArray()) }
                HistoryBackupStore(preserved).export(otherStaging, password)
                val otherBytes = otherStaging.readBytes()
                PrivateRecords(context).write("profile-$digest", JSONObject().put("test", true))
                val record = DeletionRecord(account, user, "a".repeat(43), System.currentTimeMillis(), DeletionRecord.Phase.REQUESTED)
                AccountDeletion.eraseLocal(context, record); AccountDeletion.eraseLocal(context, record)
                assertFalse(File(context.noBackupFilesDir, "messages/$account").exists())
                assertFalse(ownerStaging.exists())
                assertFalse(ownerStaging.parentFile!!.exists())
                assertArrayEquals(otherBytes, otherStaging.readBytes())
                assertArrayEquals(externalBytes, externalExport.readBytes())
                assertArrayEquals(externalBytes, legacyUnscoped.readBytes())
                assertEquals(HistoryBackupCodec.Summary(0, 0), HistoryBackupStore(preserved).validate(otherStaging, password).summary)
                assertEquals(HistoryBackupCodec.Summary(0, 0), HistoryBackupCodec.inspect(externalExport, password, account).summary)
                assertFalse(KeyStore.getInstance("AndroidKeyStore").apply { load(null) }.containsAlias("co.fallsoft.vipi.messages.$account"))
                assertNull(PrivateRecords(context).read("profile-$digest"))
                preserved.transaction { assertArrayEquals("keep".toByteArray(), preserved.get("test", "body")) }
            }
        } finally {
            root.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply { load(null); listOf(account, other).forEach { deleteEntry("co.fallsoft.vipi.messages.$it") } }
        }
    }
    @Test fun clearRemovesOnlyItsCompletedTransferCopies() {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(base.cacheDir, "backup-cancel-${UUID.randomUUID()}").apply { mkdirs() }
        val context = object : ContextWrapper(base) { override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() } }
        val account = UUID.randomUUID(); val other = UUID.randomUUID()
        try {
            val password = "synthetic backup cancellation password"
            val staged = HistoryTransferFiles.temporary(context, account)
            HistoryBackupCodec.write(staged, password, account) {}
            val exported = HistoryTransferFiles.temporary(context, account)
            staged.copyTo(exported)
            val otherActive = HistoryTransferFiles.temporary(context, other)
            HistoryBackupCodec.write(otherActive, password, other) {}
            val otherBytes = otherActive.readBytes()
            val model = HistoryBackupModel().also { it.staged = staged; it.exported = exported; it.password = "not persisted"; it.confirmation = "not persisted" }
            model.clear(); model.clear()
            assertFalse(staged.exists()); assertFalse(exported.exists())
            assertArrayEquals(otherBytes, otherActive.readBytes())
            assertEquals(HistoryBackupCodec.Summary(0, 0), HistoryBackupCodec.inspect(otherActive, password, other).summary)
            assertNull(model.staged); assertNull(model.exported); assertEquals("", model.password); assertEquals("", model.confirmation)
            assertFalse(HistoryTransferFiles.temporary(context, account).canonicalPath.startsWith(otherActive.parentFile!!.canonicalPath + File.separator))
        } finally { root.deleteRecursively() }
    }
    @Test fun clearDuringEncryptedExportRemovesItsUnfinishedCopyAfterIoStops() = runBlocking {
        val base = InstrumentationRegistry.getInstrumentation().targetContext
        val root = File(base.cacheDir, "backup-active-cancel-${UUID.randomUUID()}").apply { mkdirs() }
        val context = object : ContextWrapper(base) { override fun getNoBackupFilesDir() = File(root, "private").apply { mkdirs() } }
        val account = UUID.randomUUID(); val other = UUID.randomUUID()
        val entered = CompletableDeferred<Unit>(); val release = CountDownLatch(1)
        val model = HistoryBackupModel()
        var exporting: Job? = null
        try {
            val password = "synthetic active export password"
            val owned = HistoryTransferFiles.temporary(context, account)
            val otherActive = HistoryTransferFiles.temporary(context, other)
            HistoryBackupCodec.write(otherActive, password, other) {}
            val otherBytes = otherActive.readBytes()
            MessageVault(context, account).use { vault ->
                exporting = launch(Dispatchers.Main) {
                    model.prepareExport(owned) { file ->
                        val activeJob = currentCoroutineContext()[Job]!!
                        withContext(Dispatchers.IO) {
                            var checks = 0
                            HistoryBackupStore(vault).export(file, password) {
                                // Stop after the codec has encrypted its metadata,
                                // while the actual export still owns the output.
                                if (++checks >= 2) {
                                    entered.complete(Unit)
                                    check(release.await(10, TimeUnit.SECONDS)) { "Export cancellation fixture timed out" }
                                }
                                activeJob.ensureActive()
                            }
                        }
                    }
                }
                withContext(Dispatchers.Main) { model.job = exporting }
                // Wait for actual encrypted output after the full password KDF on this device.
                withTimeout(120_000) { entered.await() }
                assertTrue(owned.exists())
                withContext(Dispatchers.Main) { model.clear(); model.clear() }
                release.countDown()
                withTimeout(15_000) { exporting!!.join() }
                assertTrue(exporting!!.isCancelled)
                assertFalse(owned.exists()); assertNull(model.exported)
                assertArrayEquals(otherBytes, otherActive.readBytes())
                assertEquals(HistoryBackupCodec.Summary(0, 0), HistoryBackupCodec.inspect(otherActive, password, other).summary)
            }
        } finally {
            release.countDown()
            withContext(NonCancellable) { exporting?.cancelAndJoin() }
            root.deleteRecursively()
            KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry("co.fallsoft.vipi.messages.$account") }
        }
    }
    @Test fun cannotFinishUntilSavedSignInIsRemoved() = runBlocking { withContext(Dispatchers.Main) {
        val store = Store(); val api = Transport(); var attempts = 0
        val manager = AccountDeletion(store, api, {}, { attempts++; if (attempts == 1) throw IOException() })
        manager.begin(UUID.randomUUID(), "user_qa") {}
        api.statusBlock = { reply(it.account) }
        manager.resume(); manager.finish()
        assertTrue(manager.active); assertFalse(manager.pending!!.localErased)
        manager.resume(); manager.finish()
        assertFalse(manager.active); assertEquals(2, attempts)
    } }
}
