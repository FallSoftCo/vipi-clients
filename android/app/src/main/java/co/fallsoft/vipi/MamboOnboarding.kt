package co.fallsoft.vipi

import android.content.Intent
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.ArrowForward
import androidx.compose.material.icons.outlined.ArrowUpward
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect

internal const val VIPI_HOME_URL = "https://mambovipi.app"

/** Platform-neutral invite copy: the homepage resolves the user's store on the
 * receiving device, so an Android share never assumes an iPhone or vice versa. */
internal fun mamboShareMessage(context: android.content.Context): String =
    context.getString(R.string.mambo_share_text, VIPI_HOME_URL)

private enum class OnboardingPage {
    NAME,
    LANGUAGES,
    SHALLOW,
    DEEP,
    LISTEN,
    INVITE,
    PRIVACY,
}

/** Seven single-purpose pages that use the real local translator before an
 * account is required. The typed message is transient and never enters chat history. */
@Composable internal fun MamboOnboarding(model: VipiModel) {
    var page by rememberSaveable { mutableIntStateOf(0) }
    var draft by rememberSaveable { mutableStateOf("") }
    var sentMessage by rememberSaveable { mutableStateOf<String?>(null) }
    var sentRevision by rememberSaveable { mutableIntStateOf(0) }
    var accountSheet by rememberSaveable { mutableStateOf(false) }
    val pages = OnboardingPage.entries
    val current = pages[page.coerceIn(pages.indices)]
    val waterClock = rememberWaterClock()
    val sceneMode = if (current in setOf(OnboardingPage.DEEP, OnboardingPage.LISTEN))
        ImmersionMode.FULL_MESSAGES else ImmersionMode.NEW_WORD
    BackHandler(enabled = (page > 0 || model.replayingGuide) && !accountSheet) {
        if (page > 0) page-- else model.closeGuide()
    }
    Box(Modifier.fillMaxSize().testTag("mambo-background")) {
        ConversationWaterScene(sceneMode, model.animateConversationBackground, Modifier.matchParentSize(),
            waterClock, plainBackground = prefersIncreasedContrast())
        Column(Modifier.fillMaxSize().safeDrawingPadding().imePadding()) {
            OnboardingHeader(page, pages.size, showBack = page > 0 || model.replayingGuide,
                onBack = { if (page > 0) page-- else model.closeGuide() })
            Box(Modifier.weight(1f)) {
                when (current) {
                    OnboardingPage.NAME -> MamboNamePage(onContinue = { page++ },
                        onSignIn = if (model.authentication.userID == null) ({ accountSheet = true }) else null)
                    OnboardingPage.LANGUAGES -> MamboLanguagesPage(model, onContinue = { page++ })
                    OnboardingPage.SHALLOW -> MamboShallowPage(model, draft, onDraft = { draft = it },
                        sentMessage = sentMessage, sentRevision = sentRevision,
                        onSend = { text ->
                            draft = ""
                            sentMessage = text
                            sentRevision++
                        }, onContinue = { page++ })
                    OnboardingPage.DEEP -> MamboTranslationPage(model, sentMessage, sentRevision,
                        ImmersionMode.FULL_MESSAGES, onContinue = { page++ })
                    OnboardingPage.LISTEN -> MamboListenPage(model, sentMessage, sentRevision,
                        onContinue = { page++ })
                    OnboardingPage.INVITE -> MamboInvite(onContinue = { page++ })
                    OnboardingPage.PRIVACY -> MamboPrivacy(onContinue = {
                        if (model.authentication.userID != null || model.replayingGuide) model.finishGuide()
                        else accountSheet = true
                    })
                }
            }
        }
        if (accountSheet) MamboAccountSheet(model, signIn = current == OnboardingPage.NAME, onDismiss = { accountSheet = false },
            onContinueWithoutAccount = {
                accountSheet = false
                if (current != OnboardingPage.NAME) model.continueWithoutAccount()
            })
    }
}

@Composable private fun OnboardingHeader(page: Int, pageCount: Int, showBack: Boolean, onBack: () -> Unit) {
    Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically) {
        if (showBack) {
            IconButton(onClick = onBack) {
                Icon(Icons.AutoMirrored.Outlined.ArrowBack, stringResource(R.string.nav_back))
            }
        } else {
            VipiMark(34)
            Spacer(Modifier.width(10.dp))
        }
        Text(stringResource(R.string.mambo_wordmark), fontSize = 25.sp, fontWeight = FontWeight.SemiBold,
            letterSpacing = (-.7).sp)
        Spacer(Modifier.weight(1f))
        Text(stringResource(R.string.mambo_step, page + 1, pageCount), fontSize = 14.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.testTag("mambo-step"))
    }
}

@Composable private fun OnboardingCopy(title: String, detail: String, titleSize: TextUnit = 36.sp,
                                      titleTag: String? = null) {
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text(title, fontSize = titleSize, lineHeight = titleSize, fontWeight = FontWeight.Bold,
            modifier = Modifier.semantics { heading() }.then(titleTag?.let { Modifier.testTag(it) } ?: Modifier))
        Text(detail, fontSize = 19.sp, lineHeight = 28.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable private fun MamboNamePage(onContinue: () -> Unit, onSignIn: (() -> Unit)?) {
    Column(Modifier.fillMaxSize().padding(horizontal = 24.dp)) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.Center) {
            OnboardingCopy(stringResource(R.string.mambo_heading), stringResource(R.string.mambo_meaning),
                titleSize = 46.sp, titleTag = "mambo-name-title")
        }
        PrimaryButton(stringResource(R.string.continue_action), onClick = onContinue)
        if (onSignIn != null) TextButton(onClick = onSignIn, modifier = Modifier.fillMaxWidth()
            .heightIn(min = 48.dp).testTag("mambo-sign-in")) { Text(stringResource(R.string.inbox_sign_in)) }
        Spacer(Modifier.height(12.dp))
    }
}

@Composable private fun MamboLanguagesPage(model: VipiModel, onContinue: () -> Unit) {
    LaunchedEffect(model.knownLanguage, model.targetLanguage) { model.prepareSelectedPair() }
    Column(Modifier.fillMaxSize().padding(horizontal = 24.dp)) {
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(28.dp)) {
            Spacer(Modifier.height(8.dp))
            OnboardingCopy(stringResource(R.string.mambo_languages_heading),
                stringResource(R.string.mambo_languages_detail), titleTag = "mambo-languages-title")
            Column(verticalArrangement = Arrangement.spacedBy(18.dp)) {
                LanguageField(stringResource(R.string.mambo_i_speak), model.knownLanguage,
                    translationLanguages, "mambo-known-language") { model.selectKnown(it) }
                LanguageField(stringResource(R.string.mambo_im_learning), model.targetLanguage,
                    translationLanguages.filter { it.code != model.knownLanguage }, "mambo-target-language") {
                    model.selectTarget(it)
                }
            }
            Spacer(Modifier.height(4.dp))
        }
        PrimaryButton(stringResource(R.string.continue_action), onClick = onContinue)
        Spacer(Modifier.height(12.dp))
    }
}

@Composable private fun MamboShallowPage(model: VipiModel, draft: String, onDraft: (String) -> Unit,
                                        sentMessage: String?, sentRevision: Int, onSend: (String) -> Unit,
                                        onContinue: () -> Unit) {
    val scroll = rememberScrollState()
    val keyboard = LocalSoftwareKeyboardController.current
    val focus = LocalFocusManager.current
    fun send() { draft.trim().takeIf { it.isNotEmpty() }?.let(onSend) }
    Column(Modifier.fillMaxSize()) {
        Column(Modifier.weight(1f).verticalScroll(scroll).padding(horizontal = 18.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Spacer(Modifier.height(4.dp))
            OnboardingCopy(stringResource(R.string.mambo_shallow_heading),
                stringResource(R.string.mambo_shallow_detail), titleTag = "mambo-shallow-title")
            Spacer(Modifier.height(6.dp))
            if (sentMessage != null) {
                key(sentMessage, sentRevision, model.knownLanguage, model.targetLanguage) {
                    MamboOutgoingMessage(sentMessage, model.knownLanguage, model.targetLanguage,
                        ImmersionMode.NEW_WORD, model.translationFactory, scroll.value > 0)
                }
            }
        }
        Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedTextField(value = draft, onValueChange = onDraft,
                modifier = Modifier.weight(1f).testTag("mambo-message-input"),
                placeholder = { Text(stringResource(R.string.mambo_type_message)) },
                minLines = 1, maxLines = 4, shape = RoundedCornerShape(24.dp),
                colors = vipiTextFieldColors(),
                keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions = androidx.compose.foundation.text.KeyboardActions(onSend = {
                    send(); keyboard?.hide(); focus.clearFocus()
                }))
            FilledIconButton(onClick = { send(); keyboard?.hide(); focus.clearFocus() },
                enabled = draft.isNotBlank(), modifier = Modifier.size(48.dp).testTag("mambo-send")) {
                Icon(Icons.Outlined.ArrowUpward, stringResource(R.string.mambo_send))
            }
        }
        if (sentMessage != null) {
            Box(Modifier.fillMaxWidth().padding(horizontal = 18.dp)) {
                PrimaryButton(stringResource(R.string.continue_action), onClick = onContinue)
            }
        }
        Spacer(Modifier.height(12.dp))
    }
}

@Composable private fun MamboTranslationPage(model: VipiModel, message: String?, revision: Int,
                                            mode: ImmersionMode, onContinue: () -> Unit) {
    val scroll = rememberScrollState()
    Column(Modifier.fillMaxSize().padding(horizontal = 18.dp)) {
        Column(Modifier.weight(1f).verticalScroll(scroll), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Spacer(Modifier.height(4.dp))
            OnboardingCopy(stringResource(R.string.mambo_deep_heading),
                stringResource(R.string.mambo_deep_detail, languageName(model.targetLanguage)),
                titleTag = "mambo-deep-title")
            Spacer(Modifier.height(6.dp))
            if (message != null) {
                key(message, revision, model.knownLanguage, model.targetLanguage) {
                    MamboOutgoingMessage(message, model.knownLanguage, model.targetLanguage,
                        mode, model.translationFactory, scroll.value > 0)
                }
            }
            Spacer(Modifier.height(4.dp))
        }
        PrimaryButton(stringResource(R.string.continue_action), onClick = onContinue)
        Spacer(Modifier.height(12.dp))
    }
}

@Composable private fun MamboListenPage(model: VipiModel, message: String?, revision: Int,
                                        onContinue: () -> Unit) {
    val scroll = rememberScrollState()
    val targetName = languageName(model.targetLanguage)
    Column(Modifier.fillMaxSize().padding(horizontal = 18.dp)) {
        Column(Modifier.weight(1f).verticalScroll(scroll), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Spacer(Modifier.height(4.dp))
            OnboardingCopy(stringResource(R.string.mambo_listen_heading),
                stringResource(R.string.mambo_listen_detail, targetName), titleTag = "mambo-listen-title")
            Spacer(Modifier.height(6.dp))
            if (message != null) {
                key(message, revision, model.knownLanguage, model.targetLanguage) {
                    MamboOutgoingMessage(message, model.knownLanguage, model.targetLanguage,
                        ImmersionMode.FULL_MESSAGES, model.translationFactory, scroll.value > 0)
                }
            }
            Spacer(Modifier.height(4.dp))
        }
        PrimaryButton(stringResource(R.string.continue_action), onClick = onContinue)
        Spacer(Modifier.height(12.dp))
    }
}

@Composable private fun MamboInvite(onContinue: () -> Unit) {
    val context = LocalContext.current
    val shareText = mamboShareMessage(context)
    var shareError by remember { mutableStateOf(false) }
    val share = {
        val send = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, shareText)
        }
        try {
            context.startActivity(Intent.createChooser(send, context.getString(R.string.mambo_share)))
            shareError = false
        } catch (_: Exception) { shareError = true }
    }
    Column(Modifier.fillMaxSize().padding(horizontal = 24.dp)) {
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(28.dp)) {
            Spacer(Modifier.height(8.dp))
            OnboardingCopy(stringResource(R.string.mambo_invite_heading),
                stringResource(R.string.mambo_invite_detail), titleTag = "mambo-invite-title")
            Spacer(Modifier.height(4.dp))
        }
        if (shareError) Text(stringResource(R.string.mambo_share_failed), color = MaterialTheme.colorScheme.error)
        Button(onClick = share, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp).testTag("mambo-share"),
            shape = RoundedCornerShape(18.dp), contentPadding = PaddingValues(horizontal = 20.dp, vertical = 17.dp)) {
            Icon(Icons.Outlined.Share, null, Modifier.size(20.dp))
            Spacer(Modifier.width(10.dp))
            Text(stringResource(R.string.mambo_share), fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
        }
        TextButton(onClick = onContinue, modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp).testTag("mambo-invite-continue")) {
            Text(stringResource(R.string.continue_action), fontSize = 16.sp, fontWeight = FontWeight.Medium)
            Spacer(Modifier.width(8.dp))
            Icon(Icons.AutoMirrored.Outlined.ArrowForward, null, Modifier.size(18.dp))
        }
        Spacer(Modifier.height(10.dp))
    }
}

@Composable private fun MamboPrivacy(onContinue: () -> Unit) {
    Column(Modifier.fillMaxSize().padding(horizontal = 24.dp)) {
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(28.dp)) {
            Spacer(Modifier.height(8.dp))
            OnboardingCopy(stringResource(R.string.mambo_privacy_heading),
                stringResource(R.string.mambo_encryption), titleTag = "mambo-privacy-title")
            Text(stringResource(R.string.mambo_closing), fontSize = 16.sp, lineHeight = 24.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(4.dp))
        }
        PrimaryButton(stringResource(R.string.mambo_start), onClick = onContinue)
        Spacer(Modifier.height(12.dp))
    }
}

@Composable private fun LanguageField(label: String, code: String, options: List<VipiLanguage>,
                                     tag: String, onSelect: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(label, fontSize = 15.sp, fontWeight = FontWeight.Medium,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        Box {
            OutlinedButton(onClick = { expanded = true }, modifier = Modifier.fillMaxWidth().testTag(tag),
                shape = RoundedCornerShape(16.dp), contentPadding = PaddingValues(horizontal = 16.dp, vertical = 15.dp)) {
                Text(languageLabel(code),
                    Modifier.weight(1f), fontSize = 17.sp,
                    textAlign = androidx.compose.ui.text.style.TextAlign.Start)
                Icon(Icons.Outlined.ExpandMore, null)
            }
            DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                options.forEach { language ->
                    DropdownMenuItem(text = { Text(languageLabel(language.code)) },
                        onClick = { onSelect(language.code); expanded = false })
                }
            }
        }
    }
}

private class MamboTryItTranslations(context: android.content.Context, text: String, source: String,
                                     target: String, translator: LanguageTranslation) : AutoCloseable {
    private val owners = ImmersionMode.entries.associateWith { mode ->
        ConversationTranslation(context, source, target, translator = translator, mode = mode,
            language = object : MessageTranslationLanguage {
                override suspend fun identify(text: String): String = source
                override fun close() = Unit
            })
    }
    operator fun get(mode: ImmersionMode) = owners.getValue(mode)
    override fun close() = owners.values.forEach { it.close() }
}

@Composable private fun MamboOutgoingMessage(text: String, source: String, target: String, mode: ImmersionMode,
                                            factory: (() -> LanguageTranslation)?, scrolling: Boolean) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val translator = remember(source, target) { factory?.invoke() ?: LocalTranslation() }
    val owners = remember(text, source, target, translator) { MamboTryItTranslations(context, text, source, target, translator) }
    val translation = owners[mode]
    val gestures = remember(owners, mode) { FullMessageGestures().also { it.mode = mode } }
    val speech = remember(source, target) { SpeechPlayback(context, target, scope) }
    val audio = remember(translation, speech) { ConversationAutoplay(translation, speech, scope) {} }
    val messageID = remember(text, source, target) { "mambo-try-${text.hashCode()}-$source-$target" }
    val timestamp = remember(messageID) { System.currentTimeMillis() }
    val locale = androidx.compose.ui.platform.LocalConfiguration.current.locales[0]
    val warmups = remember(source, target) { mapOf(source to "1", target to "1") }
    LaunchedEffect(speech) { speech.prepare(warmups) }
    LaunchedEffect(mode, scrolling) { gestures.mode = mode; if (scrolling) gestures.held = false }
    LifecycleEventEffect(Lifecycle.Event.ON_STOP) { audio.background() }
    DisposableEffect(audio) { onDispose { audio.close() } }
    DisposableEffect(owners, speech, translator) {
        onDispose { owners.close(); speech.close(); translator.close() }
    }
    ConversationMessageRow(outgoing = true,
        modifier = Modifier.fullMessageGestures(gestures).testTag("mambo-message-bubble")) {
        FullMessageBubble(text, messageID, translation, gestures, audio) {
            ChatMessageMetadata("accepted", timestamp, true, locale, "mambo-message-meta")
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable internal fun MamboAccountSheet(model: VipiModel, signIn: Boolean, onDismiss: () -> Unit,
                                           onContinueWithoutAccount: () -> Unit) {
    val context = LocalContext.current
    val sheetState = rememberBottomSheetState(initialValue = SheetValue.Hidden,
        enabledValues = setOf(SheetValue.Hidden, SheetValue.Expanded))
    var accepted by rememberSaveable { mutableStateOf(false) }
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 24.dp).padding(bottom = 20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text(stringResource(if (signIn) R.string.inbox_sign_in else R.string.mambo_account_title), fontSize = 27.sp, lineHeight = 33.sp,
                fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurface,
                modifier = Modifier.semantics { heading() })
            Text(stringResource(R.string.mambo_account_detail), fontSize = 17.sp, lineHeight = 25.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp)
                .toggleable(value = accepted, role = Role.Checkbox, onValueChange = { accepted = it })
                .testTag("mambo-terms"), verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = accepted, onCheckedChange = null)
                Text(stringResource(R.string.mambo_terms_agree), fontSize = 16.sp, lineHeight = 24.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                TextButton(onClick = { openUrl(context, "https://mambovipi.app/terms.html") }) {
                    Text(stringResource(R.string.terms_service))
                }
                TextButton(onClick = { openUrl(context, "https://mambovipi.app/privacy.html") }) {
                    Text(stringResource(R.string.privacy_policy))
                }
            }
            model.authentication.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            Button(onClick = { model.authentication.signIn(context) }, enabled = accepted && !model.authentication.busy,
                modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp).testTag("mambo-create-account"),
                shape = RoundedCornerShape(18.dp)) {
                if (model.authentication.busy) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                else Text(stringResource(if (signIn) R.string.inbox_sign_in else R.string.mambo_create_account), fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
            }
            TextButton(onClick = onContinueWithoutAccount,
                modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("mambo-not-now")) {
                Text(stringResource(R.string.mambo_not_now), color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

private fun openUrl(context: android.content.Context, url: String) {
    runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }
}

private fun languageLabel(code: String): String {
    val name = languageName(code)
    val localName = translationLanguages.firstOrNull { it.code == code }?.localName ?: code
    return if (name.equals(localName, ignoreCase = true)) name else "$name · $localName"
}

