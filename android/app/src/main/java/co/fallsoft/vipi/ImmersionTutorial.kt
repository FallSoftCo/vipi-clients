package co.fallsoft.vipi

import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.selected
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Waves
import androidx.compose.material.icons.outlined.Anchor
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner

/** Two transient owners preserve the shallow plan when trying Deep and back.
 * No FullMessageTranslationStore, MessageVault, chat, account or send boundary. */
internal class ImmersionTutorialTranslations(context: android.content.Context, source: String, target: String) : AutoCloseable {
    private val owners = ImmersionMode.entries.associateWith { mode ->
        OnboardingPreviewSource.translation(context, source, target, mode = mode)
    }
    operator fun get(mode: ImmersionMode) = owners.getValue(mode)
    override fun close() { owners.values.forEach { it.close() } }
}

/** The real message view supplies touch and native accessibility actions. */
@Composable internal fun ImmersionTutorialContent(source: String, target: String, mode: ImmersionMode,
    onToggle: () -> Unit, scrolling: Boolean = false) {
    val context = LocalContext.current
    val owners = remember(source, target) { ImmersionTutorialTranslations(context, source, target) }
    val translation = owners[mode]
    val text = ImmersionTutorialSource.text(source)
    val id = ImmersionTutorialSource.messageID(source, target)
    val scope = rememberCoroutineScope()
    val speech = remember(source, target) { SpeechPlayback(context, target, scope) }
    val gestures = remember(source, target) { FullMessageGestures() }
    val audio = remember(translation, speech) { ConversationAutoplay(translation, speech, scope) {} }
    val warmups = remember(target) { mapOf(target to "1") }
    val state = translation.state(id, text)
    LaunchedEffect(speech) { speech.prepare(warmups) }
    LaunchedEffect(mode) { gestures.mode = mode; gestures.held = false; gestures.accessibilityMeaning = false; speech.stop() }
    LaunchedEffect(gestures.meaning, scrolling) {
        if (gestures.meaning || scrolling) audio.setAutoplayEnabled(false)
        if (scrolling) gestures.held = false
    }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(lifecycle, audio) {
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_STOP) {
            audio.setAutoplayEnabled(false); gestures.held = false
        } }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer); audio.close() }
    }
    DisposableEffect(owners) { onDispose { owners.close() } }
    DisposableEffect(speech) { onDispose { speech.close() } }
    Text(stringResource(R.string.immersion_mode_title), style = MaterialTheme.typography.headlineLarge,
        modifier = Modifier.semantics { heading() }.testTag("tutorial-title"))
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            ImmersionMode.entries.forEach { choice ->
                val active = choice == mode
                val choose = { if (!active) { audio.setAutoplayEnabled(false); onToggle() } }
                val label: @Composable () -> Unit = {
                    Icon(if (choice == ImmersionMode.FULL_MESSAGES) Icons.Outlined.Anchor else Icons.Outlined.Waves, null, Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text(stringResource(if (choice == ImmersionMode.FULL_MESSAGES) R.string.immersion_mode_full else R.string.immersion_mode_words_short), maxLines = 2)
                }
                val item = Modifier.heightIn(min = 48.dp).testTag("tutorial-mode-${choice.name}").semantics { role = Role.RadioButton; selected = active }
                if (active) FilledTonalButton(onClick = choose, modifier = item, content = { label() })
                else OutlinedButton(onClick = choose, modifier = item, content = { label() })
            }
        }
        Text(stringResource(if (mode == ImmersionMode.NEW_WORD) R.string.tutorial_shallow_description else R.string.tutorial_deep_description),
            modifier = Modifier.animateContentSize(tween(220)), color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    // The same source/id stays in place; the normal local translator generates
    // the selected pair. No lookup outputs or example audio are supplied.
    Column(Modifier.fillMaxWidth().testTag("tutorial-message").fullMessageGestures(gestures)) {
        ChatBubbleFrame(false, Modifier.fillMaxWidth()) {
            FullMessageBubble(text, id, translation, gestures, audio) {}
        }
    }
    if (state?.value != null) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (speech.state in setOf(SpeechState.READY, SpeechState.RENDERING, SpeechState.PLAYING)) Text(stringResource(R.string.tutorial_tap), color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(stringResource(R.string.tutorial_hold), color = MaterialTheme.colorScheme.onSurfaceVariant)
        if (gestures.canSwitchScript) Text(stringResource(R.string.tutorial_script), color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    if (state == null || state.phase in setOf(MessageTranslationPhase.PREPARING, MessageTranslationPhase.TRANSLATING)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
            Text(stringResource(R.string.tutorial_preparing_translation), style = MaterialTheme.typography.bodyMedium)
        }
    }
    if (speech.state == SpeechState.PREPARING) Text(stringResource(R.string.tutorial_preparing_voice), style = MaterialTheme.typography.bodyMedium)
    SpeechPreparationHelp(speech.state, speech.error) { speech.prepare(warmups) }
}
