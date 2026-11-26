package co.fallsoft.vipi

import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.Box
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalAccessibilityManager
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay

/** Names match the actual native message actions, independent of touch grammar. */
@Composable internal fun fullMessageActionDescription(showingMeaning: Boolean = false, nativeScript: Boolean = false,
    canSwitchScript: Boolean = false, mode: ImmersionMode = ImmersionMode.NEW_WORD): String = buildList {
    add(stringResource(if (mode == ImmersionMode.FULL_MESSAGES) R.string.lookup_play_message else R.string.full_translation_play))
    add(stringResource(if (showingMeaning) { if (mode == ImmersionMode.FULL_MESSAGES) R.string.full_message_show_translation else R.string.full_translation_practice } else R.string.full_translation_meaning))
    if (canSwitchScript) add(stringResource(if (nativeScript) R.string.full_translation_reading else R.string.full_translation_script))
}.joinToString(". ")

/** Running-text names follow the current app locale, without forcing case. */
@Composable private fun messageLanguageName(code: String): String =
    java.util.Locale.forLanguageTag(code).getDisplayLanguage(LocalConfiguration.current.locales[0])

@Composable internal fun FullMessageContextHint(gestures: FullMessageGestures, source: String, target: String,
    modifier: Modifier = Modifier) {
    val practice = messageLanguageName(target)
    val basic = if (gestures.mode == ImmersionMode.FULL_MESSAGES) stringResource(R.string.full_message_context_hint)
        else stringResource(R.string.full_translation_context_hint, practice)
    val writing = stringResource(R.string.full_translation_writing_hint, practice)
    val nativeName = translationLanguages.firstOrNull { it.code == target }?.localName.orEmpty()
    val reserveWriting = nativeName.codePoints().anyMatch { Character.isLetter(it) &&
        Character.UnicodeScript.of(it) != Character.UnicodeScript.LATIN }
    val actions = fullMessageActionDescription(gestures.meaning, gestures.nativeScript, gestures.canSwitchScript, gestures.mode)
    Box(modifier.clearAndSetSemantics { this[SemanticsProperties.ContentDescription] = listOf(actions) }) {
        // Capacity only: never teach/announce an unavailable script action.
        // The async Chinese reading cannot move a held message when it arrives.
        Text(if (reserveWriting) "$basic $writing" else basic,
            Modifier.alpha(0f).clearAndSetSemantics { }, style = MaterialTheme.typography.bodyMedium)
        Text(if (gestures.canSwitchScript && !gestures.nativeScript) "$basic $writing" else basic,
            style = MaterialTheme.typography.bodyMedium)
    }
}

/** A visit that has shown a hint never counts toward independent learning. */
@Composable internal fun FullMessageGestureCue(gestures: FullMessageGestures, education: HoldEducation?,
    composing: Boolean, deferred: Boolean, foreground: Boolean) {
    val density = LocalDensity.current
    val keyboard = WindowInsets.ime.getBottom(density) > 0
    val day = java.time.LocalDate.now()
    var observedReveals by remember(gestures) { mutableIntStateOf(gestures.reveals) }
    var independentlyRevealed by remember(gestures) { mutableStateOf(false) }
    var promptedThisVisit by remember(gestures) { mutableStateOf(false) }
    var visible by remember(gestures) { mutableStateOf(false) }
    var reserved by remember(gestures) { mutableStateOf(false) }
    var cueHeight by remember(gestures) { mutableStateOf(0.dp) }
    val eligible = education != null && gestures.hasVisibleTranslation && foreground && !deferred && !keyboard && !composing
    val accessibility = LocalAccessibilityManager.current
    LaunchedEffect(gestures, eligible, day, gestures.reveals, gestures.meaning) {
        val revealed = gestures.reveals != observedReveals
        observedReveals = gestures.reveals
        if (!eligible) { visible = false; reserved = false; return@LaunchedEffect }
        if (revealed) {
            visible = false
            if (!promptedThisVisit && !independentlyRevealed) {
                independentlyRevealed = true
                education.independentReveal(day)
            }
        } else if (!gestures.meaning && !promptedThisVisit && !independentlyRevealed) {
            if (education.hasPreviousImpression()) delay(4_000)
            if (education.claim(day)) {
                promptedThisVisit = true; reserved = true; visible = true
            }
        }
    }
    LaunchedEffect(visible, gestures.held) {
        if (!visible && !gestures.held) reserved = false
    }
    LaunchedEffect(visible) {
        if (visible) {
            delay(accessibility?.calculateRecommendedTimeoutMillis(8_000, containsText = true, containsControls = true) ?: 8_000)
            visible = false
        }
    }
    if (reserved && eligible && (visible || gestures.held)) {
        // Keep the row's footprint while a held message changes face.
        if (visible) Box(Modifier.onSizeChanged { cueHeight = with(density) { it.height.toDp() } }) {
            HoldHintRow(gestures) { education.dismiss(); visible = false; reserved = false }
        } else androidx.compose.foundation.layout.Spacer(Modifier.height(cueHeight))
    }
}

@Composable internal fun HoldHintRow(gestures: FullMessageGestures, dismiss: () -> Unit) {
    val description = fullMessageActionDescription(gestures.meaning, gestures.nativeScript, gestures.canSwitchScript, gestures.mode)
    androidx.compose.foundation.layout.Row(Modifier.fillMaxWidth().padding(horizontal = 14.dp),
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
        Text(stringResource(R.string.hold_original_hint), Modifier.weight(1f).clearAndSetSemantics {
            this[SemanticsProperties.TestTag] = "full-message-gesture-cue"
            this[SemanticsProperties.ContentDescription] = listOf(description)
        }, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        androidx.compose.material3.TextButton(onClick = dismiss) { Text(stringResource(R.string.hold_hint_dismiss)) }
    }
}
