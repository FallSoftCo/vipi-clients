package co.fallsoft.vipi

import androidx.compose.foundation.background
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.semantics.semantics
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
import kotlinx.coroutines.flow.collectLatest
import java.text.DateFormat
import java.util.Date
import java.util.UUID

@Composable internal fun ProfileSetupScreen(model: VipiModel) {
    val chat = model.chat ?: return
    var name by rememberSaveable { mutableStateOf("") }
    var username by rememberSaveable { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    Text(stringResource(R.string.ui_73bee38b06e8), fontFamily = FontFamily.Serif, fontSize = 34.sp, lineHeight = 40.sp)
    Text(stringResource(R.string.ui_956d8b926f8d), color = MaterialTheme.colorScheme.onSurfaceVariant)
    OutlinedTextField(name, { name = it }, label = { Text(stringResource(R.string.ui_2c6b2e253c01)) }, singleLine = true,
        modifier = Modifier.fillMaxWidth().testTag("profile-name"), shape = RoundedCornerShape(16.dp))
    OutlinedTextField(username, { username = it }, label = { Text(stringResource(R.string.ui_e3b89e9d33f8)) }, prefix = { Text("@") }, singleLine = true,
        keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None, autoCorrectEnabled = false),
        modifier = Modifier.fillMaxWidth().testTag("profile-username"), shape = RoundedCornerShape(16.dp))
    Text(stringResource(R.string.ui_33875a9b79e5), fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    chat.notice?.let { Text(it, fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    Button(onClick = { scope.launch {
        chat.createProfile(username, name)
        if (chat.ready) model.navigate(Screen.PLANS)
    } }, enabled = !chat.busy && name.isNotBlank() && name.length <= 80 && username.matches(Regex("[a-zA-Z][a-zA-Z0-9_]{2,23}")),
        shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth().testTag("profile-submit"), contentPadding = PaddingValues(20.dp)) {
        if (chat.busy) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
        else Text(stringResource(R.string.continue_action), fontWeight = FontWeight.SemiBold)
    }
    TextButton(onClick = { model.navigate(Screen.DELETE_ACCOUNT) }, enabled = !chat.busy) { Text(stringResource(R.string.ui_a2e20a335700), color = MaterialTheme.colorScheme.error) }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable internal fun FriendConversationScreen(chat: ChatSession, peer: UUID, source: String = "en", target: String = "es",
    density: Double = .25, onLanguages: (() -> Unit)? = null, onPlan: (() -> Unit)? = null,
    qaReadingProducer: (suspend (String, String) -> FullReading?)? = null,
    qaTranslator: LanguageTranslation? = null, qaContextualActions: Boolean = false,
    qaModelsReady: Boolean? = null, back: () -> Unit) {
    require(qaTranslator == null || BuildConfig.DEBUG)
    require(!qaContextualActions || BuildConfig.DEBUG)
    require(qaModelsReady == null || (BuildConfig.DEBUG && qaTranslator != null))
    var messages by remember(peer) { mutableStateOf<List<ChatItem>>(emptyList()) }
    var text by remember(peer) { mutableStateOf("") }
    var error by remember(peer) { mutableStateOf<String?>(null) }
    var earlierAvailable by remember(peer) { mutableStateOf(false) }
    var loaded by remember(peer) { mutableStateOf(false) }
    var userRefreshing by remember(peer) { mutableStateOf(false) }
    var options by remember(peer) { mutableStateOf(false) }
    var confirmBlock by remember(peer) { mutableStateOf(false) }
    var blockBusy by remember(peer) { mutableStateOf(false) }
    var reportedMessage by remember(peer) { mutableStateOf<ChatItem?>(null) }
    var reportReason by remember(peer) { mutableStateOf("") }
    var reporting by remember(peer) { mutableStateOf(false) }
    var showSecurityNumber by remember(peer) { mutableStateOf(false) }
    var showVoiceHelp by remember(peer) { mutableStateOf(false) }
    var voiceSettingsError by remember { mutableStateOf<String?>(null) }
    var followingLatest by remember(peer) { mutableStateOf(true) }
    var jumpRevision by remember(peer) { mutableIntStateOf(0) }
    val blocked = peer in chat.blockedPeers
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val immersion = remember(chat, peer, source, target, density, qaReadingProducer, qaTranslator, qaModelsReady) {
        ConversationImmersion(context, source, target, density, translator = qaTranslator ?: LocalTranslation(), qaReadingProducer = qaReadingProducer, qaModelsReady = qaModelsReady, familiarity = chat.familiarity)
    }
    val speech = remember(chat, peer, source, target) { SpeechPlayback(context, source, target, scope) }
    val warmups = remember(source, target) {
        val example = ConversationExamples.result(context, source, target)
        mapOf(source to example.original, target to example.translation)
    }
    val lifecycle = LocalLifecycleOwner.current
    var composing by remember { mutableStateOf(false) }
    LaunchedEffect(immersion) { immersion.checkDownloads() }
    LaunchedEffect(speech) { speech.prepare(warmups) }
    LaunchedEffect(speech.state) { if (speech.state == SpeechState.READY) showVoiceHelp = false }
    DisposableEffect(lifecycle, immersion, speech) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) speech.stop()
            if (event == Lifecycle.Event.ON_RESUME) {
                scope.launch { immersion.checkDownloads() }; speech.prepare(warmups)
            }
        }
        lifecycle.lifecycle.addObserver(observer)
        onDispose { lifecycle.lifecycle.removeObserver(observer) }
    }
    DisposableEffect(immersion) { onDispose { immersion.close() } }
    DisposableEffect(speech) { onDispose { speech.close() } }
    val list = rememberLazyListState()
    LaunchedEffect(list, peer) {
        snapshotFlow {
            val layout = list.layoutInfo
            val last = layout.visibleItemsInfo.lastOrNull()
            val nearBottom = last != null && last.index == layout.totalItemsCount - 1 &&
                last.offset + last.size <= layout.viewportEndOffset
            // scrollToItem updates requested state before the next measure.
            // An old bottom layout must not undo an explicit jump to history.
            Triple(list.isScrollInProgress, nearBottom,
                layout.visibleItemsInfo.firstOrNull()?.index == list.firstVisibleItemIndex)
        }.collect { (scrolling, nearBottom, measuredPosition) ->
            // Content insertion alone must not revoke the reader's choice to
            // follow latest. Only scrolling can move that choice away.
            if (measuredPosition && (scrolling || nearBottom)) followingLatest = nearBottom
        }
    }
    LaunchedEffect(list, peer) {
        var previous: Pair<Int, Map<Any, Int>>? = null
        snapshotFlow {
            val layout = list.layoutInfo
            layout.viewportSize.height to layout.visibleItemsInfo.associate { it.key to it.size }
        }.collectLatest { current ->
            val before = previous
            previous = current
            // New visible keys mean scrolling, not resizing. Compare only
            // shared rows so paging back cannot trigger a jump to the bottom.
            val resized = before != null && before.first > 0 && before.second.isNotEmpty() && (before.first != current.first ||
                current.second.any { (key, height) -> before.second[key]?.let { it != height } == true })
            if (resized && followingLatest && !list.isScrollInProgress && messages.isNotEmpty()) {
                // Layout snapshots can arrive while AndroidView is measuring.
                // Wait for the next frame before requesting a synchronous
                // scroll, then respect any intervening jump back to history.
                withFrameNanos { }
                if (followingLatest && !list.isScrollInProgress && messages.isNotEmpty()) {
                    list.scrollToItem(messages.size + 1)
                }
            }
        }
    }
    fun refresh() {
        try {
            val current = chat.messages(peer); val ids = current.map { it.id }.toSet()
            messages = (current + messages.filter { it.id !in ids }).sortedBy { it.cursor }
            if (!loaded) { text = chat.compose(peer); earlierAvailable = current.size == 50; loaded = true }
            chat.markRead(peer)
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
    LaunchedEffect(messages.lastOrNull()?.id, jumpRevision) {
        if (followingLatest && messages.isNotEmpty()) list.scrollToItem(messages.size + 1)
    }
    Scaffold(containerColor = MaterialTheme.colorScheme.background,
        topBar = { TopAppBar(title = { Text(chat.name(peer), maxLines = 1) }, colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background), navigationIcon = { IconButton(back) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, stringResource(R.string.nav_back)) } },
            actions = {
                Box {
                    IconButton(onClick = { options = true }, enabled = !blockBusy, modifier = Modifier.testTag("conversation-options")) {
                        if (blockBusy) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                        else Icon(Icons.Outlined.MoreVert, stringResource(R.string.ui_af8a897d2feb))
                    }
                    DropdownMenu(options, onDismissRequest = { options = false }) {
                        if (onLanguages != null) DropdownMenuItem(text = { Text(stringResource(R.string.ui_318655cea4bd)) }, onClick = { options = false; onLanguages() })
                        DropdownMenuItem(text = { Text(stringResource(R.string.ui_53b6cd2365c7)) }, onClick = { options = false; showSecurityNumber = true })
                        DropdownMenuItem(text = { Text(if (blocked) stringResource(R.string.ui_712da63171e0) else stringResource(R.string.ui_211d0bb8cf4f)) }, onClick = { options = false; confirmBlock = true })
                    }
                }
            }) },
        bottomBar = {
            Column(Modifier.background(MaterialTheme.colorScheme.background).navigationBarsPadding().imePadding()) {
                if (speech.state != SpeechState.UNAVAILABLE) speech.error?.let {
                    Text(it, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(horizontal = 18.dp, vertical = 8.dp))
                }
                (error ?: chat.notice)?.let { Text(it, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(horizontal = 18.dp, vertical = 8.dp)) }
                if (chat.needsPlan && onPlan != null) TextButton(onClick = onPlan, modifier = Modifier.padding(horizontal = 8.dp)) { Text(stringResource(R.string.ui_b30a48ba0b99)) }
                if (chat.needsDeviceRecovery) TextButton(onClick = back, modifier = Modifier.padding(horizontal = 8.dp)) { Text(stringResource(R.string.ui_fa3d530cf72d)) }
                if (peer in chat.peersNeedingRecovery) TextButton(onClick = { showSecurityNumber = true }, modifier = Modifier.padding(horizontal = 8.dp)) { Text(stringResource(R.string.ui_38d5b00c27da)) }
                if (blocked) Row(Modifier.fillMaxWidth().padding(16.dp).testTag("conversation-blocked"), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
                    Text(stringResource(R.string.ui_b1fe736c0809), fontSize = 14.sp)
                    TextButton(onClick = { confirmBlock = true }, enabled = !blockBusy) { Text(stringResource(R.string.ui_712da63171e0)) }
                } else {
                Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedTextField(text, { value ->
                        text = value
                        try { chat.saveCompose(value, peer) }
                        catch (_: Exception) { error = context.getString(R.string.chat_draft_save_failed) }
                    }, placeholder = { Text(stringResource(R.string.message_hint)) }, maxLines = 6, shape = RoundedCornerShape(24.dp),
                        modifier = Modifier.weight(1f).onFocusChanged { composing = it.isFocused }.testTag("message-input"))
                    FilledIconButton(onClick = {
                        try {
                            chat.send(text, peer); text = ""; error = null
                            followingLatest = true; jumpRevision++; refresh()
                            scope.launch { chat.synchronize() }
                        } catch (failure: Exception) { error = ChatSession.explanation(context, failure) }
                    }, enabled = chat.ready && peer !in chat.peersNeedingRecovery && text.isNotBlank() && text.toByteArray(Charsets.UTF_8).size <= 32768,
                        modifier = Modifier.size(48.dp).testTag("message-send")) { Icon(Icons.Outlined.ArrowUpward, stringResource(R.string.send_message)) }
                }
                }
            }
        }) { padding ->
        PullToRefreshBox(isRefreshing = userRefreshing, onRefresh = { scope.launch {
            userRefreshing = true
            try { chat.synchronize(); refresh() } finally { userRefreshing = false }
        } }, modifier = Modifier.fillMaxSize().padding(padding)) {
            LazyColumn(state = list, modifier = Modifier.fillMaxSize().testTag("conversation-timeline").semantics {
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
            }, contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                item(key = "history-header") {
                    if (earlierAvailable) TextButton(onClick = { earlier() }) { Text(stringResource(R.string.ui_561a197a2807)) }
                    if (messages.isEmpty()) Column(Modifier.fillMaxWidth().padding(30.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Icon(Icons.Outlined.Lock, null)
                        Text(stringResource(R.string.ui_9bbf916f3af5), fontWeight = FontWeight.SemiBold)
                        Text(stringResource(R.string.ui_48e35bc10280), fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                items(messages, key = { it.id }) { item ->
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (item.outgoing) Arrangement.End else Arrangement.Start) {
                        if (item.outgoing) Spacer(Modifier.width(38.dp))
                        Column(Modifier.weight(1f, fill = false).background(if (item.outgoing) MaterialTheme.colorScheme.surfaceVariant else MaterialTheme.colorScheme.surface, RoundedCornerShape(18.dp)).padding(horizontal = 15.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                            val time = remember(item.createdAt) { DateFormat.getTimeInstance(DateFormat.SHORT).format(Date(item.createdAt)) }
                            ConversationImmersionText(item.text, item.id.toString(), immersion, speech,
                                list.isScrollInProgress || (composing && text.isNotEmpty()) || reportedMessage != null,
                                contextualActions = qaContextualActions,
                                onVoiceHelp = { showVoiceHelp = true },
                                onTranslationSetup = onLanguages,
                                onReport = if (!item.outgoing && item.state != "imported") ({
                                    speech.stop(); reportedMessage = item; reportReason = chat.reportReason(item) ?: ""
                                }) else null) {
                            Text(time + if (item.outgoing) " · " + deliveryLabel(item.state) else "", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
                                modifier = Modifier.testTag("message-meta-${item.id}"))
                            }
                        }
                        if (!item.outgoing) Spacer(Modifier.width(38.dp))
                    }
                }
                item(key = "history-bottom") { Spacer(Modifier.height(1.dp)) }
            }
            if (!followingLatest && messages.isNotEmpty()) {
                FilledTonalIconButton(onClick = { followingLatest = true; jumpRevision++ },
                    modifier = Modifier.align(Alignment.BottomEnd).padding(12.dp).size(48.dp).testTag("conversation-latest")) {
                    Icon(Icons.Outlined.ArrowDownward, stringResource(R.string.ui_ef32661fdda0))
                }
            }
        }
    }
    if (showSecurityNumber) SecurityNumberSheet(chat, peer, dismiss = { showSecurityNumber = false })
    if (showVoiceHelp) AlertDialog(onDismissRequest = { showVoiceHelp = false },
        title = { Text(stringResource(R.string.ui_b7c32ca74cb0)) },
        text = { Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(speech.error ?: stringResource(R.string.voices_prepare_offline))
            voiceSettingsError?.let { Text(it) }
            TextButton(onClick = {
                voiceSettingsError = null
                try { context.startActivity(Intent("com.android.settings.TTS_SETTINGS")) }
                catch (_: Exception) { voiceSettingsError = context.getString(R.string.speech_settings_help) }
            }) { Text(stringResource(R.string.ui_8b3f05442c1b)) }
            if (speech.state == SpeechState.PREPARING) CircularProgressIndicator(Modifier.size(24.dp))
        } },
        confirmButton = { TextButton(onClick = { speech.prepare(warmups) }, enabled = speech.state != SpeechState.PREPARING) { Text(stringResource(R.string.ui_ed783fa140ed)) } },
        dismissButton = { TextButton(onClick = { showVoiceHelp = false }) { Text(stringResource(R.string.ui_11a6767d5674)) } })
    reportedMessage?.let { selected -> AlertDialog(onDismissRequest = { if (!reporting) reportedMessage = null },
        title = { Text(stringResource(R.string.ui_56dd441b2ba6)) },
        text = { Column(Modifier.heightIn(max = 380.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(stringResource(R.string.ui_967b3ede020c))
            Text(selected.text, style = MaterialTheme.typography.bodyMedium)
            val savedReason = chat.reportReason(selected)
            listOf("spam" to "Spam", "harassment" to "Harassment", "harmful" to "Harmful content", "other" to "Something else").forEach { (code, title) ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(reportReason == code, onClick = { reportReason = code }, enabled = !reporting && (savedReason == null || savedReason == code))
                    Text(title)
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
        title = { Text((if (blocked) "Unblock " else "Block ") + chat.name(peer) + "?") },
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

@Composable private fun deliveryLabel(state: String) = stringResource(when (state) {
    "delivered" -> R.string.delivery_delivered
    "accepted" -> R.string.delivery_sent
    "expired" -> R.string.delivery_expired
    "failed" -> R.string.delivery_failed
    "cancelled" -> R.string.delivery_stopped
    "imported" -> R.string.delivery_imported
    else -> R.string.delivery_waiting
})
