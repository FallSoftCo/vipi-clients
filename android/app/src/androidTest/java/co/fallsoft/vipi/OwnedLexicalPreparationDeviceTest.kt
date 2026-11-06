package co.fallsoft.vipi

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.nio.channels.FileChannel
import java.nio.file.Files
import java.nio.file.StandardOpenOption.CREATE
import java.nio.file.StandardOpenOption.WRITE
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.CancellationException
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

/** Proposed, UNCOMPILED/UNRUN here. New synthetic UUID roots only; no SQLite query,
 * model, real app cache or actual process termination. Seeded restart state is not
 * a process-death/power-loss qualification. Faults are injected, not real ENOSPC.
 */
@RunWith(AndroidJUnit4::class)
class OwnedLexicalPreparationDeviceTest {
    private val data = ByteArray(512).also { "SQLite format 3\u0000".toByteArray().copyInto(it); it[31] = 7 }
    private fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
    private val hash get() = sha(data)
    private fun fixture(block: (File) -> Unit) {
        val root = File(InstrumentationRegistry.getInstrumentation().targetContext.cacheDir,
            "owned-lexical-fixture-" + UUID.randomUUID())
        check(root.mkdirs())
        try { block(root) } finally { root.deleteRecursively() } // ONLY this newly owned test root.
    }
    private fun prepare(store: OwnedLexicalPreparation): File = store.materialize("d-en", hash, data.size.toLong(),
        accepted = { it.length() == data.size.toLong() && sha(it.readBytes()) == hash },
        writeAndValidate = { file ->
            FileOutputStream(file).use { output ->
                for (chunk in data.asList().chunked(64)) {
                    output.write(chunk.toByteArray())
                    store.checkpoint(OwnedLexicalPreparation.Point.CHUNK_WRITTEN)
                }
                store.syncData(output)
            }
            assertArrayEquals(data, file.readBytes()) // caller's length/hash/header pre-publication equivalent
        })
    private fun pending(root: File) = File(root, OwnedLexicalPreparation.DIRECTORY + "/pending")
    private fun receipts(root: File) = File(root, OwnedLexicalPreparation.DIRECTORY + "/receipts")
    private fun outcomes(root: File) = receipts(root).listFiles().orEmpty().map {
        JSONObject(File(it, "outcome.json").readText())
    }
    private fun oldFinal(root: File): File {
        val bytes = data.copyOf().also { it[31] = 9 }
        return File(root, "d-en-${sha(bytes)}.sqlite").also { it.writeBytes(bytes) }
    }
    private fun seededAttempt(root: File): File {
        // Exact producer receipt-format fixture, not an executing writer/process claim.
        val token = UUID.randomUUID().toString()
        val dir = File(pending(root), token).also { check(it.mkdirs()) }
        File(dir, "intent.json").writeText(JSONObject().put("schema", "vipi-owned-lexical-attempt-1")
            .put("producer", "BundledLexicalCatalog/owned-prepare-1")
            .put("root", sha(root.canonicalPath.toByteArray(Charsets.UTF_8)))
            .put("attempt", token).put("id", "d-en").put("sha256", hash)
            .put("bytes", data.size).put("payload", "payload.sqlite").toString())
        File(dir, "payload.sqlite").writeBytes(data.copyOfRange(0, 80))
        return dir
    }

    @Test fun recordedAbandonedAttemptRecoversButLegacyAndVerifiedRevisionRemain() = fixture { root ->
        val old = oldFinal(root); val oldBytes = old.readBytes()
        val legacy = File(root, "prepare-unrecorded.sqlite").also { it.writeText("legacy must remain") }
        val attempt = seededAttempt(root); val token = attempt.name
        val accepted = prepare(OwnedLexicalPreparation(root))
        assertArrayEquals(data, accepted.readBytes())
        assertFalse(attempt.exists())
        val closed = File(receipts(root), token)
        assertTrue(File(closed, "intent.json").isFile)
        val recovered = JSONObject(File(closed, "outcome.json").readText())
        assertEquals("recovered_abandoned", recovered.getString("state"))
        assertEquals("original_unknown", recovered.getString("publication"))
        assertEquals(80L, recovered.getLong("removed_bytes"))
        assertEquals("legacy must remain", legacy.readText())
        assertArrayEquals(oldBytes, old.readBytes())
        val stamp = accepted.lastModified(); val receiptCount = outcomes(root).size
        assertEquals(accepted, prepare(OwnedLexicalPreparation(root)))
        assertEquals(stamp, accepted.lastModified())
        assertEquals(receiptCount, outcomes(root).size)
    }

    @Test fun activeCooperativeRootLeaseRejectsBeforeAnyRecovery() = fixture { root ->
        val attempt = seededAttempt(root); val payload = File(attempt, "payload.sqlite"); val bytes = payload.readBytes()
        FileChannel.open(File(root, OwnedLexicalPreparation.LOCK).toPath(), CREATE, WRITE).use { channel ->
            channel.lock().use {
                var rejected = false
                try { prepare(OwnedLexicalPreparation(root)) } catch (_: IOException) { rejected = true }
                assertTrue(rejected)
                assertArrayEquals(bytes, payload.readBytes())
                assertFalse(File(attempt, "outcome.json").exists())
            }
        }
        assertArrayEquals(data, prepare(OwnedLexicalPreparation(root)).readBytes())
        assertEquals("recovered_abandoned", JSONObject(File(receipts(root), attempt.name + "/outcome.json").readText()).getString("state"))
    }

    @Test fun malformedUnknownExtraAndSymlinkAttemptsAreHeld() = fixture { root ->
        val unknown = File(pending(root), UUID.randomUUID().toString()).also { check(it.mkdirs()) }
        File(unknown, "intent.json").writeText("{}")
        val unknownPayload = File(unknown, "payload.sqlite").also { it.writeText("unknown") }
        val extra = seededAttempt(root)
        File(extra, "foreign.keep").writeText("uncertain ownership")
        val linked = seededAttempt(root); val linkedPayload = File(linked, "payload.sqlite")
        check(linkedPayload.delete())
        val sentinel = File(root, "unrelated.keep").also { it.writeText("do not follow") }
        Files.createSymbolicLink(linkedPayload.toPath(), sentinel.toPath())
        prepare(OwnedLexicalPreparation(root))
        assertEquals("unknown", unknownPayload.readText())
        assertTrue(File(extra, "payload.sqlite").isFile)
        assertEquals("uncertain ownership", File(extra, "foreign.keep").readText())
        assertTrue(Files.isSymbolicLink(linkedPayload.toPath()))
        assertEquals("do not follow", sentinel.readText())
    }

    @Test fun injectedPartialWriteFailureIsIndependentlyReported() = failureCase("write")
    @Test fun injectedDataFsyncFailureIsIndependentlyReported() = failureCase("sync")
    @Test fun injectedRenameFailureIsIndependentlyReported() = failureCase("rename")
    private fun failureCase(point: String) = fixture { root ->
        val old = oldFinal(root); val oldBytes = old.readBytes(); var reached = false
        val operations = object : OwnedLexicalPreparation.Operations() {
            override fun checkpoint(stage: OwnedLexicalPreparation.Point) {
                if (point == "write" && stage == OwnedLexicalPreparation.Point.CHUNK_WRITTEN) {
                    reached = true; throw IOException("synthetic ENOSPC after partial write")
                }
            }
            override fun syncData(output: FileOutputStream) {
                if (point == "sync") { reached = true; throw IOException("injected data-fsync failure") }
                super.syncData(output)
            }
            override fun publish(temporary: File, destination: File): Boolean {
                if (point == "rename") { reached = true; return false }
                return super.publish(temporary, destination)
            }
        }
        var failure: Throwable? = null
        try { prepare(OwnedLexicalPreparation(root, operations)) } catch (error: Throwable) { failure = error }
        assertTrue("fault boundary must actually be reached: $point", reached)
        assertNotNull(failure)
        assertFalse(File(root, "d-en-$hash.sqlite").exists())
        assertArrayEquals(oldBytes, old.readBytes())
        assertTrue(pending(root).listFiles().orEmpty().isEmpty())
        assertEquals(listOf("failed"), outcomes(root).map { it.getString("state") })
        assertArrayEquals(data, prepare(OwnedLexicalPreparation(root)).readBytes())
        assertEquals(setOf("failed", "published"), outcomes(root).map { it.getString("state") }.toSet())
        assertArrayEquals(oldBytes, old.readBytes())
    }

    @Test fun interruptedExceptionRemainsTheSameFailure() = cancellationCase(InterruptedException("synthetic"))
    @Test fun cancellationExceptionRemainsTheSameFailure() = cancellationCase(CancellationException("synthetic"))
    private fun cancellationCase(cancelled: Throwable) = fixture { root ->
        var ordered = false
        val operations = object : OwnedLexicalPreparation.Operations() {
            override fun checkpoint(point: OwnedLexicalPreparation.Point) {
                if (point == OwnedLexicalPreparation.Point.INTENT_SYNCED) {
                    val dir = pending(root).listFiles()!!.single()
                    assertEquals("vipi-owned-lexical-attempt-1", JSONObject(File(dir, "intent.json").readText()).getString("schema"))
                    assertFalse(File(dir, "payload.sqlite").exists()); ordered = true
                }
                if (point == OwnedLexicalPreparation.Point.CHUNK_WRITTEN) throw cancelled
            }
        }
        var observed: Throwable? = null
        try { prepare(OwnedLexicalPreparation(root, operations)) } catch (error: Throwable) { observed = error }
        assertTrue(ordered); assertSame(cancelled, observed)
        assertEquals(listOf("cancelled"), outcomes(root).map { it.getString("state") })
    }

    @Test fun unexpectedLockSymlinkIsRejectedWithoutOpeningTarget() = fixture { root ->
        val sentinel = File(root, "unrelated.keep").also { it.writeText("never open as lock") }
        Files.createSymbolicLink(File(root, OwnedLexicalPreparation.LOCK).toPath(), sentinel.toPath())
        var rejected = false
        try { prepare(OwnedLexicalPreparation(root)) } catch (_: IOException) { rejected = true }
        assertTrue(rejected)
        assertEquals("never open as lock", sentinel.readText())
        assertTrue(Files.isSymbolicLink(File(root, OwnedLexicalPreparation.LOCK).toPath()))
    }

    @Test fun repeatedConcurrentPrepareHasOneWriterAndAnExactHashBoundResult() = fixture { root ->
        val pool = Executors.newFixedThreadPool(2)
        val entered = CountDownLatch(1); val release = CountDownLatch(1); val requested = CountDownLatch(1)
        val writers = AtomicInteger()
        val operations = object : OwnedLexicalPreparation.Operations() {
            override fun checkpoint(point: OwnedLexicalPreparation.Point) {
                if (point == OwnedLexicalPreparation.Point.TEMP_CREATED) {
                    writers.incrementAndGet(); entered.countDown(); check(release.await(5, TimeUnit.SECONDS))
                }
            }
        }
        try {
            val first = pool.submit<File> { prepare(OwnedLexicalPreparation(root, operations)) }
            assertTrue(entered.await(5, TimeUnit.SECONDS))
            val second = pool.submit<File> { requested.countDown(); prepare(OwnedLexicalPreparation(root, operations)) }
            assertTrue(requested.await(5, TimeUnit.SECONDS)); assertFalse(second.isDone)
            release.countDown()
            assertEquals(first.get(5, TimeUnit.SECONDS), second.get(5, TimeUnit.SECONDS))
            assertEquals(1, writers.get())
            assertEquals(hash, sha(first.get().readBytes()))
            assertEquals(1, outcomes(root).size)
        } finally { release.countDown(); pool.shutdownNow() }
    }
}
