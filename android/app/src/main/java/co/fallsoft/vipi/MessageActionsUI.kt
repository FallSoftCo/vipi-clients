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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.MoreHoriz
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.LayoutCoordinates
import androidx.compose.ui.layout.boundsInWindow
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import java.util.UUID
import kotlin.math.abs
import kotlinx.coroutines.CancellationException

internal class TranscriptActions {
    data class Hit(val id: String, val bounds: Rect, val reply: () -> Unit, val actions: () -> Unit)

    val hits = mutableMapOf<String, Hit>()
    var active by mutableStateOf<String?>(null)
    var travel by mutableFloatStateOf(0f)
}

internal fun Modifier.messageSwipes(
    state: FullMessageGestures,
    id: String,
    reply: () -> Unit,
    actions: () -> Unit,
): Modifier = composed {
    val onReply by rememberUpdatedState(reply)
    val onActions by rememberUpdatedState(actions)
    val targets = state.actions
    DisposableEffect(targets, id) { onDispose { targets.hits.remove(id) } }
    val rtl = LocalLayoutDirection.current == LayoutDirection.Rtl
    val replyLabel = stringResource(R.string.message_reply_action)
    val reactLabel = stringResource(R.string.message_react_action)
    val background = MaterialTheme.colorScheme.primaryContainer
    val ink = MaterialTheme.colorScheme.onPrimaryContainer
    this.onGloballyPositioned {
            targets.hits[id] =
                TranscriptActions.Hit(id, it.boundsInWindow(), { onReply() }, { onActions() })
        }
        .drawWithContent {
            drawContent()
            val travel = if (targets.active == id) targets.travel else 0f
            if (travel != 0f) {
                val r = 12.dp.toPx()
                val direction = if (rtl) -1 else 1
                val x = if (travel * direction > 0) r else size.width - r
                val y = size.height / 2
                drawCircle(background, r, Offset(x, y))
                if (travel > 0) {
                    val d = direction * r * .45f
                    drawLine(ink, Offset(x + d, y), Offset(x - d, y), 2.dp.toPx())
                    drawLine(ink, Offset(x - d, y), Offset(x, y - r * .4f), 2.dp.toPx())
                    drawLine(ink, Offset(x - d, y), Offset(x, y + r * .4f), 2.dp.toPx())
                } else for (i in -1..1) drawCircle(ink, 1.3.dp.toPx(), Offset(x + .4f * r * i, y))
            }
        }
        .semantics {
            customActions =
                listOf(
                    CustomAccessibilityAction(replyLabel) {
                        onReply()
                        true
                    },
                    CustomAccessibilityAction(reactLabel) {
                        onActions()
                        true
                    },
                )
        }
}

/**
 * Observe horizontal intent on the transcript alongside its existing tap/hold recognizer. A text
 * row has no independent pointer interceptor; stationary fingers and vertical scrolling pass
 * through.
 */
internal fun Modifier.transcriptSwipes(targets: TranscriptActions): Modifier = composed {
    val rtl = LocalLayoutDirection.current == LayoutDirection.Rtl
    val haptic = LocalHapticFeedback.current
    var coordinates by remember { mutableStateOf<LayoutCoordinates?>(null) }
    this.onGloballyPositioned { coordinates = it }
        .pointerInput(targets, rtl) {
            awaitEachGesture {
                val down =
                    awaitFirstDown(requireUnconsumed = false, pass = PointerEventPass.Initial)
                val position =
                    coordinates?.takeIf { it.isAttached }?.localToWindow(down.position)
                        ?: return@awaitEachGesture
                val hit =
                    targets.hits.values.firstOrNull { it.bounds.contains(position) }
                        ?: return@awaitEachGesture
                var armed = false
                var horizontal = false
                var sign = false
                try {
                    while (true) {
                        val e = awaitPointerEvent(PointerEventPass.Initial)
                        val p = e.changes.singleOrNull() ?: break
                        val dx = (p.position.x - down.position.x) * if (rtl) -1 else 1
                        val dy = abs(p.position.y - down.position.y)
                        if (
                            !horizontal &&
                                ((dy > viewConfiguration.touchSlop && dy >= abs(dx)) ||
                                    p.uptimeMillis - down.uptimeMillis >=
                                        viewConfiguration.longPressTimeoutMillis)
                        )
                            break
                        if (
                            !horizontal &&
                                abs(dx) >= viewConfiguration.touchSlop * 2 &&
                                abs(dx) > dy * 2
                        )
                            horizontal = true
                        if (horizontal && p.pressed) {
                            targets.active = hit.id
                            targets.travel = dx
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
                                if (targets.hits.containsKey(hit.id)) {
                                    if (sign) hit.reply() else hit.actions()
                                }
                            }
                            break
                        }
                    }
                } finally {
                    targets.active = null
                    targets.travel = 0f
                }
            }
        }
}

@Composable
internal fun QuoteStrip(
    author: String,
    snippet: String,
    jump: (() -> Unit)? = null,
    remove: (() -> Unit)? = null,
) {
    val colors = MaterialTheme.colorScheme
    Row(
        Modifier.padding(horizontal = 8.dp, vertical = 3.dp)
            .background(colors.onSurface.copy(alpha = .07f), RoundedCornerShape(8.dp))
            .then(if (jump == null) Modifier else Modifier.clickable(onClick = jump))
            .padding(start = 10.dp, end = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f, fill = false).padding(vertical = 5.dp, horizontal = 2.dp)) {
            Text(
                author,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Bold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                snippet,
                style = MaterialTheme.typography.bodySmall,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
        }
        if (remove != null)
            IconButton(remove) {
                Icon(Icons.Outlined.Close, stringResource(R.string.message_remove_quote))
            }
    }
}

@Composable
internal fun SnapshotCard(value: LinkSnapshot, remove: (() -> Unit)? = null) {
    val launcher = LocalUriHandler.current
    Row(
        Modifier.padding(8.dp)
            .border(1.dp, MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(10.dp))
            .then(
                if (remove == null)
                    Modifier.clickable { runCatching { launcher.openUri(value.url) } }
                else Modifier
            )
            .padding(10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        val image =
            remember(value.thumbnail) {
                value.thumbnail
                    ?.let { Base64.decode(it, Base64.NO_WRAP) }
                    ?.let { BitmapFactory.decodeByteArray(it, 0, it.size) }
            }
        if (image != null) Image(image.asImageBitmap(), null, Modifier.size(42.dp))
        Column(Modifier.weight(1f, fill = false)) {
            Text(
                value.title,
                style = MaterialTheme.typography.titleSmall,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                value.host,
                style = MaterialTheme.typography.labelMedium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        if (remove != null)
            IconButton(remove) {
                Icon(Icons.Outlined.Close, stringResource(R.string.message_remove_preview))
            }
    }
}

@Composable
internal fun ActionComposer(
    draft: MessageActionDraft,
    text: String,
    auto: Boolean,
    author: (UUID) -> String,
    quoteText: String? = null,
    fetch: suspend (String) -> LinkSnapshot? = SenderLinkPreview::load,
) {
    draft.features.reply?.let {
        QuoteStrip(author(it.sender), quoteText ?: it.excerpt, remove = { draft.quote(null) })
    }
    val url = remember(text) { ChatFeatures.links(text).firstOrNull() }
    var requested by remember(url) { mutableStateOf(false) }
    var failed by remember(url) { mutableStateOf(false) }
    val actual = draft.features.preview
    LaunchedEffect(url, requested, auto) {
        if (actual != null && actual.url != url) draft.preview(null)
        if (url == null || actual?.url == url || (!requested && (!auto || draft.suppressed == url)))
            return@LaunchedEffect
        val result =
            try {
                fetch(url)
            } catch (cancel: CancellationException) {
                throw cancel
            } catch (_: Exception) {
                null
            }
        if (result != null) draft.preview(result) else failed = true
    }
    if (url != null) {
        if (actual?.url == url)
            SnapshotCard(actual) {
                draft.preview(null, url)
                requested = false
            }
        else if (failed)
            Text(
                stringResource(R.string.message_preview_unavailable),
                Modifier.padding(horizontal = 12.dp),
                style = MaterialTheme.typography.bodySmall,
            )
        else
            TextButton({ requested = true }, enabled = !requested) {
                Text(
                    stringResource(
                        if (requested) R.string.message_preview_loading
                        else R.string.message_add_preview
                    )
                )
            }
    }
}

@Composable
internal fun ActionFooter(
    open: Boolean,
    openChange: (Boolean) -> Unit,
    reactions: Map<UUID, String>,
    me: UUID,
    author: (UUID) -> String,
    reply: () -> Unit,
    react: (String?) -> Unit,
    meta: @Composable () -> Unit,
) {
    var picker by remember { mutableStateOf(false) }
    var detail by remember { mutableStateOf(false) }
    var custom by remember { mutableStateOf("") }
    fun pick(emoji: String) {
        openChange(false)
        picker = false
        detail = false
        react(emoji.takeUnless { reactions[me] == emoji })
    }
    FlowRow(horizontalArrangement = Arrangement.End) {
        if (reactions.isNotEmpty()) {
            val label = stringResource(R.string.message_reactions)
            val glyphs = reactions.values.distinct().take(3).joinToString("")
            val count = java.text.NumberFormat.getIntegerInstance().format(reactions.size)
            Box(
                Modifier.sizeIn(minWidth = 48.dp, minHeight = 48.dp).clickable(
                    role = Role.Button,
                    onClickLabel = label,
                ) {
                    detail = true
                },
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    if (reactions.size == 1) glyphs else "$glyphs $count",
                    Modifier.background(
                            MaterialTheme.colorScheme.surface.copy(alpha = .8f),
                            RoundedCornerShape(16.dp),
                        )
                        .border(
                            1.dp,
                            MaterialTheme.colorScheme.outline.copy(alpha = .5f),
                            RoundedCornerShape(16.dp),
                        )
                        .padding(horizontal = 8.dp, vertical = 2.dp),
                    color = MaterialTheme.colorScheme.onSurface,
                    style = MaterialTheme.typography.labelMedium,
                )
            }
        }
        Box {
            Row(
                Modifier.heightIn(min = 48.dp)
                    .clickable { openChange(true) }
                    .padding(horizontal = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                meta()
                Icon(
                    Icons.Outlined.MoreHoriz,
                    stringResource(R.string.message_actions),
                    Modifier.size(18.dp),
                )
            }
            DropdownMenu(open, { openChange(false) }) {
                Row(Modifier.padding(horizontal = 4.dp)) {
                    listOf("❤️", "👍", "😂", "🎉").forEach { emoji ->
                        TextButton(
                            { pick(emoji) },
                            contentPadding = PaddingValues(0.dp),
                            modifier = Modifier.sizeIn(minWidth = 48.dp, minHeight = 48.dp),
                        ) {
                            Text(emoji)
                        }
                    }
                }
                DropdownMenuItem(
                    { Text(stringResource(R.string.message_more_emoji)) },
                    {
                        openChange(false)
                        picker = true
                    },
                )
                DropdownMenuItem(
                    { Text(stringResource(R.string.message_reply_action)) },
                    {
                        openChange(false)
                        reply()
                    },
                )
            }
        }
    }
    if (picker)
        AlertDialog(
            onDismissRequest = { picker = false },
            title = { Text(stringResource(R.string.message_react_action)) },
            text = {
                Column {
                    listOf(listOf("🔥", "😍", "😮", "👏"), listOf("😢", "🙏", "✨", "💯")).forEach {
                        row ->
                        Row {
                            row.forEach { e ->
                                TextButton(
                                    { pick(e) },
                                    Modifier.weight(1f),
                                    contentPadding = PaddingValues(0.dp),
                                ) {
                                    Text(e)
                                }
                            }
                        }
                    }
                    OutlinedTextField(
                        custom,
                        { custom = it.take(64) },
                        singleLine = true,
                        label = { Text(stringResource(R.string.message_any_emoji)) },
                    )
                }
            },
            confirmButton = {
                TextButton({ pick(custom) }, enabled = ChatFeatures.validEmoji(custom)) {
                    Text(stringResource(R.string.message_react_action))
                }
            },
        )
    if (detail)
        AlertDialog(
            onDismissRequest = { detail = false },
            title = { Text(stringResource(R.string.message_reactions)) },
            text = {
                Column(Modifier.heightIn(max = 360.dp).verticalScroll(rememberScrollState())) {
                    reactions.entries.forEach { (id, e) -> Text("$e  " + author(id)) }
                }
            },
            confirmButton = {
                TextButton({
                    detail = false
                    openChange(true)
                }) {
                    Text(stringResource(R.string.message_react_action))
                }
            },
        )
}
