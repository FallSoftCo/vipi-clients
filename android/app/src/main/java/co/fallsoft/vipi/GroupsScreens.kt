package co.fallsoft.vipi

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.Groups
import androidx.compose.ui.res.stringResource
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.distinctUntilChanged
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.UUID

/** The opt-in debug build opens this route with the signed-in account’s immersion owner. */
@Composable internal fun GroupsNavigator(session: GroupsSession, people: List<ChatProfile>, translation: ConversationTranslation,
    source: String, target: String, changeMode: (ImmersionMode) -> Unit, reviewIdentity: (UUID) -> Unit, onBack: () -> Unit) {
    var route by remember(session.account) { mutableStateOf("home") }
    var selected by remember(session.account) { mutableStateOf<UUID?>(null) }
    val back = { route = if (route in setOf("info", "invite")) "conversation" else "home" }
    BackHandler { if (route == "home") onBack() else back() }
    when (route) {
        "create" -> GroupCreateScreen(session, people, onBack = { route = "home" }, onCreated = { selected = it; route = "conversation" })
        "conversation" -> selected?.let { GroupConversationScreen(session, it, people, translation, source, target, changeMode, onInfo = { route = "info" }, onBack = { route = "home" }) }
        "info" -> selected?.let { GroupInfoScreen(session, it, people, reviewIdentity, onInvite = { route = "invite" }, onLeft = { route = "home" }, onBack = { route = "conversation" }) }
        "invite" -> selected?.let { GroupInviteScreen(session, it, people, onBack = { route = "info" }) }
        else -> GroupsHomeScreen(session, onCreate = { route = "create" }, onOpen = { selected = it; route = "conversation" }, onBack = onBack)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable private fun GroupFrame(title: String, onBack: () -> Unit, action: (@Composable () -> Unit)? = null, content: @Composable (PaddingValues) -> Unit) {
    Scaffold(topBar = { TopAppBar(title = { Text(title, style = MaterialTheme.typography.titleLarge) }, navigationIcon = { TextButton(onClick = onBack) { Text("Back") } }, actions = { action?.invoke() }) }, content = content)
}
@Composable private fun GroupNotice(session: GroupsSession) {
    val scope = rememberCoroutineScope()
    session.notice?.let { Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(it, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite })
        TextButton(onClick = { scope.launch { session.refresh() } }, enabled = !session.busy) { Text("Refresh group") }
    } }
}
@Composable internal fun GroupsHomeScreen(session: GroupsSession, onCreate: () -> Unit, onOpen: (UUID) -> Unit, onBack: () -> Unit) {
    val scope = rememberCoroutineScope(); val revision = session.revision
    LaunchedEffect(session) { session.refresh() }
    GroupFrame("Groups", onBack, action = { TextButton(onClick = onCreate) { Text("Create group") } }) { padding ->
        LazyColumn(Modifier.fillMaxSize().padding(padding), contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
            item { GroupNotice(session) }
            if (session.busy && !session.loaded) item { Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) { CircularProgressIndicator(); Text("Loading groups", style = MaterialTheme.typography.bodyLarge) } }
            if (session.invitations.isNotEmpty()) item { Text("Invitations", style = MaterialTheme.typography.titleLarge) }
            items(session.invitations, key = { "invite:${it.id}" }) { invitation ->
                OutlinedCard(Modifier.fillMaxWidth()) { Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(invitation.title, style = MaterialTheme.typography.titleMedium)
                    Text("You’re invited to join. You’ll receive messages sent after you join; earlier messages stay private.", style = MaterialTheme.typography.bodyLarge)
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Button(onClick = { scope.launch { session.answer(invitation, true) } }, enabled = !session.busy) { Text("Join group") }
                        OutlinedButton(onClick = { scope.launch { session.answer(invitation, false) } }, enabled = !session.busy) { Text("Decline") }
                    }
                } }
            }
            if (session.groups.isEmpty() && !session.busy) item {
                Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    Text("Bring your people together", style = MaterialTheme.typography.headlineMedium)
                    Text("Create a group for up to 16 people, including you. Everyone keeps their own language practice settings.", style = MaterialTheme.typography.bodyLarge)
                    Button(onClick = onCreate) { Text("Create group") }
                }
            }
            items(session.groups.sortedBy { it.title.lowercase() }, key = { it.id }) { group ->
                Card(onClick = { onOpen(group.id) }, modifier = Modifier.fillMaxWidth()) { Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(group.title, style = MaterialTheme.typography.titleLarge)
                    Text("${group.members.size} people${if (GroupsUpgrade.muteDeliveryQualified && session.preferences(group.id).muted) " · Muted" else ""}", style = MaterialTheme.typography.bodyLarge)
                    val unread = session.unread(group.id)
                    if (unread > 0) Text("$unread unread", style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.Bold)
                } }
            }
            if (session.departedGroups.isNotEmpty()) item { Text("Past groups", style = MaterialTheme.typography.titleLarge) }
            items(session.departedGroups, key = { "past:${it.id}" }) { group -> Card(onClick = { onOpen(group.id) }, modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) { Text(group.title, style = MaterialTheme.typography.titleLarge); Text("Left group · Messages saved here", style = MaterialTheme.typography.bodyLarge) }
            } }
            item { TextButton(onClick = { scope.launch { session.refresh() } }, enabled = !session.busy) { Text("Refresh groups") } }
        }
    }
}

@Composable private fun GroupPeoplePicker(people: List<ChatProfile>, account: UUID, occupied: Set<UUID>, selected: Set<UUID>, onChange: (Set<UUID>) -> Unit, onError: (String) -> Unit) {
    var search by remember { mutableStateOf("") }
    OutlinedTextField(search, { search = it }, label = { Text("Search names or usernames") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
    val matches = people.filter { it.id != account && it.id !in occupied && (search.isEmpty() || it.displayName.contains(search, true) || it.username.contains(search, true)) }.sortedBy { it.displayName.lowercase() }
    if (matches.isEmpty()) Text(if (people.isEmpty()) "Add a friend before creating a group." else "No matching people. Try another name or username.", style = MaterialTheme.typography.bodyLarge)
    matches.forEach { person ->
        Surface(onClick = {
            try { onChange(GroupSelection.toggle(person.id, selected, account, occupied)) }
            catch (e: IllegalArgumentException) { onError(e.message ?: "You can choose up to 15 other people.") }
        }, modifier = Modifier.fillMaxWidth().semantics(mergeDescendants = true) { role = Role.Checkbox; stateDescription = if (person.id in selected) "Selected" else "Not selected" }) {
            Row(Modifier.padding(vertical = 12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    Text(person.displayName, style = MaterialTheme.typography.titleMedium)
                    Text("@${person.username}", style = MaterialTheme.typography.bodyLarge)
                }
                Checkbox(person.id in selected, onCheckedChange = null)
            }
        }
    }
}
@Composable internal fun GroupCreateScreen(session: GroupsSession, people: List<ChatProfile>, onBack: () -> Unit, onCreated: (UUID) -> Unit) {
    var name by remember { mutableStateOf(session.pendingCreateTitle() ?: "") }; var selected by remember { mutableStateOf(emptySet<UUID>()) }
    var created by remember { mutableStateOf<UUID?>(null) }; var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    GroupFrame("New group", onBack) { padding ->
        LazyColumn(Modifier.fillMaxSize().padding(padding), contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
            item { OutlinedTextField(name, { name = it }, label = { Text("Group name") }, placeholder = { Text("For example, Weekend friends") }, enabled = created == null && !session.busy, modifier = Modifier.fillMaxWidth()) }
            item { Text("Maximum 16 people", style = MaterialTheme.typography.bodyLarge) }
            item { Text("${selected.size + 1} of 16 people selected, including you", style = MaterialTheme.typography.titleMedium) }
            item { Column(verticalArrangement = Arrangement.spacedBy(12.dp)) { GroupPeoplePicker(people, session.account, emptySet(), selected, { selected = it; error = null }, { error = it }) } }
            item { (error ?: session.notice)?.let { Text(it, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.error) } }
            item { Button(onClick = { scope.launch {
                var current = created?.let(session::group) ?: session.create(name)?.also { created = it.id } ?: return@launch
                for (id in selected.sortedBy(UUID::toString)) {
                    if (!session.invite(current, id)) return@launch
                    selected = selected - id; current = session.group(current.id) ?: return@launch
                }; onCreated(current.id)
            } }, enabled = !session.busy && selected.isNotEmpty() && runCatching { GroupSelection.name(name) }.isSuccess, modifier = Modifier.fillMaxWidth()) { Text(if (created == null) "Create group and invite ${selected.size}" else "Retry remaining invitations") } }
            item { Text("Message text is end-to-end encrypted. Vipi can see the group name, people and invitations.", style = MaterialTheme.typography.bodyLarge) }
        }
    }
}

@Composable internal fun GroupConversationScreen(session: GroupsSession, groupID: UUID, people: List<ChatProfile>, translation: ConversationTranslation,
    source: String, target: String, changeMode: (ImmersionMode) -> Unit, onInfo: () -> Unit, onBack: () -> Unit) {
    val revision = session.revision; val group = session.group(groupID); val messages = session.messages(groupID)
    var text by remember(session.account, groupID) { mutableStateOf(session.preferences(groupID).draft) }
    val scope = rememberCoroutineScope()
    val list = rememberLazyListState()
    val context = LocalContext.current
    val speech = remember(session, groupID, source, target) { SpeechPlayback(context, target, scope) }
    var voiceHelp by remember(speech) { mutableStateOf(false) }
    val audio = remember(translation, speech) { ConversationAutoplay(translation, speech, scope) { voiceHelp = true } }
    val gestures = remember(session, groupID, translation.mode) { FullMessageGestures().also { it.mode = translation.mode } }
    val warmups = remember(source, target) { mapOf(source to "1", target to "1") }
    LaunchedEffect(speech) { speech.prepare(warmups) }
    LaunchedEffect(speech.state) { if (speech.state == SpeechState.READY) voiceHelp = false }
    DisposableEffect(audio) { onDispose { audio.close() } }
    DisposableEffect(speech) { onDispose { speech.close() } }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var foreground by remember { mutableStateOf(lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) }
    DisposableEffect(lifecycle, audio, session, groupID) {
        val owner = Any()
        session.observe(owner) { message ->
            if (message.group == groupID && foreground) {
                val id = message.id
                audio.offerStored(message.renderID) { session.messageOriginal(groupID, id) }
            }
        }
        val observer = LifecycleEventObserver { _, event -> foreground = lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED); if (event == Lifecycle.Event.ON_STOP) { audio.background(); speech.stop(); gestures.held = false } }
        lifecycle.addObserver(observer); onDispose { session.removeObserver(owner); lifecycle.removeObserver(observer); audio.setAutoplayEnabled(false) }
    }
    LaunchedEffect(groupID) { session.refresh() }
    Scaffold(topBar = {
        ConversationHeader(group?.title ?: "Group", groupID, audio.enabled, true,
            onAutoplay = { audio.setAutoplayEnabled(!audio.enabled) },
            mode = translation.mode,
            onMode = {
                audio.background()
                changeMode(if (translation.mode == ImmersionMode.FULL_MESSAGES) ImmersionMode.NEW_WORD else ImmersionMode.FULL_MESSAGES)
            }, minHeight = 56.dp, modifier = Modifier.fillMaxWidth().statusBarsPadding(),
            back = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, stringResource(R.string.nav_back)) } },
            overflow = { IconButton(onClick = onInfo) { Icon(Icons.Outlined.Groups, "Group info") } })
    }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).imePadding()) {
            GroupNotice(session)
            LazyColumn(Modifier.weight(1f).fillMaxWidth().fullMessageGestures(gestures), state = list, contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
                if (messages.isEmpty()) item { Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("Your group starts here", style = MaterialTheme.typography.headlineSmall)
                    Text("Say hello. Invited people can read new messages after they join. Your language practice settings apply only to you.", style = MaterialTheme.typography.bodyLarge)
                } }
                items(session.heldMessages(groupID), key = { "held:${it.routed.envelope.id}" }) { item -> Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("Message waiting for encryption review", style = MaterialTheme.typography.titleMedium)
                    Text("Confirm this sender’s encryption details to open their saved message. It is kept securely on this device.", style = MaterialTheme.typography.bodyLarge)
                    TextButton(onClick = onInfo) { Text("Review sender in Group info") }
                    TextButton(onClick = { session.retryHeld(groupID) }) { Text("Try opening saved message") }
                } }
                items(messages, key = { it.id }) { message ->
                    val name = if (message.sender == session.account) "You" else group?.members?.firstOrNull { it.id == message.sender }?.name ?: people.firstOrNull { it.id == message.sender }?.displayName ?: session.savedSenderName(groupID, message.sender) ?: "Group member"
                    val status = groupDelivery(message)
                    Column(Modifier.fillMaxWidth().background(if (message.sender == session.account) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceContainer, RoundedCornerShape(18.dp)).padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text(name, style = MaterialTheme.typography.titleMedium, modifier = Modifier.semantics { heading() })
                        if (message.delivery == GroupDelivery.WITHHELD) {
                            if (message.withheldReason == "changed") {
                                Text("The people in this group changed before this message arrived. Ask $name to send it again.", style = MaterialTheme.typography.bodyLarge)
                                TextButton(onClick = { text = "$name, could you send your last message again?"; session.draft(groupID, text) }) { Text("Ask sender to resend") }
                            } else {
                                Text("An admin needs to confirm who’s in this group before this message can open. It is saved securely on this device.", style = MaterialTheme.typography.bodyLarge)
                                TextButton(onClick = onInfo) { Text("Review group approval") }
                            }
                        }
                        else FullMessageBubble(message.text, message.renderID, translation, gestures, audio, "$name. $status") { Text(status, style = MaterialTheme.typography.bodyLarge) }
                        if (message.sender == session.account && message.delivery in setOf(GroupDelivery.QUEUED, GroupDelivery.FAILED)) TextButton(onClick = { scope.launch { session.retry(message) } }, enabled = !session.busy) { Text("Retry sending to everyone") }
                        if (message.delivery in setOf(GroupDelivery.MEMBERSHIP_CHANGED, GroupDelivery.IDENTITY_CHANGED)) {
                            Text("This message wasn’t sent. Review Group info, then copy it into a new message when you’re ready.", style = MaterialTheme.typography.bodyLarge)
                            TextButton(onClick = { text = message.text; session.draft(groupID, text) }) { Text("Copy to draft") }
                        }
                    }
                }
            }
            val readable = messages.filter { it.delivery == GroupDelivery.RECEIVED && it.sender != session.account }.map { it.id }.toSet()
            LaunchedEffect(groupID, foreground, list, readable) {
                snapshotFlow { list.layoutInfo.visibleItemsInfo.mapNotNull { it.key as? UUID }.toSet() }.distinctUntilChanged().collect { visible ->
                    if (foreground && visible.isNotEmpty()) session.markRead(groupID, visible)
                }
            }
            if (voiceHelp || speech.state == SpeechState.UNAVAILABLE)
                SpeechPreparationHelp(speech.state, speech.error) { speech.prepare(warmups) }
            if (session.isActive(groupID) && group?.role(session.account) != null) Row(Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(text, { text = it; session.draft(groupID, it) }, label = { Text("Message the group") }, maxLines = 6, modifier = Modifier.weight(1f))
                Button(onClick = { val draft = text; scope.launch { if (session.send(group, draft) && text == draft) text = "" } }, enabled = !session.busy && text.isNotBlank(), modifier = Modifier.heightIn(min = 48.dp)) { Text("Send") }
            } else Text("You’re no longer in this group. Saved messages remain on this device.", style = MaterialTheme.typography.bodyLarge, modifier = Modifier.padding(18.dp))
        }
    }
}
private fun groupDelivery(message: GroupMessage) = when (message.delivery) {
    GroupDelivery.QUEUED -> "Saved on this device · Waiting to send"
    GroupDelivery.ACCEPTED -> "Sent to the group"
    GroupDelivery.FAILED -> "Couldn’t send to everyone"
    GroupDelivery.EXPIRED -> "Not sent · Message expired"
    GroupDelivery.MEMBERSHIP_CHANGED -> "Not sent · Group changed"
    GroupDelivery.IDENTITY_CHANGED -> "Not sent · Encryption review needed"
    GroupDelivery.WITHHELD -> "Held · Membership confirmation needed"
    GroupDelivery.RECEIVED -> DateTimeFormatter.ofLocalizedTime(java.time.format.FormatStyle.SHORT).withZone(ZoneId.systemDefault()).format(Instant.ofEpochMilli(message.createdAt))
}

private data class GroupConfirmation(val title: String, val detail: String, val action: String, val suffix: String, val method: String, val fields: Map<String, String> = emptyMap())
@Composable internal fun GroupInfoScreen(session: GroupsSession, groupID: UUID, people: List<ChatProfile>, reviewIdentity: (UUID) -> Unit, onInvite: () -> Unit, onLeft: () -> Unit, onBack: () -> Unit) {
    val group = session.group(groupID); val revision = session.revision
    var name by remember(groupID) { mutableStateOf(group?.title ?: "") }; var confirmation by remember { mutableStateOf<GroupConfirmation?>(null) }
    var bootstrap by remember { mutableStateOf<GroupPendingControl?>(null) }
    val scope = rememberCoroutineScope()
    GroupFrame("Group info", onBack) { padding ->
        LazyColumn(Modifier.fillMaxSize().padding(padding), contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
            if (group == null) item { Text("You’re no longer a member of this group.", style = MaterialTheme.typography.bodyLarge) }
            if (group != null) {
                if (session.hasRejectedApproval(groupID)) item { Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("An invalid group approval was blocked", style = MaterialTheme.typography.titleLarge)
                    Text("That approval couldn’t change who’s in this group. Your existing messages are still saved. Review the people and their encryption details before continuing.", style = MaterialTheme.typography.bodyLarge)
                    TextButton(onClick = { session.dismissRejectedApproval(groupID) }) { Text("Dismiss this notice") }
                } }
                if (session.pendingChanges(groupID) > 0) item { Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("Saved group change", style = MaterialTheme.typography.titleLarge)
                    session.pendingDescriptions(groupID, people).forEach { Text(it, style = MaterialTheme.typography.titleMedium) }
                    Text("This change is waiting to be confirmed. Continue it before making another change or sending messages.", style = MaterialTheme.typography.bodyLarge)
                    Button(onClick = { scope.launch { session.resumePending(groupID) } }, enabled = !session.busy && !session.recoveryCancelled(groupID)) { Text("Resume saved group change") }
                    GroupRecoveryCard(session, groupID)
                } }
                if (!session.isActive(groupID)) item { Text("You’re no longer in this group. These people and roles describe the last saved roster. Your messages remain available here.", style = MaterialTheme.typography.bodyLarge) }
                if (session.hasMembershipConflict(groupID)) item { Text("Conflicting encrypted group approvals were received. New messages are held. Ask an admin to resolve the group history or create a new group with confirmed identities.", style = MaterialTheme.typography.bodyLarge) }
                item { Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    if (session.isActive(groupID) && group.manages(session.account)) {
                        OutlinedTextField(name, { name = it }, label = { Text("Group name") }, modifier = Modifier.fillMaxWidth())
                        Button(onClick = { scope.launch { session.rename(group, name) } }, enabled = !session.busy && name != group.title && runCatching { GroupSelection.name(name) }.isSuccess) { Text("Save name") }
                    } else Text(group.title, style = MaterialTheme.typography.headlineMedium)
                    if (GroupsUpgrade.muteDeliveryQualified) {
                        Row { Text("Mute this group", style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f)); Switch(session.preferences(groupID).muted, { session.mute(groupID, it) }) }
                        Text("Muted groups keep unread counts. Your device won’t alert you about new messages from this group.", style = MaterialTheme.typography.bodyLarge)
                    }
                    Text("Your language practice settings apply to you alone. Other people can practise different languages in the same conversation.", style = MaterialTheme.typography.bodyLarge)
                    Text("People · ${group.members.size} of 16", style = MaterialTheme.typography.titleLarge)
                } }
                items(session.heldControls(groupID), key = { "held-control:${it.routed.envelope.id}" }) { item -> Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("Group approval waiting for encryption review", style = MaterialTheme.typography.titleLarge)
                    Text("Confirm the inviter’s existing encryption details, then try opening the saved group approval.", style = MaterialTheme.typography.bodyLarge)
                    TextButton(onClick = { reviewIdentity(item.routed.envelope.sender) }) { Text("Review inviter’s encryption details") }
                    TextButton(onClick = { session.retryHeld(groupID) }) { Text("Try opening group approval") }
                } }
                items(session.pendingApprovals(groupID), key = { "approval:${it.id}" }) { control -> Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Text("Confirm group membership", style = MaterialTheme.typography.titleLarge)
                    Text("This approval came through an existing encrypted conversation. Review the inviter’s encryption details and everyone listed below before you confirm.", style = MaterialTheme.typography.bodyLarge)
                    TextButton(onClick = { reviewIdentity(control.sender) }) { Text("Review inviter’s encryption details") }
                    control.transition.members.forEach { person ->
                        val member = group.members.firstOrNull { it.id == person.id }
                        Text((member?.let { "${it.name} · @${it.username}" } ?: person.id.toString()) + " · ${person.role.wire}", style = MaterialTheme.typography.bodyLarge)
                    }
                    if (session.canBootstrap(control)) Button(onClick = { bootstrap = control }) { Text("Confirm these people") }
                    else Text("An earlier group approval is missing. If its original sender is still in this group, ask them to resend it. If they’ve left or changed devices, start a new group after confirming everyone’s encryption details. These messages stay saved here.", style = MaterialTheme.typography.bodyLarge)
                } }
                items(group.members, key = { it.id }) { member ->
                    OutlinedCard(Modifier.fillMaxWidth()) { Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text(member.name + if (member.id == session.account) " (you)" else "", style = MaterialTheme.typography.titleMedium)
                        Text("@${member.username} · ${member.role.wire.replaceFirstChar(Char::uppercase)}", style = MaterialTheme.typography.bodyLarge)
                        if (member.id != session.account) TextButton(onClick = { reviewIdentity(member.id) }) { Text("Encryption details") }
                        if (!session.approved(groupID, member.id) && session.isActive(groupID) && group.manages(session.account) && member.id != session.account) {
                            Text("This person joined, and an existing admin still needs to approve their membership securely.", style = MaterialTheme.typography.bodyLarge)
                            TextButton(onClick = { confirmation = GroupConfirmation("Approve ${member.name} for this group?", "Confirm their encryption details first. Your approval will let everyone send them future group messages.", "Approve membership", "/approve/${member.id}", "POST") }) { Text("Approve this person") }
                        }
                        if (session.isActive(groupID) && group.role(session.account) == GroupRole.OWNER && member.id != session.account) {
                            TextButton(onClick = { confirmation = GroupConfirmation(if (member.role == GroupRole.ADMIN) "Remove admin role?" else "Make ${member.name} an admin?", "Admins can invite people, rename the group and remove members.", "Confirm role change", "/members/${member.id}", "PATCH", mapOf("role" to if (member.role == GroupRole.ADMIN) "member" else "admin")) }) { Text(if (member.role == GroupRole.ADMIN) "Remove admin role" else "Make admin") }
                            TextButton(onClick = { confirmation = GroupConfirmation("Make ${member.name} the owner?", "They’ll manage admin roles and ownership. You’ll become an admin.", "Transfer ownership", "/members/${member.id}", "PATCH", mapOf("role" to "owner")) }) { Text("Transfer ownership") }
                        }
                        if (session.isActive(groupID) && group.removes(session.account, member.id)) TextButton(onClick = { confirmation = GroupConfirmation("Remove ${member.name}?", "They won’t receive future messages. Messages already delivered stay on their device.", "Remove person", "/members/${member.id}", "DELETE") }) { Text("Remove from group", color = MaterialTheme.colorScheme.error) }
                    } }
                }
                if (session.isActive(groupID) && group.manages(session.account)) item { Button(onClick = onInvite, enabled = group.members.size < 16) { Text("Invite people") } }
                if (group.invitations.isNotEmpty()) item { Text("Pending invitations", style = MaterialTheme.typography.titleLarge) }
                items(group.invitations, key = { "pending:${it.id}" }) { invitation -> Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(people.firstOrNull { it.id == invitation.user }?.displayName ?: "Invited person", style = MaterialTheme.typography.titleMedium)
                    Text("Waiting for them to accept", style = MaterialTheme.typography.bodyLarge)
                    if (session.isActive(groupID) && group.manages(session.account)) TextButton(onClick = { confirmation = GroupConfirmation("Cancel this invitation?", "This person won’t be able to join using this invitation.", "Cancel invitation", "/invitations/${invitation.id}", "DELETE") }) { Text("Cancel invitation") }
                } }
                item { Column(verticalArrangement = Arrangement.spacedBy(18.dp)) {
                    Text("Message text is end-to-end encrypted between current devices. Vipi can see the group name, people, roles and invitations. New members don’t receive earlier messages.", style = MaterialTheme.typography.bodyLarge)
                    Text("Removing someone or leaving can’t erase copies already delivered. Blocking a person also leaves groups you share.", style = MaterialTheme.typography.bodyLarge)
                    OutlinedButton(enabled = session.isActive(groupID), onClick = { confirmation = GroupConfirmation("Leave ${group.title}?", (if (session.isActive(groupID) && group.role(session.account) == GroupRole.OWNER) "Transfer ownership to another person before leaving. " else "") + "You’ll stop receiving new messages. Your saved messages remain on this device.", "Leave group", "/leave", "POST") }) { Text("Leave group", color = MaterialTheme.colorScheme.error) }
                } }
            }
            item { GroupNotice(session) }
        }
    }
    confirmation?.let { action -> AlertDialog(onDismissRequest = { confirmation = null }, title = { Text(action.title) }, text = { Text(action.detail, style = MaterialTheme.typography.bodyLarge) }, confirmButton = { TextButton(onClick = {
        confirmation = null; if (group != null) scope.launch { if (action.suffix == "/leave") { if (session.leave(group)) onLeft() } else if (action.suffix.startsWith("/approve/")) session.approveJoin(group, UUID.fromString(action.suffix.removePrefix("/approve/"))) else session.change(group, action.method, action.suffix, action.fields) }
    }) { Text(action.action) } }, dismissButton = { TextButton(onClick = { confirmation = null }) { Text("Cancel") } }) }
    bootstrap?.let { control -> AlertDialog(onDismissRequest = { bootstrap = null }, title = { Text("Trust this inviter and confirm this exact group?") }, text = { Text("Only confirm after reviewing the inviter’s existing encryption details and the complete list of people above.", style = MaterialTheme.typography.bodyLarge) }, confirmButton = { TextButton(onClick = { session.confirmBootstrap(control); bootstrap = null }) { Text("Confirm group membership") } }, dismissButton = { TextButton(onClick = { bootstrap = null }) { Text("Cancel") } }) }
}
@Composable internal fun GroupInviteScreen(session: GroupsSession, groupID: UUID, people: List<ChatProfile>, onBack: () -> Unit) {
    var selected by remember { mutableStateOf(emptySet<UUID>()) }; var notice by remember { mutableStateOf<String?>(null) }; val scope = rememberCoroutineScope()
    GroupFrame("Invite people", onBack) { padding ->
        LazyColumn(Modifier.fillMaxSize().padding(padding), contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
            item { Text("People choose whether to join. They’ll only receive messages sent after they accept.", style = MaterialTheme.typography.bodyLarge) }
            session.group(groupID)?.let { group ->
                item { Column(verticalArrangement = Arrangement.spacedBy(12.dp)) { GroupPeoplePicker(people, session.account, (group.members.filter { it.id != session.account }.map { it.id } + group.invitations.map { it.user }).toSet(), selected, { selected = it; notice = null }, { notice = it }) } }
                item { (notice ?: session.notice)?.let { Text(it, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.error) } }
                item { Button(onClick = { scope.launch {
                    for (id in selected.sortedBy(UUID::toString)) { val current = session.group(groupID) ?: return@launch; if (!session.invite(current, id)) return@launch; selected = selected - id }; onBack()
                } }, enabled = !session.busy && selected.isNotEmpty()) { Text("Invite ${selected.size} people") } }
            }
        }
    }
}
