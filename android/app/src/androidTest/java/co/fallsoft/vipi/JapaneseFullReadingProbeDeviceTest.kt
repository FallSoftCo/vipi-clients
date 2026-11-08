package co.fallsoft.vipi

import android.icu.text.Transliterator
import android.icu.util.VersionInfo
import android.os.Debug
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.atilika.kuromoji.ipadic.Token
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.security.MessageDigest
import java.time.Instant

/** Frozen QA-only morphology/reading observation. No new dictionary or production override. */
@RunWith(AndroidJUnit4::class)
class JapaneseFullReadingProbeDeviceTest {
    private val inputHash = "98e26a9fa030796ea138bb92a5dd62d445c405259e90127b6a572b296d042a38"
    private fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
    private fun japanese(text: String) = text.codePoints().anyMatch { Character.UnicodeScript.of(it) in setOf(
        Character.UnicodeScript.HAN, Character.UnicodeScript.HIRAGANA, Character.UnicodeScript.KATAKANA) }
    private fun kana(text: String?) = !text.isNullOrBlank() && text.codePoints().allMatch {
        it == 0x30fc || Character.UnicodeScript.of(it) in setOf(Character.UnicodeScript.HIRAGANA, Character.UnicodeScript.KATAKANA)
    }
    private fun literal(text: String) = !japanese(text) || text.codePoints().anyMatch {
        Character.isDigit(it) || Character.UnicodeScript.of(it) == Character.UnicodeScript.LATIN
    }
    private fun memory(): JSONObject {
        val info = Debug.MemoryInfo(); Debug.getMemoryInfo(info)
        val status = File("/proc/self/status").readLines().filter { it.startsWith("VmRSS:") || it.startsWith("VmHWM:") }
        return JSONObject().put("pss_kib", info.totalPss).put("proc_status", JSONArray(status))
    }
    private fun tokenJSON(token: Token): JSONObject = JSONObject()
        .put("surface", token.surface).put("surface_utf16_units", JSONArray(token.surface.map { it.code }))
        .put("source_start_utf16", token.position).put("source_end_utf16", token.position + token.surface.length)
        .put("known", token.isKnown).put("user_dictionary", token.isUser)
        .put("pos", JSONArray(listOf(token.partOfSpeechLevel1, token.partOfSpeechLevel2, token.partOfSpeechLevel3, token.partOfSpeechLevel4)))
        .put("base_form", token.baseForm).put("conjugation_type", token.conjugationType).put("conjugation_form", token.conjugationForm)
        .put("reading", token.reading).put("pronunciation", token.pronunciation).put("all_features", token.allFeatures)

    @Test fun captureExactlyTwelveFrozenJapaneseInputs() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val input = File(context.filesDir, "full-reading-probe-inputs-r01.json").readBytes()
        assertEquals(inputHash, sha(input))
        val original = JSONObject(input.toString(Charsets.UTF_8))
        assertEquals("vipi-full-reading-probe-1", original.getString("schema"))
        val cases = original.getJSONArray("cases")
        val selected = (0 until cases.length()).map { cases.getJSONObject(it) }.filter { it.getString("language") == "ja" }
        assertEquals(12, selected.size)
        val report = JSONObject().put("schema", "vipi-android-japanese-reading-probe-1")
            .put("input_sha256", inputHash).put("started_at", Instant.now().toString()).put("complete", false)
            .put("semantic_review", "not performed; script availability is not meaning or pronunciation accuracy")
            .put("sdk", android.os.Build.VERSION.SDK_INT).put("fingerprint", android.os.Build.FINGERPRINT)
            .put("icu_version", VersionInfo.ICU_VERSION.toString()).put("kuromoji", "com.atilika.kuromoji:kuromoji-ipadic:0.9.0")
            .put("process_id", android.os.Process.myPid()).put("process_start_elapsed_ms", android.os.Process.getStartElapsedRealtime())
            .put("new_dictionary_or_model_downloads", false).put("translation_calls", 0).put("audio_renders", 0)
            .put("production_changes", false).put("memory_before", memory())
        val output = File(context.filesDir, "japanese-full-reading-probe-001.json")
        fun save() { output.writeText(report.toString(2)) }
        val transformID = "Hiragana-Katakana; Katakana-Latin"
        val transformStarted = SystemClock.elapsedRealtimeNanos()
        val transform = try { Transliterator.getInstance(transformID) } catch (error: Exception) {
            report.put("romanizer_error_class", error.javaClass.simpleName); null
        }
        report.put("romanizer", transformID).put("romanizer_public_api_since", 29)
            .put("romanizer_init_ms", (SystemClock.elapsedRealtimeNanos() - transformStarted) / 1e6)
            .put("memory_after_romanizer", memory())
        val rows = JSONArray(); report.put("cases", rows); save()
        for ((index, sample) in selected.withIndex()) {
            val text = sample.getString("text")
            val row = JSONObject().put("id", sample.getString("id")).put("language", "ja")
                .put("group", sample.getString("group")).put("text", text)
                .put("first_tokenizer_call_in_probe", index == 0)
            rows.put(row)
            try {
                var started = SystemClock.elapsedRealtimeNanos()
                val tokens = LocalImmersion.japaneseTokens(text)
                row.put("tokenize_ms", (SystemClock.elapsedRealtimeNanos() - started) / 1e6)
                if (index == 0) report.put("memory_after_first_tokenizer", memory())
                val raw = JSONArray(tokens.map(::tokenJSON)); row.put("tokens", raw)
                var cursor = 0
                val reconstruction = StringBuilder(); val gaps = JSONArray()
                for (token in tokens) {
                    val start = token.position; val end = start + token.surface.length
                    check(start >= cursor && end <= text.length)
                    check(text.substring(start, end) == token.surface)
                    val gap = text.substring(cursor, start)
                    if (gap.isNotEmpty()) gaps.put(JSONObject().put("start_utf16", cursor).put("end_utf16", start).put("text", gap))
                    reconstruction.append(gap).append(token.surface); cursor = end
                }
                reconstruction.append(text.substring(cursor)); check(text == reconstruction.toString())
                row.put("source_gaps", gaps).put("exact_source_reconstruction", true)
                started = SystemClock.elapsedRealtimeNanos()
                val warm = LocalImmersion.japaneseTokens(text)
                row.put("warm_tokenize_ms", (SystemClock.elapsedRealtimeNanos() - started) / 1e6)
                    .put("warm_tokens_identical", JSONArray(warm.map(::tokenJSON)).toString() == raw.toString())
                started = SystemClock.elapsedRealtimeNanos()
                try { row.put("current_speech_adapter_kana", JapaneseSpeechReading.convert(text)) }
                catch (error: Exception) { row.put("current_speech_adapter_error_class", error.javaClass.simpleName) }
                row.put("speech_adapter_ms", (SystemClock.elapsedRealtimeNanos() - started) / 1e6)
                started = SystemClock.elapsedRealtimeNanos()
                val candidate = StringBuilder(); val spaced = StringBuilder(); val pieces = JSONArray()
                cursor = 0; var previousRoman = false
                for (token in tokens) {
                    val start = token.position; val end = start + token.surface.length
                    val gap = text.substring(cursor, start)
                    val preserve = literal(token.surface)
                    val pronunciation = if (!preserve && kana(token.pronunciation)) token.pronunciation else null
                    val reading = if (!preserve && pronunciation == null && kana(token.reading)) token.reading else null
                    val chosen = pronunciation ?: reading
                    val rendered = if (chosen != null && transform != null) transform.transliterate(chosen) else token.surface
                    val roman = chosen != null && transform != null
                    candidate.append(gap).append(rendered)
                    spaced.append(gap)
                    if (gap.isEmpty() && previousRoman && roman) spaced.append(' ')
                    spaced.append(rendered)
                    pieces.put(JSONObject().put("start_utf16", start).put("end_utf16", end).put("original", token.surface)
                        .put("preserved_literal", preserve).put("chosen_kana", chosen ?: JSONObject.NULL)
                        .put("basis", when { preserve -> "literal_preserved"; pronunciation != null -> "native_pronunciation"; reading != null -> "native_reading_fallback"; else -> "unresolved_original_preserved" })
                        .put("romanized", rendered).put("known", token.isKnown))
                    previousRoman = roman; cursor = end
                }
                candidate.append(text.substring(cursor)); spaced.append(text.substring(cursor))
                val remainingJapanese = japanese(candidate.toString())
                row.put("candidate_conversion_ms", (SystemClock.elapsedRealtimeNanos() - started) / 1e6)
                    .put("candidate_pieces", pieces).put("unreviewed_gap_preserving_candidate", candidate.toString())
                    .put("unreviewed_token_spaced_candidate", spaced.toString())
                    .put("spacing_policy", "Extra space only between adjacent romanized morphological tokens; no phrase overrides")
                    .put("remaining_japanese_script", remainingJapanese)
                    .put("full_reading_candidate", if (transform != null && !remainingJapanese) candidate.toString() else JSONObject.NULL)
            } catch (error: Exception) { row.put("error_class", error.javaClass.simpleName) }
            if (index == 5) report.put("memory_midpoint", memory())
            save()
        }
        report.put("memory_after", memory()).put("finished_at", Instant.now().toString()).put("complete", true)
        save()
        assertEquals(12, rows.length())
    }
}
