package co.fallsoft.vipi

import android.os.SystemClock
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.ImmersionPresentation
import co.fallsoft.vipi.core.ImmersionText
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.security.MessageDigest

/** Exercises current default lookup on ordinary messages, without supplied targets.
 * Structural assertions are deliberately separate from linguistic review/reach.
 * All zero-match cases remain in the report. No broad accuracy claim is made. */
class ConversationJourneyLanguageDeviceTest {
    @Test fun qualifyReviewedBookCoffeeContexts() = runBlocking {
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("vipiDedicatedEmulator") == "true")
        val run = requireNotNull(args.getString("vipiContextRun"))
        require(run.matches(Regex("[0-9]{3}")))
        val expectedHash = requireNotNull(args.getString("vipiContextInputSHA"))
        require(expectedHash.matches(Regex("[0-9a-f]{64}")))
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val folder = File(context.filesDir, "context-increment-$run")
        val input = File(folder, "inputs.json").readBytes()
        val digest = MessageDigest.getInstance("SHA-256").digest(input).joinToString("") { "%02x".format(it) }
        assertEquals(expectedHash, digest)
        val fixture = JSONObject(input.toString(Charsets.UTF_8))
        assertEquals("vipi-context-increment-probes-1", fixture.getString("schema"))
        val cases = fixture.getJSONArray("cases")
        check(cases.length() > 0)
        val languages = initialLanguages.map { it.code }
        val output = File(folder, "outcomes.jsonl")
        val summary = File(folder, "summary.json")
        check(!output.exists() && !summary.exists())
        var rows = 0
        var violations = 0
        val started = SystemClock.elapsedRealtime()
        for (source in languages) for (target in languages.filter { it != source }) {
            val owner = ConversationImmersion(context, source, target, .35)
            try {
                for (index in 0 until cases.length()) {
                    val item = cases.getJSONObject(index)
                    check(item.getString("source") in languages)
                    if (item.getString("source") != source) continue
                    val targets = item.optJSONArray("targets")
                    if (targets != null && (0 until targets.length()).none { targets.getString(it) == target }) continue
                    val text = item.getString("text")
                    val id = item.getString("id")
                    val failures = JSONArray()
                    fun expect(condition: Boolean, why: String) {
                        if (!condition) { failures.put(why); violations++ }
                    }
                    val begin = SystemClock.elapsedRealtimeNanos()
                    val result = try { owner.presentation(text, messageID = id) }
                        catch (error: Exception) { expect(false, "Default lookup threw: ${error.javaClass.simpleName}"); null }
                    val spans = result?.spans.orEmpty()
                    expect(owner.lastOutcome != null, "Missing observable default outcome")
                    expect(owner.lastOutcome?.status?.name in setOf("READY", "PARTIAL", "NO_LOCAL_MATCH"), "Default lookup returned an unexpected error or invalid state")
                    expect(owner.lastInvocation.readiness == 0, "Automatic lookup consulted model readiness")
                    expect(owner.lastOutcome?.resolvedInputLanguage == source, "Default source identification differs")
                    expect((owner.lastOutcome?.localTranslationCalls ?: 0) == 0, "Automatic lookup invoked translation")
                    expect(result == null || result.original == text, "Original text changed")
                    if (item.has("required_focus")) {
                        val required = item.getString("required_focus")
                        check(required.isNotBlank() && text.contains(required))
                        expect(spans.any { it.original == required }, "Required content word absent: $required")
                    }
                    val forbidden = item.optJSONArray("forbidden_focus") ?: JSONArray()
                    for (offset in 0 until forbidden.length()) {
                        val word = forbidden.getString(offset)
                        check(word.isNotBlank() && text.contains(word))
                        expect(spans.none { it.original == word }, "Forbidden source word admitted: $word")
                    }
                    val entries = JSONArray()
                    var previousEnd = 0
                    for (span in spans) {
                        val valid = span.start >= previousEnd && span.end > span.start && span.end <= text.length
                        expect(valid, "Invalid/overlapping UTF16 source range")
                        if (valid) expect(text.substring(span.start, span.end) == span.original, "Source range does not match original")
                        previousEnd = span.end
                        expect(span.translated.isNotBlank(), "Empty target word")
                        if (target in setOf("ar", "ja", "ko", "zh")) expect(!span.romanization.isNullOrBlank(), "Missing required reading")
                        if (target == "zh" && span.translated.any { Character.UnicodeScript.of(it.code) == Character.UnicodeScript.HAN })
                            expect(span.romanization.orEmpty().any { it in "āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ" }, "Chinese reading lost tone marks")
                        entries.put(JSONObject().put("original", span.original).put("translated", span.translated)
                            .put("reading", span.romanization ?: JSONObject.NULL).put("start", span.start).put("end", span.end))
                    }
                    output.appendText(JSONObject().put("id", id).put("source_language", source).put("target_language", target)
                        .put("original", text).put("spans", entries).put("failures", failures)
                        .put("resolved_input_language", owner.lastOutcome?.resolvedInputLanguage ?: JSONObject.NULL)
                        .put("translation_calls", owner.lastOutcome?.localTranslationCalls ?: JSONObject.NULL)
                        .put("readiness_calls", owner.lastInvocation.readiness)
                        .put("status", owner.lastOutcome?.status?.name ?: JSONObject.NULL)
                        .put("elapsed_ms", (SystemClock.elapsedRealtimeNanos() - begin) / 1_000_000.0)
                        .put("mixed_script", result?.let { ImmersionText.project(it, showScript = true) } ?: text)
                        .put("mixed_reading", result?.let { ImmersionText.project(it) } ?: text).toString() + "\n")
                    rows++
                    check(output.length() < 8 * 1024 * 1024 && SystemClock.elapsedRealtime() - started < 600_000)
                }
            } finally { owner.close() }
        }
        val expectedRows = (0 until cases.length()).sumOf { index -> cases.getJSONObject(index).optJSONArray("targets")?.length() ?: (languages.size - 1) }
        summary.writeText(JSONObject().put("complete", true).put("rows", rows).put("expected_rows", expectedRows)
            .put("violations", violations).put("input_sha256", digest).put("population_coverage", false)
            .put("target_provider_or_span_injected", false).put("seconds", (SystemClock.elapsedRealtime() - started) / 1000.0).toString(2))
        assertEquals(expectedRows, rows)
        assertEquals("Inspect all retained context qualification failures", 0, violations)
    }

    @Test fun captureOrdinaryConversationAcrossEverySupportedDirection() = runBlocking {
        val args = InstrumentationRegistry.getArguments()
        check(args.getString("vipiDedicatedEmulator") == "true")
        val run = requireNotNull(args.getString("vipiConversationJourneyRun"))
        require(run.matches(Regex("[0-9]{3}")))
        val expectedHash = requireNotNull(args.getString("vipiConversationInputSHA"))
        require(expectedHash.matches(Regex("[0-9a-f]{64}")))
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val folder = File(context.filesDir, "conversation-journey-$run")
        val input = File(folder, "inputs.json").readBytes()
        val digest = MessageDigest.getInstance("SHA-256").digest(input).joinToString("") { "%02x".format(it) }
        assertEquals(expectedHash, digest)
        val fixture = JSONObject(input.toString(Charsets.UTF_8))
        assertEquals("vipi-conversation-journey-input-1", fixture.getString("schema"))
        val cases = fixture.getJSONArray("cases")
        assertEquals(33, cases.length())
        val languages = initialLanguages.map { it.code }
        assertEquals(11, languages.size)
        assertEquals(languages.toSet(), (0 until cases.length()).map { cases.getJSONObject(it).getString("source") }.toSet())
        val output = File(folder, "outcomes.jsonl")
        val summary = File(folder, "summary.json")
        check(!output.exists() && !summary.exists()) { "Use a fresh run ID; preserve the original capture" }
        val started = SystemClock.elapsedRealtime()
        var rows = 0
        var withSpans = 0
        var withContent = 0
        var violations = 0
        for (source in languages) for (target in languages.filter { it != source }) {
            // Same owner and default producer as a conversation. No readiness,
            // language choice, target, source provider or reading override.
            val owner = ConversationImmersion(context, source, target, .35)
            try {
                for (index in 0 until cases.length()) {
                    val item = cases.getJSONObject(index)
                    if (item.getString("source") != source) continue
                    val text = item.getString("text")
                    val id = item.getString("id")
                    val row = JSONObject().put("id", id).put("source_language", source)
                        .put("target_language", target).put("original", text)
                    val failures = JSONArray()
                    fun requireEvidence(condition: Boolean, description: String) {
                        if (!condition) { failures.put(description); violations++ }
                    }
                    val callStart = SystemClock.elapsedRealtimeNanos()
                    var result: ImmersionPresentation? = null
                    try {
                        result = owner.presentation(text, messageID = id)
                    } catch (error: Exception) {
                        row.put("exception", error.javaClass.name)
                        requireEvidence(false, "Default conversation lookup threw")
                    }
                    row.put("elapsed_ms", (SystemClock.elapsedRealtimeNanos() - callStart) / 1_000_000.0)
                    val outcome = owner.lastOutcome
                    row.put("status", outcome?.status?.name ?: JSONObject.NULL)
                        .put("origin", outcome?.origin?.name ?: JSONObject.NULL)
                        .put("resolved_input_language", outcome?.resolvedInputLanguage ?: JSONObject.NULL)
                        .put("translation_calls", outcome?.localTranslationCalls ?: JSONObject.NULL)
                        .put("readiness_calls", owner.lastInvocation.readiness)
                    requireEvidence(outcome != null, "Outcome must be observable")
                    requireEvidence(outcome?.status?.name in setOf("READY", "PARTIAL", "NO_LOCAL_MATCH"), "Default lookup returned an unexpected error or invalid state")
                    requireEvidence(owner.lastInvocation.readiness == 0, "Automatic lookup consulted model readiness")
                    requireEvidence((outcome?.localTranslationCalls ?: 0) == 0, "Automatic immersion must remain local lookup")
                    val spans = result?.spans.orEmpty()
                    val entries = JSONArray()
                    var end = 0
                    var content = false
                    val fragments = item.getJSONArray("content_fragments")
                    val contentRanges = (0 until fragments.length()).map { fragments.getString(it) }.map { fragment ->
                        val start = text.indexOf(fragment)
                        check(start >= 0) { "Invalid source-only content anchor: $id" }
                        start until start + fragment.length
                    }
                    if (result != null) requireEvidence(result.original == text, "Original text must remain exact")
                    for (span in spans) {
                        val validRange = span.start >= end && span.end > span.start && span.end <= text.length
                        requireEvidence(validRange, "Spans must be ordered, disjoint UTF16 source ranges")
                        if (validRange) {
                            requireEvidence(text.substring(span.start, span.end) == span.original, "Source slice must match exactly")
                            content = content || contentRanges.any { range -> span.start <= range.first && span.end > range.last }
                        }
                        end = span.end
                        requireEvidence(span.translated.isNotBlank(), "A flipped word must not be empty")
                        if (target in setOf("ar", "ja", "ko", "zh")) {
                            requireEvidence(!span.romanization.isNullOrBlank(), "Non-Latin immersion requires a reading")
                        }
                        if (target == "zh" && span.translated.any { Character.UnicodeScript.of(it.code) == Character.UnicodeScript.HAN }) {
                            requireEvidence(span.romanization.orEmpty().any { it in "āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ" }, "Chinese reading must retain tone marks")
                        }
                        entries.put(JSONObject().put("original", span.original).put("translated", span.translated)
                            .put("reading", span.romanization ?: JSONObject.NULL)
                            .put("start", span.start).put("end", span.end))
                    }
                    if (spans.isNotEmpty()) withSpans++
                    if (content) withContent++
                    row.put("spans", entries).put("content_anchor_selected", content)
                        .put("mixed_reading", result?.let { ImmersionText.project(it) } ?: text)
                        .put("mixed_script", result?.let { ImmersionText.project(it, showScript = true) } ?: text)
                        .put("structural_failures", failures)
                    output.appendText(row.toString() + "\n")
                    rows++
                    check(output.length() < 8 * 1024 * 1024 && SystemClock.elapsedRealtime() - started < 600_000)
                }
            } finally { owner.close() }
        }
        summary.writeText(JSONObject().put("complete", true).put("rows", rows)
            .put("with_spans", withSpans).put("with_content_anchor", withContent)
            .put("structural_violations", violations).put("input_sha256", digest)
            .put("linguistic_acceptance", false).put("representative_coverage", false)
            .put("authored_preview", false).put("target_provider_or_span_injected", false)
            .put("physical_or_acoustic_acceptance", false)
            .put("seconds", (SystemClock.elapsedRealtime() - started) / 1000.0).toString(2))
        assertEquals(330, rows)
        assertEquals("Inspect every retained structural failure", 0, violations)
    }
}
