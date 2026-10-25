package co.fallsoft.vipi

import androidx.compose.foundation.background
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
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material.icons.outlined.MoreVert
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import kotlinx.coroutines.CancellationException
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
        if (chat.ready) model.navigate(Screen.HOME)
    } }, enabled = !chat.busy && name.isNotBlank() && name.length <= 80 && username.matches(Regex("[a-zA-Z][a-zA-Z0-9_]{2,23}")),
        shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth().testTag("profile-submit"), contentPadding = PaddingValues(20.dp)) {
        if (chat.busy) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
        else Text("Start chatting", fontWeight = FontWeight.SemiBold)
    }
    TextButton(onClick = { model.navigate(Screen.DELETE_ACCOUNT) }, enabled = !chat.busy) { Text("Delete account", color = MaterialTheme.colorScheme.error) }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable internal fun FriendConversationScreen(chat: ChatSession, peer: UUID, back: () -> Unit) {
    var messages by remember(peer) { mutableStateOf<List<ChatItem>>(emptyList()) }
    var text by remember(peer) { mutableStateOf("") }
    var error by remember(peer) { mutableStateOf<String?>(null) }
    var earlierAvailable by remember(peer) { mutableStateOf(false) }
    var loaded by remember(peer) { mutableStateOf(false) }
    var userRefreshing by remember(peer) { mutableStateOf(false) }
    var options by remember(peer) { mutableStateOf(false) }
    var confirmBlock by remember(peer) { mutableStateOf(false) }
    var blockBusy by remember(peer) { mutableStateOf(false) }
    var showSecurityNumber by remember(peer) { mutableStateOf(false) }
    val blocked = peer in chat.blockedPeers
    val scope = rememberCoroutineScope()
    val list = rememberLazyListState()
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
            val page = chat.messages(peer, messages.firstOrNull()?.cursor); val ids = messages.map { it.id }.toSet()
            messages = page.reversed().filter { it.id !in ids } + messages; earlierAvailable = page.size == 50
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
    LaunchedEffect(messages.lastOrNull()?.id) { if (messages.isNotEmpty()) list.scrollToItem(messages.size + 1) }
    Scaffold(containerColor = MaterialTheme.colorScheme.background,
        topBar = { TopAppBar(title = { Text(chat.name(peer), maxLines = 1) }, colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background), navigationIcon = { IconButton(back) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, "Back") } },
            actions = {
                Box {
                    IconButton(onClick = { options = true }, enabled = !blockBusy, modifier = Modifier.testTag("conversation-options")) {
                        if (blockBusy) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                        else Icon(Icons.Outlined.MoreVert, "Conversation options")
                    }
                    DropdownMenu(options, onDismissRequest = { options = false }) {
                        DropdownMenuItem(text = { Text("Verify encryption") }, onClick = { options = false; showSecurityNumber = true })
                        DropdownMenuItem(text = { Text(if (blocked) "Unblock" else "Block") }, onClick = { options = false; confirmBlock = true })
                    }
                }
            }) },
        bottomBar = {
            Column(Modifier.background(MaterialTheme.colorScheme.background).navigationBarsPadding().imePadding()) {
                (error ?: chat.notice)?.let { Text(it, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(horizontal = 18.dp, vertical = 8.dp)) }
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
                        modifier = Modifier.weight(1f).testTag("message-input"))
                    FilledIconButton(onClick = {
                        try {
                            chat.send(text, peer); text = ""; error = null; refresh()
                            scope.launch { chat.synchronize() }
                        } catch (failure: Exception) { error = ChatSession.explanation(failure) }
                    }, enabled = text.isNotBlank() && text.toByteArray(Charsets.UTF_8).size <= 32768,
                        modifier = Modifier.size(48.dp).testTag("message-send")) { Icon(Icons.Outlined.ArrowUpward, "Send message") }
                }
                }
            }
        }) { padding ->
        PullToRefreshBox(isRefreshing = userRefreshing, onRefresh = { scope.launch {
            userRefreshing = true
            try { chat.synchronize(); refresh() } finally { userRefreshing = false }
        } }, modifier = Modifier.fillMaxSize().padding(padding)) {
            LazyColumn(state = list, modifier = Modifier.fillMaxSize(), contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                item {
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
                            SelectionContainer { Text(item.text, lineHeight = 24.sp) }
                            val time = remember(item.createdAt) { DateFormat.getTimeInstance(DateFormat.SHORT).format(Date(item.createdAt)) }
                            Text(time + if (item.outgoing) " · " + deliveryLabel(item.state) else "", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        if (!item.outgoing) Spacer(Modifier.width(38.dp))
                    }
                }
                item { Spacer(Modifier.height(1.dp)) }
            }
        }
    }
    if (showSecurityNumber) SecurityNumberSheet(chat, peer, dismiss = { showSecurityNumber = false })
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
    else -> "Waiting to send"
}
