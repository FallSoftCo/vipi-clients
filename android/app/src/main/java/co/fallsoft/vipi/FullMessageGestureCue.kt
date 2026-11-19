package co.fallsoft.vipi

import android.content.Context
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.Box
import androidx.compose.material3.Snackbar
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.LocalAccessibilityManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay

/** Names match the actual native message actions, independent of touch grammar. */
@Composable internal fun fullMessageActionDescription(showingMeaning: Boolean = false, nativeScript: Boolean = false,
    canSwitchScript: Boolean = false): String = buildList {
    add(stringResource(R.string.full_translation_play))
    add(stringResource(if (showingMeaning) R.string.full_translation_practice else R.string.full_translation_meaning))
    if (canSwitchScript) add(stringResource(if (nativeScript) R.string.full_translation_reading else R.string.full_translation_script))
}.joinToString(". ")

/** Running-text names follow the current app locale, without forcing case. */
@Composable private fun messageLanguageName(code: String): String =
    java.util.Locale.forLanguageTag(code).getDisplayLanguage(LocalConfiguration.current.locales[0])

@Composable internal fun FullMessageContextHint(gestures: FullMessageGestures, source: String, target: String,
    modifier: Modifier = Modifier) {
    val practice = messageLanguageName(target)
    val basic = stringResource(R.string.full_translation_context_hint, practice, messageLanguageName(source))
    val writing = stringResource(R.string.full_translation_writing_hint, practice)
    val nativeName = initialLanguages.firstOrNull { it.code == target }?.localName.orEmpty()
    val reserveWriting = nativeName.codePoints().anyMatch { Character.isLetter(it) &&
        Character.UnicodeScript.of(it) != Character.UnicodeScript.LATIN }
    val actions = fullMessageActionDescription(gestures.meaning, gestures.nativeScript, gestures.canSwitchScript)
    Box(modifier.clearAndSetSemantics { this[SemanticsProperties.ContentDescription] = listOf(actions) }) {
        // Capacity only: never teach/announce an unavailable script action.
        // The async Chinese reading cannot move a held message when it arrives.
        Text(if (reserveWriting) "$basic $writing" else basic,
            Modifier.alpha(0f).clearAndSetSemantics { }, style = MaterialTheme.typography.bodyMedium)
        Text(if (gestures.canSwitchScript && !gestures.nativeScript) "$basic $writing" else basic,
            style = MaterialTheme.typography.bodyMedium)
    }
}

/** Intrinsic first-policy slot, outside the weighted timeline. Once shown, its
 * space survives acknowledgement/timeout until this chat leaves or the user
 * focuses the composer; hiding the cue never moves a message under a finger. */
@Composable internal fun FullMessageGestureCue(gestures: FullMessageGestures, composing: Boolean,
    deferred: Boolean, modifier: Modifier = Modifier, source: String = "en", target: String = "es") {
    val context = LocalContext.current
    val preferences = remember(context) { context.getSharedPreferences("full-message-gestures", Context.MODE_PRIVATE) }
    var reserved by remember(gestures) { mutableStateOf(!preferences.getBoolean("hold-script-policy-1", false)) }
    var shown by remember(gestures) { mutableStateOf(false) }
    var showing by remember(gestures) { mutableStateOf(true) }
    val actionDescription = fullMessageActionDescription(gestures.meaning, gestures.nativeScript, gestures.canSwitchScript)
    val keyboard = WindowInsets.ime.getBottom(LocalDensity.current) > 0
    val accessibility = LocalAccessibilityManager.current
    LaunchedEffect(gestures, gestures.interactions) {
        if (gestures.interactions > 0) {
            preferences.edit().putBoolean("hold-script-policy-1", true).apply()
            showing = false
            if (!shown) reserved = false
        }
    }
    LaunchedEffect(composing) { if (composing) { reserved = false; showing = false } }
    LaunchedEffect(shown) {
        if (shown) {
            delay(accessibility?.calculateRecommendedTimeoutMillis(4_000L, containsIcons = false,
                containsText = true, containsControls = false) ?: 4_000L)
            showing = false
        }
    }
    if (reserved && !deferred && !keyboard && !composing) {
        val opacity by animateFloatAsState(if (showing) 1f else 0f, label = "gesture cue")
        Snackbar(modifier.padding(horizontal = 12.dp, vertical = 8.dp).alpha(opacity)
            .then(if (!showing) Modifier.clearAndSetSemantics { } else Modifier.clearAndSetSemantics {
                this[SemanticsProperties.TestTag] = "full-message-gesture-cue"
                this[SemanticsProperties.ContentDescription] = listOf(actionDescription)
            })
            .onGloballyPositioned {
                if (!shown && showing && it.size.height > 0) {
                    shown = true
                    preferences.edit().putBoolean("hold-script-policy-1", true).apply()
                }
            }) { FullMessageContextHint(gestures, source, target) }
    }
}
