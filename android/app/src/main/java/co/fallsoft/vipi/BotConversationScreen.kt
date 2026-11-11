package co.fallsoft.vipi

import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.ArrowUpward
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.launch
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle

@OptIn(ExperimentalMaterial3Api::class)
@Composable internal fun BotConversationScreen(model: VipiModel, bot: BotSession) {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val owner = LocalLifecycleOwner.current
    val immersion = remember(bot, model.knownLanguage, model.targetLanguage, model.density) { ConversationImmersion(context, model.knownLanguage, model.targetLanguage, model.density, familiarity = bot.familiarity) }
    val speech = remember(bot, model.knownLanguage, model.targetLanguage) { SpeechPlayback(context, model.knownLanguage, model.targetLanguage, scope) }
    val warmups = remember(immersion) {
        val example = ConversationExamples.result(context, model.knownLanguage, model.targetLanguage)
        mapOf(model.knownLanguage to example.original, model.targetLanguage to example.translation)
    }
    var composing by remember { mutableStateOf(false) }
    var consentChecked by remember { mutableStateOf(false) }
    var localError by remember { mutableStateOf<String?>(null) }
    var reportedMessage by remember { mutableStateOf<BotMessage?>(null) }
    var reportText by remember { mutableStateOf("") }
    var reportReason by remember { mutableStateOf("") }
    val list = rememberLazyListState()
    val access = model.subscriptions?.access?.active(SubscriptionPlan.BOT_MINI) == true
    LaunchedEffect(bot) { bot.refreshAllowance() }
    LaunchedEffect(immersion) { immersion.checkDownloads() }
    LaunchedEffect(speech) { speech.prepare(warmups) }
    LaunchedEffect(bot.messages.lastOrNull()?.id) { if (bot.messages.isNotEmpty()) list.scrollToItem(bot.messages.size) }
    DisposableEffect(owner, immersion, speech) {
        val listener = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) speech.stop()
            if (event == Lifecycle.Event.ON_RESUME) { scope.launch { bot.refreshAllowance(); immersion.checkDownloads() }; speech.prepare(warmups) }
        }
        owner.lifecycle.addObserver(listener)
        onDispose { owner.lifecycle.removeObserver(listener); immersion.close(); speech.close() }
    }
    Scaffold(topBar = {
        TopAppBar(title = { Text("vBot") }, navigationIcon = { IconButton(onClick = { model.back() }) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, "Back") } },
            actions = { TextButton(onClick = { model.navigate(Screen.BOT_PLAN) }) { Text("Bot mini") } })
    }, bottomBar = {
        Column(Modifier.background(MaterialTheme.colorScheme.background).navigationBarsPadding().imePadding().padding(horizontal = 12.dp)) {
            (localError ?: bot.notice)?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
            bot.allowance?.let { allowance ->
                Text("${allowance.remaining} of ${allowance.monthly} replies left · resets ${DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM).withZone(ZoneId.systemDefault()).format(allowance.resetsAt)}", style = MaterialTheme.typography.labelSmall)
            }
            if (!access) TextButton(onClick = { model.navigate(Screen.BOT_PLAN) }) { Text("View or restore Bot mini") }
            else if (!bot.consent) {
                Text("Messages you send here and recent vBot conversation context go to Vipi and DeepSeek for replies. This is a service chat, not an end-to-end encrypted conversation with a friend. Friend chats are never included.", style = MaterialTheme.typography.bodyMedium)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(consentChecked, onCheckedChange = { consentChecked = it })
                    Text("I understand and want to chat with vBot.", style = MaterialTheme.typography.bodyMedium)
                }
                Button(onClick = { runCatching { bot.acceptConsent() }.onFailure { localError = "Your choice couldn’t be saved. Please try again." } }, enabled = consentChecked) { Text("Continue") }
            } else {
                Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(bot.draft, { value ->
                        if (value.toByteArray(Charsets.UTF_8).size <= 8192) runCatching { bot.saveDraft(value); localError = null }
                            .onFailure { localError = "Your draft couldn’t be saved. Please try again." }
                        else localError = "This message is too long. Send a shorter message."
                    }, placeholder = { Text("Message vBot") }, maxLines = 5, modifier = Modifier.weight(1f).onFocusChanged { composing = it.isFocused }.testTag("bot-message-input"), shape = RoundedCornerShape(24.dp))
                    FilledIconButton(onClick = { scope.launch { bot.send() } }, enabled = !bot.busy && bot.draft.isNotBlank() && bot.allowance?.let { it.available && it.remaining > 0 } == true) {
                        if (bot.busy) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp) else Icon(Icons.Outlined.ArrowUpward, "Send to vBot")
                    }
                }
                if (bot.allowance == null || bot.allowance?.remaining == 0) TextButton(onClick = { scope.launch { bot.refreshAllowance() } }) { Text("Refresh allowance") }
            }
        }
    }) { padding ->
        LazyColumn(state = list, modifier = Modifier.fillMaxSize().padding(padding), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item {
                if (bot.earlierAvailable) TextButton(onClick = { runCatching { bot.earlier() }.onFailure { localError = "Earlier messages couldn’t be opened." } }) { Text("Earlier messages") }
                else Text("Ask vBot a question or talk about your day. vBot is a chatbot and can make mistakes; check important details.", style = MaterialTheme.typography.bodySmall)
            }
            items(bot.messages, key = { it.id }) { message ->
                Column(Modifier.fillMaxWidth().background(if (message.role == "user") MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surface, RoundedCornerShape(20.dp)).padding(14.dp)) {
                    ConversationImmersionText(message.text, message.id, immersion, speech, (composing && bot.draft.isNotEmpty()) || list.isScrollInProgress || reportedMessage != null,
                        onVoiceHelp = { runCatching { context.startActivity(Intent("com.android.settings.TTS_SETTINGS")) }.onFailure { localError = "Speech settings couldn’t open." } },
                        onTranslationSetup = { model.navigate(Screen.LANGUAGE_DOWNLOAD) },
                        onReport = if (message.role == "assistant" && message.requestID != null) ({
                            speech.stop(); reportedMessage = message; reportReason = ""
                            reportText = message.text
                            while (reportText.toByteArray(Charsets.UTF_8).size > 4000) reportText = reportText.dropLast(Character.charCount(reportText.codePointBefore(reportText.length)))
                        }) else null) {
                        Text(if (message.role == "assistant") "vBot" else if (message.status == "unconfirmed") "You · reply unconfirmed" else if (message.status == "rejected") "You · request not accepted" else "You", style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }
    }
    reportedMessage?.let { message -> AlertDialog(onDismissRequest = { if (!bot.reporting) reportedMessage = null },
        title = { Text("Report this vBot reply") },
        text = { Column(Modifier.heightIn(max = 360.dp).verticalScroll(rememberScrollState())) {
            Text("Only the selected reply text and reason go to Fallible Software for review. Friend conversations aren’t included. Reports are kept for up to 30 days.")
            OutlinedTextField(reportText, { reportText = it }, label = { Text("Selected reply text") }, maxLines = 5)
            listOf("harmful" to "Harmful or offensive", "inaccurate" to "Inaccurate", "other" to "Something else").forEach { (code, title) ->
                Row(verticalAlignment = Alignment.CenterVertically) { RadioButton(reportReason == code, onClick = { reportReason = code }); TextButton(onClick = { reportReason = code }) { Text(title) } }
            }
            if (reportText.toByteArray(Charsets.UTF_8).size > 4000 || !message.text.contains(reportText)) Text("Choose a shorter excerpt from this reply.", style = MaterialTheme.typography.bodySmall)
        } },
        confirmButton = { TextButton(enabled = !bot.reporting && reportReason.isNotEmpty() && reportText.isNotBlank() && message.text.contains(reportText) && reportText.toByteArray(Charsets.UTF_8).size <= 4000,
            onClick = { scope.launch { if (bot.report(message, reportReason, reportText)) reportedMessage = null } }) { Text(if (bot.reporting) "Sending…" else "Send report") } },
        dismissButton = { TextButton(enabled = !bot.reporting, onClick = { reportedMessage = null }) { Text("Cancel") } }) }
}
