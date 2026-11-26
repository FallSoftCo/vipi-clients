package co.fallsoft.vipi

import android.graphics.BitmapFactory
import android.util.Base64
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.MoreHoriz
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.CancellationException
import java.util.UUID
import kotlin.math.abs

internal fun Modifier.messageSwipes(reply: () -> Unit, actions: () -> Unit): Modifier = composed {
    val onReply by rememberUpdatedState(reply)
    val onActions by rememberUpdatedState(actions)
    val rtl = LocalLayoutDirection.current == LayoutDirection.Rtl
    val haptic = LocalHapticFeedback.current
    val replyLabel = stringResource(R.string.message_reply_action)
    val reactLabel = stringResource(R.string.message_react_action)
    this.semantics { customActions = listOf(CustomAccessibilityAction(replyLabel) { onReply(); true }, CustomAccessibilityAction(reactLabel) { onActions(); true }) }
        .pointerInput(rtl) {
            awaitEachGesture {
                val down = awaitFirstDown(requireUnconsumed = false)
                var armed = false
                var horizontal = false
                var sign = false
                while (true) {
                    val e = awaitPointerEvent(PointerEventPass.Initial)
                    val p = e.changes.singleOrNull() ?: break
                    val dx = (p.position.x - down.position.x) * if (rtl) -1 else 1
                    val dy = abs(p.position.y - down.position.y)
                    if (!horizontal && (dy > viewConfiguration.touchSlop || p.uptimeMillis - down.uptimeMillis >= viewConfiguration.longPressTimeoutMillis)) break
                    if (!horizontal && abs(dx) >= viewConfiguration.touchSlop * 2 && abs(dx) > dy * 2) horizontal = true
                    if (horizontal && p.pressed) {
                        p.consume()
                        if (!armed && abs(dx) >= 56.dp.toPx()) {
                            armed = true
                            sign = dx > 0
                            haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                        }
                    }
                    if (!p.pressed) {
                        if (horizontal) p.consume()
                        if (armed && abs(dx) >= 48.dp.toPx() && sign == (dx > 0)) {
                            if (sign) onReply() else onActions()
                        }
                        break
                    }
                }
            }
        }
}

@Composable internal fun QuoteStrip(author: String, snippet: String, jump: (() -> Unit)? = null, remove: (() -> Unit)? = null) {
    val colors = MaterialTheme.colorScheme
    Row(Modifier.padding(horizontal = 8.dp, vertical = 3.dp)
        .background(colors.onSurface.copy(alpha = .07f), RoundedCornerShape(8.dp))
        .then(if (jump == null) Modifier else Modifier.clickable(onClick = jump)).padding(start = 10.dp, end = 4.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f, fill = false).padding(vertical = 5.dp, horizontal = 2.dp)) {
            Text(author, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(snippet, style = MaterialTheme.typography.bodySmall, maxLines = 2, overflow = TextOverflow.Ellipsis)
        }
        if (remove != null) IconButton(remove) { Icon(Icons.Outlined.Close, stringResource(R.string.message_remove_quote)) }
    }
}

@Composable internal fun SnapshotCard(value: LinkSnapshot, remove: (() -> Unit)? = null) {
    val launcher = LocalUriHandler.current
    Row(Modifier.padding(8.dp).border(1.dp, MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(10.dp))
        .then(if (remove == null) Modifier.clickable { runCatching { launcher.openUri(value.url) } } else Modifier)
        .padding(10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        val image = remember(value.thumbnail) { value.thumbnail?.let { Base64.decode(it, Base64.NO_WRAP) }?.let { BitmapFactory.decodeByteArray(it, 0, it.size) } }
        if (image != null) Image(image.asImageBitmap(), null, Modifier.size(42.dp))
        Column(Modifier.weight(1f, fill = false)) {
            Text(value.title, style = MaterialTheme.typography.titleSmall, maxLines = 2, overflow = TextOverflow.Ellipsis)
            Text(value.host, style = MaterialTheme.typography.labelMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        if (remove != null) IconButton(remove) { Icon(Icons.Outlined.Close, stringResource(R.string.message_remove_preview)) }
    }
}

@Composable internal fun ActionComposer(draft: MessageActionDraft, text: String, auto: Boolean, author: (UUID) -> String) {
    draft.features.reply?.let { QuoteStrip(author(it.sender), it.excerpt, remove = { draft.quote(null) }) }
    val url = remember(text) { ChatFeatures.links(text).firstOrNull() }
    var requested by remember(url) { mutableStateOf(false) }
    var failed by remember(url) { mutableStateOf(false) }
    val actual = draft.features.preview
    LaunchedEffect(url, requested, auto) {
        if (actual != null && actual.url != url) draft.preview(null)
        if (url == null || actual?.url == url || (!requested && (!auto || draft.suppressed == url))) return@LaunchedEffect
        val result = try { SenderLinkPreview.load(url) } catch (cancel: CancellationException) { throw cancel } catch (_: Exception) { null }
        if (result != null) draft.preview(result) else failed = true
    }
    if (url != null) {
        if (actual?.url == url) SnapshotCard(actual) { draft.preview(null, url); requested = false }
        else if (failed) Text(stringResource(R.string.message_preview_unavailable), Modifier.padding(horizontal = 12.dp), style = MaterialTheme.typography.bodySmall)
        else TextButton({ requested = true }, enabled = !requested) {
            Text(stringResource(if (requested) R.string.message_preview_loading else R.string.message_add_preview))
        }
    }
}

@Composable internal fun ActionFooter(open: Boolean, openChange: (Boolean) -> Unit, reactions: Map<UUID,String>, me: UUID,
    author: (UUID) -> String, reply: () -> Unit, react: (String?) -> Unit, meta: @Composable () -> Unit) {
    var picker by remember { mutableStateOf(false) }
    var detail by remember { mutableStateOf(false) }
    var custom by remember { mutableStateOf("") }
    fun pick(emoji: String) { openChange(false); picker = false; detail = false; react(emoji.takeUnless { reactions[me] == emoji }) }
    Column {
        Box {
            Row(Modifier.heightIn(min = 48.dp).clickable { openChange(true) }.padding(horizontal = 6.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                meta()
                Icon(Icons.Outlined.MoreHoriz, stringResource(R.string.message_actions), Modifier.size(18.dp))
            }
            DropdownMenu(open, { openChange(false) }) {
                Row(Modifier.padding(horizontal = 4.dp)) {
                    listOf("❤️", "👍", "😂", "🎉").forEach { emoji ->
                        TextButton({ pick(emoji) }, contentPadding = PaddingValues(0.dp), modifier = Modifier.sizeIn(minWidth = 48.dp, minHeight = 48.dp)) { Text(emoji) }
                    }
                }
                DropdownMenuItem({ Text(stringResource(R.string.message_more_emoji)) }, { openChange(false); picker = true })
                DropdownMenuItem({ Text(stringResource(R.string.message_reply_action)) }, { openChange(false); reply() })
            }
        }
        if (reactions.isNotEmpty()) TextButton({ detail = true }, contentPadding = PaddingValues(horizontal = 8.dp)) {
            Text(reactions.values.groupingBy { it }.eachCount().entries.joinToString("  ") { (emoji,n) -> if (n == 1) emoji else "$emoji $n" })
        }
    }
    if (picker) AlertDialog(onDismissRequest = { picker = false }, title = { Text(stringResource(R.string.message_react_action)) }, text = {
        Column {
            listOf(listOf("🔥","😍","😮","👏"),listOf("😢","🙏","✨","💯")).forEach { row -> Row { row.forEach { e ->
                TextButton({ pick(e) }, Modifier.weight(1f), contentPadding = PaddingValues(0.dp)) { Text(e) }
            } } }
            OutlinedTextField(custom, { custom = it.take(64) }, singleLine = true, label = { Text(stringResource(R.string.message_any_emoji)) })
        }
    }, confirmButton = { TextButton({ pick(custom) }, enabled = ChatFeatures.validEmoji(custom)) { Text(stringResource(R.string.message_react_action)) } })
    if (detail) AlertDialog(onDismissRequest = { detail = false }, title = { Text(stringResource(R.string.message_reactions)) },
        text = { Column { reactions.entries.forEach { (id,e) -> Text("$e  " + author(id)) } } },
        confirmButton = { TextButton({ detail = false; openChange(true) }) { Text(stringResource(R.string.message_react_action)) } })
}
