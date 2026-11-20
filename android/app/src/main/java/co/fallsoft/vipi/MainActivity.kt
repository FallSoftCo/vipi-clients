package co.fallsoft.vipi

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.ArrowForward
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.boundsInWindow
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLinkStyles
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withLink
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import co.fallsoft.vipi.core.SpeechSpan
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.core.view.WindowCompat

class MainActivity : ComponentActivity() {
    private val model: VipiModel by viewModels()
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        handleCallback(intent)
        if (BuildConfig.DEBUG) PersistenceProbe.start(this, intent.getStringExtra("vipi_storage_probe"))
        if (BuildConfig.DEBUG) {
            when (intent.getStringExtra("vipi_screen")) {
                "welcome" -> model.navigate(Screen.WELCOME)
                "language" -> model.navigate(Screen.LANGUAGE)
                "home" -> model.navigate(Screen.HOME)
                "translation" -> model.navigate(Screen.LANGUAGE_DOWNLOAD)
            }
        }
        if (BuildConfig.DEBUG) {
            val source = intent.getStringExtra("vipi_source")
            val target = intent.getStringExtra("vipi_target")
            if (source in initialLanguages.map { it.code }) model.selectKnown(source!!)
            if (target in initialLanguages.map { it.code } && target != model.knownLanguage) model.selectTarget(target!!)
        }
        setContent { VipiTheme(model.appearance) { VipiApp(model) } }
    }
    override fun onNewIntent(intent: Intent) { super.onNewIntent(intent); setIntent(intent); handleCallback(intent) }
    private fun handleCallback(intent: Intent) {
        if (intent.action == Intent.ACTION_VIEW) intent.data?.let { uri ->
            if (!model.acceptInvitation(uri.toString())) lifecycleScope.launch { model.authentication.complete(uri) }
        }
        if (intent.action == PushDelivery.ACTION) model.openNotification(intent.getStringExtra("notification_peer"))
    }
}

@Composable internal fun VipiTheme(appearance: Appearance, content: @Composable () -> Unit) {
    val dark = appearance == Appearance.DARK || (appearance == Appearance.SYSTEM && isSystemInDarkTheme())
    val activity = generateSequence(LocalContext.current) { context ->
        (context as? android.content.ContextWrapper)?.baseContext?.takeIf { it !== context }
    }.filterIsInstance<android.app.Activity>().firstOrNull()
    SideEffect {
        activity?.let { host -> WindowCompat.getInsetsController(host.window, host.window.decorView).apply {
            isAppearanceLightStatusBars = !dark; isAppearanceLightNavigationBars = !dark
        } }
    }
    val increased = prefersIncreasedContrast()
    val palette = when {
        dark && increased -> VipiPalettes.IncreasedContrastDark
        dark -> VipiPalettes.Dark
        increased -> VipiPalettes.IncreasedContrastLight
        else -> VipiPalettes.Light
    }
    val colors = palette.materialColors(dark)
    MaterialTheme(colorScheme = colors, typography = Typography(
        bodyLarge = androidx.compose.ui.text.TextStyle(fontSize = 18.sp, lineHeight = 27.sp),
        bodyMedium = androidx.compose.ui.text.TextStyle(fontSize = 16.sp, lineHeight = 24.sp),
        bodySmall = androidx.compose.ui.text.TextStyle(fontSize = 14.sp, lineHeight = 20.sp),
        labelLarge = androidx.compose.ui.text.TextStyle(fontSize = 16.sp, lineHeight = 22.sp, fontWeight = FontWeight.SemiBold)
    )) {
        CompositionLocalProvider(LocalVipiPalette provides palette,
            androidx.compose.material3.LocalContentColor provides palette.ink,
            androidx.compose.foundation.text.selection.LocalTextSelectionColors provides
                androidx.compose.foundation.text.selection.TextSelectionColors(palette.focus, palette.practiceFill)) {
            content()
        }
    }
}

@Composable private fun VipiApp(model: VipiModel) {
    LaunchedEffect(model.authentication.userID, model.authentication.signInRevision, model.deletion.active) {
        if (model.deletion.active) model.deletion.resume()
        else model.activateChats()
    }
    if (model.deletion.active) { AccountDeletionProgress(model.deletion, model.authentication) { model.navigate(Screen.WELCOME) }; return }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val syncScope = rememberCoroutineScope()
    DisposableEffect(lifecycle, model.chat) {
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_RESUME) {
            androidx.core.app.NotificationManagerCompat.from(model.getApplication()).cancel(1)
            syncScope.launch { model.chat?.synchronize() }
        } }
        lifecycle.addObserver(observer); onDispose { lifecycle.removeObserver(observer) }
    }
    DisposableEffect(lifecycle, model.chat, model.chat?.ready, model.chat?.needsReauthentication, model.authentication.userID) {
        val chat = model.chat
        val events = chat?.takeIf { it.ready && !it.needsReauthentication && it.userID == model.authentication.userID }?.let {
            model.foregroundEvents(syncScope, it)
        }
        val observer = LifecycleEventObserver { _, event -> when (event) {
            Lifecycle.Event.ON_START -> events?.start()
            Lifecycle.Event.ON_STOP -> events?.stop()
            else -> Unit
        } }
        lifecycle.addObserver(observer)
        if (lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) events?.start()
        onDispose { lifecycle.removeObserver(observer); events?.close() }
    }
    val scrollState = rememberScrollState()
    LaunchedEffect(model.screen) { scrollState.scrollTo(0) }
    val onboarding = model.screen in setOf(Screen.WELCOME, Screen.LANGUAGE, Screen.ACCOUNT)
    val largeText = androidx.compose.ui.platform.LocalDensity.current.fontScale >= 1.5f
    BackHandler(enabled = model.screen != Screen.WELCOME && model.screen != Screen.HOME) { model.back() }
    val inboxScroll = key(model.authentication.userID) { androidx.compose.foundation.lazy.rememberLazyListState() }
    if (model.screen == Screen.HOME) { ChatsInbox(model, inboxScroll); return }
    if (model.screen == Screen.BACKUP && model.chat != null) { HistoryBackupScreen(model.chat!!) { model.back() }; return }
    if (model.screen == Screen.LICENSES) { LegalNoticesScreen { model.back() }; return }
    if (model.screen == Screen.CONVERSATION) {
        val chat = model.chat; val peer = model.selectedPeer
        if (chat != null && peer != null) { FriendConversationScreen(chat, peer, model.knownLanguage, model.targetLanguage,
            onLanguages = { model.navigate(Screen.LANGUAGE_DOWNLOAD) }, onImmersionMode = model::selectImmersionMode, notificationEducation = model.replyNotificationEducation, onNotificationPermission = model::notificationPermissionChanged) { model.back() }; return }
    }
    Scaffold(containerColor = MaterialTheme.colorScheme.background,
        bottomBar = { if (onboarding && !largeText) OnboardingAction(model) }) { padding ->
        Box(Modifier.fillMaxSize().padding(padding).consumeWindowInsets(padding).imePadding(), contentAlignment = Alignment.TopCenter) {
        Column(Modifier.fillMaxHeight().widthIn(max = 680.dp).fillMaxWidth().padding(horizontal = 26.dp).verticalScroll(scrollState), verticalArrangement = Arrangement.spacedBy(if (model.screen == Screen.LANGUAGE) 16.dp else 24.dp)) {
            TopBar(model)
            when (model.screen) {
                Screen.WELCOME -> Welcome(scrollState.isScrollInProgress, model.immersionMode)
                Screen.LANGUAGE -> LanguageSelection(model, scrollState.isScrollInProgress)
                Screen.ACCOUNT -> AccountView()
                Screen.SETTINGS -> SettingsView(model)
                Screen.NEW_CHAT -> NewChatView(model)
                Screen.LANGUAGE_DOWNLOAD -> DownloadView(model)
                Screen.PROFILE -> ProfileSetupScreen(model)
                Screen.DELETE_ACCOUNT -> DeleteAccountScreen { model.beginDeletion() }
                Screen.HOME, Screen.CONVERSATION, Screen.BACKUP, Screen.LICENSES -> Unit
            }
            if (onboarding && largeText) OnboardingAction(model, inScroll = true)
            Spacer(Modifier.height(20.dp))
        }
        }
    }
}

@Composable internal fun VipiMark(size: Int = 36) {
    val art = if (MaterialTheme.colorScheme.background.luminance() < .5f)
        R.drawable.vipi_mark_night else R.drawable.vipi_mark_day
    // Transparent optical artwork follows the selected app appearance. The
    // launcher owns its separate full-bleed asset; no in-app tile or clipping.
    androidx.compose.foundation.Image(painter = androidx.compose.ui.res.painterResource(art),
        contentDescription = null, modifier = Modifier.size(size.dp))
}

@Composable private fun TopBar(model: VipiModel) {
    Row(Modifier.fillMaxWidth().padding(top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
        if (model.screen != Screen.WELCOME) {
            IconButton(onClick = { model.back() }) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, stringResource(R.string.nav_back)) }
        } else if (model.screen == Screen.WELCOME) { VipiMark(34); Spacer(Modifier.width(10.dp)) }
        Text(stringResource(when (model.screen) {
            Screen.NEW_CHAT -> R.string.nav_new_chat
            else -> R.string.ui_2f7e29fbc47d
        }), fontSize = 27.sp, letterSpacing = (-1).sp, fontWeight = FontWeight.SemiBold, maxLines = 1, softWrap = false)
        Spacer(Modifier.weight(1f))
        if (model.screen in setOf(Screen.LANGUAGE, Screen.ACCOUNT)) {
            val fullStep = if (model.screen == Screen.LANGUAGE) stringResource(R.string.ui_00e255330e43) else stringResource(R.string.ui_de6e21a278c4)
            val shortStep = if (model.screen == Screen.LANGUAGE) "1 / 2" else "2 / 2"
            Text(if (androidx.compose.ui.platform.LocalDensity.current.fontScale >= 1.5f) shortStep else fullStep,
                fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.semantics { contentDescription = fullStep })
        }
    }
}

@Composable private fun Heading(eyebrow: String, title: String, detail: String) {
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text(title, fontSize = 34.sp, lineHeight = 39.sp, fontWeight = FontWeight.Bold)
        if (detail.isNotBlank()) Text(detail, fontSize = 18.sp, lineHeight = 27.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable internal fun PrimaryButton(title: String, enabled: Boolean = true, busy: Boolean = false, onClick: () -> Unit) {
    Button(onClick = onClick, enabled = enabled && !busy, shape = RoundedCornerShape(18.dp),
        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary, contentColor = MaterialTheme.colorScheme.onPrimary),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 17.dp), modifier = Modifier.fillMaxWidth()) {
        if (busy) CircularProgressIndicator(Modifier.size(20.dp), color = MaterialTheme.colorScheme.onPrimary, strokeWidth = 2.dp)
        else { Text(title, fontSize = 17.sp, fontWeight = FontWeight.SemiBold); Spacer(Modifier.width(10.dp)); Icon(Icons.AutoMirrored.Outlined.ArrowForward, null, Modifier.size(18.dp)) }
    }
}

@Composable private fun Welcome(scrolling: Boolean, mode: ImmersionMode) {
    Heading("", stringResource(R.string.welcome_title_concise), stringResource(if (mode == ImmersionMode.FULL_MESSAGES) R.string.welcome_detail_full else R.string.welcome_detail_concise))
    ConversationPreview("en", "es", scrolling, mode)
}

@Composable private fun LanguageSelection(model: VipiModel, scrolling: Boolean) {
    var targetMenu by remember { mutableStateOf(false) }
    var knownMenu by remember { mutableStateOf(false) }
    val uiLocale = androidx.compose.ui.platform.LocalConfiguration.current.locales[0]
    fun displayLanguage(code: String): String = java.util.Locale.forLanguageTag(code)
        .getDisplayLanguage(uiLocale).replaceFirstChar { it.titlecase(uiLocale) }
    Heading("", stringResource(R.string.languages_title_concise), "")
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(stringResource(R.string.speak_concise), color = MaterialTheme.colorScheme.onSurfaceVariant, fontWeight = FontWeight.Medium)
        Box {
            Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, RoundedCornerShape(16.dp)).clickable { knownMenu = true }.padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(displayLanguage(model.knownLanguage)); Spacer(Modifier.weight(1f)); Icon(Icons.Outlined.ExpandMore, stringResource(R.string.ui_aae89a15c1be))
            }
            DropdownMenu(expanded = knownMenu, onDismissRequest = { knownMenu = false }) {
                initialLanguages.forEach { language -> DropdownMenuItem(text = { Text(displayLanguage(language.code)) }, onClick = { model.selectKnown(language.code); knownMenu = false }) }
            }
        }
    }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
    Text(stringResource(R.string.learn_concise), color = MaterialTheme.colorScheme.onSurfaceVariant, fontWeight = FontWeight.Medium)
    Box {
        Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, RoundedCornerShape(16.dp)).clickable { targetMenu = true }.padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(displayLanguage(model.targetLanguage)); Spacer(Modifier.weight(1f)); Icon(Icons.Outlined.ExpandMore, stringResource(R.string.ui_0c574552109f))
        }
        DropdownMenu(expanded = targetMenu, onDismissRequest = { targetMenu = false }) {
            initialLanguages.filter { it.code != model.knownLanguage }.forEach { language -> DropdownMenuItem(text = { Text("${displayLanguage(language.code)} · ${language.localName}") }, onClick = { model.selectTarget(language.code); targetMenu = false }) }
        }
    }
    }
    key(model.knownLanguage, model.targetLanguage) { ConversationPreview(model.knownLanguage, model.targetLanguage, scrolling, model.immersionMode) }
}

@Composable private fun AccountView() {
    Heading("", stringResource(R.string.account_title_concise), stringResource(R.string.account_detail_concise))
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Icon(Icons.Outlined.Lock, null, tint = MaterialTheme.colorScheme.primary)
            Text(stringResource(R.string.account_private_title), fontWeight = FontWeight.SemiBold)
        }
        Text(stringResource(R.string.account_private_detail), color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(stringResource(R.string.account_trial_concise), fontWeight = FontWeight.Medium)
    }
}

@Composable private fun OnboardingAction(model: VipiModel, inScroll: Boolean = false) {
    var accepted by rememberSaveable { mutableStateOf(false) }
    val context = LocalContext.current
    val largeText = androidx.compose.ui.platform.LocalDensity.current.fontScale >= 1.5f
    Box(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.background), contentAlignment = Alignment.TopCenter) {
    Column(Modifier.widthIn(max = 680.dp).fillMaxWidth().then(if (inScroll) Modifier else Modifier.navigationBarsPadding()).padding(horizontal = if (inScroll) 0.dp else 26.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        if (model.screen == Screen.ACCOUNT) {
            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp)
                .toggleable(value = accepted, role = Role.Checkbox, onValueChange = { accepted = it }),
                verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = accepted, onCheckedChange = null)
                Text(stringResource(R.string.ui_9ed65d7add5f), fontSize = 16.sp, lineHeight = 24.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            val legalLinks: @Composable () -> Unit = {
                TextButton(onClick = { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://api.mambovipi.app/terms"))) }) { Text(stringResource(R.string.terms_service), fontSize = 15.sp) }
                TextButton(onClick = { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://api.mambovipi.app/privacy"))) }) { Text(stringResource(R.string.privacy_policy), fontSize = 15.sp) }
            }
            if (largeText) Column(verticalArrangement = Arrangement.spacedBy(4.dp)) { legalLinks() }
            else Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) { legalLinks() }
            model.authentication.error?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error) }
        }
        PrimaryButton(when (model.screen) { Screen.WELCOME -> stringResource(R.string.choose_languages); Screen.LANGUAGE -> stringResource(R.string.continue_action); else -> stringResource(R.string.continue_signin) }, enabled = model.screen != Screen.ACCOUNT || accepted, busy = model.authentication.busy) {
            when (model.screen) { Screen.WELCOME -> model.navigate(Screen.LANGUAGE); Screen.LANGUAGE -> model.navigate(Screen.ACCOUNT); else -> model.authentication.signIn(context) }
        }
    }
    }
}

/** Demand only previews intersecting the clipped window. Uses the account's
 * existing owner and encrypted completion cache; opening Chats never waits. */
@Composable internal fun HomeTranslationPreview(chat: ChatSession, message: ChatItem, unread: Boolean) {
    val owner = chat.translations
    val id = message.id.toString()
    var visible by remember(owner, id, message.text) { mutableStateOf(false) }
    DisposableEffect(owner, id, message.text, visible) {
        if (visible && owner != null) { owner.retain(id, message.text); owner.enqueue(id, message.text) }
        onDispose { if (visible) owner?.release(id, message.text) }
    }
    val state = owner?.state(id, message.text)
    val value = state?.value
    val preview = value?.let { it.practiceReading ?: it.practiceText }
        ?: message.text
    Text(preview, maxLines = 2, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
        fontSize = 16.sp, lineHeight = 21.sp,
        fontWeight = if (unread) FontWeight.Medium else FontWeight.Normal,
        color = if (unread) vipiPalette().ink else vipiPalette().secondary,
        modifier = Modifier.testTag("home-message-preview-$id").onGloballyPositioned {
            val bounds = it.boundsInWindow()
            visible = bounds.width > 0f && bounds.height > 0f
        })
}

@Composable private fun NewChatView(model: VipiModel) {
    val context = LocalContext.current
    val keyboard = LocalSoftwareKeyboardController.current
    val form = remember { BringIntoViewRequester() }
    val usernameField = remember { BringIntoViewRequester() }
    var usernameFocused by remember { mutableStateOf(false) }
    val imeBottom = WindowInsets.ime.getBottom(androidx.compose.ui.platform.LocalDensity.current)
    var username by rememberSaveable(model.invitationUsername) { mutableStateOf(model.invitationUsername.orEmpty()) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    LaunchedEffect(error) {
        if (error != null) { withFrameNanos { }; form.bringIntoView() }
    }
    LaunchedEffect(usernameFocused, imeBottom) {
        if (usernameFocused && imeBottom > 0) { withFrameNanos { }; usernameField.bringIntoView() }
    }
    fun findFriend() {
        if (username.isBlank() || busy) return
        val requestedUsername = username
        keyboard?.hide()
        val chat = model.chat
        if (chat == null) error = context.getString(R.string.friends_sign_in_required)
        else {
            busy = true; error = null
            scope.launch {
                try { model.openConversation(chat.find(requestedUsername).id) }
                catch (failure: kotlinx.coroutines.CancellationException) { throw failure }
                catch (failure: Exception) { error = ChatSession.explanation(context, failure) }
                finally { busy = false }
            }
        }
    }
    Text(stringResource(R.string.ui_e131c9a64a5b), style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
    Column(Modifier.fillMaxWidth().bringIntoViewRequester(form), verticalArrangement = Arrangement.spacedBy(24.dp)) {
    OutlinedTextField(value = username, onValueChange = { username = it }, colors = vipiTextFieldColors(), label = { Text(stringResource(R.string.ui_8a74ed1b7a84)) }, singleLine = true,
        keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None, autoCorrectEnabled = false, imeAction = ImeAction.Search),
        keyboardActions = KeyboardActions(onSearch = { findFriend() }),
        modifier = Modifier.fillMaxWidth().bringIntoViewRequester(usernameField).onFocusChanged { usernameFocused = it.isFocused }, shape = RoundedCornerShape(16.dp))
    PrimaryButton(stringResource(R.string.ui_ba6e8c9b0c3e), enabled = username.isNotBlank(), busy = busy, onClick = ::findFriend)
    error?.let { Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    }
    InviteFriendButton(model)
}

@Composable private fun SettingsView(model: VipiModel) {
    val context = LocalContext.current
    val uri = androidx.compose.ui.platform.LocalUriHandler.current
    var linkError by remember { mutableStateOf<String?>(null) }
    Text(stringResource(R.string.settings_title), fontSize = 34.sp)
    InviteFriendButton(model)
    Text(stringResource(R.string.ui_339484dc1f78), fontWeight = FontWeight.SemiBold)
    if (model.chat?.profile != null) TextButton(onClick = { model.navigate(Screen.BACKUP) }) { Text(stringResource(R.string.ui_24f13e3dc8e4)) }
    if (model.chat?.ready == true) NotificationSetup()
    LanguageSettingsLink(languageName(model.targetLanguage)) { model.navigate(Screen.LANGUAGE_DOWNLOAD) }
    Text(stringResource(R.string.ui_3907fa7f8072), fontWeight = FontWeight.SemiBold)
    Appearance.entries.forEach { appearance ->
        Row(Modifier.fillMaxWidth().clickable { model.changeAppearance(appearance) }.semantics { role = Role.RadioButton; selected = model.appearance == appearance }, verticalAlignment = Alignment.CenterVertically) {
            RadioButton(selected = model.appearance == appearance, onClick = { model.changeAppearance(appearance) }); Text(stringResource(when (appearance) { Appearance.SYSTEM -> R.string.appearance_system; Appearance.LIGHT -> R.string.appearance_light; Appearance.DARK -> R.string.appearance_dark }))
        }
    }
    Text(stringResource(R.string.ui_380f81884c22), fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    TextButton(onClick = { model.navigate(Screen.LICENSES) }) { Text(stringResource(R.string.ui_2a6b4d12ccfb)) }
    Row {
        listOf(R.string.nav_terms to "terms", R.string.nav_privacy to "privacy", R.string.nav_help to "help").forEach { (title, path) ->
            TextButton(onClick = { runCatching { uri.openUri("https://api.mambovipi.app/$path") }.onFailure { linkError = context.getString(R.string.settings_page_open_failed) } }) { Text(stringResource(title)) }
        }
    }
    linkError?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
    if (model.chat?.profile != null && model.authentication.canLinkFallsoft) {
        TextButton(onClick = { model.beginFallsoftLink(context) }, enabled = !model.authentication.busy && model.chat?.eventDevice() != null,
            modifier = Modifier.testTag("fallsoft-link-start")) {
            Text(stringResource(R.string.fallsoft_link_title))
        }
        Text(stringResource(R.string.fallsoft_link_detail), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        model.authentication.error?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error) }
    }
    if (model.chat?.profile != null) TextButton(onClick = { model.navigate(Screen.DELETE_ACCOUNT) }) {
        Text(stringResource(R.string.ui_a2e20a335700), color = MaterialTheme.colorScheme.error)
    }
}

@Composable private fun DownloadView(model: VipiModel) { LanguageDownloadsScreen(model) }

@Composable internal fun LanguageSettingsLink(language: String, onClick: () -> Unit) {
    val modifier = Modifier.fillMaxWidth().clickable(onClick = onClick).padding(vertical = 14.dp)
    if (androidx.compose.ui.platform.LocalDensity.current.fontScale >= 1.3f) {
        Column(modifier) { Text(stringResource(R.string.ui_e7cde359a05e)); Text(language, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    } else {
        Row(modifier) { Text(stringResource(R.string.ui_e7cde359a05e)); Spacer(Modifier.weight(1f)); Text(language, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    }
}

@Composable private fun InviteFriendButton(model: VipiModel) {
    val username = model.chat?.profile?.username ?: return
    val context = LocalContext.current
    val inviteTitle = stringResource(R.string.nav_invite)
    var error by remember { mutableStateOf(false) }
    TextButton(onClick = {
        val invitation = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, context.getString(R.string.invite_share_text, username, "https://api.mambovipi.app/invite/$username"))
        }
        try { context.startActivity(Intent.createChooser(invitation, inviteTitle)); error = false }
        catch (_: android.content.ActivityNotFoundException) { error = true }
    }) { Text(stringResource(R.string.nav_invite)) }
    Text(stringResource(R.string.public_username, username), style = MaterialTheme.typography.bodySmall)
    if (error) Text(stringResource(R.string.ui_e5bd91ac481d), style = MaterialTheme.typography.bodySmall)
}
