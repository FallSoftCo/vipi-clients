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
import androidx.compose.ui.res.stringResource
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
    val subscriptions = model.subscriptions
    LaunchedEffect(subscriptions) { subscriptions?.refreshAccess(ifNeeded = true) }
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
        TopAppBar(title = { Text(stringResource(R.string.ui_f173182378d0)) }, navigationIcon = { IconButton(onClick = { model.back() }) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, stringResource(R.string.nav_back)) } },
            actions = { TextButton(onClick = { model.navigate(Screen.BOT_PLAN) }) { Text(stringResource(R.string.ui_ff245b368781)) } })
    }, bottomBar = {
        Column(Modifier.background(MaterialTheme.colorScheme.background).navigationBarsPadding().imePadding().padding(horizontal = 12.dp)) {
            (localError ?: bot.notice)?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
            bot.allowance?.let { allowance ->
                Text(stringResource(R.string.bot_allowance_remaining, java.text.NumberFormat.getIntegerInstance().format(allowance.remaining), java.text.NumberFormat.getIntegerInstance().format(allowance.monthly), DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM).withZone(ZoneId.systemDefault()).format(allowance.resetsAt)), style = MaterialTheme.typography.labelSmall)
            }
            BotPlanAccessGate(subscriptions?.accessCheckState ?: AccessCheckState.UNKNOWN, subscriptions?.access,
                onRetry = { scope.launch { subscriptions?.refreshAccess() } },
                onPlan = { model.navigate(Screen.BOT_PLAN) }) {
            if (!bot.consent) {
                Text(stringResource(R.string.ui_42ed79b95da1), style = MaterialTheme.typography.bodyMedium)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(consentChecked, onCheckedChange = { consentChecked = it })
                    Text(stringResource(R.string.ui_99a6cb8ef035), style = MaterialTheme.typography.bodyMedium)
                }
                Button(onClick = { runCatching { bot.acceptConsent() }.onFailure { localError = context.getString(R.string.bot_consent_save_failed) } }, enabled = consentChecked) { Text(stringResource(R.string.continue_action)) }
            } else {
                Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(bot.draft, { value ->
                        if (value.toByteArray(Charsets.UTF_8).size <= 8192) runCatching { bot.saveDraft(value); localError = null }
                            .onFailure { localError = context.getString(R.string.bot_draft_save_failed) }
                        else localError = context.getString(R.string.bot_message_too_long)
                    }, placeholder = { Text(stringResource(R.string.ui_9f60f6c0e9e0)) }, maxLines = 5, modifier = Modifier.weight(1f).onFocusChanged { composing = it.isFocused }.testTag("bot-message-input"), shape = RoundedCornerShape(24.dp))
                    FilledIconButton(onClick = { scope.launch { bot.send() } }, enabled = !bot.busy && bot.draft.isNotBlank() && bot.allowance?.let { it.available && it.remaining > 0 } == true) {
                        if (bot.busy) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp) else Icon(Icons.Outlined.ArrowUpward, stringResource(R.string.ui_4b34e1b08868))
                    }
                }
                if (bot.allowance == null || bot.allowance?.remaining == 0) TextButton(onClick = { scope.launch { bot.refreshAllowance() } }) { Text(stringResource(R.string.ui_cf0b3e3d47ec)) }
            }
            }
        }
    }) { padding ->
        LazyColumn(state = list, modifier = Modifier.fillMaxSize().padding(padding), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item {
                if (bot.earlierAvailable) TextButton(onClick = { runCatching { bot.earlier() }.onFailure { localError = context.getString(R.string.bot_earlier_open_failed) } }) { Text(stringResource(R.string.ui_561a197a2807)) }
                else Text(stringResource(R.string.ui_cc39ebccb529), style = MaterialTheme.typography.bodySmall)
            }
            items(bot.messages, key = { it.id }) { message ->
                Column(Modifier.fillMaxWidth().background(if (message.role == "user") MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surface, RoundedCornerShape(20.dp)).padding(14.dp)) {
                    ConversationImmersionText(message.text, message.id, immersion, speech, (composing && bot.draft.isNotEmpty()) || list.isScrollInProgress || reportedMessage != null,
                        onVoiceHelp = { runCatching { context.startActivity(Intent("com.android.settings.TTS_SETTINGS")) }.onFailure { localError = context.getString(R.string.speech_settings_open_failed) } },
                        onTranslationSetup = { model.navigate(Screen.LANGUAGE_DOWNLOAD) },
                        onReport = if (message.role == "assistant" && message.requestID != null) ({
                            speech.stop(); reportedMessage = message; reportReason = ""
                            reportText = message.text
                            while (reportText.toByteArray(Charsets.UTF_8).size > 4000) reportText = reportText.dropLast(Character.charCount(reportText.codePointBefore(reportText.length)))
                        }) else null) {
                        Text(if (message.role == "assistant") stringResource(R.string.ui_f173182378d0) else if (message.status == "unconfirmed") stringResource(R.string.ui_c654d70db3ac) else if (message.status == "rejected") stringResource(R.string.ui_e28ba924e405) else stringResource(R.string.ui_08b041935798), style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }
    }
    reportedMessage?.let { message -> AlertDialog(onDismissRequest = { if (!bot.reporting) reportedMessage = null },
        title = { Text(stringResource(R.string.ui_9e0f3ffbf015)) },
        text = { Column(Modifier.heightIn(max = 360.dp).verticalScroll(rememberScrollState())) {
            Text(stringResource(R.string.ui_c48de4e830a9))
            OutlinedTextField(reportText, { reportText = it }, label = { Text(stringResource(R.string.ui_6382f38cc7cc)) }, maxLines = 5)
            listOf("harmful" to "Harmful or offensive", "inaccurate" to "Inaccurate", "other" to "Something else").forEach { (code, title) ->
                Row(verticalAlignment = Alignment.CenterVertically) { RadioButton(reportReason == code, onClick = { reportReason = code }); TextButton(onClick = { reportReason = code }) { Text(title) } }
            }
            if (reportText.toByteArray(Charsets.UTF_8).size > 4000 || !message.text.contains(reportText)) Text(stringResource(R.string.ui_e7be3e288153), style = MaterialTheme.typography.bodySmall)
        } },
        confirmButton = { TextButton(enabled = !bot.reporting && reportReason.isNotEmpty() && reportText.isNotBlank() && message.text.contains(reportText) && reportText.toByteArray(Charsets.UTF_8).size <= 4000,
            onClick = { scope.launch { if (bot.report(message, reportReason, reportText)) reportedMessage = null } }) { Text(if (bot.reporting) stringResource(R.string.ui_b8ed5279e897) else stringResource(R.string.ui_a44d35311325)) } },
        dismissButton = { TextButton(enabled = !bot.reporting, onClick = { reportedMessage = null }) { Text(stringResource(R.string.cancel_action)) } }) }
}

@Composable internal fun BotPlanAccessGate(state: AccessCheckState, access: SubscriptionAccess?,
    onRetry: () -> Unit, onPlan: () -> Unit, content: @Composable () -> Unit) {
    when (state) {
        AccessCheckState.UNKNOWN, AccessCheckState.CHECKING -> Text(stringResource(R.string.ui_ee7fdea20d0b))
        AccessCheckState.ERROR -> {
            Text(stringResource(R.string.ui_541ecffcdb87))
            TextButton(onClick = onRetry) { Text(stringResource(R.string.try_again)) }
        }
        AccessCheckState.LOADED -> if (access?.bot?.verificationUnavailable == true || access?.serverTime == null) {
            Text(stringResource(if (access?.bot?.verificationUnavailable == true) R.string.bot_verification_unavailable else R.string.plan_clock_unavailable))
            TextButton(onClick = onRetry) { Text(stringResource(R.string.try_again)) }
        } else if (access?.active(SubscriptionPlan.BOT_MINI) == true) content()
            else TextButton(onClick = onPlan) { Text(stringResource(R.string.ui_a843a5adb644)) }
    }
}
