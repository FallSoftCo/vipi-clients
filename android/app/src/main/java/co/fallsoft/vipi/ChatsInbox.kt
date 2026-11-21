package co.fallsoft.vipi

import android.text.format.DateUtils
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AccountCircle
import androidx.compose.material.icons.outlined.Edit
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material.icons.outlined.Forum
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import java.text.NumberFormat
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.temporal.ChronoUnit

@Composable internal fun ChatsInbox(model: VipiModel, listState: LazyListState, waterClock: WaterClock) {
    val chat = model.chat
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val threads = chat?.threads.orEmpty()
    val ready = chat?.ready == true
    val needsRecovery = chat?.needsDeviceRecovery == true
    val needsSignIn = chat?.needsReauthentication == true
    val loading = model.authentication.userID != null && !needsRecovery && !needsSignIn &&
        (!ready || model.chatError != null)
    val newChat = { model.navigate(Screen.NEW_CHAT) }
    val newChatLabel = stringResource(R.string.nav_new_chat)
    val settingsLabel = stringResource(R.string.nav_settings)
    // The action belongs to the conversation pane on expanded/folded widths.
    // The outer canvas still covers the complete edge-to-edge window.
    Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background), contentAlignment = Alignment.TopCenter) {
    ConversationWaterScene(model.immersionMode, model.animateConversationBackground,
        Modifier.matchParentSize(), waterClock, plainBackground = prefersIncreasedContrast(), listSurface = true)
    Scaffold(modifier = Modifier.widthIn(max = 680.dp).fillMaxSize(),
        containerColor = androidx.compose.ui.graphics.Color.Transparent,
        contentWindowInsets = WindowInsets.safeDrawing,
        floatingActionButtonPosition = FabPosition.End,
        floatingActionButton = {
            if (threads.isNotEmpty()) FloatingActionButton(
                onClick = { if (ready) newChat() },
                containerColor = if (ready) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceVariant,
                contentColor = if (ready) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.testTag("inbox-compose").semantics {
                    contentDescription = newChatLabel
                    if (!ready) disabled()
                }) { Icon(Icons.Outlined.Edit, null) }
        }) { insets ->
        Box(Modifier.fillMaxSize().padding(insets), contentAlignment = Alignment.TopCenter) {
            Column(Modifier.widthIn(max = 680.dp).fillMaxSize()) {
                Row(Modifier.fillMaxWidth().padding(start = 20.dp, end = 12.dp).heightIn(min = 72.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    val chatsLabel = stringResource(R.string.nav_chats)
                    val locale = LocalConfiguration.current.locales[0]
                    val practice = java.util.Locale.forLanguageTag(model.targetLanguage)
                        .getDisplayLanguage(locale).replaceFirstChar { it.titlecase(locale) }
                    Box(Modifier.testTag("inbox-wordmark").clearAndSetSemantics {
                        contentDescription = "Vipi, $chatsLabel"; heading()
                    }) { VipiMark(size = 60) }
                    var choosingLanguage by remember { mutableStateOf(false) }
                    val changeLanguage = stringResource(R.string.chats_practice_language)
                    Box(Modifier.weight(1f)) {
                        Row(Modifier.heightIn(min = 48.dp).testTag("inbox-practice-language")
                            .clickable(role = Role.Button, onClickLabel = changeLanguage) { choosingLanguage = true }
                            .semantics { contentDescription = changeLanguage; stateDescription = practice }
                            .padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(practice, Modifier.weight(1f, fill = false).clearAndSetSemantics { },
                                style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
                                maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Icon(Icons.Outlined.ExpandMore, null, Modifier.size(18.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        LanguageChoiceMenu(choosingLanguage, model.targetLanguage, initialLanguages.filter { it.code != model.knownLanguage },
                            { choosingLanguage = false }, model::selectTarget)
                    }
                    IconButton(onClick = { model.navigate(Screen.SETTINGS) },
                        modifier = Modifier.semantics { contentDescription = settingsLabel }) {
                        val profile = chat?.profile
                        if (profile != null) ContactAvatar(profile.displayName.ifBlank { profile.username }, profile.id)
                        else Icon(Icons.Outlined.AccountCircle, null)
                    }
                }
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = .65f))
                // Reserve the complete 56dp FAB +16dp placement gap +16dp
                // breathing room, so the final row scrolls fully above it.
                LazyColumn(Modifier.fillMaxSize().testTag("inbox-list"), state = listState,
                    contentPadding = PaddingValues(bottom = if (threads.isNotEmpty()) 88.dp else 0.dp)) {
                    if (chat != null && needsRecovery) item("recovery") {
                        Box(Modifier.padding(20.dp)) { DeviceRecoveryCard(chat) { model.authentication.signIn(context, expectedUser = chat.userID) } }
                    } else if (chat != null && needsSignIn) item("authorization") {
                        Box(Modifier.padding(20.dp)) {
                            ReauthenticationCard(chat, model.authentication.busy, model.authentication.error) { expected ->
                                model.authentication.signIn(context, expectedUser = expected)
                            }
                        }
                    }
                    if (loading) item("loading") {
                        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            if (chat?.busy == true) Text(stringResource(R.string.ui_b68710eee013), style = MaterialTheme.typography.titleMedium)
                            Text(model.chatError ?: chat?.notice ?: stringResource(R.string.conversations_local),
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                            if (chat?.busy == true) CircularProgressIndicator(Modifier.size(24.dp))
                            else TextButton(onClick = { scope.launch { model.activateChats() } }) { Text(stringResource(R.string.ui_d8b8392e2c54)) }
                        }
                    } else {
                        if (!needsSignIn && !needsRecovery) chat?.notice?.let { notice ->
                            item("notice") { Text(notice, Modifier.padding(20.dp), color = MaterialTheme.colorScheme.onSurfaceVariant) }
                        }
                        if (threads.isNotEmpty() && chat != null) {
                            items(threads, key = { thread -> thread.peer.toString() }) { thread ->
                                InboxConversationRow(chat, thread) { model.openConversation(thread.peer) }
                            }
                        } else if (!needsRecovery && !needsSignIn) item("empty") {
                            Column(Modifier.fillParentMaxSize().testTag("inbox-empty").padding(24.dp),
                                verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
                                Surface(shape = CircleShape, color = MaterialTheme.colorScheme.primaryContainer) {
                                    Icon(Icons.Outlined.Forum, null, Modifier.padding(18.dp).size(32.dp), tint = MaterialTheme.colorScheme.primary)
                                }
                                Spacer(Modifier.height(18.dp))
                                Text(stringResource(R.string.inbox_find_or_invite), textAlign = TextAlign.Center,
                                    fontSize = 23.sp, lineHeight = 29.sp, fontWeight = FontWeight.SemiBold)
                                Spacer(Modifier.height(16.dp))
                                Button(onClick = newChat, enabled = ready,
                                    modifier = Modifier.heightIn(min = 48.dp).testTag("inbox-compose").semantics { contentDescription = newChatLabel }) {
                                    Text(newChatLabel, style = MaterialTheme.typography.titleMedium)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    }
}

@Composable private fun InboxConversationRow(chat: ChatSession, thread: ChatThread, open: () -> Unit) {
    val name = chat.name(thread.peer)
    val unread = thread.unread > 0
    val locale = LocalConfiguration.current.locales[0]
    val largeText = LocalDensity.current.fontScale >= 1.5f
    val context = LocalContext.current
    val time = thread.latest.createdAt
    val zone = ZoneId.systemDefault()
    val today = LocalDate.now(zone)
    val sentDate = Instant.ofEpochMilli(time).atZone(zone).toLocalDate()
    val dateFlags = when {
        sentDate == today -> DateUtils.FORMAT_SHOW_TIME
        ChronoUnit.DAYS.between(sentDate, today) in 1..6 -> DateUtils.FORMAT_SHOW_WEEKDAY or DateUtils.FORMAT_ABBREV_WEEKDAY
        else -> DateUtils.FORMAT_SHOW_DATE or DateUtils.FORMAT_ABBREV_MONTH or
            (if (sentDate.year == today.year) DateUtils.FORMAT_NO_YEAR else DateUtils.FORMAT_SHOW_YEAR)
    }
    val date = DateUtils.formatDateTime(context, time, dateFlags)
    Row(Modifier.fillMaxWidth().testTag("inbox-row-${thread.peer}").clickable(role = Role.Button, onClick = open)
        .heightIn(min = 80.dp).padding(horizontal = 16.dp, vertical = 11.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
        ContactAvatar(name, thread.peer, diameter = 54.dp)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            val timestamp: @Composable () -> Unit = {
                Text(date, Modifier.testTag("inbox-date-${thread.peer}"), maxLines = 1,
                    style = MaterialTheme.typography.labelMedium, fontSize = 13.sp,
                    color = if (unread) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(name, Modifier.weight(1f), fontSize = 18.sp, lineHeight = 23.sp,
                    fontWeight = if (unread) FontWeight.Bold else FontWeight.Medium,
                    maxLines = if (largeText) 2 else 1, overflow = TextOverflow.Ellipsis)
                if (!largeText) timestamp()
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                if (thread.latest.outgoing) ChatDeliveryIcon(thread.latest.state, deliveryLabel(thread.latest.state))
                Box(Modifier.weight(1f)) { HomeTranslationPreview(chat, thread.latest, unread) }
                if (unread) {
                    val count = NumberFormat.getIntegerInstance(locale).format(thread.unread)
                    val spoken = pluralStringResource(R.plurals.inbox_unread, thread.unread, count)
                    Surface(shape = CircleShape, color = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.testTag("inbox-unread-${thread.peer}").semantics { contentDescription = spoken }) {
                        Box(Modifier.defaultMinSize(minWidth = 23.dp, minHeight = 23.dp).padding(horizontal = 6.dp), contentAlignment = Alignment.Center) {
                            Text(count, Modifier.clearAndSetSemantics { }, fontSize = 13.sp, lineHeight = 17.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
            if (largeText) timestamp()
        }
    }
}
