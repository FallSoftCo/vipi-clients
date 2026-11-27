package co.fallsoft.vipi

import android.os.StatFs
import android.system.Os
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.io.RandomAccessFile
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Bounded provider resource qualification, not a throughput/production limit. */
@RunWith(AndroidJUnit4::class)
class MediaResourceDeviceTest {
    private val context
        get() = InstrumentationRegistry.getInstrumentation().targetContext

    private fun memory(name: String): Long? = runCatching {
        Regex("(?m)^$name:\\s+(\\d+) kB")
            .find(File("/proc/self/status").readText())
            ?.groupValues
            ?.get(1)
            ?.toLong()
            ?.times(1024)
    }
        .getOrNull()

    private fun physical(directory: File): Long =
        directory.walkTopDown().filter(File::isFile).sumOf {
            runCatching { Os.stat(it.path).st_blocks * 512 }.getOrDefault(0L)
        }

    @Test
    fun providerAdmissionSerializesSealAgainstOpenAcrossRepositories() {
        val directory =
            File(context.noBackupFilesDir, "media-admission-${UUID.randomUUID()}").also {
                check(it.mkdir())
            }
        val key = MediaCryptography.freshKey()
        val attachment = UUID.randomUUID()
        val content = ByteArray(16384) { 7 }
        val (part, source) =
            MediaCryptography.seal(content.inputStream(), directory, key, attachment, "original")
        val firstEntered = java.util.concurrent.CountDownLatch(1)
        val release = java.util.concurrent.CountDownLatch(1)
        val secondEntered = java.util.concurrent.CountDownLatch(1)
        val firstCheck = AtomicBoolean(true)
        val pool = java.util.concurrent.Executors.newFixedThreadPool(2)
        try {
            val first = pool.submit {
                MediaCryptography.seal(
                    content.inputStream(),
                    directory,
                    key,
                    UUID.randomUUID(),
                    "original",
                ) {
                    if (firstCheck.compareAndSet(true, false)) {
                        firstEntered.countDown()
                        check(release.await(3, java.util.concurrent.TimeUnit.SECONDS))
                    }
                }
            }
            assertTrue(firstEntered.await(1, java.util.concurrent.TimeUnit.SECONDS))
            val second = pool.submit {
                MediaCryptography.open(
                    source,
                    File(directory, "verified.bin"),
                    key,
                    attachment,
                    part,
                ) {
                    secondEntered.countDown()
                }
            }
            assertFalse(
                "Two provider operations admitted together",
                secondEntered.await(100, java.util.concurrent.TimeUnit.MILLISECONDS),
            )
            release.countDown()
            first.get(5, java.util.concurrent.TimeUnit.SECONDS)
            second.get(5, java.util.concurrent.TimeUnit.SECONDS)
            assertEquals(0, secondEntered.count.toInt())
        } finally {
            release.countDown()
            pool.shutdownNow()
            directory.deleteRecursively()
        }
    }

    @Test
    fun boundedThirtyTwoMiBProviderMemoryTemporaryDiskAndCancellation() {
        val size = MediaCryptography.MAX_BYTES
        assertTrue(
            "Insufficient isolated-emulator data reserve",
            StatFs(context.noBackupFilesDir.path).availableBytes > 256L * 1024 * 1024 + size * 4,
        )
        val directory =
            File(context.noBackupFilesDir, "media-resource-${UUID.randomUUID()}").also {
                check(it.mkdir())
            }
        val input = File(directory, "synthetic-zero-input.bin")
        val running = AtomicBoolean(true)
        val peakLogical = AtomicLong()
        val peakPhysical = AtomicLong()
        val peakFD = AtomicLong()
        val baselineHWM = memory("VmHWM")
        val baselineRSS = memory("VmRSS")
        val sampler = Thread {
            while (running.get()) {
                peakLogical.accumulateAndGet(
                    directory.walkTopDown().filter(File::isFile).sumOf(File::length),
                    ::maxOf,
                )
                peakPhysical.accumulateAndGet(physical(directory), ::maxOf)
                peakFD.accumulateAndGet(File("/proc/self/fd").list()?.size?.toLong() ?: 0, ::maxOf)
                try {
                    Thread.sleep(10)
                } catch (_: InterruptedException) {
                    break
                }
            }
        }
            .also { it.start() }
        try {
            input.outputStream().use { output ->
                val buffer = ByteArray(65536)
                repeat((size / buffer.size).toInt()) { output.write(buffer) }
            }
            val key = MediaCryptography.freshKey()
            val attachment = UUID.randomUUID()
            val started = System.nanoTime()
            val (part, ciphertext) =
                input.inputStream().use {
                    MediaCryptography.seal(it, directory, key, attachment, "original")
                }
            val sealedAt = System.nanoTime()
            val afterSealHWM = memory("VmHWM")
            val plaintext = File(directory, "verified.bin")
            MediaCryptography.open(ciphertext, plaintext, key, attachment, part)
            val openedAt = System.nanoTime()
            val afterOpenHWM = memory("VmHWM")
            assertEquals(size, plaintext.length())
            plaintext.inputStream().use { stream ->
                val buffer = ByteArray(65536)
                while (true) {
                    val count = stream.read(buffer)
                    if (count < 0) break
                    for (index in 0 until count) if (buffer[index] != 0.toByte())
                        fail("Plaintext changed")
                }
            }
            var checks = 0
            assertTrue(
                runCatching {
                        input.inputStream().use {
                            MediaCryptography.seal(
                                it,
                                directory,
                                key,
                                UUID.randomUUID(),
                                "original",
                            ) {
                                if (++checks > 8) error("cancelled")
                            }
                        }
                    }
                    .isFailure
            )
            checks = 0
            val cancelled = File(directory, "cancelled-must-not-publish.bin")
            assertTrue(
                runCatching {
                        MediaCryptography.open(ciphertext, cancelled, key, attachment, part) {
                            if (++checks > 8) error("cancelled")
                        }
                    }
                    .isFailure
            )
            assertFalse(cancelled.exists())
            assertFalse(directory.listFiles().orEmpty().any { it.name.endsWith(".partial") })
            RandomAccessFile(input, "rw").use { it.setLength(size + 1) }
            assertTrue(
                runCatching {
                        input.inputStream().use {
                            MediaCryptography.seal(
                                it,
                                directory,
                                key,
                                UUID.randomUUID(),
                                "original",
                            )
                        }
                    }
                    .isFailure
            )
            assertFalse(directory.listFiles().orEmpty().any { it.name.endsWith(".partial") })
            File(context.filesDir, "media-resource-receipt.json")
                .writeText(
                    JSONObject()
                        .put(
                            "proof",
                            "single Android emulator/native AES-GCM32MiB, not server capacity or codec throughput",
                        )
                        .put("process_id", android.os.Process.myPid())
                        .put("plaintext_bytes", size)
                        .put("ciphertext_bytes", part.ciphertextBytes)
                        .put("seal_ms", (sealedAt - started) / 1_000_000.0)
                        .put("authenticated_open_ms", (openedAt - sealedAt) / 1_000_000.0)
                        .put("baseline_rss_bytes", baselineRSS)
                        .put("baseline_kernel_hwm_bytes", baselineHWM)
                        .put("after_seal_kernel_hwm_bytes", afterSealHWM)
                        .put("after_open_kernel_hwm_bytes", afterOpenHWM)
                        .put("sampled_peak_logical_bytes", peakLogical.get())
                        .put("sampled_peak_allocated_disk_bytes", peakPhysical.get())
                        .put("sampled_peak_process_fds", peakFD.get())
                        .put("sample_interval_ms", 10)
                        .put("cancel_seal_and_open_cleaned", true)
                        .put("oversize_rejected_without_published_partial", true)
                        .toString()
                )
        } finally {
            running.set(false)
            sampler.interrupt()
            sampler.join(1000)
            directory.deleteRecursively()
        }
    }
}
