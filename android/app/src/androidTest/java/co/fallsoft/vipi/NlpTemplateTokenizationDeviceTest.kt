package co.fallsoft.vipi

import android.os.Debug
import android.os.SystemClock
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.MessageDigest
import java.time.Instant

/** Source geometry only. No translator, model preparation, candidate data or app state mutation. */
class NlpTemplateTokenizationDeviceTest {
    private fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes)
        .joinToString("") { "%02x".format(it) }
    private fun sha(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().buffered().use { stream ->
            val buffer = ByteArray(65_536)
            while (true) { val count = stream.read(buffer); if (count < 0) break; digest.update(buffer, 0, count) }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
    private fun ranges(values: List<IntRange>) = JSONArray(values.map { JSONArray(listOf(it.first, it.last + 1)) })

    @Test fun captureFrozenSourceGeometry() {
        val ins = InstrumentationRegistry.getInstrumentation()
        val args = InstrumentationRegistry.getArguments()
        require(args.getString("vipiDedicatedEmulator") == "true")
        require(android.os.Build.MODEL.contains("sdk_gphone") || android.os.Build.FINGERPRINT.contains("generic"))
        val run = requireNotNull(args.getString("vipiNlpRun")).also { require(it.matches(Regex("[0-9]{3}"))) }
        val expectedSha = requireNotNull(args.getString("vipiNlpInputSha")).also { require(it.matches(Regex("[a-f0-9]{64}"))) }
        val expectedCount = requireNotNull(args.getString("vipiNlpInputCount")).toInt().also { require(it in 1..9695) }
        val input = File(ins.targetContext.filesDir, "nlp-template-tokenizer-input-$run.json")
        require(input.length() in 1..(32L * 1024 * 1024))
        val bytes = input.readBytes(); assertEquals(expectedSha, sha(bytes))
        val root = JSONObject(bytes.toString(Charsets.UTF_8))
        val contract = "3767a5f794023ff1fef85f5120658ce7881be0c143fd2357dcfcfe705272fdf2"
        assertEquals(contract, root.getString("contract_sha256"))
        val cases = root.getJSONArray("cases"); assertEquals(expectedCount, cases.length())
        val directory = File(ins.targetContext.filesDir, "nlp-template-tokenizer-$run")
        check(directory.mkdir())
        val output = File(directory, "rows.jsonl")
        val summary = File(directory, "summary.json")
        val started = SystemClock.elapsedRealtime()
        val report = JSONObject().put("schema", "vipi-android-nlp-source-geometry-1")
            .put("complete", false).put("input_sha256", expectedSha).put("contract_sha256", contract)
            .put("started_at", Instant.now().toString()).put("translation_calls", 0).put("model_downloads", 0)
            .put("expected_count", expectedCount).put("captured_count", 0)
            .put("provider_instantiated", false).put("timing_scope", "Source word/sentence/window computation only, excluding JSON serialization; warm is immediate same-input replay.")
        val memory = JSONArray(); report.put("memory", memory)
        fun sample(stage: String) {
            val value = Debug.MemoryInfo(); Debug.getMemoryInfo(value)
            memory.put(JSONObject().put("stage", stage).put("total_pss_kib", value.totalPss)
                .put("java_used_bytes", Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory())
                .put("elapsed_ms", SystemClock.elapsedRealtime() - started))
        }
        fun save() {
            val temporary = File(directory, "summary.json.tmp")
            temporary.writeText(report.toString(2)); check(temporary.renameTo(summary))
        }
        val identities = hashSetOf<String>()
        data class Geometry(val words: List<IntRange>, val sentences: List<IntRange>, val windows: List<IntRange>?)
        fun geometry(text: String, language: String) = Geometry(LocalImmersion.words(text, language),
            LocalImmersion.sentences(text, language), ReviewedFrameLookup.windows(text, language)?.values
                ?.flatten()?.sortedWith(compareBy<IntRange> { it.first }.thenBy { it.last }))
        sample("start"); save()
        try {
            output.bufferedWriter(Charsets.UTF_8).use { stream ->
                for (index in 0 until cases.length()) {
                    check(SystemClock.elapsedRealtime() - started < 600_000) { "Bounded source geometry capture timed out" }
                    val row = cases.getJSONObject(index)
                    val id = row.getString("id"); check(identities.add(id))
                    val text = row.getString("text"); val source = row.getString("source_language")
                    require(source == "en" && text.length <= 16_384)
                    val firstStart = SystemClock.elapsedRealtimeNanos(); val first = geometry(text, source)
                    val firstMs = (SystemClock.elapsedRealtimeNanos() - firstStart) / 1e6
                    val warmStart = SystemClock.elapsedRealtimeNanos(); val warm = geometry(text, source)
                    val warmMs = (SystemClock.elapsedRealtimeNanos() - warmStart) / 1e6
                    assertEquals(first, warm)
                    for (range in first.words + first.sentences + first.windows.orEmpty()) {
                        assertTrue(range.first >= 0 && range.last >= range.first && range.last < text.length)
                        assertFalse(range.first > 0 && Character.isLowSurrogate(text[range.first]))
                        assertFalse(range.last + 1 < text.length && Character.isLowSurrogate(text[range.last + 1]))
                    }
                    val capture = JSONObject().put("id", id).put("text", text).put("source_language", source)
                        .put("text_utf8_sha256", sha(text.toByteArray(Charsets.UTF_8)))
                        .put("native_source_word_ranges_utf16", ranges(first.words))
                        .put("native_sentence_ranges_utf16", ranges(first.sentences))
                        .put("native_window_ranges_utf16", first.windows?.let(::ranges) ?: JSONObject.NULL)
                        .put("window_status", if (first.windows == null) "existing_window_bound_rejected" else "available")
                        .put("first_ms", firstMs).put("warm_ms", warmMs)
                    stream.write(capture.toString()); stream.newLine()
                    report.put("captured_count", index + 1)
                    if ((index + 1) % 250 == 0) { stream.flush(); sample("case-${index + 1}"); save() }
                }
            }
            report.put("complete", true).put("rows_sha256", sha(output))
        } finally {
            sample("finish"); report.put("finished_at", Instant.now().toString())
                .put("elapsed_ms", SystemClock.elapsedRealtime() - started); save()
        }
    }
}
