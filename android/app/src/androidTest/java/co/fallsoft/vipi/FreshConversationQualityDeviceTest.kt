package co.fallsoft.vipi

import android.os.SystemClock
import androidx.test.platform.app.InstrumentationRegistry
import co.fallsoft.vipi.core.ImmersionText
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File

/** Frozen independent natural-chat diagnostic; annotations never enter the matching path. */
class FreshConversationQualityDeviceTest {
    @Test fun captureUnmodifiedFriendChatWithActualDefault() = runBlocking {
        val inst = InstrumentationRegistry.getInstrumentation(); val args = InstrumentationRegistry.getArguments()
        check(args.getString("vipiDedicatedEmulator") == "true" && BundledStarterLookup.ALL_PAIR_PROMOTION_ENABLED)
        val context = inst.targetContext
        val bytes = File(context.filesDir, "fresh-conversations-frozen-r01.json").readBytes()
        assertEquals("ac6332cacdde6594f9083e57f04d100bb0fdf1ce7862bef2a18630324fdbca71", JapaneseStarterLookup.sha(bytes))
        val input = JSONObject(bytes.toString(Charsets.UTF_8)); val items = input.getJSONArray("items"); assertEquals(132, items.length())
        val folder = File(context.filesDir, "fresh-conversation-default-r01"); check(!folder.exists()); check(folder.mkdir())
        val index = JSONArray(); val report = JSONObject().put("schema", "vipi-fresh-conversation-native-1")
            .put("input_sha256", JapaneseStarterLookup.sha(bytes)).put("bundled_index_sha256", BundledSourceFrameCatalog.INDEX_SHA256)
            .put("actual_default_provider", true).put("density", 0.25).put("pair_files", index).put("complete", false)
        fun save() { File(folder, "index.json").writeText(report.toString(2)) }
        val languages = listOf("en", "es", "fr", "de", "it", "pt", "ar", "zh", "ja", "ko", "sw")
        val guesses = mutableMapOf<String, String?>()
        MessageLanguage().use { classifier ->
            for (i in 0 until items.length()) {
                val item = items.getJSONObject(i); require(item.getString("source_language") in languages)
                guesses[item.getString("id")] = classifier.identify(item.getString("message"))
            }
        }
        val catalog = BundledImmersionCatalog(context); var total = 0
        try {
            for (source in languages) for (target in languages) if (source != target) {
                val rows = JSONArray(); val owner = ConversationImmersion(context, source, target, 0.25)
                try {
                    for (i in 0 until items.length()) {
                        val item = items.getJSONObject(i); if (item.getString("source_language") != source) continue
                        val original = item.getString("message"); val started = SystemClock.elapsedRealtimeNanos()
                        val value = owner.presentation(original); val outcome = requireNotNull(owner.lastOutcome)
                        assertEquals(0, outcome.localTranslationCalls)
                        val spans = JSONArray(value?.spans.orEmpty().map { span ->
                            check(requireNotNull(value).original.substring(span.start, span.end) == span.original)
                            JSONObject().put("start", span.start).put("end", span.end).put("original", span.original)
                                .put("target", span.translated).put("reading", span.romanization ?: JSONObject.NULL)
                        })
                        rows.put(JSONObject().put("id", item.getString("id")).put("source", source).put("target", target)
                            .put("original", original).put("classifier_guess", guesses[item.getString("id")] ?: JSONObject.NULL)
                            .put("exact_forward_reference", catalog.reference(original, source, target) != null)
                            .put("exact_reverse_reference", catalog.reference(original, target, source) != null)
                            .put("status", outcome.status.name).put("origin", outcome.origin?.name ?: JSONObject.NULL)
                            .put("source_evidence_source", outcome.sourceEvidence?.source ?: JSONObject.NULL)
                            .put("presentation_original", value?.original ?: original).put("spans", spans)
                            .put("mixed_native", value?.let { ImmersionText.project(it, showScript = true) } ?: original)
                            .put("mixed_reading", value?.let { ImmersionText.project(it) } ?: original)
                            .put("local_translation_calls", outcome.localTranslationCalls)
                            .put("elapsed_ms", (SystemClock.elapsedRealtimeNanos() - started) / 1_000_000.0))
                    }
                } finally { owner.close() }
                assertEquals(12, rows.length())
                val file = File(folder, "$source-$target.json"); val data = JSONObject().put("pair", "$source-$target").put("cases", rows).toString().toByteArray(Charsets.UTF_8)
                file.writeBytes(data); index.put(JSONObject().put("file", file.name).put("bytes", data.size).put("sha256", JapaneseStarterLookup.sha(data)).put("cases", rows.length()))
                total += rows.length(); report.put("cases", total); save()
            }
            assertEquals(1320, total); assertEquals(110, index.length()); report.put("complete", true); save()
        } catch (error: Throwable) { report.put("error", error.toString()); save(); throw error }
    }
}
