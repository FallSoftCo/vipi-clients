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
    Text("How will friends\nfind you?", fontFamily = FontFamily.Serif, fontSize = 34.sp, lineHeight = 40.sp)
    Text("Choose a name they’ll recognise and a username to share.", color = MaterialTheme.colorScheme.onSurfaceVariant)
    OutlinedTextField(name, { name = it }, label = { Text("Your name") }, singleLine = true,
        modifier = Modifier.fillMaxWidth().testTag("profile-name"), shape = RoundedCornerShape(16.dp))
    OutlinedTextField(username, { username = it }, label = { Text("Username") }, prefix = { Text("@") }, singleLine = true,
        keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None, autoCorrectEnabled = false),
        modifier = Modifier.fillMaxWidth().testTag("profile-username"), shape = RoundedCornerShape(16.dp))
    Text("3–24 letters, numbers or underscores. Your phone number and contacts stay private.", fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    chat.notice?.let { Text(it, fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    Button(onClick = { scope.launch {
        chat.createProfile(username, name)
        if (chat.ready) model.navigate(Screen.PLANS)
    } }, enabled = !chat.busy && name.isNotBlank() && name.length <= 80 && username.matches(Regex("[a-zA-Z][a-zA-Z0-9_]{2,23}")),
        shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth().testTag("profile-submit"), contentPadding = PaddingValues(20.dp)) {
        if (chat.busy) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
        else Text("Continue", fontWeight = FontWeight.SemiBold)
    }
    TextButton(onClick = { model.navigate(Screen.DELETE_ACCOUNT) }, enabled = !chat.busy) { Text("Delete account", color = MaterialTheme.colorScheme.error) }
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
        } catch (_: Exception) { error = "Your saved messages couldn’t be opened. Please try again." }
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
        } catch (_: Exception) { error = "Earlier messages couldn’t be opened. Please try again." }
    }
    LaunchedEffect(peer) {
        refresh(); blockBusy = true
        try { chat.refreshBlock(peer) }
        catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { error = "Block status couldn’t be checked. Your last confirmed choice is saved." }
        finally { blockBusy = false }
        chat.synchronize()
    }
    LaunchedEffect(chat.revision) { refresh() }
    LaunchedEffect(messages.lastOrNull()?.id, jumpRevision) {
        if (followingLatest && messages.isNotEmpty()) list.scrollToItem(messages.size + 1)
    }
    Scaffold(containerColor = MaterialTheme.colorScheme.background,
        topBar = { TopAppBar(title = { Text(chat.name(peer), maxLines = 1) }, colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background), navigationIcon = { IconButton(back) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, "Back") } },
            actions = {
                Box {
                    IconButton(onClick = { options = true }, enabled = !blockBusy, modifier = Modifier.testTag("conversation-options")) {
                        if (blockBusy) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                        else Icon(Icons.Outlined.MoreVert, "Conversation options")
                    }
                    DropdownMenu(options, onDismissRequest = { options = false }) {
                        if (onLanguages != null) DropdownMenuItem(text = { Text("Languages") }, onClick = { options = false; onLanguages() })
                        DropdownMenuItem(text = { Text("Verify encryption") }, onClick = { options = false; showSecurityNumber = true })
                        DropdownMenuItem(text = { Text(if (blocked) "Unblock" else "Block") }, onClick = { options = false; confirmBlock = true })
                    }
                }
            }) },
        bottomBar = {
            Column(Modifier.background(MaterialTheme.colorScheme.background).navigationBarsPadding().imePadding()) {
                if (speech.state != SpeechState.UNAVAILABLE) speech.error?.let {
                    Text(it, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(horizontal = 18.dp, vertical = 8.dp))
                }
                (error ?: chat.notice)?.let { Text(it, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(horizontal = 18.dp, vertical = 8.dp)) }
                if (chat.needsPlan && onPlan != null) TextButton(onClick = onPlan, modifier = Modifier.padding(horizontal = 8.dp)) { Text("View or restore Vipi plan") }
                if (chat.needsDeviceRecovery) TextButton(onClick = back, modifier = Modifier.padding(horizontal = 8.dp)) { Text("Connect this device") }
                if (peer in chat.peersNeedingRecovery) TextButton(onClick = { showSecurityNumber = true }, modifier = Modifier.padding(horizontal = 8.dp)) { Text("Review changed encryption") }
                if (blocked) Row(Modifier.fillMaxWidth().padding(16.dp).testTag("conversation-blocked"), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
                    Text("You blocked this person.", fontSize = 14.sp)
                    TextButton(onClick = { confirmBlock = true }, enabled = !blockBusy) { Text("Unblock") }
                } else {
                Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedTextField(text, { value ->
                        text = value
                        try { chat.saveCompose(value, peer) }
                        catch (_: Exception) { error = "This draft couldn’t be saved. Keep this conversation open and try again." }
                    }, placeholder = { Text("Message") }, maxLines = 6, shape = RoundedCornerShape(24.dp),
                        modifier = Modifier.weight(1f).onFocusChanged { composing = it.isFocused }.testTag("message-input"))
                    FilledIconButton(onClick = {
                        try {
                            chat.send(text, peer); text = ""; error = null
                            followingLatest = true; jumpRevision++; refresh()
                            scope.launch { chat.synchronize() }
                        } catch (failure: Exception) { error = ChatSession.explanation(failure) }
                    }, enabled = chat.ready && peer !in chat.peersNeedingRecovery && text.isNotBlank() && text.toByteArray(Charsets.UTF_8).size <= 32768,
                        modifier = Modifier.size(48.dp).testTag("message-send")) { Icon(Icons.Outlined.ArrowUpward, "Send message") }
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
                    if (earlierAvailable) TextButton(onClick = { earlier() }) { Text("Earlier messages") }
                    if (messages.isEmpty()) Column(Modifier.fillMaxWidth().padding(30.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Icon(Icons.Outlined.Lock, null)
                        Text("Just between you two", fontWeight = FontWeight.SemiBold)
                        Text("Say hello. Your messages are end-to-end encrypted.", fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
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
                    Icon(Icons.Outlined.ArrowDownward, "Jump to latest messages")
                }
            }
        }
    }
    if (showSecurityNumber) SecurityNumberSheet(chat, peer, dismiss = { showSecurityNumber = false })
    if (showVoiceHelp) AlertDialog(onDismissRequest = { showVoiceHelp = false },
        title = { Text("Hear both languages") },
        text = { Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(speech.error ?: "Prepare the voices for both languages to listen without a connection.")
            voiceSettingsError?.let { Text(it) }
            TextButton(onClick = {
                voiceSettingsError = null
                try { context.startActivity(Intent("com.android.settings.TTS_SETTINGS")) }
                catch (_: Exception) { voiceSettingsError = "Open your phone’s Settings and search for text-to-speech." }
            }) { Text("Speech settings") }
            if (speech.state == SpeechState.PREPARING) CircularProgressIndicator(Modifier.size(24.dp))
        } },
        confirmButton = { TextButton(onClick = { speech.prepare(warmups) }, enabled = speech.state != SpeechState.PREPARING) { Text("Retry voices") } },
        dismissButton = { TextButton(onClick = { showVoiceHelp = false }) { Text("Done") } })
    reportedMessage?.let { selected -> AlertDialog(onDismissRequest = { if (!reporting) reportedMessage = null },
        title = { Text("Report this message") },
        text = { Column(Modifier.heightIn(max = 380.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("The original message below, its sender and your reason will go to Fallible Software for review. The rest of your conversation stays private. Reports are kept for up to 30 days.")
            Text(selected.text, style = MaterialTheme.typography.bodyMedium)
            val savedReason = chat.reportReason(selected)
            listOf("spam" to "Spam", "harassment" to "Harassment", "harmful" to "Harmful content", "other" to "Something else").forEach { (code, title) ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(reportReason == code, onClick = { reportReason = code }, enabled = !reporting && (savedReason == null || savedReason == code))
                    Text(title)
                }
            }
            if (savedReason != null) Text("Retrying keeps the same report, so it is not submitted twice.", style = MaterialTheme.typography.bodySmall)
        } },
        confirmButton = { TextButton(enabled = !reporting && reportReason.isNotEmpty(), onClick = {
            reporting = true
            scope.launch {
                try { chat.report(selected, reportReason); reportedMessage = null; error = "Report received. You can also block this person from Conversation options." }
                catch (cancelled: CancellationException) { throw cancelled }
                catch (_: Exception) { error = "We couldn’t confirm the report. You can retry this same report." }
                finally { reporting = false }
            }
        }) { Text(if (reporting) "Sending…" else "Send report") } },
        dismissButton = { TextButton(enabled = !reporting, onClick = { reportedMessage = null }) { Text("Cancel") } }) }
    if (confirmBlock) AlertDialog(onDismissRequest = { confirmBlock = false },
        title = { Text((if (blocked) "Unblock " else "Block ") + chat.name(peer) + "?") },
        text = { Text(if (blocked) "You can exchange new messages again. Stopped messages won’t be resent." else "Messages between you will stop. Your chat stays on this device. You can unblock anytime.") },
        dismissButton = { TextButton(onClick = { confirmBlock = false }) { Text("Cancel") } },
        confirmButton = { TextButton(onClick = {
            val desired = !blocked; confirmBlock = false; blockBusy = true
            scope.launch {
                try { chat.setBlocked(desired, peer); error = null; refresh() }
                catch (cancelled: CancellationException) { throw cancelled }
                catch (_: Exception) { error = "Couldn’t confirm the change. Check your connection and try again." }
                finally { blockBusy = false }
            }
        }) { Text(if (blocked) "Unblock" else "Block") } })
}

private fun deliveryLabel(state: String) = when (state) {
    "delivered" -> "Delivered"
    "accepted" -> "Sent"
    "expired" -> "Not delivered · 72 hours passed"
    "failed" -> "Not delivered"
    "cancelled" -> "Stopped"
    "imported" -> "Imported"
    else -> "Waiting to send"
}
