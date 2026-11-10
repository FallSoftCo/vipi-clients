package co.fallsoft.vipi

import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import co.fallsoft.vipi.core.ImmersionResult
import co.fallsoft.vipi.core.VocabularyEntry
import org.json.JSONObject

internal object ConversationExamples {
    fun reading(context: Context, target: String): String? = JSONObject(context.assets.open("immersion-preview.json").bufferedReader().use { it.readText() }).getJSONObject("languages").getJSONObject(target).optString("reading").takeIf { it.isNotBlank() }
    fun result(context: Context, source: String, target: String): ImmersionResult {
        val languages = JSONObject(context.assets.open("immersion-preview.json").bufferedReader().use { it.readText() }).getJSONObject("languages")
        val from = languages.getJSONObject(source); val to = languages.getJSONObject(target)
        val a = from.getJSONObject("words"); val b = to.getJSONObject("words")
        val entries = a.keys().asSequence().map { key ->
            val destination = b.getJSONObject(key); val surface = destination.getString("surface")
            VocabularyEntry(a.getJSONObject(key).getString("surface"), listOf(surface),
                if (destination.has("reading")) mapOf(surface to listOf(destination.getString("reading"))) else emptyMap())
        }.toList()
        return LocalImmersion.align(from.getString("text"), to.getString("text"), entries, .5, source, target)
    }
}

@Composable internal fun ConversationPreview(source: String, target: String, scrolling: Boolean = false) {
    val context = LocalContext.current
    val result = remember(source, target) { ConversationExamples.result(context, source, target) }
    val fullReading = remember(target) { ConversationExamples.reading(context, target) }
    var mode by remember(source, target) { mutableStateOf(ReadingMode.IMMERSED) }
    val scope = rememberCoroutineScope()
    val speech = remember(source, target) { SpeechPlayback(context, source, target, scope) }
    LaunchedEffect(speech) { speech.prepare(mapOf(source to result.original, target to result.translation)) }
    DisposableEffect(speech) { onDispose { speech.close() } }
    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = .48f), RoundedCornerShape(28.dp)).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("EXAMPLE MESSAGE", fontSize = 10.sp, letterSpacing = 1.2.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        ImmersionBubble(result, mode, speech, source, target, "language-preview-$source-$target", scrolling, fullReading = fullReading)
        Text("Highlighted words switch between your two languages. This is a prepared example; available words in your chats vary by language. You can also view a prepared full translation.", fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        TextButton(onClick = { mode = if (mode == ReadingMode.TRANSLATION) ReadingMode.IMMERSED else ReadingMode.TRANSLATION }) {
            Text(if (mode == ReadingMode.TRANSLATION) "Resume word switching" else "Show full translation in ${languageName(target)}", fontSize = 13.sp)
        }
        speech.error?.let { Text(it, fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    }
}
