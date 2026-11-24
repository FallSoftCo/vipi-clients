package co.fallsoft.vipi

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.VolumeOff
import androidx.compose.material.icons.automirrored.outlined.VolumeUp
import androidx.compose.material.icons.outlined.Anchor
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.Translate
import androidx.compose.material.icons.outlined.Waves
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import java.util.UUID

private val iconSize = 20.dp
private val labelGap = 5.dp
private val chipPadding = 8.dp
private val headerGap = 4.dp
private val avatarSize = 34.dp
private val nameGap = 8.dp

@Composable internal fun ConversationHeader(name: String, peer: UUID, autoplay: Boolean, audioAvailable: Boolean,
    onAutoplay: () -> Unit, mode: ImmersionMode, onMode: (() -> Unit)?, minHeight: Dp, modifier: Modifier,
    streak: Int = 0, groupStreak: Boolean = false,
    languageSource: String? = null, languageTarget: String? = null, languageDefaultTarget: String? = null,
    languageUsesDefault: Boolean = true, onLanguage: ((String) -> Unit)? = null,
    onUseDefaultLanguage: (() -> Unit)? = null,
    back: @Composable () -> Unit, overflow: @Composable () -> Unit) {
    val autoplayLabel = stringResource(R.string.autoplay_label)
    val shallow = stringResource(R.string.immersion_mode_words_short)
    val deep = stringResource(R.string.immersion_mode_full)
    val languageLabel = stringResource(R.string.conversation_language)
    val languageChange = stringResource(R.string.conversation_language_change)
    val useDefault = stringResource(R.string.conversation_language_use_default,
        languageDefaultTarget?.let(::languageName).orEmpty())
    val labelStyle = MaterialTheme.typography.labelLarge
    val nameStyle = MaterialTheme.typography.titleLarge
    val measurer = rememberTextMeasurer()
    val density = LocalDensity.current
    fun width(text: String, style: TextStyle) = with(density) {
        measurer.measure(text, style, softWrap = false, maxLines = 1).size.width.toDp()
    }
    val autoplayWidth = width(autoplayLabel, labelStyle)
    val modeWidth = maxOf(width(shallow, labelStyle), width(deep, labelStyle))
    fun chipWidth(label: Dp) = maxOf(48.dp, chipPadding * 2 + iconSize + labelGap + label)
    val nameWidth = width(name, nameStyle)
    val showLanguage = languageTarget != null && onLanguage != null
    val languageFullLabel = languageTarget?.let(::languageName).orEmpty()
    val languageCodeLabel = languageTarget?.uppercase().orEmpty()
    val languageFullWidth = if (showLanguage) chipWidth(width(languageFullLabel, labelStyle)) else 0.dp
    val languageCodeWidth = if (showLanguage) maxOf(56.dp, chipWidth(width(languageCodeLabel, labelStyle))) else 0.dp
    val controlCount = 1 + (if (onMode == null) 0 else 1) + (if (showLanguage) 1 else 0)
    val actionGap = headerGap * (controlCount - 1)
    val fullActionWidth = languageFullWidth + chipWidth(autoplayWidth) +
        (if (onMode == null) 0.dp else chipWidth(modeWidth)) + actionGap
    val codeActionWidth = languageCodeWidth + chipWidth(autoplayWidth) +
        (if (onMode == null) 0.dp else chipWidth(modeWidth)) + actionGap
    val iconActionWidth = languageCodeWidth + 48.dp +
        (if (onMode == null) 0.dp else 48.dp) + actionGap
    val streakWidth = if (streak < 2) 0.dp else nameGap + maxOf(48.dp,
        25.dp + width(streakNumeral(streak), MaterialTheme.typography.titleSmall.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.Bold, fontFeatureSettings = "tnum")))
    val full = mode == ImmersionMode.FULL_MESSAGES
    var languageMenu by remember { mutableStateOf(false) }
    BoxWithConstraints(modifier) {
        val centerWidth = maxWidth - 48.dp * 2 // Back and overflow each own one 48dp target.
        val identity = avatarSize + nameGap + headerGap + streakWidth
        val minimumName = minOf(nameWidth, with(density) { nameStyle.fontSize.toDp() } * 2)
        // Preserve the original single-row header when the identity and three
        // icon actions fit. Labels are added when they fit, but never at the
        // cost of moving the controls away from the conversation name.
        val inlineFull = centerWidth >= identity + minimumName + headerGap + fullActionWidth
        val inlineCompact = centerWidth >= identity + minimumName + headerGap + iconActionWidth
        val secondRow = !inlineFull && !inlineCompact
        val rowFullLabels = secondRow && maxWidth >= fullActionWidth
        val rowCompactLabels = secondRow && !rowFullLabels && maxWidth >= codeActionWidth
        val controlLabels = inlineFull || rowFullLabels || rowCompactLabels
        val fullLanguage = inlineFull || rowFullLabels
        val inline = !secondRow
        val languageMenuWidth = (maxWidth - 16.dp).coerceIn(200.dp, 340.dp)
        val actions: @Composable RowScope.() -> Unit = {
            if (showLanguage) Box {
                HeaderAction("conversation-language", languageLabel,
                    if (fullLanguage) languageFullLabel else languageCodeLabel, languageChange, languageChange,
                    Icons.Outlined.Translate, false, true, true,
                    if (fullLanguage) languageFullWidth else languageCodeWidth,
                    toggle = false, click = { languageMenu = true })
                DropdownMenu(expanded = languageMenu, onDismissRequest = { languageMenu = false },
                    modifier = Modifier.width(languageMenuWidth)) {
                    Text(languageLabel, Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
                        style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    initialLanguages.filter { it.code != languageSource }.forEach { language ->
                        val active = language.code == languageTarget
                        DropdownMenuItem(
                            text = { Text("${languageName(language.code)} · ${language.localName}") },
                            modifier = Modifier.semantics { selected = active }.testTag("conversation-language-${language.code}"),
                            trailingIcon = if (active) {{ Icon(Icons.Outlined.CheckCircle, null) }} else null,
                            onClick = { languageMenu = false; if (!active) onLanguage(language.code) })
                    }
                    if (!languageUsesDefault && onUseDefaultLanguage != null && languageDefaultTarget != null) {
                        HorizontalDivider()
                        DropdownMenuItem(text = { Text(useDefault) },
                            modifier = Modifier.testTag("conversation-language-default"),
                            onClick = { languageMenu = false; onUseDefaultLanguage() })
                    }
                }
            }
            HeaderAction("conversation-autoplay", autoplayLabel, autoplayLabel,
                stringResource(if (autoplay) R.string.settings_on else R.string.settings_off),
                stringResource(if (autoplay) R.string.autoplay_turn_off else R.string.autoplay_turn_on),
                if (autoplay) Icons.AutoMirrored.Outlined.VolumeUp else Icons.AutoMirrored.Outlined.VolumeOff,
                autoplay, audioAvailable, controlLabels, chipWidth(autoplayWidth), click = onAutoplay)
            if (onMode != null) {
                // Switch the one visible face at the midpoint, keeping the glyph and text legible.
                // Compose duration scale also covers disabled system animations.
                val depth = animateFloatAsState(if (full) 1f else 0f, tween(200), label = "Immersion")
                val deepFace = depth.value >= .5f
                val current = if (full) deep else shallow
                HeaderAction("conversation-immersion", stringResource(R.string.immersion_mode_title), if (deepFace) deep else shallow, current,
                    stringResource(R.string.chat_switch_mode, if (full) shallow else deep),
                    if (deepFace) Icons.Outlined.Anchor else Icons.Outlined.Waves, full, true, controlLabels, chipWidth(modeWidth),
                    faceAlpha = { .8f + .2f * kotlin.math.abs(2f * depth.value - 1f) }, click = onMode)
            }
        }
        Column {
            Row(Modifier.fillMaxWidth().heightIn(min = minHeight), verticalAlignment = Alignment.CenterVertically) {
                back()
                Row(Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(nameGap),
                    verticalAlignment = Alignment.CenterVertically) {
                    ContactAvatar(name, peer, avatarSize)
                    Text(name, Modifier.weight(1f, fill = false).testTag("conversation-contact"), style = nameStyle,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                    ChatStreakBadge(streak, groupStreak, explain = true)
                }
                if (!secondRow) {
                    Spacer(Modifier.width(headerGap))
                    Row(horizontalArrangement = Arrangement.spacedBy(headerGap), content = actions)
                }
                overflow()
            }
            if (secondRow) Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(headerGap, Alignment.End), content = actions)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable private fun HeaderAction(tag: String, name: String, label: String, state: String, action: String,
    icon: ImageVector, selected: Boolean, enabled: Boolean, showLabel: Boolean, fullWidth: Dp,
    faceAlpha: () -> Float = { 1f }, toggle: Boolean = true, click: () -> Unit) {
    val colors = MaterialTheme.colorScheme
    val tint = if (selected) colors.onSecondaryContainer else colors.onSurfaceVariant
    val button: @Composable () -> Unit = {
        val base = Modifier.width(if (showLabel) fullWidth else 48.dp).heightIn(min = 48.dp)
            .clip(CircleShape).testTag(tag).semantics {
                contentDescription = name
                stateDescription = state
                if (toggle) onClick(label = action, action = null)
            }
        val interaction = if (toggle) base.toggleable(value = selected, enabled = enabled, role = Role.Switch) { click() }
            else base.clickable(enabled = enabled, role = Role.Button, onClickLabel = action) { click() }
        Box(interaction,
            contentAlignment = Alignment.Center) {
            Row(Modifier.graphicsLayer { alpha = faceAlpha() }.heightIn(min = if (showLabel) 36.dp else 40.dp)
                .then(if (showLabel) Modifier.fillMaxWidth() else Modifier.width(40.dp))
                .background(if (selected) colors.secondaryContainer else colors.surfaceContainerHigh, CircleShape)
                .clearAndSetSemantics { }, verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(labelGap, Alignment.CenterHorizontally)) {
                Icon(icon, null, Modifier.size(if (showLabel) iconSize else 24.dp),
                    tint = if (enabled) tint else tint.copy(alpha = .38f))
                if (showLabel) Text(label, Modifier.testTag("$tag-label"), style = MaterialTheme.typography.labelLarge,
                    maxLines = 1, softWrap = false, color = tint)
            }
        }
    }
    if (showLabel) button() else TooltipBox(
        positionProvider = TooltipDefaults.rememberTooltipPositionProvider(TooltipAnchorPosition.Above),
        tooltip = { PlainTooltip { Text(action) } }, state = rememberTooltipState(), content = button)
}
