package co.fallsoft.vipi

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.dropShadow
import androidx.compose.ui.graphics.shadow.Shadow
import androidx.compose.ui.unit.DpOffset
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.text.DateFormat
import java.util.Date
import java.util.Locale

/** The decorative canvas has no hit targets; the complete scroll/gesture viewport remains intact. */
@Composable internal fun ChatCanvas(modifier: Modifier = Modifier) {
    val ink = MaterialTheme.colorScheme.onBackground.copy(alpha = .045f)
    Canvas(modifier) {
        val step = 32.dp.toPx()
        var y = step / 2
        var row = 0
        while (y < size.height) {
            var x = if (row % 2 == 0) step / 2 else step
            while (x < size.width) {
                drawCircle(ink, .8.dp.toPx(), Offset(x, y))
                x += step
            }
            row++; y += step
        }
    }
}

@Composable internal fun ChatBubbleFrame(outgoing: Boolean, modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    val palette = vipiPalette()
    val context = if (outgoing) palette.onOutgoing() else palette
    val shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp,
        bottomStart = if (outgoing) 20.dp else 5.dp, bottomEnd = if (outgoing) 5.dp else 20.dp)
    val light = palette.canvas.luminance() > .5f
    val frame = modifier.widthIn(max = 520.dp).then(if (light) Modifier.dropShadow(shape,
        Shadow(radius = 2.dp, spread = 0.dp, color = palette.bubbleShadow,
            offset = DpOffset(0.dp, 1.dp))) else Modifier)
    Surface(modifier = frame, shape = shape,
        color = if (outgoing) palette.outgoing else palette.incoming,
        contentColor = context.ink,
        shadowElevation = if (light) 0.dp else 1.dp,
        border = BorderStroke(if (light) 1.dp else .5.dp, if (outgoing) palette.outgoingOutline else palette.incomingOutline)) {
        CompositionLocalProvider(LocalVipiPalette provides context) {
            MaterialTheme(colorScheme = MaterialTheme.colorScheme.copy(
                onSurface = context.ink, onSurfaceVariant = context.secondary,
                primary = context.action, onPrimary = context.onAction, error = context.failed)) { content() }
        }
    }
}

@Composable internal fun ChatModeToggle(mode: ImmersionMode, onToggle: () -> Unit) {
    val full = mode == ImmersionMode.FULL_MESSAGES
    val title = stringResource(R.string.immersion_mode_title)
    val state = stringResource(if (full) R.string.immersion_mode_full else R.string.immersion_mode_words_short)
    val next = stringResource(if (full) R.string.immersion_mode_words_short else R.string.immersion_mode_full)
    val action = stringResource(R.string.chat_switch_mode, next)
    FilledTonalButton(onClick = onToggle, contentPadding = PaddingValues(horizontal = 12.dp),
        modifier = Modifier.heightIn(min = 48.dp).testTag("conversation-immersion").semantics {
            role = Role.Switch; toggleableState = if (full) androidx.compose.ui.state.ToggleableState.On else androidx.compose.ui.state.ToggleableState.Off
            contentDescription = title; stateDescription = state; onClick(label = action, action = null)
        }) {
        val depth = animateFloatAsState(if (full) 1f else 0f, tween(200), label = "Immersion control")
        // Both labels set the intrinsic width, including in translated layouts.
        // The switch owns the accessible name and current value.
        Box(contentAlignment = Alignment.Center, modifier = Modifier.clearAndSetSemantics { }) {
            for (deepLabel in listOf(false, true)) {
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.graphicsLayer {
                    val progress = depth.value
                    alpha = if (deepLabel == (progress >= .5f)) .78f + .22f * kotlin.math.abs(2f * progress - 1f) else 0f
                }) {
                    Icon(if (deepLabel) Icons.Outlined.Anchor else Icons.Outlined.Waves, null, Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text(stringResource(if (deepLabel) R.string.immersion_mode_full else R.string.immersion_mode_words_short),
                        maxLines = 2, fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}

/** A check is never a read assertion. Only the explicit remote 'read' state gets read tint. */
@Composable internal fun ChatMessageMetadata(item: ChatItem, locale: Locale) {
    val status = deliveryLabel(item.state, item.outgoing)
    val time = DateFormat.getTimeInstance(DateFormat.SHORT, locale).format(Date(item.createdAt))
    val error = item.state in setOf("failed", "expired", "cancelled")
    val palette = vipiPalette()
    val ink = if (error) palette.failed else palette.secondary
    Row(Modifier.testTag("message-meta-${item.id}").clearAndSetSemantics { },
        horizontalArrangement = Arrangement.End, verticalAlignment = Alignment.CenterVertically) {
        // Nonroutine failures/imports/unknowns keep a readable explanation, never an unexplained glyph.
        if (error || item.state == "imported" || item.state !in setOf("queued", "pending", "accepted", "delivered", "read")) {
            Text(status, fontSize = 12.sp, lineHeight = 16.sp, color = ink)
            Spacer(Modifier.width(8.dp))
        }
        Text(time, fontSize = 12.sp, lineHeight = 16.sp, color = ink)
        if (item.outgoing) {
            Spacer(Modifier.width(4.dp))
            ChatDeliveryIcon(item.state, null)
        }
    }
}

@Composable internal fun ChatDeliveryIcon(state: String, description: String?) {
    val palette = vipiPalette()
    val ink = if (state in setOf("failed", "expired", "cancelled")) palette.failed else palette.secondary
    val icon = when (state) {
        "accepted" -> Icons.Outlined.Done
        "delivered", "read" -> Icons.Outlined.DoneAll
        "queued", "pending" -> Icons.Outlined.Schedule
        "failed", "expired", "cancelled" -> Icons.Outlined.ErrorOutline
        else -> Icons.Outlined.HelpOutline
    }
    val tint = if (state != "read") ink else palette.read
    Icon(icon, description, modifier = Modifier.size(16.dp), tint = tint)
}

/** Initials are derived from actual contact text, never fetched/invented photos. */
internal fun contactInitials(name: String): String {
    val words = name.trim().split(Regex("\\s+")).filter { it.isNotBlank() }
    fun first(value: String): String {
        val iterator = android.icu.text.BreakIterator.getCharacterInstance(Locale.ROOT)
        iterator.setText(value); iterator.first()
        val end = iterator.next()
        return if (end == android.icu.text.BreakIterator.DONE) "" else value.substring(0, end)
    }
    return when (words.size) { 0 -> ""; 1 -> first(words.first()); else -> first(words.first()) + first(words.last()) }.uppercase(Locale.ROOT)
}

@Composable internal fun ContactAvatar(name: String, peer: java.util.UUID, diameter: androidx.compose.ui.unit.Dp = 34.dp) {
    // This is a decorative identity icon; the adjacent real name scales with
    // text settings. Keep its glyph inside the fixed circle at every font size.
    val glyphSize = with(LocalDensity.current) { (diameter.toPx() * .42f).toSp() }
    val palette = vipiPalette()
    val slot = ((peer.mostSignificantBits xor peer.leastSignificantBits) and 3).toInt()
    Surface(color = palette.avatars[slot], shape = androidx.compose.foundation.shape.CircleShape,
        modifier = Modifier.size(diameter).clearAndSetSemantics { }) {
        Box(contentAlignment = Alignment.Center) {
            Text(contactInitials(name), fontSize = glyphSize, lineHeight = glyphSize * 1.15f, fontWeight = FontWeight.SemiBold,
                color = palette.avatarInk, maxLines = 1)
        }
    }
}
