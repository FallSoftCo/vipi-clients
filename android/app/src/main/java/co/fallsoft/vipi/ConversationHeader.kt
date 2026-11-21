package co.fallsoft.vipi

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.VolumeOff
import androidx.compose.material.icons.automirrored.outlined.VolumeUp
import androidx.compose.material.icons.outlined.Anchor
import androidx.compose.material.icons.outlined.Waves
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
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
    back: @Composable () -> Unit, overflow: @Composable () -> Unit) {
    val autoplayLabel = stringResource(R.string.autoplay_label)
    val shallow = stringResource(R.string.immersion_mode_words_short)
    val deep = stringResource(R.string.immersion_mode_full)
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
    val full = mode == ImmersionMode.FULL_MESSAGES
    BoxWithConstraints(modifier) {
        val centerWidth = maxWidth - 48.dp * 2 // Back and overflow each own one 48dp target.
        val identity = avatarSize + nameGap + headerGap
        val modeGap = if (onMode == null) 0.dp else headerGap
        val labels = centerWidth >= identity + nameWidth + chipWidth(autoplayWidth) + modeGap +
            (if (onMode == null) 0.dp else chipWidth(modeWidth))
        val minimumName = minOf(nameWidth, with(density) { nameStyle.fontSize.toDp() } * 2)
        val secondRow = centerWidth < identity + minimumName + 48.dp + modeGap + (if (onMode == null) 0.dp else 48.dp)
        val actions: @Composable RowScope.() -> Unit = {
            HeaderAction("conversation-autoplay", autoplayLabel, autoplayLabel,
                stringResource(if (autoplay) R.string.settings_on else R.string.settings_off),
                stringResource(if (autoplay) R.string.autoplay_turn_off else R.string.autoplay_turn_on),
                if (autoplay) Icons.AutoMirrored.Outlined.VolumeUp else Icons.AutoMirrored.Outlined.VolumeOff,
                autoplay, audioAvailable, labels, chipWidth(autoplayWidth), click = onAutoplay)
            if (onMode != null) {
                // Switch the one visible face at the midpoint, keeping the glyph and text legible.
                // Compose duration scale also covers disabled system animations.
                val depth = animateFloatAsState(if (full) 1f else 0f, tween(200), label = "Immersion")
                val deepFace = depth.value >= .5f
                val current = if (full) deep else shallow
                HeaderAction("conversation-immersion", stringResource(R.string.immersion_mode_title), if (deepFace) deep else shallow, current,
                    stringResource(R.string.chat_switch_mode, if (full) shallow else deep),
                    if (deepFace) Icons.Outlined.Anchor else Icons.Outlined.Waves, full, true, labels, chipWidth(modeWidth),
                    faceAlpha = { .8f + .2f * kotlin.math.abs(2f * depth.value - 1f) }, click = onMode)
            }
        }
        Column {
            Row(Modifier.fillMaxWidth().heightIn(min = minHeight), verticalAlignment = Alignment.CenterVertically) {
                back()
                Row(Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(nameGap),
                    verticalAlignment = Alignment.CenterVertically) {
                    ContactAvatar(name, peer, avatarSize)
                    Text(name, Modifier.testTag("conversation-contact"), style = nameStyle,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
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
    icon: ImageVector, selected: Boolean, enabled: Boolean, showLabel: Boolean, fullWidth: Dp, faceAlpha: () -> Float = { 1f }, click: () -> Unit) {
    val colors = MaterialTheme.colorScheme
    val tint = if (selected) colors.onSecondaryContainer else colors.onSurfaceVariant
    val button: @Composable () -> Unit = {
        Box(Modifier.width(if (showLabel) fullWidth else 48.dp).heightIn(min = 48.dp)
            .clip(CircleShape).testTag(tag).semantics {
                contentDescription = name
                stateDescription = state
                onClick(label = action, action = null)
            }.toggleable(value = selected, enabled = enabled, role = Role.Switch) { click() },
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
