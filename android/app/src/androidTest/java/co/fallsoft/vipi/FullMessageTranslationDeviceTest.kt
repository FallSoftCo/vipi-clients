package co.fallsoft.vipi

import android.os.SystemClock
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.util.concurrent.CopyOnWriteArrayList
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/**
 * Real ML Kit path: no supplied target text, detector, readings or translator. Synthetic
 * source-only inputs; semantic quality is reviewed from raw outputs, never inferred from nonblank
 * text or model completion.
 */
class FullMessageTranslationDeviceTest {
    private class ObservedLocalTranslation : LanguageTranslation {
        private val actual = LocalTranslation()
        val calls = CopyOnWriteArrayList<JSONObject>()

        override suspend fun prepare(source: String, target: String, cellularAllowed: Boolean) {
            val row =
                JSONObject().put("kind", "prepare").put("source", source).put("target", target)
            calls += row
            val started = SystemClock.elapsedRealtime()
            try {
                actual.prepare(source, target, cellularAllowed)
                row.put("completed", true)
            } catch (failure: Exception) {
                row.put("failure", failure.javaClass.name)
                throw failure
            } finally {
                row.put("elapsed_ms", SystemClock.elapsedRealtime() - started)
            }
        }

        override suspend fun translate(text: String, source: String, target: String): String {
            val row =
                JSONObject()
                    .put("kind", "translate")
                    .put("source", source)
                    .put("target", target)
                    .put("input", text)
            calls += row
            val started = SystemClock.elapsedRealtime()
            try {
                return actual.translate(text, source, target).also {
                    row.put("output", it).put("unchanged", it == text)
                }
            } catch (failure: Exception) {
                row.put("failure", failure.javaClass.name)
                throw failure
            } finally {
                row.put("elapsed_ms", SystemClock.elapsedRealtime() - started)
            }
        }

        override fun close() = actual.close()
    }

    @Test
    fun everyConfiguredDirectionRequestsFullLocalTranslation(): Unit = runBlocking {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        check(BuildConfig.DEBUG && BuildConfig.APPLICATION_ID.endsWith(".sourcecontextqa"))
        check(InstrumentationRegistry.getArguments().getString("vipiDedicatedEmulator") == "true")
        val context = instrumentation.targetContext
        val run =
            InstrumentationRegistry.getArguments().getString("vipiFullTranslationRun") ?: "001"
        require(run.matches(Regex("[0-9]{3}")))
        val directory = File(context.filesDir, "full-message-provider-$run")
        check(!directory.exists())
        check(directory.mkdirs())
        val sources =
            linkedMapOf(
                "en" to
                    listOf("I left the blue notebook beside the kitchen window yesterday.", "Yes."),
                "es" to
                    listOf("Ayer dejé el cuaderno azul junto a la ventana de la cocina.", "Sí."),
                "fr" to
                    listOf(
                        "Hier, j'ai laissé le cahier bleu près de la fenêtre de la cuisine.",
                        "Oui.",
                    ),
                "pt" to listOf("Ontem deixei o caderno azul ao lado da janela da cozinha.", "Sim."),
                "de" to
                    listOf(
                        "Gestern habe ich das blaue Heft neben dem Küchenfenster liegen lassen.",
                        "Ja.",
                    ),
                "it" to
                    listOf(
                        "Ieri ho lasciato il quaderno blu accanto alla finestra della cucina.",
                        "Sì.",
                    ),
                "sw" to
                    listOf("Jana niliacha daftari la buluu karibu na dirisha la jikoni.", "Ndiyo."),
                "ar" to listOf("تركت الدفتر الأزرق بجانب نافذة المطبخ أمس.", "نعم."),
                "zh" to listOf("昨天我把蓝色笔记本放在厨房窗户旁边了。", "好的。"),
                "ja" to listOf("昨日、青いノートを台所の窓のそばに置き忘れました。", "はい。"),
                "ko" to listOf("어제 파란 공책을 부엌 창문 옆에 두고 왔어요.", "네."),
            )
        assertEquals(initialLanguages.map { it.code }.toSet(), sources.keys)
        data class Input(val id: String, val kind: String, val text: String)
        data class Direction(val source: String, val target: String, val cases: List<Input>)
        val mode =
            InstrumentationRegistry.getArguments().getString("vipiFullTranslationCorpus")
                ?: "functional226"
        var inputSHA: String? = null
        val directions =
            when (mode) {
                "functional226" ->
                    sources.flatMap { (source, inputs) ->
                        sources.keys
                            .filter { it != source }
                            .map { target ->
                                val special =
                                    when (source to target) {
                                        "en" to "zh" ->
                                            listOf(
                                                "already-practice" to "我们明天下午在车站见面。",
                                                "third-language" to
                                                    "Dejé el cuaderno en la mesa de la cocina.",
                                                "short-shared" to "OK",
                                                "literal-name-emoji" to
                                                    "José https://example.test/Case9?x=A ☕",
                                            )
                                        "en" to "es" ->
                                            listOf(
                                                "already-practice" to
                                                    "Nos vemos mañana por la tarde.",
                                                "third-language" to
                                                    "J'ai laissé le cahier près de la fenêtre.",
                                            )
                                        else -> emptyList()
                                    }
                                Direction(
                                    source,
                                    target,
                                    (inputs.map { "configured-source" to it } + special)
                                        .mapIndexed { index, (kind, text) ->
                                            Input("$source-$target-$index", kind, text)
                                        },
                                )
                            }
                    }
                "shared-development220" -> {
                    val bytes =
                        File(context.filesDir, "full-message-provider-input-$run.json").readBytes()
                    inputSHA =
                        java.security.MessageDigest.getInstance("SHA-256")
                            .digest(bytes)
                            .joinToString("") { "%02x".format(it) }
                    assertEquals(
                        "b7db0a1ff038f1f0b49a3902b7317d3293987a541e597c593f37e26788e7e8b2",
                        inputSHA,
                    )
                    val pairs = JSONObject(bytes.toString(Charsets.UTF_8)).getJSONArray("pairs")
                    (0 until pairs.length()).map { index ->
                        val pair = pairs.getJSONObject(index)
                        val cases = pair.getJSONArray("cases")
                        Direction(
                            pair.getString("source"),
                            pair.getString("target"),
                            (0 until cases.length()).map { item ->
                                val record = cases.getJSONObject(item)
                                Input(
                                    record.getString("id"),
                                    "same-input-development",
                                    record.getString("text"),
                                )
                            },
                        )
                    }
                }
                else -> error("Unknown source-only corpus mode")
            }
        assertEquals(110, directions.size)
        assertEquals(110, directions.map { it.source to it.target }.toSet().size)
        require(
            directions.all {
                it.source in sources && it.target in sources && it.source != it.target
            }
        )
        val expectedRows = if (mode == "functional226") 226 else 220
        val rows = JSONArray()
        val failures = JSONArray()
        val report =
            JSONObject()
                .put("policy", FullMessageTranslation.POLICY)
                .put("complete", false)
                .put("provider", "actual ML Kit local translator and language identification")
                .put("source_only_authored_inputs", true)
                .put("injected_target_or_readings", false)
                .put("semantic_quality_claimed", false)
                .put("corpus_mode", mode)
                .put("input_sha256", inputSHA ?: JSONObject.NULL)
                .put("same_input_cross_provider_semantics_claimed", false)
                .put("rows", rows)
                .put("failures", failures)
        fun save() {
            File(directory, "receipt.json").writeText(report.toString(2))
        }
        save()
        try {
            withTimeout(1_800_000) {
                for (direction in directions) {
                    val source = direction.source
                    val target = direction.target
                    val provider = ObservedLocalTranslation()
                    val owner =
                        ConversationTranslation(context, source, target, translator = provider)
                    try {
                        for (sample in direction.cases) {
                            val id = sample.id
                            val kind = sample.kind
                            val text = sample.text
                            val before =
                                provider.calls.count { it.getString("kind") == "translate" }
                            val started = SystemClock.elapsedRealtime()
                            val row =
                                JSONObject()
                                    .put("id", id)
                                    .put("configured_source", source)
                                    .put("target", target)
                                    .put("original", text)
                                    .put("case_kind", kind)
                            try {
                                val result = withTimeout(180_000) { owner.resolve(id, text) }
                                val calls =
                                    provider.calls.count { it.getString("kind") == "translate" } -
                                        before
                                row.put("result", result.json())
                                    .put("translation_calls", calls)
                                    .put("practice_unchanged", result.practiceText == text)
                                    .put("state", owner.state(id, text)?.phase?.name)
                                assertEquals(text, result.original)
                                assertEquals(target, result.practiceLanguage)
                                assertEquals(source, result.meaningLanguage)
                                assertTrue(
                                    "Every uncached message must invoke a real model, including short/shared text",
                                    calls > 0,
                                )
                                assertTrue(
                                    result.practiceText.isNotBlank() &&
                                        result.meaningText.isNotBlank()
                                )
                            } catch (cancelled: CancellationException) {
                                throw cancelled
                            } catch (failure: Throwable) {
                                row.put("failure", failure.javaClass.name)
                                    .put("detail", failure.message)
                                    .put("state", owner.state(id, text)?.phase?.name)
                                failures.put(
                                    JSONObject()
                                        .put("id", id)
                                        .put("failure", failure.javaClass.name)
                                        .put("detail", failure.message)
                                )
                            } finally {
                                row.put("elapsed_ms", SystemClock.elapsedRealtime() - started)
                                rows.put(row)
                                save()
                            }
                        }
                    } finally {
                        owner.close()
                        File(directory, "$source-$target-calls.json")
                            .writeText(JSONArray(provider.calls).toString(2))
                        instrumentation.sendStatus(
                            0,
                            android.os.Bundle().apply {
                                putString(
                                    "vipi_full_translation_progress",
                                    "$source->$target rows=${rows.length()}",
                                )
                            },
                        )
                    }
                }
            }
            assertEquals(expectedRows, rows.length())
            report.put("complete", true)
            assertEquals(
                "Actual local model failures retained in receipt; do not count as successful immersion",
                0,
                failures.length(),
            )
        } finally {
            save()
        }
    }
}
