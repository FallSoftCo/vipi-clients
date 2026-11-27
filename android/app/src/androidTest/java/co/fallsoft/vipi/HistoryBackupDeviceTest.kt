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
class HistoryBackupDeviceTest {
    private val instrumentation
        get() = InstrumentationRegistry.getInstrumentation()

    private val context
        get() = instrumentation.targetContext

    private val account = UUID.fromString("11111111-1111-4111-8111-111111111111")

    private fun fixture(name: String): File =
        File(context.cacheDir, "backup-test-${UUID.randomUUID()}").also { file ->
            instrumentation.context.assets.open(name).use { input ->
                file.outputStream().use(input::copyTo)
            }
        }

    @Test
    fun importsActualSwiftNativeExport() {
        val file = File(context.filesDir, "ios-history-v1.vipihistory")
        org.junit.Assume.assumeTrue("Explicit cross-platform fixture required", file.isFile)
        val digest =
            java.security.MessageDigest.getInstance("SHA-256")
                .digest(file.readBytes())
                .joinToString("") { "%02x".format(it) }
        assertEquals("68a1c1e85376dfffab45fe29c529633219fb21e34cf505d3bf49b39c603a9165", digest)
        val password = "Vipi café 日本語 🔐 2026"
        val root = File(context.cacheDir, "history-swift-${UUID.randomUUID()}").apply { mkdirs() }
        val isolated =
            object : ContextWrapper(context) {
                override fun getNoBackupFilesDir() = root
            }
        try {
            MessageVault(isolated, account).use { vault ->
                val history = ConversationHistory(vault)
                val backup = HistoryBackupStore(vault)
                val inspected = backup.validate(file, password)
                assertEquals(HistoryBackupCodec.Summary(1, 2), inspected.summary)
                assertEquals(digest, inspected.sha256)
                assertEquals(
                    HistoryBackupStore.Imported(2, 0),
                    backup.merge(file, password, inspected),
                )
                assertEquals(
                    HistoryBackupStore.Imported(0, 2),
                    backup.merge(file, password, inspected),
                )
                val messages =
                    history.messages(UUID.fromString("22222222-2222-4222-8222-222222222222"))
                assertEquals(
                    setOf("Habari! Tutaonana kesho. 👋", "See you tomorrow. 日本語 العربية café"),
                    messages.map { it.text }.toSet(),
                )
                vault.transaction {
                    for (kind in
                        listOf(
                            "incoming",
                            "outgoing",
                            "pending",
                            "receipt",
                            "draft",
                            "signal",
                            "local",
                        )) assertTrue(vault.ids(kind).isEmpty())
                }
            }
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun largeHistoryUsesBoundedRecordsAndRetainsStrictFooter() {
        val file = File(context.cacheDir, "large-history-${UUID.randomUUID()}")
        val password = "Large history test passphrase"
        val peer = "22222222-2222-4222-8222-222222222222"
        val text = "A private conversation. ".repeat(1100)
        val runtime = Runtime.getRuntime()
        var peak = runtime.totalMemory() - runtime.freeMemory()
        val initial = peak
        try {
            HistoryBackupCodec.write(file, password, account) { emit ->
                emit(
                    JSONObject()
                        .put("type", "peer")
                        .put("id", peer)
                        .put("username", JSONObject.NULL)
                        .put("display_name", JSONObject.NULL)
                )
                repeat(700) { index ->
                    emit(
                        JSONObject()
                            .put("type", "message")
                            .put("id", UUID(0, index.toLong() + 1).toString())
                            .put("peer_id", peer)
                            .put("direction", "incoming")
                            .put("sent_at_ms", index.toLong())
                            .put("text", text)
                    )
                }
            }
            assertTrue(file.length() > 16_000_000)
            val summary =
                HistoryBackupCodec.read(
                    file,
                    password,
                    account,
                    record = {
                        peak = maxOf(peak, runtime.totalMemory() - runtime.freeMemory())
                    },
                )
            assertEquals(HistoryBackupCodec.Summary(1, 700), summary)
            assertTrue(
                "Streaming heap grew excessively: ${peak - initial}",
                peak - initial < 96L * 1024 * 1024,
            )
            File(context.filesDir, "history-large-stream-receipt.json")
                .writeText(
                    JSONObject()
                        .put("messages", 700)
                        .put("encrypted_bytes", file.length())
                        .put("peak_heap_delta_bytes", peak - initial)
                        .toString()
                )
        } finally {
            file.delete()
        }
    }

    @Test
    fun nativeCodecReadsReferenceVectorsAndRejectsDamage() {
        val vectors =
            JSONObject(
                    instrumentation.context.assets.open("vectors.json").bufferedReader().readText()
                )
                .getJSONArray("vectors")
        for (index in 0 until vectors.length()) {
            val vector = vectors.getJSONObject(index)
            val file = fixture(vector.getString("file"))
            try {
                val rows = mutableListOf<JSONObject>()
                val result =
                    HistoryBackupCodec.read(
                        file,
                        vector.getString("password"),
                        account,
                        record = { rows.add(it) },
                    )
                assertEquals(HistoryBackupCodec.Summary(1, 2), result)
                assertEquals("Habari! Tutaonana kesho. 👋", rows[2].getString("text"))
                assertEquals(
                    result,
                    HistoryBackupCodec.read(file, vector.getString("nfd_password"), account),
                )
                assertTrue(
                    runCatching { HistoryBackupCodec.read(file, "wrong password 2026", account) }
                        .isFailure
                )
                assertTrue(
                    runCatching {
                        HistoryBackupCodec.read(
                            file,
                            vector.getString("password"),
                            UUID.randomUUID(),
                        )
                    }
                        .exceptionOrNull() is HistoryBackupCodec.DifferentAccount
                )
                val bytes = file.readBytes()
                val invalid =
                    listOf(
                        bytes.copyOf(bytes.size - 1),
                        bytes + byteArrayOf(1),
                        bytes.copyOf().apply { this[55] = (this[55].toInt() xor 1).toByte() },
                        bytes.copyOf().apply { this[8] = 1 },
                        bytes.copyOf().apply { this[36] = 127 },
                    )
                for (bad in invalid) {
                    file.writeBytes(bad)
                    assertTrue(
                        runCatching {
                            HistoryBackupCodec.read(file, vector.getString("password"), account)
                        }
                            .isFailure
                    )
                }
            } finally {
                file.delete()
            }
        }
    }

    @Test
    fun importIsAtomicIdempotentAndCannotRestoreTransportState() {
        val root = File(context.cacheDir, "history-vault-${UUID.randomUUID()}").apply { mkdirs() }
        val isolated =
            object : ContextWrapper(context) {
                override fun getNoBackupFilesDir() = root
            }
        val file = fixture("unicode.vipihistory")
        val password = "Vipi café 日本語 🔐 2026"
        val output = File(context.filesDir, "android-history-v1.vipihistory")
        try {
            MessageVault(isolated, account).use { vault ->
                val history = ConversationHistory(vault)
                val backup = HistoryBackupStore(vault)
                vault.transaction {
                    vault.put("signal", "sentinel", byteArrayOf(4, 5, 6))
                    vault.put("local", "sentinel", byteArrayOf(7, 8))
                }
                val inspected = backup.validate(file, password)
                val valid = file.readBytes()
                file.writeBytes(valid.copyOf(valid.size - 1))
                assertTrue(runCatching { backup.merge(file, password, inspected) }.isFailure)
                vault.transaction {
                    assertTrue(vault.ids("imported").isEmpty())
                    assertTrue(vault.ids("imported-peer").isEmpty())
                }
                val replacement = File(context.cacheDir, "replacement-${UUID.randomUUID()}")
                try {
                    val sameRows =
                        JSONObject(
                                instrumentation.context.assets
                                    .open("vectors.json")
                                    .bufferedReader()
                                    .readText()
                            )
                            .getJSONArray("records")
                    HistoryBackupCodec.write(replacement, password, account) { emit ->
                        for (index in 1 until sameRows.length() - 1) emit(
                            sameRows.getJSONObject(index)
                        )
                    }
                    assertEquals(inspected.summary, backup.validate(replacement, password).summary)
                    assertTrue(
                        runCatching { backup.merge(replacement, password, inspected) }.isFailure
                    )
                    vault.transaction {
                        assertTrue(vault.ids("imported").isEmpty())
                        assertTrue(vault.ids("history").isEmpty())
                        assertTrue(vault.ids("imported-peer").isEmpty())
                    }
                } finally {
                    replacement.delete()
                }
                file.writeBytes(valid)
                assertEquals(
                    HistoryBackupStore.Imported(2, 0),
                    backup.merge(file, password, inspected),
                )
                assertEquals(
                    HistoryBackupStore.Imported(0, 2),
                    backup.merge(file, password, inspected),
                )
                assertEquals(
                    2,
                    history.messages(UUID.fromString("22222222-2222-4222-8222-222222222222")).size,
                )
                assertTrue(
                    history.threads().all { it.unread == 0 && it.latest.state == "imported" }
                )
                vault.transaction {
                    assertArrayEquals(byteArrayOf(4, 5, 6), vault.get("signal", "sentinel"))
                    assertArrayEquals(byteArrayOf(7, 8), vault.get("local", "sentinel"))
                    for (kind in
                        listOf(
                            "incoming",
                            "outgoing",
                            "pending",
                            "receipt",
                            "draft",
                            "trust",
                            "contact",
                        )) assertTrue(vault.ids(kind).isEmpty())
                }
                backup.export(output, password)
                assertEquals(
                    HistoryBackupCodec.Summary(1, 2),
                    HistoryBackupCodec.read(output, password, account),
                )
                val records =
                    JSONObject(
                            instrumentation.context.assets
                                .open("vectors.json")
                                .bufferedReader()
                                .readText()
                        )
                        .getJSONArray("records")
                HistoryBackupCodec.write(file, password, account) { emit ->
                    for (index in 1 until records.length() - 1) {
                        val row = JSONObject(records.getJSONObject(index).toString())
                        if (row.optString("type") == "message")
                            row.put("text", "Conflicting imported content")
                        emit(row)
                    }
                }
                assertTrue(
                    runCatching { backup.merge(file, password, backup.validate(file, password)) }
                        .isFailure
                )
                assertEquals(
                    2,
                    history.messages(UUID.fromString("22222222-2222-4222-8222-222222222222")).size,
                )
                assertEquals(
                    "See you tomorrow. 日本語 العربية café",
                    history
                        .messages(UUID.fromString("22222222-2222-4222-8222-222222222222"))
                        .first()
                        .text,
                )
            }
            MessageVault(isolated, account).use { reopened ->
                val restored =
                    ConversationHistory(reopened)
                        .messages(UUID.fromString("22222222-2222-4222-8222-222222222222"))
                assertEquals(2, restored.size)
                assertTrue(restored.all { it.state == "imported" })
            }
        } finally {
            file.delete()
            root.deleteRecursively()
        }
    }
}
