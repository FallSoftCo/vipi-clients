package co.fallsoft.vipi

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import java.util.UUID

internal data class SavedFriend(val id: UUID, val name: String, val username: String?)

@Composable internal fun NewChatView(model: VipiModel) {
    val chat = model.chat?.takeIf { it.userID == model.authentication.userID && it.ready && !it.needsReauthentication }
    key(chat, model.invitationUsername) {
        val context = LocalContext.current
        val keyboard = LocalSoftwareKeyboardController.current
        val scope = rememberCoroutineScope()
        var query by remember { mutableStateOf(model.invitationUsername.orEmpty()) }
        var editing by remember { mutableStateOf(false) }
        var busy by remember { mutableStateOf(false) }
        var error by remember { mutableStateOf<String?>(null) }
        var contactsOpen by remember { mutableStateOf(false) }
        val friends = remember(chat, chat?.contacts, chat?.threads, chat?.blockedPeers, chat?.profile) { chat?.savedFriends().orEmpty() }
        val term = query.trim().removePrefix("@")
        val matches = remember(friends, term) { friends.filter { it.name.contains(term, true) || it.username?.contains(term, true) == true } }
        val exact = runCatching { normalizeLookupUsername(query) }.getOrNull()
        fun current() = chat != null && model.chat === chat && model.authentication.userID == chat.userID && chat.ready && !chat.needsReauthentication
        fun open(id: UUID) {
            if (current() && id != chat?.profile?.id && id !in requireNotNull(chat).blockedPeers) {
                keyboard?.hide()
                model.openConversation(id)
            }
        }
        fun submit() {
            if (busy || !current() || exact == null) return
            val saved = friends.firstOrNull { it.username.equals(exact, ignoreCase = true) }
            if (saved != null) { open(saved.id); return }
            val active = requireNotNull(chat)
            busy = true
            error = null
            keyboard?.hide()
            scope.launch {
                try {
                    val result = active.find(exact)
                    if (current() && result.id in active.blockedPeers) error = context.getString(R.string.new_chat_unavailable)
                    else open(result.id)
                } catch (cancelled: CancellationException) { throw cancelled }
                catch (failure: Exception) { if (current()) error = ChatSession.explanation(context, failure) }
                finally { busy = false }
            }
        }
        Scaffold { padding ->
            LazyColumn(Modifier.fillMaxSize().padding(padding).consumeWindowInsets(padding).imePadding().testTag("new-chat-list"),
                contentPadding = PaddingValues(horizontal = 20.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                item { TopBar(model) }
                item {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        OutlinedTextField(value = query, onValueChange = { query = it; error = null }, enabled = !busy,
                            label = { Text(stringResource(R.string.new_chat_search)) }, singleLine = true,
                            colors = vipiTextFieldColors(), keyboardOptions = KeyboardOptions(autoCorrectEnabled = false, imeAction = ImeAction.Search),
                            keyboardActions = KeyboardActions(onSearch = { submit() }), modifier = Modifier.weight(1f).onFocusChanged { editing = it.isFocused }.testTag("new-chat-search"))
                        ScreenSpot(R.drawable.vipi_spot_new_chat, editing)
                    }
                }
                if (chat == null) item { Text(stringResource(R.string.friends_sign_in_required)) }
                else {
                    if (exact != null && friends.none { it.username.equals(exact, true) }) item {
                        TextButton(onClick = ::submit, enabled = !busy) { Text(stringResource(R.string.new_chat_lookup, exact)) }
                    }
                    error?.let { failure -> item { Text(failure, color = MaterialTheme.colorScheme.error,
                        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }) } }
                    item {
                        Column(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
                            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                InviteFriendButton(model)
                                TextButton(onClick = { keyboard?.hide(); contactsOpen = true }) { Text(stringResource(R.string.new_chat_phone_contacts)) }
                            }
                            Text(stringResource(R.string.new_chat_privacy), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                    item { HorizontalDivider(); Text(stringResource(R.string.new_chat_saved), style = MaterialTheme.typography.titleSmall,
                        modifier = Modifier.padding(top = 14.dp, bottom = 4.dp).semantics { heading() }) }
                    if (matches.isEmpty()) item {
                        Text(stringResource(if (query.isBlank()) R.string.new_chat_empty else R.string.new_chat_no_matches),
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    items(matches, key = { it.id }) { friend ->
                        Row(Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable(role = Role.Button) { open(friend.id) }.testTag("saved-friend-${friend.id}"),
                            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            ContactAvatar(friend.name, friend.id)
                            Column(Modifier.weight(1f).padding(vertical = 6.dp)) {
                                Text(friend.name, style = MaterialTheme.typography.bodyLarge)
                                friend.username?.let { Text("@$it", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                            }
                        }
                    }
                }
            }
        }
        val owner = chat?.profile
        if (contactsOpen && owner != null) PhoneContactInvitations(owner.username) { contactsOpen = false }
    }
}
