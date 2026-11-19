package co.fallsoft.vipi

import android.os.Debug
import android.os.Process
import android.os.SystemClock
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.io.FileOutputStream
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicReference

/** Measurement collector only. Calls the unchanged primary phonetic producers;
 * it does not translate, play audio, force GC, or imply pronunciation quality. */
class FullReadingProfileDeviceTest {
    private data class Sample(val id: String, val language: String, val shape: String, val text: String)
    private data class Active(val row: Int, val id: String, val started: Long, val cold: Boolean,
        val peakJava: AtomicLong, val peakRss: AtomicLong)
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrumentation.targetContext
    private fun sha(text: String) = MessageDigest.getInstance("SHA-256").digest(text.toByteArray(Charsets.UTF_8))
        .joinToString("") { "%02x".format(it) }
    @Synchronized private fun save(file: File, value: JSONObject) {
        val temporary = File(file.parentFile, ".${file.name}.tmp")
        FileOutputStream(temporary).use { output ->
            output.write(value.toString(2).toByteArray(Charsets.UTF_8)); output.fd.sync()
        }
        Files.move(temporary.toPath(), file.toPath(), StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
    }
    private fun memory(): JSONObject {
        val status = File("/proc/self/status").readLines()
        fun bytes(name: String) = status.single { it.startsWith("$name:") }.trim().split(Regex("\\s+"))[1].toLong() * 1024
        val runtime = Runtime.getRuntime()
        val stats = Debug.getRuntimeStats()
        return JSONObject().put("java_used", runtime.totalMemory() - runtime.freeMemory())
            .put("java_max", runtime.maxMemory()).put("java_committed", runtime.totalMemory())
            .put("rss", bytes("VmRSS")).put("process_high_water_rss", bytes("VmHWM"))
            .put("native_allocated", Debug.getNativeHeapAllocatedSize())
            .put("gc_count", stats["art.gc.gc-count"] ?: JSONObject.NULL)
            .put("gc_time", stats["art.gc.gc-time"] ?: JSONObject.NULL)
            .put("allocated_bytes", stats["art.gc.bytes-allocated"] ?: JSONObject.NULL)
            .put("freed_bytes", stats["art.gc.bytes-freed"] ?: JSONObject.NULL)
    }
    private fun samples(length: Int): List<Sample> {
        val ordinary = listOf(
        Triple("zh", "银行行长喜欢音乐。", "银行。 "),
        Triple("ko", "내일 도서관에서 친구를 만나요. ", "한글. "),
        Triple("ja", "明日は駅の近くで会いましょう。", "カナ。 ")
    ).flatMap { (code, sentence, prefix) ->
        val dense = sentence.repeat(length / sentence.length + 1).take(length)
        val suffix = " cafe\u0301 \uD83D\uDE42 https://example.test/9"
        val opaque = prefix + "x".repeat(length - prefix.length - suffix.length) + suffix
        listOf(Sample("$code-native-$length", code, "native", dense), Sample("$code-opaque-$length", code, "opaque", opaque))
        }
        if (length == 4096) return ordinary // Preserve the six historical 4K inputs.
        val unseparatedUnit = "明日は駅の近くで会いましょう"
        val unseparated = unseparatedUnit.repeat(length / unseparatedUnit.length + 1).take(length)
        check(unseparated.none { it == '。' || it == '、' || it.isWhitespace() || it.code < 128 })
        return ordinary + Sample("ja-unseparated-$length", "ja", "unseparated_native_stress", unseparated)
    }
    private fun rangesValid(text: String, ranges: List<Pair<Int, Int>>): Boolean =
        ranges.isNotEmpty() && ranges.first().first == 0 && ranges.last().second == text.length &&
            ranges.zipWithNext().all { (a, b) -> a.second == b.first } && ranges.all { (a, b) ->
                a >= 0 && b > a && b <= text.length && listOf(a, b).none { edge ->
                    edge in 1 until text.length && text[edge - 1].isHighSurrogate() && text[edge].isLowSurrogate()
                }
            }

    @Test fun collectPrimaryReadersAt4K() = collect(4096)
    @Test fun collectPrimaryReadersAt8K() = collect(8192)
    @Test fun collectPrimaryReadersAt16K() = collect(16384)

    private fun collect(length: Int) {
        check(length in setOf(4096, 8192, 16384)) // No 65K entry point in this packet.
        val args = InstrumentationRegistry.getArguments()
        check(BuildConfig.DEBUG && BuildConfig.APPLICATION_ID == "co.fallsoft.vipi.sourcecontextqa")
        check(args.getString("vipiDedicatedEmulator") == "true" && android.os.Build.MODEL.contains("sdk"))
        check(args.getString("vipiReaderLength") == length.toString()) // Selected method fixes the admitted length.
        val variant = requireNotNull(args.getString("vipiReaderVariant")).also { require(it in setOf("current", "candidate")) }
        val run = requireNotNull(args.getString("vipiReaderRun")).also { require(it.matches(Regex("$variant-${length / 1024}k-[0-9]{3}"))) }
        val nonce = requireNotNull(args.getString("vipiReaderNonce")).also { require(it.matches(Regex("[a-f0-9]{32}"))) }
        val cases = samples(length)
        assertEquals(args.getString("vipiReaderInputHashes"), cases.joinToString(",") { sha(it.text) })
        val output = File(context.filesDir, "reading-profile-$run")
        check(!output.exists() && output.mkdirs()) { "Never replay an existing native profile" }
        val stat = File("/proc/self/stat").readText(); val startTicks = stat.substringAfterLast(") ").trim().split(Regex("\\s+"))[19]
        val command = File("/proc/self/cmdline").readBytes().toString(Charsets.UTF_8).substringBefore('\u0000')
        check(command == BuildConfig.APPLICATION_ID && Process.myUid() / 100_000 == 10)
        val owner = JSONObject().put("run", run).put("variant", variant).put("input_length_utf16", length).put("nonce", nonce).put("pid", Process.myPid())
            .put("start_ticks", startTicks).put("cmdline", command).put("uid", Process.myUid())
        save(File(output, "owner.json"), owner)
        val rows = JSONArray(); val enteredCalls = AtomicInteger(); val active = AtomicReference<Active?>()
        val done = AtomicBoolean(); val monitorErrors = java.util.concurrent.CopyOnWriteArrayList<String>()
        val progressSequence = AtomicLong(); val monitorSamples = AtomicLong(); var chinese: ChineseReadings? = null
        val firstLanguages = mutableSetOf<String>(); var collectionReturned = false
        val sampler = Thread({
            var lastPublished = 0L
            while (!done.get()) {
                try {
                    val m = memory(); monitorSamples.incrementAndGet(); val row = active.get()
                    row?.peakJava?.accumulateAndGet(m.getLong("java_used"), ::maxOf)
                    row?.peakRss?.accumulateAndGet(m.getLong("rss"), ::maxOf)
                    val now = SystemClock.elapsedRealtime()
                    if (now - lastPublished >= 100) {
                        save(File(output, "progress.json"), JSONObject(owner.toString()).put("sequence", progressSequence.incrementAndGet())
                            .put("phase", if (row == null) "between_rows" else "running_row")
                            .put("row", row?.row ?: JSONObject.NULL).put("id", row?.id ?: JSONObject.NULL)
                            .put("row_started_elapsed_ms", row?.started ?: JSONObject.NULL)
                            .put("row_elapsed_ms", row?.let { now - it.started } ?: JSONObject.NULL)
                            .put("cold_first_producer_call", row?.cold ?: JSONObject.NULL).put("memory", m)
                            .put("sampled_peak_java", row?.peakJava?.get() ?: JSONObject.NULL)
                            .put("sampled_peak_rss", row?.peakRss?.get() ?: JSONObject.NULL)
                            .put("monitor_errors", JSONArray(monitorErrors)))
                        lastPublished = now
                    }
                    Thread.sleep(20)
                } catch (_: InterruptedException) { break }
                catch (error: Exception) { monitorErrors += error.toString(); Thread.sleep(20) }
            }
        }, "reading-profile-monitor").apply { isDaemon = true }
        sampler.start()
        try {
            for (sample in cases) repeat(3) { iteration ->
                val index = rows.length(); val cold = firstLanguages.add(sample.language)
                val before = memory(); val started = SystemClock.elapsedRealtime()
                val row = JSONObject(owner.toString()).put("index", index).put("id", sample.id).put("language", sample.language)
                    .put("shape", sample.shape).put("iteration", iteration).put("first_producer_call", cold)
                    .put("input_utf16", sample.text.length).put("input_utf8", sample.text.toByteArray(Charsets.UTF_8).size)
                    .put("input_sha256", sha(sample.text)).put("phase", "running").put("started_elapsed_ms", started)
                    .put("before", before).put("reader_call_entered", false)
                    .put("unseparated_native_stress", sample.shape == "unseparated_native_stress")
                val file = File(output, "row-${index.toString().padStart(2, '0')}.json")
                rows.put(row); save(file, row)
                val tracking = Active(index, sample.id, started, cold, AtomicLong(before.getLong("java_used")), AtomicLong(before.getLong("rss")))
                active.set(tracking)
                try {
                    var guide: String?; var original: String; var ranges: List<Pair<Int, Int>>; var issues: List<String>
                    when (sample.language) {
                        "zh" -> {
                            if (chinese == null) {
                                row.put("constructor_entered", true); save(file, row)
                                val constructorStart = SystemClock.elapsedRealtimeNanos()
                                chinese = ChineseReadings(context.assets.open("readings/chinese-ordinary.json").use { it.readBytes() })
                                row.put("chinese_construction_ms", (SystemClock.elapsedRealtimeNanos() - constructorStart) / 1e6)
                            }
                            row.put("reader_call_entered", true); enteredCalls.incrementAndGet(); save(file, row)
                            val callStartedNanos = SystemClock.elapsedRealtimeNanos()
                            val result = requireNotNull(chinese).resolve(sample.text)
                            row.put("producer_elapsed_ms", (SystemClock.elapsedRealtimeNanos() - callStartedNanos) / 1e6)
                            guide = result.reading; original = result.pieces.joinToString("") { it.source }
                            ranges = result.pieces.map { it.startUTF16 to it.endUTF16 }
                            issues = result.unresolved.map { "unresolved:${it.first}:${it.last + 1}" }
                        }
                        "ko" -> {
                            row.put("reader_call_entered", true); enteredCalls.incrementAndGet(); save(file, row)
                            val callStartedNanos = SystemClock.elapsedRealtimeNanos()
                            val result = KoreanReadings.resolve(sample.text)
                            row.put("producer_elapsed_ms", (SystemClock.elapsedRealtimeNanos() - callStartedNanos) / 1e6)
                            guide = result.reading; original = result.pieces.joinToString("") { it.source }
                            ranges = result.pieces.map { it.startUTF16 to it.endUTF16 }; issues = result.issues.toList()
                        }
                        else -> {
                            row.put("reader_call_entered", true); enteredCalls.incrementAndGet(); save(file, row)
                            val callStartedNanos = SystemClock.elapsedRealtimeNanos()
                            val result = JapaneseReadings.read(sample.text)
                            row.put("producer_elapsed_ms", (SystemClock.elapsedRealtimeNanos() - callStartedNanos) / 1e6)
                            guide = result.reading; original = result.pieces.joinToString("") { it.original }
                            ranges = result.pieces.map { it.start to it.end }; issues = result.issues.map { it.name }
                        }
                    }
                    row.put("reading_available", guide != null).put("reading_utf16", guide?.length ?: JSONObject.NULL)
                        .put("reading_sha256", guide?.let(::sha) ?: JSONObject.NULL)
                        .put("reading_prefix", guide?.take(96) ?: JSONObject.NULL).put("reading_suffix", guide?.takeLast(96) ?: JSONObject.NULL)
                        .put("issues", JSONArray(issues)).put("source_reconstruction", original == sample.text)
                        .put("source_ranges_contiguous_and_surrogate_safe", rangesValid(sample.text, ranges))
                        .put("phase", "returned")
                } catch (error: Exception) {
                    row.put("phase", "exception").put("exception", error.toString())
                } finally {
                    val after = memory(); tracking.peakJava.accumulateAndGet(after.getLong("java_used"), ::maxOf)
                    tracking.peakRss.accumulateAndGet(after.getLong("rss"), ::maxOf)
                    row.put("after", after).put("row_elapsed_ms", SystemClock.elapsedRealtime() - started)
                        .put("sampled_peak_java", tracking.peakJava.get()).put("sampled_peak_rss", tracking.peakRss.get())
                        .put("memory_scope", "Whole process including result inspection/JSON; sampling can miss short peaks, HWM can predate row. No forced GC.")
                    save(file, row); active.set(null)
                }
            }
            collectionReturned = true
        } finally {
            done.set(true); sampler.interrupt(); sampler.join(5_000)
            save(File(output, "summary.json"), JSONObject(owner.toString()).put("schema", "vipi-reading-profile-1")
                .put("collection_complete", collectionReturned).put("planned_rows", cases.size * 3).put("actual_reader_calls", enteredCalls.get())
                .put("rows", rows).put("monitor_stopped", !sampler.isAlive).put("monitor_errors", JSONArray(monitorErrors))
                .put("monitor_samples", monitorSamples.get()).put("monitor_interval_ms", 20).put("progress_interval_ms", 100)
                .put("current_policy", FullMessageReadings.policy("zh")).put("chinese_data_sha256", ChineseReadings.DATA_SHA256)
                .put("performance_accepted", false).put("pronunciation_accepted", false)
                .put("scope", "Primary phonetic readers only; stress input is not a proven global worst case. No model, audio, UI, new data, or production implementation change."))
        }
        assertTrue("Monitor must run and stop", !sampler.isAlive && monitorErrors.isEmpty() && monitorSamples.get() > 0)
        assertEquals(cases.size * 3, rows.length()); assertEquals(cases.size * 3, enteredCalls.get())
        // Null readings/exceptions are preserved findings, never converted to
        // successful readings. JUnit success establishes collection only.
    }
}
