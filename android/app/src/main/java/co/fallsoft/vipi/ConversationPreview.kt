package co.fallsoft.vipi

import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.ui.res.stringResource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Preview is a real local translation request, not a lookup/example catalog. */
@Composable internal fun ConversationPreview(source: String, target: String, scrolling: Boolean = false) {
    val context = LocalContext.current
    val translation = remember(source, target) { ConversationTranslation(context, source, target) }
    val gestures = remember(source, target) { FullMessageGestures() }
    val scope = rememberCoroutineScope()
    val speech = remember(source, target) { SpeechPlayback(context, target, scope) }
    val warmups = remember(source, target) { mapOf(source to "1", target to "1") }
    val audio = remember(translation, speech) { ConversationAutoplay(translation, speech, scope) {} }
    LaunchedEffect(speech) { speech.prepare(warmups) }
    LaunchedEffect(scrolling) { if (scrolling) gestures.held = false }
    DisposableEffect(translation, speech) { onDispose { audio.close(); translation.close(); speech.close() } }
    Column(Modifier.fillMaxWidth().fullMessageGestures(gestures), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Surface(shape = RoundedCornerShape(18.dp), color = MaterialTheme.colorScheme.surface,
            modifier = Modifier.fillMaxWidth()) {
            FullMessageBubble("Let's meet tomorrow after work.", "language-preview-$source-$target", translation,
                gestures, audio) {}
        }
        FullMessageContextHint(gestures, source, target)
        SpeechPreparationHelp(speech.state, speech.error) { speech.prepare(warmups) }
    }
}

/** Actionable recovery when a selected pair cannot prepare offline speech. */
@Composable internal fun SpeechPreparationHelp(state: SpeechState, error: String?, openSettings: (() -> Boolean)? = null, retry: () -> Unit) {
    val context = LocalContext.current
    var settingsError by remember { mutableStateOf(false) }
    error?.let { Text(it, fontSize = 16.sp, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    if (state == SpeechState.UNAVAILABLE) {
        if (error == null) Text(stringResource(R.string.ui_6a8b22232bef), fontSize = 16.sp)
        if (settingsError) Text(stringResource(R.string.ui_dad92e0774f7), fontSize = 16.sp)
        Row {
            TextButton(onClick = {
                settingsError = !(openSettings?.invoke() ?: runCatching { context.startActivity(Intent("com.android.settings.TTS_SETTINGS")) }.isSuccess)
            }) { Text(stringResource(R.string.ui_8b3f05442c1b)) }
            TextButton(onClick = { settingsError = false; retry() }) { Text(stringResource(R.string.ui_ed783fa140ed)) }
        }
    }
}
