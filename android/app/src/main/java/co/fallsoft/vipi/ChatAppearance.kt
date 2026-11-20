package co.fallsoft.vipi

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
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

@Composable internal fun ChatBubbleFrame(outgoing: Boolean, content: @Composable () -> Unit) {
    val shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp,
        bottomStart = if (outgoing) 20.dp else 5.dp, bottomEnd = if (outgoing) 5.dp else 20.dp)
    Surface(modifier = Modifier.widthIn(max = 520.dp), shape = shape,
        color = if (outgoing) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surface,
        contentColor = MaterialTheme.colorScheme.onSurface,
        shadowElevation = 1.dp,
        border = BorderStroke(.5.dp, MaterialTheme.colorScheme.onSurface.copy(alpha = .07f))) { content() }
}

@Composable internal fun ChatModeToggle(mode: ImmersionMode, onToggle: () -> Unit) {
    val full = mode == ImmersionMode.FULL_MESSAGES
    val title = stringResource(R.string.immersion_mode_title)
    val state = stringResource(if (full) R.string.immersion_mode_full else R.string.immersion_mode_words)
    val visible = stringResource(if (full) R.string.immersion_mode_full else R.string.immersion_mode_words_short)
    val next = stringResource(if (full) R.string.immersion_mode_words else R.string.immersion_mode_full)
    val action = stringResource(R.string.chat_switch_mode, next)
    FilledTonalButton(onClick = onToggle, contentPadding = PaddingValues(horizontal = 12.dp),
        modifier = Modifier.heightIn(min = 48.dp).testTag("conversation-immersion").semantics {
            role = Role.Switch; toggleableState = if (full) androidx.compose.ui.state.ToggleableState.On else androidx.compose.ui.state.ToggleableState.Off
            contentDescription = title; stateDescription = state; onClick(label = action, action = null)
        }) {
        Icon(Icons.Outlined.Translate, null, modifier = Modifier.size(18.dp))
        Spacer(Modifier.width(6.dp))
        Text(visible, maxLines = 2, fontWeight = FontWeight.SemiBold)
    }
}

/** A check is never a read assertion. Only the explicit remote 'read' state gets read tint. */
@Composable internal fun ChatMessageMetadata(item: ChatItem, locale: Locale) {
    val status = deliveryLabel(item.state, item.outgoing)
    val time = DateFormat.getTimeInstance(DateFormat.SHORT, locale).format(Date(item.createdAt))
    val error = item.state in setOf("failed", "expired", "cancelled")
    val ink = if (error) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant
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
    val ink = if (state in setOf("failed", "expired", "cancelled")) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant
    val icon = when (state) {
        "accepted" -> Icons.Outlined.Done
        "delivered", "read" -> Icons.Outlined.DoneAll
        "queued", "pending" -> Icons.Outlined.Schedule
        "failed", "expired", "cancelled" -> Icons.Outlined.ErrorOutline
        else -> Icons.Outlined.HelpOutline
    }
    val tint = if (state != "read") ink
        else if (MaterialTheme.colorScheme.background.luminance() < .5f) Color(0xFF79C8F5) else Color(0xFF236FA1)
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
    val dark = MaterialTheme.colorScheme.background.luminance() < .5f
    val slot = ((peer.mostSignificantBits xor peer.leastSignificantBits) and 3).toInt()
    val palette = if (dark) longArrayOf(0xFF533F2F, 0xFF263E53, 0xFF423754, 0xFF2C493A)
        else longArrayOf(0xFFF2D8BE, 0xFFCCDEEF, 0xFFDDD6EF, 0xFFD0E6D9)
    Surface(color = Color(palette[slot]), shape = androidx.compose.foundation.shape.CircleShape,
        modifier = Modifier.size(diameter).clearAndSetSemantics { }) {
        Box(contentAlignment = Alignment.Center) {
            Text(contactInitials(name), fontSize = glyphSize, lineHeight = glyphSize * 1.15f, fontWeight = FontWeight.SemiBold,
                color = if (dark) Color(0xFFF0F0E7) else Color(0xFF18251D), maxLines = 1)
        }
    }
}
