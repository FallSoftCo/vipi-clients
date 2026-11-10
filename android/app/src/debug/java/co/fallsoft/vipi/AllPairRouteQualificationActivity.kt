package co.fallsoft.vipi

import android.os.Bundle
import android.os.Debug
import android.os.SystemClock
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import co.fallsoft.vipi.core.ImmersionText
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/** Debug host for the real default conversation engine and stable native message row. */
class AllPairRouteQualificationActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        check(BundledStarterLookup.ALL_PAIR_PROMOTION_ENABLED)
        val id = requireNotNull(intent.getStringExtra("case_id"))
        val run = requireNotNull(intent.getStringExtra("run")); require(run.matches(Regex("[0-9]{3}")))
        val cases = JSONArray(File(filesDir, "all-pair-ui-cases-r01.json").readText())
        val row = (0 until cases.length()).map { cases.getJSONObject(it) }.single { it.getString("id") == id }
        val source = row.getString("source"); val target = row.getString("target"); val original = row.getString("original")
        require(source in initialLanguages.map { it.code } && target in initialLanguages.map { it.code } && source != target)
        val out = File(filesDir, "all-pair-ui-$run-$source-$target"); check(out.isDirectory)
        setContent { VipiTheme(Appearance.LIGHT) {
            val scope = rememberCoroutineScope()
            val owner = remember { ConversationImmersion(this, source, target, 0.25) }
            val speech = remember { SpeechPlayback(this, source, target, scope) }
            var ready by remember { mutableStateOf(false) }
            DisposableEffect(Unit) { onDispose { owner.close(); speech.close() } }
            LaunchedEffect(Unit) {
                val runtime = Runtime.getRuntime(); val heapBefore = runtime.totalMemory() - runtime.freeMemory()
                val started = SystemClock.elapsedRealtimeNanos()
                check(owner.inputLanguage(id) == null)
                val result = requireNotNull(owner.presentation(original, messageID = id)); val outcome = requireNotNull(owner.lastOutcome)
                val elapsed = (SystemClock.elapsedRealtimeNanos() - started) / 1_000_000.0
                check(outcome.origin?.name == "SOURCE_REFERENCE_PARTIAL" && outcome.localTranslationCalls == 0)
                check(ImmersionText.project(result) == row.getString("latin"))
                check(ImmersionText.project(result, showScript = true) == row.getString("native"))
                val memory = Debug.MemoryInfo(); Debug.getMemoryInfo(memory)
                val proof = JSONObject().put("case", id).put("source", source).put("target", target).put("original", original)
                    .put("default_provider", true).put("manual_input_language", JSONObject.NULL).put("density", 0.25)
                    .put("latin", ImmersionText.project(result)).put("native", ImmersionText.project(result, showScript = true))
                    .put("spans", JSONArray(result.spans.map { JSONObject().put("start", it.start).put("end", it.end)
                        .put("original", it.original).put("target", it.translated).put("reading", it.romanization ?: JSONObject.NULL) }))
                    .put("translation_calls", outcome.localTranslationCalls).put("origin", outcome.origin.toString())
                    .put("first_presentation_ms", elapsed).put("heap_before", heapBefore)
                    .put("heap_after", runtime.totalMemory() - runtime.freeMemory()).put("heap_limit", runtime.maxMemory())
                    .put("instrumented_process_pss_kib", memory.totalPss).put("memory_observation_is_instrumented", true)
                File(out, "proof.json").writeText(proof.toString(2)); ready = true
            }
            Surface(Modifier.fillMaxSize()) { Column(Modifier.fillMaxWidth().padding(24.dp)) {
                Text("Reading a message", style = MaterialTheme.typography.titleLarge)
                Spacer(Modifier.height(24.dp))
                if (ready) ConversationImmersionText(original, id, owner, speech, false, {}, metadata = { Text("Local conversation") })
            } }
        } }
    }
}
