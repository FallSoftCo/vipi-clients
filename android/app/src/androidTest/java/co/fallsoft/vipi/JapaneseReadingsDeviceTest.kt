package co.fallsoft.vipi

import android.os.Debug
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.security.MessageDigest
import java.time.Instant
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class JapaneseReadingsDeviceTest {
    @Test
    fun frozenDiagnosticAuthoredAndRetainedCorpus() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val args = InstrumentationRegistry.getArguments()
        val input =
            readingRegressionFile(context, "japanese-reading-candidate-protocol-r03b.json")
                .readBytes()
        val hash =
            MessageDigest.getInstance("SHA-256").digest(input).joinToString("") {
                "%02x".format(it)
            }
        assertEquals(args.getString("protocol_sha256"), hash)
        val protocol = JSONObject(input.toString(Charsets.UTF_8))
        val cases = protocol.getJSONArray("cases")
        assertEquals(270, cases.length())
        assertFalse(JapaneseReadings.supported(27))
        assertTrue(JapaneseReadings.supported(28))
        fun memory(): JSONObject {
            val info = Debug.MemoryInfo()
            Debug.getMemoryInfo(info)
            return JSONObject()
                .put("pss_kib", info.totalPss)
                .put(
                    "proc_status",
                    JSONArray(
                        File("/proc/self/status").readLines().filter {
                            it.startsWith("VmRSS:") || it.startsWith("VmHWM:")
                        }
                    ),
                )
        }
        val report =
            JSONObject()
                .put("schema", "vipi-japanese-reading-candidate-capture-2")
                .put("input_sha256", hash)
                .put("started_at", Instant.now().toString())
                .put("complete", false)
                .put("sdk", android.os.Build.VERSION.SDK_INT)
                .put("fingerprint", android.os.Build.FINGERPRINT)
                .put("production_call_sites_changed", false)
                .put(
                    "api28",
                    "No ICU dependency in candidate; JVM8/source qualification only, no API28 device runtime",
                )
                .put("translation_calls", 0)
                .put("audio_renders", 0)
                .put("new_models", false)
                .put("memory_before", memory())
        val rows = JSONArray()
        report.put("cases", rows)
        val file = readingRegressionFile(context, "japanese-reading-candidate-003.json")
        fun save() = file.writeText(report.toString(2))
        var controlsPassed = true
        for (index in 0 until cases.length()) {
            val sample = cases.getJSONObject(index)
            val text = sample.getString("text")
            val row =
                JSONObject()
                    .put("id", sample.getString("id"))
                    .put("group", sample.getString("group"))
                    .put("text", text)
            rows.put(row)
            try {
                var started = SystemClock.elapsedRealtimeNanos()
                val result = JapaneseReadings.read(text)
                row.put("elapsed_ms", (SystemClock.elapsedRealtimeNanos() - started) / 1e6)
                    .put("reading", result.reading ?: JSONObject.NULL)
                    .put("issues", JSONArray(result.issues.map { it.name }))
                    .put(
                        "pieces",
                        JSONArray(
                            result.pieces.map { piece ->
                                JSONObject()
                                    .put("start_utf16", piece.start)
                                    .put("end_utf16", piece.end)
                                    .put("original", piece.original)
                                    .put("value", piece.value)
                                    .put("kind", piece.kind.name)
                                    .put("reading_bases", JSONArray(piece.bases.map { it.name }))
                            }
                        ),
                    )
                val reconstruction = result.pieces.joinToString("") { it.original } == text
                val sourceBounds =
                    result.pieces.all {
                        it.start >= 0 &&
                            it.end <= text.length &&
                            text.substring(it.start, it.end) == it.original
                    }
                row.put("source_reconstruction", reconstruction).put("source_bounds", sourceBounds)
                started = SystemClock.elapsedRealtimeNanos()
                val warm = JapaneseReadings.read(text)
                row.put("warm_ms", (SystemClock.elapsedRealtimeNanos() - started) / 1e6)
                    .put("warm_identical", warm == result)
                val analysis = KanaRomanizer.normalizeKana(text)
                row.put("analysis_text", analysis.text)
                    .put("analysis_source_boundaries", JSONArray(analysis.sourceBoundaries))
                val tokens = NativeJapaneseTokenizer.tokens(analysis.text)
                row.put(
                    "native_tokens",
                    JSONArray(
                        tokens.map { token ->
                            JSONObject()
                                .put("surface", token.surface)
                                .put("start_utf16", token.position)
                                .put("end_utf16", token.position + token.surface.length)
                                .put("coordinate_space", "normalized_analysis_utf16")
                                .put(
                                    "source_start_utf16",
                                    analysis
                                        .sourceRange(
                                            token.position,
                                            token.position + token.surface.length,
                                        )
                                        ?.first ?: JSONObject.NULL,
                                )
                                .put(
                                    "source_end_utf16",
                                    analysis
                                        .sourceRange(
                                            token.position,
                                            token.position + token.surface.length,
                                        )
                                        ?.let { it.last + 1 } ?: JSONObject.NULL,
                                )
                                .put(
                                    "pos",
                                    JSONArray(
                                        listOf(token.partOfSpeechLevel1, token.partOfSpeechLevel2)
                                    ),
                                )
                                .put("reading", token.reading)
                                .put("pronunciation", token.pronunciation)
                                .put("known", token.isKnown)
                        }
                    ),
                )
                if (sample.has("reference_reading"))
                    row.put("authored_reference", sample.getString("reference_reading"))
                var passed =
                    reconstruction &&
                        sourceBounds &&
                        warm == result &&
                        (result.reading == null || '~' !in result.reading)
                if (sample.has("expected_available"))
                    passed =
                        passed &&
                            (result.reading != null) == sample.getBoolean("expected_available")
                val required = sample.optJSONArray("required_fragments") ?: JSONArray()
                for (i in 0 until required.length()) passed =
                    passed && result.reading?.contains(required.getString(i)) == true
                val unspaced = sample.optJSONArray("required_ignoring_spaces") ?: JSONArray()
                for (i in 0 until unspaced.length()) passed =
                    passed &&
                        result.reading?.replace(" ", "")?.contains(unspaced.getString(i)) == true
                val ifAvailable = sample.optJSONArray("required_if_available") ?: JSONArray()
                if (result.reading != null)
                    for (i in 0 until ifAvailable.length()) passed =
                        passed && result.reading.contains(ifAvailable.getString(i))
                if (sample.optBoolean("forbid_copular_rule", false))
                    passed =
                        passed &&
                            result.pieces.none { JapaneseReadings.Basis.COPULAR_NAN in it.bases }
                val literals = sample.optJSONArray("preserved_literals") ?: JSONArray()
                val literalChecks = JSONArray()
                for (i in 0 until literals.length()) {
                    val literal = literals.getString(i)
                    val preserved =
                        result.pieces.any {
                            it.kind == JapaneseReadings.Kind.LITERAL &&
                                it.original.contains(literal) &&
                                it.value == it.original
                        }
                    literalChecks.put(
                        JSONObject()
                            .put("literal", literal)
                            .put("preserved_in_opaque_piece", preserved)
                    )
                    passed = passed && preserved
                }
                row.put("literal_checks", literalChecks)
                    .put("mechanical_and_frozen_controls_pass", passed)
                controlsPassed = controlsPassed && passed
            } catch (error: Exception) {
                row.put("error_class", error.javaClass.simpleName)
                controlsPassed = false
            }
            if (index == 0) report.put("memory_after_first", memory())
            if (index == cases.length() / 2) report.put("memory_midpoint", memory())
            save()
        }
        report
            .put("memory_after", memory())
            .put("finished_at", Instant.now().toString())
            .put("complete", true)
            .put("mechanical_and_frozen_controls_pass", controlsPassed)
        save()
        assertTrue(
            "All rows retained; inspect frozen control failures before changing any candidate policy",
            controlsPassed,
        )
    }
}
