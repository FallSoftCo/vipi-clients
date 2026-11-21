package co.fallsoft.vipi

import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.stopScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.ArrowUpward
import androidx.compose.material.icons.outlined.ArrowDownward
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material.icons.outlined.MoreVert
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.scrollToIndex
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import android.content.Intent
import kotlinx.coroutines.launch
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.isActive
import java.text.DateFormat
import java.util.Date
import java.util.UUID

/** Match Compose1.9.3's Android paragraph resolver: enlarged text preserves
 * line-height/font-size proportions instead of independently scaling larger sp.
 * Round outward in physical pixels before adding unchanged Material padding. */
internal fun androidx.compose.ui.unit.Density.resolvedComposeLineHeight(style: androidx.compose.ui.text.TextStyle): androidx.compose.ui.unit.Dp {
    require(style.fontSize.type == androidx.compose.ui.unit.TextUnitType.Sp &&
        style.lineHeight.type == androidx.compose.ui.unit.TextUnitType.Sp && style.fontSize.value > 0)
    val fontPx = style.fontSize.toPx()
    val linePx = if (fontScale > 1.05f) style.lineHeight.value / fontPx.toSp().value * fontPx
        else style.lineHeight.toPx()
    return kotlin.math.ceil(linePx).toDp()
}

internal val EmbeddedMessageVerticalPadding = 12.dp

/** Keep opposing messages together on wide screens without narrowing the
 * scrolling/gesture surface or changing the available width on phones. */
@Composable internal fun ConversationTranscriptItem(content: @Composable () -> Unit) {
    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.TopCenter) {
        Box(Modifier.widthIn(max = 644.dp).fillMaxWidth()) { content() }
    }
}

@Composable internal fun ProfileSetupScreen(model: VipiModel) {
    val chat = model.chat ?: return
    var name by rememberSaveable { mutableStateOf("") }
    var username by rememberSaveable { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    Text(stringResource(R.string.ui_73bee38b06e8), fontSize = 34.sp, lineHeight = 40.sp)
    Text(stringResource(R.string.ui_956d8b926f8d), color = MaterialTheme.colorScheme.onSurfaceVariant)
    OutlinedTextField(name, { name = it }, colors = vipiTextFieldColors(), label = { Text(stringResource(R.string.ui_2c6b2e253c01)) }, singleLine = true,
        modifier = Modifier.fillMaxWidth().testTag("profile-name"), shape = RoundedCornerShape(16.dp))
    OutlinedTextField(username, { username = it }, colors = vipiTextFieldColors(), label = { Text(stringResource(R.string.ui_e3b89e9d33f8)) }, prefix = { Text("@") }, singleLine = true,
        keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None, autoCorrectEnabled = false),
        modifier = Modifier.fillMaxWidth().testTag("profile-username"), shape = RoundedCornerShape(16.dp))
    Text(stringResource(R.string.ui_33875a9b79e5), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    chat.notice?.let { Text(it, fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    Button(onClick = { scope.launch {
        chat.createProfile(username, name)
        if (chat.ready) {
            model.navigate(Screen.HOME)
        }
    } }, enabled = !chat.busy && name.isNotBlank() && name.length <= 80 && username.matches(Regex("[a-zA-Z][a-zA-Z0-9_]{2,23}")),
        shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth().testTag("profile-submit"), contentPadding = PaddingValues(20.dp)) {
        if (chat.busy) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
        else Text(stringResource(R.string.continue_action), fontWeight = FontWeight.SemiBold)
    }
    TextButton(onClick = { model.navigate(Screen.DELETE_ACCOUNT) }, enabled = !chat.busy) { Text(stringResource(R.string.ui_a2e20a335700), color = MaterialTheme.colorScheme.error) }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable internal fun FriendConversationScreen(chat: ChatSession, peer: UUID, source: String = "en", target: String = "es",
    animateBackground: Boolean = true,
    waterClock: WaterClock = rememberWaterClock(),
    onLanguages: (() -> Unit)? = null,
    onImmersionMode: ((ImmersionMode) -> Unit)? = null,
    notificationEducation: ReplyNotificationEducation? = null,
    onNotificationPermission: () -> Unit = {},
    back: () -> Unit) {
    var messages by remember(peer) { mutableStateOf<List<ChatItem>>(emptyList()) }
    var text by remember(peer) { mutableStateOf("") }
    var error by remember(peer) { mutableStateOf<String?>(null) }
    var rejectedDraftEdit by remember(peer) { mutableStateOf(false) }
    val messageTooLong = text.toByteArray(Charsets.UTF_8).size > 32768
    var earlierAvailable by remember(peer) { mutableStateOf(false) }
    var loaded by remember(peer) { mutableStateOf(false) }
    var userRefreshing by remember(peer) { mutableStateOf(false) }
    var options by remember(peer) { mutableStateOf(false) }
    var confirmBlock by remember(peer) { mutableStateOf(false) }
    var blockBusy by remember(peer) { mutableStateOf(false) }
    var chooseReport by remember(peer) { mutableStateOf(false) }
    var chooseCopy by remember(peer) { mutableStateOf(false) }
    var copyOriginImeVisible by remember(peer) { mutableStateOf(false) }
    var copyOriginComposerFocused by remember(peer) { mutableStateOf(false) }
    var reportedMessage by remember(peer) { mutableStateOf<ChatItem?>(null) }
    var reportReason by remember(peer) { mutableStateOf("") }
    var reporting by remember(peer) { mutableStateOf(false) }
    var showSecurityNumber by remember(peer) { mutableStateOf(false) }
    var showVoiceHelp by remember(peer) { mutableStateOf(false) }
    var followingLatest by rememberSaveable(peer) { mutableStateOf(true) }
    var positioningLatest by remember(peer) { mutableStateOf(false) }
    var newMessagesBelow by remember(peer) { mutableIntStateOf(0) }
    var jumpRevision by remember(peer) { mutableIntStateOf(0) }
    LaunchedEffect(chat, peer) { chat.visitedConversation = true }
    val blocked = peer in chat.blockedPeers
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val focusManager = LocalFocusManager.current
    val translation = chat.translations
    val gestures = remember(chat, peer, source, target) { FullMessageGestures().also { it.mode = translation?.mode ?: ImmersionMode.NEW_WORD } }
    LaunchedEffect(chat, source, target) { chat.configureTranslations(source, target) }
    val speech = remember(chat, peer, source, target) { SpeechPlayback(context, target, scope) }
    val warmups = remember(source, target) { mapOf(source to "1", target to "1") }
    val audio = remember(translation, speech) { translation?.let { ConversationAutoplay(it, speech, scope) { showVoiceHelp = true } } }
    DisposableEffect(audio, chat, peer) {
        val source = java.lang.ref.WeakReference(chat)
        if (audio != null) chat.observeNewMessages(audio, peer) { id, _ -> audio.offerStored(id) { source.get()?.messageOriginal(id) } }
        onDispose { if (audio != null) { chat.removeNewMessageObserver(audio); audio.close() } }
    }
    val lifecycle = LocalLifecycleOwner.current
    var foreground by remember(lifecycle) { mutableStateOf(lifecycle.lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) }
    val peerTyping = foreground && chat.isPeerTyping(peer)
    var composing by remember { mutableStateOf(false) }
    var topBarHeightPx by remember { mutableIntStateOf(0) }
    val composerStatusScroll = rememberScrollState()
    LaunchedEffect(peer, error, chat.notice, speech.error, messageTooLong, rejectedDraftEdit) { composerStatusScroll.scrollTo(0) }
    LaunchedEffect(speech) { speech.prepare(warmups) }
    LaunchedEffect(speech.state) { if (speech.state == SpeechState.READY) showVoiceHelp = false }
    DisposableEffect(lifecycle, speech, audio) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) { foreground = false; chat.composerActivity(peer, false); chat.visibleMessages(peer, emptyList(), emptyList()); gestures.held = false; audio?.background(); speech.stop() }
            if (event == Lifecycle.Event.ON_RESUME) {
                foreground = true
                translation?.preparePair(); speech.prepare(warmups)
            }
        }
        lifecycle.lifecycle.addObserver(observer)
        onDispose { lifecycle.lifecycle.removeObserver(observer); chat.composerActivity(peer, false); chat.visibleMessages(peer, emptyList(), emptyList()) }
    }
    DisposableEffect(speech) { onDispose { speech.close() } }
    DisposableEffect(notificationEducation, peer) { onDispose { notificationEducation?.dismiss() } }
    val list = rememberLazyListState()
    val messageTextInset = with(LocalDensity.current) { EmbeddedMessageVerticalPadding.roundToPx() }
    suspend fun revealNewestMessage() {
        val newest = messages.lastOrNull() ?: return
        if (!followingLatest || list.isScrollInProgress) return
        fun showLeadingEdgeIfOversized(): Boolean {
            val layout = list.layoutInfo
            val row = layout.visibleItemsInfo.firstOrNull { it.key == newest.id } ?: return false
            // The footer spacer/gap and both list paddings also consume the
            // physical viewport. A row can fit its raw height while its first
            // text line is pushed under the toolbar by bottom-follow scrolling.
            val trailingEnd = layout.visibleItemsInfo.filter { it.index > row.index }
                .maxOfOrNull { it.offset + it.size } ?: (row.offset + row.size)
            val trailingExtent = (trailingEnd - row.offset - row.size).coerceAtLeast(0)
            val usableHeight = (layout.viewportSize.height - layout.beforeContentPadding -
                layout.afterContentPadding - trailingExtent).coerceAtLeast(0)
            if (layout.viewportSize.height <= 0 || row.size <= usableHeight) return false
            // A long row cannot fit together with its metadata/audio. Show its
            // leading text instead of its decorative top padding or trailing controls
            // visible. This non-scrolling remeasure preserves follow intent;
            // an actual reader drag still opts out through the observer below.
            list.requestScrollToItem(row.index, layout.beforeContentPadding + messageTextInset)
            return true
        }
        positioningLatest = true
        try {
        // Reuse a measured oversized row directly on IME/paragraph resize;
        // do not bounce it to the bottom on every layout observation.
        if (showLeadingEdgeIfOversized()) { withFrameNanos { }; return }
        list.scrollToItem((list.layoutInfo.totalItemsCount - 1).coerceAtLeast(0))
        withFrameNanos { }
        if (followingLatest && !list.isScrollInProgress && messages.lastOrNull()?.id == newest.id) {
            showLeadingEdgeIfOversized()
        }
        } finally { positioningLatest = false }
    }
    LaunchedEffect(list, peer) {
        snapshotFlow {
            val layout = list.layoutInfo
            val last = layout.visibleItemsInfo.lastOrNull()
            val nearBottom = last != null && layout.viewportSize.height > 0 && !list.canScrollForward
            // scrollToItem updates requested state before the next measure.
            // An old bottom layout must not undo an explicit jump to history.
            Triple(list.isScrollInProgress && !positioningLatest, nearBottom,
                layout.visibleItemsInfo.firstOrNull()?.index == list.firstVisibleItemIndex)
        }.collect { (scrolling, nearBottom, measuredPosition) ->
            // Content insertion alone must not revoke the reader's choice to
            // follow latest. Only scrolling can move that choice away.
            if (measuredPosition && (scrolling || nearBottom)) followingLatest = nearBottom
        }
    }
    LaunchedEffect(list, peer) {
        data class Row(val key: Any, val index: Int, val offset: Int, val size: Int)
        data class Viewport(val height: Int, val start: Int, val end: Int, val rows: List<Row>,
            val firstIndex: Int, val firstScrollOffset: Int)
        var previous: Viewport? = null
        fun measuredViewport(): Viewport {
            val layout = list.layoutInfo
            return Viewport(layout.viewportSize.height, layout.viewportStartOffset, layout.viewportEndOffset,
                layout.visibleItemsInfo.map { Row(it.key, it.index, it.offset, it.size) },
                list.firstVisibleItemIndex, list.firstVisibleItemScrollOffset)
        }
        // Finish an admitted correction before observing the next conflated
        // layout; another prepared row must not cancel and lose its anchor.
        snapshotFlow { measuredViewport() }.collect { current ->
            val before = previous
            previous = current
            // New keys alone represent scrolling/paging, not a row reflow.
            val sharedSizeChanged = before != null && current.rows.any { row ->
                before.rows.firstOrNull { it.key == row.key }?.let { it.size != row.size } == true
            }
            val resized = before != null && before.height > 0 && before.rows.isNotEmpty() &&
                (before.height != current.height || sharedSizeChanged)
            if (resized && followingLatest && !list.isScrollInProgress && messages.isNotEmpty()) {
                withFrameNanos { }
                if (followingLatest && !list.isScrollInProgress && messages.isNotEmpty()) revealNewestMessage()
            } else if (sharedSizeChanged && before != null && before.height == current.height &&
                !followingLatest && !list.isScrollInProgress) {
                // Keeping a clipped first row's top fixed still moves the
                // readable row below it when that clipped row gains word slots.
                // Preserve the prior first fully visible MESSAGE row instead.
                val anchor = before.rows.firstOrNull { it.key is UUID && it.offset >= before.start &&
                    it.offset + it.size <= before.end }
                val moved = anchor?.let { saved -> current.rows.firstOrNull { it.key == saved.key } }
                if (anchor != null && moved != null && moved.offset != anchor.offset) {
                    withFrameNanos { }
                    // An intervening reader gesture or jump always wins.
                    if (!followingLatest && !list.isScrollInProgress && list.firstVisibleItemIndex == current.firstIndex &&
                        list.firstVisibleItemScrollOffset == current.firstScrollOffset) {
                        try { list.scrollToItem(moved.index, -anchor.offset) }
                        catch (cancelled: CancellationException) {
                            // User input may interrupt this default-priority
                            // scroll without ending future resize observation.
                            if (!currentCoroutineContext().isActive) throw cancelled
                        }
                        // Do not interpret our own correction as fresh drift.
                        previous = measuredViewport()
                    }
                }
            }
        }
    }
    fun refresh() {
        try {
            val current = chat.messages(peer); val ids = current.map { it.id }.toSet()
            if (loaded && !followingLatest) newMessagesBelow += current.count { incoming -> !incoming.outgoing && messages.none { it.id == incoming.id } }
            messages = (current + messages.filter { it.id !in ids }).sortedBy { it.cursor }
            if (!loaded) { text = chat.compose(peer); earlierAvailable = current.size == 50; loaded = true }
            if (followingLatest) chat.markRead(peer)
        } catch (_: Exception) { error = context.getString(R.string.chat_saved_open_failed) }
    }
    fun earlier() {
        try {
            val existing = messages.map { it.id }.toSet()
            val anchor = list.layoutInfo.visibleItemsInfo.firstOrNull { it.key in existing }
            val page = chat.messages(peer, messages.firstOrNull()?.cursor); val ids = messages.map { it.id }.toSet()
            messages = page.reversed().filter { it.id !in ids } + messages; earlierAvailable = page.size == 50
            if (anchor != null) {
                followingLatest = false
                val index = messages.indexOfFirst { it.id == anchor.key }
                if (index >= 0) list.requestScrollToItem(index + 1, -anchor.offset)
            }
        } catch (_: Exception) { error = context.getString(R.string.chat_earlier_open_failed) }
    }
    LaunchedEffect(peer) {
        refresh(); blockBusy = true
        try { chat.refreshBlock(peer) }
        catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { error = context.getString(R.string.chat_block_check_failed) }
        finally { blockBusy = false }
        chat.synchronize()
    }
    LaunchedEffect(chat.revision) { refresh() }
    LaunchedEffect(messages.lastOrNull()?.id, jumpRevision, peerTyping) {
        // Let appended rows and IME constraints measure before choosing the tail.
        withFrameNanos { }
        if (followingLatest && messages.isNotEmpty()) revealNewestMessage()
    }
    LaunchedEffect(followingLatest) {
        if (followingLatest) { newMessagesBelow = 0; chat.markRead(peer) }
    }
    LaunchedEffect(chat, peer, foreground, options, chooseCopy, chooseReport, showSecurityNumber, confirmBlock, reportedMessage) {
        try {
            snapshotFlow {
                val layout = list.layoutInfo
                val clear = foreground && !options && !chooseCopy && !chooseReport && !showSecurityNumber && !confirmBlock && reportedMessage == null
                if (!clear) emptyList<ChatItem>() else {
                    val visibleKeys = layout.visibleItemsInfo.filter { row ->
                        val overlap = minOf(row.offset + row.size, layout.viewportEndOffset) - maxOf(row.offset, layout.viewportStartOffset)
                        overlap >= minOf(row.size, messageTextInset * 2 + 24)
                    }.map { it.key }.toSet()
                    messages.filter { it.id in visibleKeys && it.state != "imported" }
                }
            }.collect { visible ->
                chat.visibleMessages(peer, visible.filter { !it.outgoing }.take(64).map { it.id },
                    visible.filter { it.outgoing && it.state in setOf("accepted", "delivered", "read") }.take(64).map { it.id })
            }
        } finally { chat.visibleMessages(peer, emptyList(), emptyList()) }
    }
    BoxWithConstraints(Modifier.fillMaxSize()) {
    val viewDensity = LocalDensity.current
    val keyboardInsets = WindowInsets.ime
    val bottomInsets = with(viewDensity) { maxOf(WindowInsets.ime.getBottom(this), WindowInsets.navigationBars.getBottom(this)).toDp() }
    val composerPadding = OutlinedTextFieldDefaults.contentPadding()
    val minimumComposerHeight = maxOf(OutlinedTextFieldDefaults.MinHeight,
        with(viewDensity) { resolvedComposeLineHeight(MaterialTheme.typography.bodyLarge) } +
            composerPadding.calculateTopPadding() + composerPadding.calculateBottomPadding())
    val normalTopBarHeight = TopAppBarDefaults.TopAppBarExpandedHeight +
        with(viewDensity) { TopAppBarDefaults.windowInsets.getTop(this).toDp() }
    val availableHeight = (maxHeight - with(viewDensity) { topBarHeightPx.toDp() } - bottomInsets).coerceAtLeast(0.dp)
    // Native StableImmersionText has its own font/slot metrics. This scaled
    // reading-space preference is qualified by actual native ink, not assumed
    // to equal a Compose paragraph's measured line height.
    val messageLineHeight = with(viewDensity) { 28.sp.toDp() }
    val hasReplyInvitation = notificationEducation?.let { it.friend != null || it.settingsUnavailable } == true
    val hasStatus = hasReplyInvitation || rejectedDraftEdit || messageTooLong || showVoiceHelp || speech.state == SpeechState.UNAVAILABLE || (speech.state != SpeechState.UNAVAILABLE && speech.error != null) || error != null || chat.notice != null ||
        chat.needsDeviceRecovery || peer in chat.peersNeedingRecovery
    // Reserve readable conversation space before a growing draft consumes it.
    // Three current scaled message lines is a preference, bounded by half the
    // actual viewport and the minimum editable/status lines. Tiny landscapes
    // prioritize the native editable line when both cannot fit.
    val preferredHistoryHeight = if (messages.isNotEmpty())
        minOf(availableHeight * .5f, messageLineHeight * 3 + EmbeddedMessageVerticalPadding * 2) else 0.dp
    val statusLineHeight = if (hasReplyInvitation) 128.dp else if (hasStatus) maxOf(48.dp,
        with(viewDensity) { resolvedComposeLineHeight(MaterialTheme.typography.bodyLarge.copy(fontSize = 14.sp)) }) else 0.dp
    val compact = maxHeight - bottomInsets - normalTopBarHeight - preferredHistoryHeight <
        minimumComposerHeight + statusLineHeight + 16.dp
    val compactBarHeight = maxOf(48.dp,
        with(viewDensity) { resolvedComposeLineHeight(MaterialTheme.typography.titleLarge) })
    val composerOuterPadding = if (compact) 0.dp else 16.dp
    val candidateHistoryHeight = minOf(preferredHistoryHeight,
        (availableHeight - minimumComposerHeight - statusLineHeight - composerOuterPadding).coerceAtLeast(0.dp))
    val historyReserve = if (candidateHistoryHeight >= messageLineHeight + EmbeddedMessageVerticalPadding * 2)
        candidateHistoryHeight else 0.dp
    val footerContentHeight = (availableHeight - historyReserve).coerceAtLeast(0.dp)
    val footerMaxHeight = (maxHeight - with(viewDensity) { topBarHeightPx.toDp() } - historyReserve).coerceAtLeast(0.dp)
    // Keep normal expansion when it fits; longer drafts scroll inside the real
    // editor instead of collapsing the timeline or moving controls under IME.
    val composerMaxHeight = maxOf(minimumComposerHeight, footerContentHeight - statusLineHeight - composerOuterPadding)
    Scaffold(containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            val mode = translation?.mode ?: ImmersionMode.NEW_WORD
            ConversationHeader(chat.name(peer), peer, audio?.enabled == true, audio != null,
                    onAutoplay = {
                        val enable = audio?.enabled != true
                        audio?.setAutoplayEnabled(enable)
                        if (enable && audio?.enabled == true)
                            android.widget.Toast.makeText(context, R.string.autoplay_on_notice, android.widget.Toast.LENGTH_SHORT).show()
                    }, mode = mode, onMode = onImmersionMode?.let { change -> {
                        audio?.close()
                        change(if (mode == ImmersionMode.FULL_MESSAGES) ImmersionMode.NEW_WORD else ImmersionMode.FULL_MESSAGES)
                    } }, minHeight = if (compact) compactBarHeight else TopAppBarDefaults.TopAppBarExpandedHeight,
                modifier = Modifier.fillMaxWidth().onSizeChanged { topBarHeightPx = it.height }
                    .background(MaterialTheme.colorScheme.background).windowInsetsPadding(TopAppBarDefaults.windowInsets)
                    .padding(horizontal = 4.dp), back = {
                    IconButton(back, Modifier.size(48.dp)) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, stringResource(R.string.nav_back)) }
                }) {
                Box {
                    IconButton(onClick = {
                        copyOriginImeVisible = keyboardInsets.getBottom(viewDensity) > 0
                        copyOriginComposerFocused = composing
                        options = true
                    }, enabled = !blockBusy, modifier = Modifier.size(48.dp).testTag("conversation-options")) {
                        if (blockBusy) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                        else Icon(Icons.Outlined.MoreVert, stringResource(R.string.ui_af8a897d2feb))
                    }
                    DropdownMenu(options, onDismissRequest = { options = false }) {
                        DropdownMenuItem(text = { Text(stringResource(R.string.full_translation_copy_original)) },
                            enabled = messages.isNotEmpty(), modifier = Modifier.testTag("conversation-copy"),
                            onClick = {
                                audio?.setAutoplayEnabled(false)
                                // A hidden keyboard must not reopen when the
                                // modal returns focus to the composer. Keep its
                                // text/selection; active typing restores normally.
                                if (!copyOriginImeVisible && copyOriginComposerFocused) focusManager.clearFocus(force = true)
                                options = false; chooseCopy = true
                            })
                        DropdownMenuItem(text = { Text(stringResource(R.string.report_message)) },
                            enabled = messages.any { !it.outgoing && it.state != "imported" }, modifier = Modifier.testTag("conversation-report"),
                            onClick = { options = false; chooseReport = true })
                        if (onLanguages != null) DropdownMenuItem(text = { Text(stringResource(R.string.ui_318655cea4bd)) }, onClick = { options = false; onLanguages() })
                        DropdownMenuItem(text = { Text(stringResource(R.string.ui_53b6cd2365c7)) }, onClick = { options = false; showSecurityNumber = true })
                        DropdownMenuItem(text = { Text(if (blocked) stringResource(R.string.ui_712da63171e0) else stringResource(R.string.ui_211d0bb8cf4f)) }, onClick = { options = false; confirmBlock = true })
                    }
                }
            }
        },
        bottomBar = {
            // Scaffold measures bars independently. Keep the complete footer
            // below the measured toolbar, even with a multiline draft and IME.
            Column(Modifier.heightIn(max = footerMaxHeight).background(MaterialTheme.colorScheme.background).navigationBarsPadding().imePadding()) {
                Column(Modifier.fillMaxWidth().weight(1f, fill = false).verticalScroll(composerStatusScroll)) {
                if (notificationEducation != null) ReplyNotificationCard(notificationEducation, chat.notificationPreviews, onNotificationPermission)
                if (rejectedDraftEdit || messageTooLong) Text(
                    stringResource(if (rejectedDraftEdit) R.string.draft_edit_too_large else R.string.bot_message_too_long),
                    color = MaterialTheme.colorScheme.error, fontSize = 14.sp,
                    modifier = Modifier.padding(horizontal = 18.dp).testTag("message-length-notice"))
                if (showVoiceHelp || speech.state == SpeechState.UNAVAILABLE)
                    SpeechPreparationHelp(speech.state, speech.error) { speech.prepare(warmups) }
                if (speech.state != SpeechState.UNAVAILABLE) speech.error?.let {
                    Text(it, fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(horizontal = 18.dp, vertical = if (compact) 0.dp else 8.dp))
                }
                // A failed security check must not hide the current connection or
                // persistence explanation. Keep both distinct current failures
                // in the same bounded status area, with transport recovery first.
                listOfNotNull(chat.notice, error).distinct().forEach {
                    Text(it, fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(horizontal = 18.dp, vertical = if (compact) 0.dp else 8.dp))
                }
                if (chat.needsDeviceRecovery) TextButton(onClick = back, modifier = Modifier.padding(horizontal = 8.dp)) { Text(stringResource(R.string.ui_fa3d530cf72d)) }
                if (peer in chat.peersNeedingRecovery) TextButton(onClick = { showSecurityNumber = true }, modifier = Modifier.padding(horizontal = 8.dp)) { Text(stringResource(R.string.ui_38d5b00c27da)) }
                }
                if (blocked) Row(Modifier.fillMaxWidth().padding(16.dp).testTag("conversation-blocked"), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
                    Text(stringResource(R.string.ui_b1fe736c0809), fontSize = 14.sp)
                    TextButton(onClick = { confirmBlock = true }, enabled = !blockBusy) { Text(stringResource(R.string.ui_712da63171e0)) }
                } else {
                Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = if (compact) 0.dp else 8.dp), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedTextField(text, { value ->
                        if (!loaded) return@OutlinedTextField
                        if (value.toByteArray(Charsets.UTF_8).size > ConversationHistory.MAX_DRAFT_BYTES) {
                            rejectedDraftEdit = true; return@OutlinedTextField
                        }
                        // Selection/restoration can echo the unchanged value
                        // after a rejected paste. Keep its reason until an
                        // accepted content change actually replaces that draft.
                        if (value != text) rejectedDraftEdit = false
                        if (value != text) chat.composerActivity(peer, value.isNotBlank())
                        text = value
                        try { chat.saveCompose(value, peer) }
                        catch (_: Exception) { error = context.getString(R.string.chat_draft_save_failed) }
                    }, colors = vipiTextFieldColors(), enabled = loaded, textStyle = MaterialTheme.typography.bodyLarge.copy(textDirection = androidx.compose.ui.text.style.TextDirection.Content),
                        placeholder = { Text(stringResource(R.string.message_hint)) }, maxLines = 6, shape = RoundedCornerShape(24.dp),
                        modifier = Modifier.weight(1f).heightIn(min = minimumComposerHeight, max = composerMaxHeight)
                            .onFocusChanged { composing = it.isFocused }.testTag("message-input"))
                    FilledIconButton(onClick = {
                        if (!loaded) return@FilledIconButton
                        try {
                            chat.send(text, peer); notificationEducation?.committedUserSend(chat.name(peer)); chat.composerActivity(peer, false); text = ""; error = null
                            followingLatest = true; newMessagesBelow = 0; jumpRevision++; refresh()
                            scope.launch { list.stopScroll(); withFrameNanos { }; revealNewestMessage(); chat.synchronize() }
                        } catch (failure: Exception) { error = ChatSession.explanation(context, failure) }
                    }, enabled = loaded && chat.ready && peer !in chat.peersNeedingRecovery && text.isNotBlank() && !messageTooLong,
                        modifier = Modifier.size(48.dp).testTag("message-send")) { Icon(Icons.Outlined.ArrowUpward, stringResource(R.string.send_message)) }
                }
                }
            }
        }) { padding ->
        PullToRefreshBox(isRefreshing = userRefreshing, onRefresh = { scope.launch {
            userRefreshing = true
            try { chat.synchronize(); refresh() } finally { userRefreshing = false }
        } }, modifier = Modifier.fillMaxSize().padding(padding)) {
            Column(Modifier.fillMaxSize()) {
            BoxWithConstraints(Modifier.weight(1f).fillMaxWidth()) {
            // Below one complete reading line plus the existing list/bubble
            // insets, the IME owns this viewport. Keep the list state outside
            // this branch and restore it when typing ends; never paint a strip.
            val showTranscript = keyboardInsets.getBottom(viewDensity) == 0 ||
                maxHeight >= messageLineHeight + 36.dp + EmbeddedMessageVerticalPadding * 2
            if (!showTranscript) Box(Modifier.fillMaxSize().testTag("conversation-compact-composing"))
            // A saved history index must not be measured against a temporary
            // empty list while the encrypted rows hydrate after recreation.
            if (showTranscript && !loaded && error == null)
                CircularProgressIndicator(Modifier.align(Alignment.Center))
            if (showTranscript && loaded) {
            ConversationWaterScene(translation?.mode ?: ImmersionMode.NEW_WORD, animateBackground,
                Modifier.matchParentSize(), waterClock, plainBackground = prefersIncreasedContrast())
            LazyColumn(state = list, modifier = Modifier.fillMaxSize().fullMessageGestures(gestures).testTag("conversation-timeline").semantics {
                scrollToIndex { index ->
                    if (index !in 0 until list.layoutInfo.totalItemsCount) false else {
                        // Accessibility jumps can complete within one frame,
                        // before a scroll-in-progress observer sees the choice.
                        scope.launch(start = kotlinx.coroutines.CoroutineStart.UNDISPATCHED) {
                            followingLatest = index == list.layoutInfo.totalItemsCount - 1
                            list.scrollToItem(index)
                        }
                        true
                    }
                }
            }, contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                item(key = "history-header") {
                    ConversationTranscriptItem {
                        Column {
                            if (earlierAvailable) TextButton(onClick = { earlier() }, colors = ButtonDefaults.textButtonColors(containerColor = MaterialTheme.colorScheme.background)) { Text(stringResource(R.string.ui_561a197a2807)) }
                            if (messages.isEmpty()) Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.background, RoundedCornerShape(20.dp)).padding(30.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                Icon(Icons.Outlined.Lock, null)
                                Text(stringResource(R.string.ui_9bbf916f3af5), fontWeight = FontWeight.SemiBold)
                                Text(stringResource(R.string.ui_48e35bc10280), fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                }
                itemsIndexed(messages, key = { _, item -> item.id }) { index, item ->
                    ConversationTranscriptItem {
                        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            val locale = androidx.compose.ui.platform.LocalConfiguration.current.locales[0]
                            if (index == 0 || java.time.Instant.ofEpochMilli(item.createdAt).atZone(java.time.ZoneId.systemDefault()).toLocalDate() !=
                                java.time.Instant.ofEpochMilli(messages[index-1].createdAt).atZone(java.time.ZoneId.systemDefault()).toLocalDate()) {
                                Text(DateFormat.getDateInstance(DateFormat.MEDIUM, locale).format(Date(item.createdAt)),
                                    modifier = Modifier.align(Alignment.CenterHorizontally).background(MaterialTheme.colorScheme.background, RoundedCornerShape(20.dp)).padding(horizontal = 10.dp, vertical = 6.dp),
                                    fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = if (item.outgoing) Arrangement.End else Arrangement.Start) {
                                if (item.outgoing) Spacer(Modifier.width(32.dp))
                                Box(Modifier.weight(1f, fill = false).widthIn(max = 520.dp).testTag("message-row-${item.id}")) {
                                    ChatBubbleFrame(item.outgoing) {
                                        val status = deliveryLabel(item.state, item.outgoing)
                                        val accessible = MessageTimelineMetadata.exactTime(item.createdAt, locale) + " · " + status
                                        if (translation != null && audio != null) FullMessageBubble(item.text, item.id.toString(), translation, gestures, audio,
                                            accessibilityContext = accessible) { ChatMessageMetadata(item, locale) }
                                    }
                                }
                                if (!item.outgoing) Spacer(Modifier.width(32.dp))
                            }
                        }
                    }
                }
                if (peerTyping) item(key = "peer-typing") {
                    ConversationTranscriptItem {
                        ChatBubbleFrame(false) {
                            Text(stringResource(R.string.chat_typing, chat.name(peer)),
                                modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp).testTag("conversation-typing").semantics { liveRegion = androidx.compose.ui.semantics.LiveRegionMode.Polite },
                                fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
                item(key = "history-bottom") { Spacer(Modifier.height(1.dp)) }
            }
            if (!followingLatest && messages.isNotEmpty()) {
                FilledTonalButton(onClick = { followingLatest = true; newMessagesBelow = 0; jumpRevision++ },
                    modifier = Modifier.align(Alignment.BottomEnd).padding(12.dp).heightIn(min = 48.dp).testTag("conversation-latest"),
                    contentPadding = PaddingValues(horizontal = 14.dp)) {
                    Icon(Icons.Outlined.ArrowDownward, stringResource(R.string.ui_ef32661fdda0), modifier = Modifier.size(20.dp))
                    if (newMessagesBelow > 0) { Spacer(Modifier.width(6.dp)); Text(stringResource(R.string.chat_new_messages)) }
                }
            }
            }
            }
            FullMessageGestureCue(gestures, chat.holdEducation, composing, list.isScrollInProgress || compact,
                foreground = foreground && !options && !chooseCopy && !chooseReport && !showSecurityNumber && !confirmBlock && reportedMessage == null)
            }
        }
    }
    }
    if (showSecurityNumber) SecurityNumberSheet(chat, peer, dismiss = { showSecurityNumber = false })
    if (chooseCopy) MessageOriginalChooser(messages.map { MessageChoice(it.id.toString(), it.text) }, dismiss = { chooseCopy = false })
    if (chooseReport) MessageReportChooser(messages.filter { !it.outgoing && it.state != "imported" }.map { MessageChoice(it.id.toString(), it.text) },
        select = { id -> reportedMessage = messages.single { it.id.toString() == id }; reportReason = ""; chooseReport = false },
        dismiss = { chooseReport = false })
    reportedMessage?.let { selected -> AlertDialog(onDismissRequest = { if (!reporting) reportedMessage = null },
        title = { Text(stringResource(R.string.ui_56dd441b2ba6)) },
        text = { Column(Modifier.heightIn(max = 380.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(stringResource(R.string.ui_967b3ede020c))
            Text(selected.text, style = MaterialTheme.typography.bodyMedium)
            val savedReason = chat.reportReason(selected)
            listOf("spam" to R.string.report_spam, "harassment" to R.string.report_harassment, "harmful" to R.string.report_harmful_content, "other" to R.string.report_other).forEach { (code, title) ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(reportReason == code, onClick = { reportReason = code }, enabled = !reporting && (savedReason == null || savedReason == code))
                    Text(stringResource(title))
                }
            }
            if (savedReason != null) Text(stringResource(R.string.ui_70526d2742fe), style = MaterialTheme.typography.bodySmall)
        } },
        confirmButton = { TextButton(enabled = !reporting && reportReason.isNotEmpty(), onClick = {
            reporting = true
            scope.launch {
                try { chat.report(selected, reportReason); reportedMessage = null; error = context.getString(R.string.chat_report_received) }
                catch (cancelled: CancellationException) { throw cancelled }
                catch (_: Exception) { error = context.getString(R.string.chat_report_unconfirmed) }
                finally { reporting = false }
            }
        }) { Text(if (reporting) stringResource(R.string.ui_b8ed5279e897) else stringResource(R.string.ui_a44d35311325)) } },
        dismissButton = { TextButton(enabled = !reporting, onClick = { reportedMessage = null }) { Text(stringResource(R.string.cancel_action)) } }) }
    if (confirmBlock) AlertDialog(onDismissRequest = { confirmBlock = false },
        title = { Text(stringResource(if (blocked) R.string.unblock_person_question else R.string.block_person_question, chat.name(peer))) },
        text = { Text(if (blocked) stringResource(R.string.ui_25cb0ec8237b) else stringResource(R.string.ui_817b085ae5a9)) },
        dismissButton = { TextButton(onClick = { confirmBlock = false }) { Text(stringResource(R.string.cancel_action)) } },
        confirmButton = { TextButton(onClick = {
            val desired = !blocked; confirmBlock = false; blockBusy = true
            scope.launch {
                try { chat.setBlocked(desired, peer); error = null; refresh() }
                catch (cancelled: CancellationException) { throw cancelled }
                catch (_: Exception) { error = context.getString(R.string.chat_change_unconfirmed) }
                finally { blockBusy = false }
            }
        }) { Text(if (blocked) stringResource(R.string.ui_712da63171e0) else stringResource(R.string.ui_211d0bb8cf4f)) } })
}

@Composable internal fun deliveryLabel(state: String, outgoing: Boolean = true) = stringResource(when (state) {
    "read" -> if (outgoing) R.string.delivery_read else R.string.delivery_received
    "delivered" -> if (outgoing) R.string.delivery_delivered else R.string.delivery_received
    "accepted" -> R.string.delivery_sent
    "expired" -> R.string.delivery_expired
    "failed" -> R.string.delivery_failed
    "cancelled" -> R.string.delivery_stopped
    "imported" -> R.string.delivery_imported
    "queued", "pending" -> R.string.delivery_waiting
    else -> R.string.delivery_unknown
})
