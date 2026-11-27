package co.fallsoft.vipi

import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.security.MessageDigest
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class KanaRomanizerDeviceTest {
    @Test
    fun frozenConverterAndCanonicalSourceMapping() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val input =
            readingRegressionFile(context, "japanese-kana-converter-protocol-r04.json").readBytes()
        val hash =
            MessageDigest.getInstance("SHA-256").digest(input).joinToString("") {
                "%02x".format(it)
            }
        assertEquals(
            InstrumentationRegistry.getArguments().getString("converter_protocol_sha256"),
            hash,
        )
        val protocol = JSONObject(input.toString(Charsets.UTF_8))
        val cases = protocol.getJSONArray("rows")
        assertEquals(652, cases.length())
        val report =
            JSONObject()
                .put("input_sha256", hash)
                .put("complete", false)
                .put("sdk", android.os.Build.VERSION.SDK_INT)
                .put("production_call_sites_changed", false)
                .put("rows", JSONArray())
        val output = readingRegressionFile(context, "japanese-kana-converter-001.json")
        fun save() = output.writeText(report.toString(2))
        var passed = true
        for (i in 0 until cases.length()) {
            val sample = cases.getJSONObject(i)
            val text = sample.getString("input")
            val start = SystemClock.elapsedRealtimeNanos()
            val value = KanaRomanizer.romanize(text)
            val row =
                JSONObject()
                    .put("id", sample.getString("id"))
                    .put("input", text)
                    .put("reading", value ?: JSONObject.NULL)
                    .put("elapsed_ms", (SystemClock.elapsedRealtimeNanos() - start) / 1e6)
            val warm = KanaRomanizer.romanize(text)
            row.put("warm_identical", value == warm)
            var valid = value == warm
            if (sample.has("expected")) {
                val expected = if (sample.isNull("expected")) null else sample.getString("expected")
                valid = valid && value == expected
            }
            row.put("controls_pass", valid)
            passed = passed && valid
            report.getJSONArray("rows").put(row)
        }
        val pairs = protocol.getJSONArray("canonical_equivalence")
        val pairRows = JSONArray()
        report.put("canonical_equivalence", pairRows)
        for (i in 0 until pairs.length()) {
            val sample = pairs.getJSONObject(i)
            val a = sample.getString("composed")
            val b = sample.getString("decomposed")
            val first = JapaneseReadings.read(a)
            val second = JapaneseReadings.read(b)
            val mapping = KanaRomanizer.normalizeKana(b)
            val reconstruction =
                first.pieces.joinToString("") { it.original } == a &&
                    second.pieces.joinToString("") { it.original } == b
            val bounds = second.pieces.all { b.substring(it.start, it.end) == it.original }
            val valid =
                reconstruction &&
                    bounds &&
                    first.reading == second.reading &&
                    first.issues == second.issues
            pairRows.put(
                JSONObject()
                    .put("id", sample.getString("id"))
                    .put("composed", a)
                    .put("decomposed", b)
                    .put("first", first.reading ?: JSONObject.NULL)
                    .put("second", second.reading ?: JSONObject.NULL)
                    .put("first_issues", JSONArray(first.issues.map { it.name }))
                    .put("second_issues", JSONArray(second.issues.map { it.name }))
                    .put("analysis", mapping.text)
                    .put("source_boundaries", JSONArray(mapping.sourceBoundaries))
                    .put(
                        "pieces",
                        JSONArray(
                            second.pieces.map {
                                JSONObject()
                                    .put("start", it.start)
                                    .put("end", it.end)
                                    .put("original", it.original)
                                    .put("value", it.value)
                            }
                        ),
                    )
                    .put("source_reconstruction", reconstruction)
                    .put("source_bounds", bounds)
                    .put("controls_pass", valid)
            )
            passed = passed && valid
        }
        val guards = protocol.getJSONArray("additional_guards")
        val guardRows = JSONArray()
        report.put("additional_guards", guardRows)
        for (i in 0 until guards.length()) {
            val sample = guards.getJSONObject(i)
            val value = KanaRomanizer.romanize(sample.getString("text"))
            val valid = (value != null) == sample.getBoolean("available")
            passed = passed && valid
            guardRows.put(
                JSONObject()
                    .put("text", sample.getString("text"))
                    .put("reading", value ?: JSONObject.NULL)
                    .put("controls_pass", valid)
            )
        }
        report.put("complete", true).put("controls_pass", passed)
        save()
        assertTrue("All converter outputs retained before assertion", passed)
    }
}
