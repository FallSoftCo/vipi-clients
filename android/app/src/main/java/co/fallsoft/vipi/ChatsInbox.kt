package co.fallsoft.vipi

import android.text.format.DateUtils
import androidx.compose.foundation.BorderStroke
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
import androidx.compose.ui.graphics.compositeOver
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.text.NumberFormat
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.temporal.ChronoUnit
import kotlinx.coroutines.launch

@Composable
internal fun ChatsInbox(model: VipiModel, listState: LazyListState, waterClock: WaterClock) {
    val chat = model.chat
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var accountSheet by androidx.compose.runtime.saveable.rememberSaveable { mutableStateOf(false) }
    val threads = chat?.threads.orEmpty()
    val groups = chat?.takeIf { it.userID == model.authentication.userID }?.groups
    val activeGroups =
        remember(groups, groups?.groups) {
            if (groups == null) emptyList()
            else groups.groups.filter { it.role(groups.account) != null }
        }
    var summaries by
        remember(groups) { mutableStateOf(emptyMap<java.util.UUID, Pair<GroupMessage?, Int>>()) }
    LaunchedEffect(groups, activeGroups, groups?.revision) {
        if (groups != null && activeGroups.isNotEmpty()) {
            // Older histories build their encrypted summary once, outside the UI thread.
            summaries =
                kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
                    activeGroups.associate { it.id to groups.store.inboxSummary(it.id) }
                }
        }
    }
    val groupRows =
        remember(activeGroups, summaries) {
            activeGroups.map { group ->
                InboxGroup(group, summaries[group.id]?.first, summaries[group.id]?.second ?: 0)
            }
        }
    val rows =
        remember(threads, groupRows) {
            (threads.map { InboxEntry.Direct(it) } + groupRows).sortedWith(
                compareByDescending<InboxEntry> { it.time }.thenBy { it.key }
            )
        }
    val groupStreaks =
        streakCounts(chat?.streakVault, true, groupRows.map { it.group.id }, groups?.revision ?: 0)
    val streaks =
        streakCounts(chat?.streakVault, false, threads.map { it.peer }, chat?.revision ?: 0)
    val ready = chat?.ready == true
    val needsRecovery = chat?.needsDeviceRecovery == true
    val needsSignIn = chat?.needsReauthentication == true
    val loading =
        model.authentication.userID != null &&
            !needsRecovery &&
            !needsSignIn &&
            (!ready || model.chatError != null)
    val newChat = { model.navigate(Screen.NEW_CHAT) }
    val canCompose =
        ready && !needsRecovery && !needsSignIn && chat.userID == model.authentication.userID
    val newChatLabel = stringResource(R.string.nav_new_chat)
    // The action belongs to the conversation pane on expanded/folded widths.
    // The outer canvas still covers the complete edge-to-edge window.
    Box(
        Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background),
        contentAlignment = Alignment.TopCenter,
    ) {
        ConversationWaterScene(
            model.immersionMode,
            model.animateConversationBackground,
            Modifier.matchParentSize(),
            waterClock,
            plainBackground = prefersIncreasedContrast(),
            listSurface = true,
        )
        Scaffold(
            modifier = Modifier.widthIn(max = 680.dp).fillMaxSize(),
            containerColor = androidx.compose.ui.graphics.Color.Transparent,
            contentWindowInsets = WindowInsets.safeDrawing,
            floatingActionButtonPosition = FabPosition.End,
            floatingActionButton = {
                if (canCompose) NewChatFab(newChat)
                else if (rows.isNotEmpty())
                    FloatingActionButton(
                        onClick = { if (ready) newChat() },
                        containerColor =
                            if (ready) MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.surfaceVariant,
                        contentColor =
                            if (ready) MaterialTheme.colorScheme.onPrimary
                            else MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier =
                            Modifier.testTag("inbox-compose").semantics {
                                contentDescription = newChatLabel
                                if (!ready) disabled()
                            },
                    ) {
                        Icon(Icons.Outlined.Edit, null)
                    }
            },
        ) { insets ->
            Box(Modifier.fillMaxSize().padding(insets), contentAlignment = Alignment.TopCenter) {
                Column(Modifier.widthIn(max = 680.dp).fillMaxSize()) {
                    ChatsHeader(model)
                    if (canCompose) FeedbackInvitation(chat, model.feedbackSession)
                    HorizontalDivider(
                        color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = .65f)
                    )
                    // Reserve the complete 56dp FAB +16dp placement gap +16dp
                    // breathing room, so the final row scrolls fully above it.
                    LazyColumn(
                        Modifier.fillMaxSize().testTag("inbox-list"),
                        state = listState,
                        contentPadding =
                            PaddingValues(
                                bottom = if (rows.isNotEmpty() || canCompose) 88.dp else 0.dp
                            ),
                    ) {
                        if (chat != null && needsRecovery)
                            item("recovery") {
                                Box(Modifier.padding(20.dp)) {
                                    DeviceRecoveryCard(chat) {
                                        model.authentication.signIn(
                                            context,
                                            expectedUser = chat.userID,
                                        )
                                    }
                                }
                            }
                        else if (chat != null && needsSignIn)
                            item("authorization") {
                                Box(Modifier.padding(20.dp)) {
                                    ReauthenticationCard(
                                        chat,
                                        model.authentication.busy,
                                        model.authentication.error,
                                    ) { expected ->
                                        model.authentication.signIn(
                                            context,
                                            expectedUser = expected,
                                        )
                                    }
                                }
                            }
                        if (loading)
                            item("loading") {
                                Column(
                                    Modifier.padding(20.dp),
                                    verticalArrangement = Arrangement.spacedBy(8.dp),
                                ) {
                                    if (chat?.busy == true)
                                        Text(
                                            stringResource(R.string.ui_b68710eee013),
                                            style = MaterialTheme.typography.titleMedium,
                                        )
                                    Text(
                                        model.chatError
                                            ?: chat?.notice
                                            ?: stringResource(R.string.conversations_local),
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                    if (chat?.busy == true)
                                        CircularProgressIndicator(Modifier.size(24.dp))
                                    else
                                        TextButton(
                                            onClick = { scope.launch { model.activateChats() } }
                                        ) {
                                            Text(stringResource(R.string.ui_d8b8392e2c54))
                                        }
                                }
                            }
                        else {
                            if (!needsSignIn && !needsRecovery)
                                chat?.notice?.let { notice ->
                                    item("notice") {
                                        Text(
                                            notice,
                                            Modifier.padding(20.dp),
                                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        )
                                    }
                                }
                            if (rows.isNotEmpty() && chat != null) {
                                items(rows, key = { it.key }) { row ->
                                    when (row) {
                                        is InboxEntry.Direct ->
                                            InboxConversationRow(
                                                chat,
                                                row.thread,
                                                streaks[row.thread.peer] ?: 0,
                                            ) {
                                                model.openConversation(row.thread.peer)
                                            }
                                        is InboxGroup ->
                                            InboxRow(
                                                row.group.id,
                                                row.group.title,
                                                row.unread,
                                                row.latest?.createdAt,
                                                groupStreaks[row.group.id] ?: 0,
                                                true,
                                                { model.openInboxGroup(row.group.id) },
                                            ) {
                                                row.latest?.let { message ->
                                                    InboxMessagePreview(
                                                        chat,
                                                        ConversationRef.Group(row.group.id),
                                                        message.renderID,
                                                        message.text,
                                                        row.unread > 0,
                                                    )
                                                }
                                                    ?: Text(
                                                        stringResource(R.string.groups_title),
                                                        color =
                                                            MaterialTheme.colorScheme
                                                                .onSurfaceVariant,
                                                    )
                                            }
                                    }
                                }
                            } else if (model.authentication.userID == null)
                                item("account") {
                                    Column(
                                        Modifier.fillParentMaxSize()
                                            .testTag("inbox-account")
                                            .padding(24.dp),
                                        verticalArrangement = Arrangement.Center,
                                        horizontalAlignment = Alignment.CenterHorizontally,
                                    ) {
                                        Surface(
                                            shape = CircleShape,
                                            color = MaterialTheme.colorScheme.primaryContainer,
                                        ) {
                                            Icon(
                                                Icons.Outlined.AccountCircle,
                                                null,
                                                Modifier.padding(18.dp).size(32.dp),
                                                tint = MaterialTheme.colorScheme.primary,
                                            )
                                        }
                                        Spacer(Modifier.height(18.dp))
                                        val invited = model.invitationUsername
                                        val heading =
                                            if (invited == null)
                                                stringResource(R.string.inbox_account_required)
                                            else
                                                stringResource(
                                                    R.string.inbox_invited_account,
                                                    invited,
                                                )
                                        Text(
                                            heading,
                                            textAlign = TextAlign.Center,
                                            fontSize = 23.sp,
                                            lineHeight = 29.sp,
                                            fontWeight = FontWeight.SemiBold,
                                        )
                                        Spacer(Modifier.height(10.dp))
                                        Text(
                                            stringResource(R.string.inbox_account_detail),
                                            textAlign = TextAlign.Center,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        )
                                        Spacer(Modifier.height(20.dp))
                                        Button(
                                            onClick = { accountSheet = true },
                                            modifier =
                                                Modifier.heightIn(min = 48.dp)
                                                    .testTag("inbox-sign-in"),
                                        ) {
                                            Text(
                                                stringResource(R.string.inbox_sign_in),
                                                style = MaterialTheme.typography.titleMedium,
                                            )
                                        }
                                    }
                                }
                            else if (!needsRecovery && !needsSignIn)
                                item("empty") {
                                    Column(
                                        Modifier.fillParentMaxSize()
                                            .testTag("inbox-empty")
                                            .padding(24.dp),
                                        verticalArrangement = Arrangement.Center,
                                        horizontalAlignment = Alignment.CenterHorizontally,
                                    ) {
                                        Surface(
                                            shape = CircleShape,
                                            color = MaterialTheme.colorScheme.primaryContainer,
                                        ) {
                                            Icon(
                                                Icons.Outlined.Forum,
                                                null,
                                                Modifier.padding(18.dp).size(32.dp),
                                                tint = MaterialTheme.colorScheme.primary,
                                            )
                                        }
                                        Spacer(Modifier.height(18.dp))
                                        Text(
                                            stringResource(R.string.inbox_find_or_invite),
                                            textAlign = TextAlign.Center,
                                            fontSize = 23.sp,
                                            lineHeight = 29.sp,
                                            fontWeight = FontWeight.SemiBold,
                                        )
                                        if (!canCompose) Spacer(Modifier.height(16.dp))
                                        if (!canCompose)
                                            Button(
                                                onClick = newChat,
                                                enabled = ready,
                                                modifier =
                                                    Modifier.heightIn(min = 48.dp)
                                                        .testTag("inbox-compose")
                                                        .semantics {
                                                            contentDescription = newChatLabel
                                                        },
                                            ) {
                                                Text(
                                                    newChatLabel,
                                                    style = MaterialTheme.typography.titleMedium,
                                                )
                                            }
                                    }
                                }
                        }
                    }
                }
            }
        }
    }
    if (accountSheet)
        MamboAccountSheet(
            model,
            signIn = true,
            onDismiss = { accountSheet = false },
            onContinueWithoutAccount = { accountSheet = false },
        )
}

@Composable
private fun ChatsHeader(model: VipiModel) {
    val locale = LocalConfiguration.current.locales[0]
    val practice =
        java.util.Locale.forLanguageTag(model.targetLanguage)
            .getDisplayLanguage(locale)
            .replaceFirstChar { it.titlecase(locale) }
    val chatsLabel = stringResource(R.string.nav_chats)
    val settingsLabel = stringResource(R.string.nav_settings)
    val changeLanguage = stringResource(R.string.chats_practice_language)
    val textStyle = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold)
    val measurer = rememberTextMeasurer()
    val textWidth =
        with(LocalDensity.current) {
            (measurer.measure(practice, textStyle, softWrap = false).size.width + 1).toDp()
        }
    val capsulePadding = 14.dp
    val chevron = 18.dp
    val gap = 4.dp
    val labelWidth = textWidth + capsulePadding * 2 + gap + chevron
    var choosingLanguage by
        androidx.compose.runtime.saveable.rememberSaveable { mutableStateOf(false) }
    val colors = MaterialTheme.colorScheme
    val languageControl: @Composable () -> Unit = {
        Box(contentAlignment = Alignment.Center) {
            Surface(
                shape = CircleShape,
                color = colors.primary.copy(alpha = .10f).compositeOver(colors.surface),
                contentColor = colors.primary,
                border = BorderStroke(1.dp, colors.primary.copy(alpha = .32f)),
            ) {
                Row(
                    Modifier.testTag("inbox-practice-language")
                        .clickable(role = Role.Button, onClickLabel = changeLanguage) {
                            choosingLanguage = true
                        }
                        .semantics {
                            contentDescription = changeLanguage
                            stateDescription = practice
                        }
                        .heightIn(min = 48.dp)
                        .padding(horizontal = capsulePadding, vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(gap),
                ) {
                    Text(
                        practice,
                        Modifier.weight(1f, fill = false)
                            .width(textWidth)
                            .testTag("inbox-practice-text"),
                        style = textStyle,
                        textAlign = TextAlign.Center,
                    )
                    Icon(Icons.Outlined.ExpandMore, null, Modifier.size(chevron))
                }
            }
            if (choosingLanguage)
                LanguageChoiceMenu(
                    true,
                    model.targetLanguage,
                    rememberPracticeOptions().targets(model.knownLanguage, model.targetLanguage),
                    { choosingLanguage = false },
                    model::selectTarget,
                )
        }
    }
    BoxWithConstraints(Modifier.fillMaxWidth().padding(horizontal = 16.dp)) {
        // Reserve the larger flank on both sides of the actual center, including the gap.
        val flank = 60.dp + 8.dp
        val inlineWidth = maxWidth - flank * 2
        val inline = labelWidth <= inlineWidth
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Box(Modifier.fillMaxWidth().heightIn(min = if (inline) 72.dp else 60.dp)) {
                Box(
                    Modifier.align(Alignment.CenterStart)
                        .testTag("inbox-wordmark")
                        .clearAndSetSemantics {
                            contentDescription = "Vipi, $chatsLabel"
                            heading()
                        }
                ) {
                    VipiMark(size = 60)
                }
                IconButton(
                    onClick = { model.navigate(Screen.SETTINGS) },
                    modifier =
                        Modifier.align(Alignment.CenterEnd).semantics {
                            contentDescription = settingsLabel
                        },
                ) {
                    val profile = model.chat?.profile
                    if (profile != null)
                        ContactAvatar(profile.displayName.ifBlank { profile.username }, profile.id)
                    else Icon(Icons.Outlined.AccountCircle, null)
                }
                if (inline)
                    Box(Modifier.align(Alignment.Center).widthIn(max = inlineWidth)) {
                        languageControl()
                    }
            }
            if (!inline) Box(Modifier.padding(bottom = 8.dp)) { languageControl() }
        }
    }
}

@Composable
private fun InboxConversationRow(
    chat: ChatSession,
    thread: ChatThread,
    streak: Int,
    open: () -> Unit,
) {
    InboxRow(
        thread.peer,
        chat.name(thread.peer),
        thread.unread,
        thread.latest.createdAt,
        streak,
        false,
        open,
    ) {
        if (thread.latest.outgoing)
            ChatDeliveryIcon(thread.latest.state, deliveryLabel(thread.latest.state))
        HomeTranslationPreview(chat, thread.peer, thread.latest, thread.unread > 0)
    }
}

private sealed interface InboxEntry {
    val time: Long?
    val key: String

    data class Direct(val thread: ChatThread) : InboxEntry {
        override val time
            get() = thread.latest.createdAt

        override val key
            get() = thread.peer.toString()
    }
}

private data class InboxGroup(
    val group: GroupSnapshot,
    val latest: GroupMessage?,
    val unread: Int,
) : InboxEntry {
    override val time
        get() = latest?.createdAt

    override val key
        get() = "group-${group.id}"
}

@Composable
private fun InboxRow(
    id: java.util.UUID,
    name: String,
    unreadCount: Int,
    time: Long?,
    streak: Int,
    group: Boolean,
    open: () -> Unit,
    preview: @Composable () -> Unit,
) {
    val unread = unreadCount > 0
    val locale = LocalConfiguration.current.locales[0]
    val largeText = LocalDensity.current.fontScale >= 1.5f
    val context = LocalContext.current
    val date = time?.let { time ->
        val zone = ZoneId.systemDefault()
        val today = LocalDate.now(zone)
        val sentDate = Instant.ofEpochMilli(time).atZone(zone).toLocalDate()
        val dateFlags =
            when {
                sentDate == today -> DateUtils.FORMAT_SHOW_TIME
                ChronoUnit.DAYS.between(sentDate, today) in 1..6 ->
                    DateUtils.FORMAT_SHOW_WEEKDAY or DateUtils.FORMAT_ABBREV_WEEKDAY
                else ->
                    DateUtils.FORMAT_SHOW_DATE or
                        DateUtils.FORMAT_ABBREV_MONTH or
                        (if (sentDate.year == today.year) DateUtils.FORMAT_NO_YEAR
                        else DateUtils.FORMAT_SHOW_YEAR)
            }
        DateUtils.formatDateTime(context, time, dateFlags)
    }
    Row(
        Modifier.fillMaxWidth()
            .testTag(if (group) "inbox-group-row-$id" else "inbox-row-$id")
            .clickable(role = Role.Button, onClick = open)
            .heightIn(min = 80.dp)
            .padding(horizontal = 16.dp, vertical = 11.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        if (group)
            Surface(
                Modifier.size(54.dp),
                shape = CircleShape,
                color = MaterialTheme.colorScheme.secondaryContainer,
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(Icons.Outlined.Forum, stringResource(R.string.groups_title))
                }
            }
        else ContactAvatar(name, id, diameter = 54.dp)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            val timestamp: @Composable () -> Unit = {
                if (date != null)
                    Text(
                        date,
                        Modifier.testTag("inbox-date-$id"),
                        maxLines = 1,
                        style = MaterialTheme.typography.labelMedium,
                        fontSize = 13.sp,
                        color =
                            if (unread) MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.onSurfaceVariant,
                    )
            }
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Row(
                    Modifier.weight(1f),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    Text(
                        name,
                        Modifier.weight(1f, fill = false),
                        fontSize = 18.sp,
                        lineHeight = 23.sp,
                        fontWeight = if (unread) FontWeight.Bold else FontWeight.Medium,
                        maxLines = if (largeText) 2 else 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    ChatStreakBadge(streak, group = group)
                }
                if (!largeText) timestamp()
            }
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(5.dp),
            ) {
                Row(
                    Modifier.weight(1f),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(5.dp),
                ) {
                    preview()
                }
                if (unread) {
                    val count = NumberFormat.getIntegerInstance(locale).format(unreadCount)
                    val spoken = pluralStringResource(R.plurals.inbox_unread, unreadCount, count)
                    Surface(
                        shape = CircleShape,
                        color = MaterialTheme.colorScheme.primary,
                        modifier =
                            Modifier.testTag("inbox-unread-$id").semantics {
                                contentDescription = spoken
                            },
                    ) {
                        Box(
                            Modifier.defaultMinSize(minWidth = 23.dp, minHeight = 23.dp)
                                .padding(horizontal = 6.dp),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text(
                                count,
                                Modifier.clearAndSetSemantics {},
                                fontSize = 13.sp,
                                lineHeight = 17.sp,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                    }
                }
            }
            if (largeText) timestamp()
        }
    }
}
