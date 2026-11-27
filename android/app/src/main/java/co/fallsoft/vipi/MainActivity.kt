package co.fallsoft.vipi

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.layout.boundsInWindow
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLinkStyles
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withLink
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.view.WindowCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.lifecycleScope
import co.fallsoft.vipi.core.SpeechSpan
import java.util.UUID
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private val model: VipiModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        // The invitation is already persisted or was consumed by this activity. Recreating it
        // must not reopen a friend the user has left. Newly delivered links still use onNewIntent.
        if (
            savedInstanceState == null ||
                FriendInvitationLink.username(intent.dataString.orEmpty()) == null
        ) {
            handleCallback(intent)
        }
        if (BuildConfig.DEBUG)
            PersistenceProbe.start(this, intent.getStringExtra("vipi_storage_probe"))
        if (BuildConfig.DEBUG) {
            when (intent.getStringExtra("vipi_screen")) {
                "welcome" -> model.navigate(Screen.WELCOME)
                "language" -> model.navigate(Screen.LANGUAGE)
                "tutorial" -> {
                    model.navigate(Screen.LANGUAGE)
                    model.openTutorial()
                }
                "home" -> model.navigate(Screen.HOME)
                "translation" -> model.navigate(Screen.LANGUAGE_DOWNLOAD)
            }
        }
        if (BuildConfig.DEBUG) {
            val source = intent.getStringExtra("vipi_source")
            val target = intent.getStringExtra("vipi_target")
            source?.let(model::selectKnown)
            target?.let(model::selectTarget)
        }
        setContent {
            VipiTheme(model.appearance) {
                androidx.compose.runtime.CompositionLocalProvider(
                    LocalAvatarChat provides model.chat
                ) {
                    VipiApp(model)
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleCallback(intent)
    }

    private fun handleCallback(intent: Intent) {
        if (intent.action == Intent.ACTION_VIEW)
            intent.data?.let { uri ->
                if (!model.acceptInvitation(uri.toString()))
                    lifecycleScope.launch { model.authentication.complete(uri) }
            }
        if (intent.action == PushDelivery.ACTION)
            model.openNotification(
                intent.getStringExtra("notification_peer"),
                intent.getStringExtra("notification_account"),
            )
    }
}

@Composable
internal fun VipiTheme(appearance: Appearance, content: @Composable () -> Unit) {
    val dark =
        appearance == Appearance.DARK || (appearance == Appearance.SYSTEM && isSystemInDarkTheme())
    val activity =
        generateSequence(LocalContext.current) { context ->
                (context as? android.content.ContextWrapper)?.baseContext?.takeIf { it !== context }
            }
            .filterIsInstance<android.app.Activity>()
            .firstOrNull()
    SideEffect {
        activity?.let { host ->
            WindowCompat.getInsetsController(host.window, host.window.decorView).apply {
                isAppearanceLightStatusBars = !dark
                isAppearanceLightNavigationBars = !dark
            }
        }
    }
    val increased = prefersIncreasedContrast()
    val palette =
        when {
            dark && increased -> VipiPalettes.IncreasedContrastDark
            dark -> VipiPalettes.Dark
            increased -> VipiPalettes.IncreasedContrastLight
            else -> VipiPalettes.Light
        }
    val colors = palette.materialColors(dark)
    MaterialTheme(
        colorScheme = colors,
        typography =
            Typography(
                bodyLarge =
                    androidx.compose.ui.text.TextStyle(fontSize = 18.sp, lineHeight = 27.sp),
                bodyMedium =
                    androidx.compose.ui.text.TextStyle(fontSize = 16.sp, lineHeight = 24.sp),
                bodySmall =
                    androidx.compose.ui.text.TextStyle(fontSize = 14.sp, lineHeight = 20.sp),
                labelLarge =
                    androidx.compose.ui.text.TextStyle(
                        fontSize = 16.sp,
                        lineHeight = 22.sp,
                        fontWeight = FontWeight.SemiBold,
                    ),
            ),
    ) {
        CompositionLocalProvider(
            LocalVipiPalette provides palette,
            androidx.compose.material3.LocalContentColor provides palette.ink,
            androidx.compose.foundation.text.selection.LocalTextSelectionColors provides
                androidx.compose.foundation.text.selection.TextSelectionColors(
                    palette.focus,
                    palette.practiceFill,
                ),
        ) {
            content()
        }
    }
}

@Composable
private fun VipiApp(model: VipiModel) {
    LaunchedEffect(
        model.authentication.userID,
        model.authentication.signInRevision,
        model.deletion.active,
    ) {
        if (model.deletion.active) model.deletion.resume() else model.activateChats()
    }
    if (model.deletion.active) {
        AccountDeletionProgress(model.deletion, model.authentication) {
            model.navigate(Screen.WELCOME)
        }
        return
    }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val syncScope = rememberCoroutineScope()
    DisposableEffect(model) {
        val process = androidx.lifecycle.ProcessLifecycleOwner.get().lifecycle
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) model.newForegroundSession()
        }
        process.addObserver(observer)
        onDispose { process.removeObserver(observer) }
    }
    DisposableEffect(lifecycle, model.chat) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                androidx.core.app.NotificationManagerCompat.from(model.getApplication()).cancel(1)
                syncScope.launch { model.chat?.synchronize() }
            }
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }
    DisposableEffect(
        lifecycle,
        model.chat,
        model.chat?.ready,
        model.chat?.needsReauthentication,
        model.authentication.userID,
    ) {
        val chat = model.chat
        val events =
            chat
                ?.takeIf {
                    it.ready &&
                        !it.needsReauthentication &&
                        it.userID == model.authentication.userID
                }
                ?.let {
                    model.foregroundEvents(syncScope, it)
                }
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_START -> events?.start()
                Lifecycle.Event.ON_STOP -> events?.stop()
                else -> Unit
            }
        }
        lifecycle.addObserver(observer)
        if (lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) events?.start()
        onDispose {
            lifecycle.removeObserver(observer)
            events?.close()
        }
    }
    val scrollState = rememberScrollState()
    LaunchedEffect(model.screen) { scrollState.scrollTo(0) }
    val onboarding =
        model.screen in setOf(Screen.WELCOME, Screen.LANGUAGE, Screen.TUTORIAL, Screen.ACCOUNT)
    val largeText = androidx.compose.ui.platform.LocalDensity.current.fontScale >= 1.5f
    BackHandler(enabled = model.screen != Screen.WELCOME && model.screen != Screen.HOME) {
        model.back()
    }
    if (model.screen == Screen.WELCOME) {
        MamboOnboarding(model)
        return
    }
    val inboxScroll =
        key(model.authentication.userID) {
            androidx.compose.foundation.lazy.rememberLazyListState()
        }
    val waterClock = rememberWaterClock()
    if (model.screen == Screen.NEW_CHAT) {
        NewChatView(model)
        return
    }
    if (model.screen == Screen.HOME) {
        ChatsInbox(model, inboxScroll, waterClock)
        return
    }
    if (model.screen == Screen.GROUPS) {
        val chat = model.chat
        val groups = chat?.groups
        if (
            groups != null &&
                chat.ready &&
                !chat.needsReauthentication &&
                chat.userID == model.authentication.userID
        ) {
            GroupsNavigator(
                groups,
                chat.contacts.values.filter { it.id !in chat.blockedPeers },
                source = model.knownLanguage,
                defaultTarget = model.targetLanguage,
                translationFor = { chat.translationFor(it) },
                targetFor = { chat.targetLanguage(it) },
                usesDefaultFor = { chat.usesDefaultLanguage(it) },
                onLanguage = { ref, code -> model.selectConversationLanguage(ref, code) },
                onUseDefaultLanguage = { model.useDefaultConversationLanguage(it) },
                changeMode = model::selectImmersionMode,
                reviewIdentity = model::openConversation,
                onBack = model::back,
                startWithCreate = model.createGroupOnEntry,
                entryGroup = model.inboxGroup,
                onVisitConversation = { groupID ->
                    chat.activateConversation(ConversationRef.Group(groupID))
                    chat.visitedConversation = true
                },
            )
        } else LaunchedEffect(Unit) { model.navigate(Screen.HOME) }
        return
    }
    if (model.screen == Screen.BACKUP && model.chat != null) {
        HistoryBackupScreen(model.chat!!) { model.back() }
        return
    }
    if (model.screen == Screen.LICENSES) {
        LegalNoticesScreen { model.back() }
        return
    }
    if (model.screen == Screen.CONVERSATION) {
        val chat = model.chat
        val peer = model.selectedPeer
        if (chat != null && peer != null) {
            val ref = ConversationRef.Direct(peer)
            FriendConversationScreen(
                chat,
                peer,
                model.knownLanguage,
                animateBackground = model.animateConversationBackground,
                waterClock = waterClock,
                onConversationLanguage = { model.selectConversationLanguage(ref, it) },
                onUseDefaultConversationLanguage = { model.useDefaultConversationLanguage(ref) },
                onImmersionMode = model::selectImmersionMode,
                notificationEducation = model.replyNotificationEducation,
                onNotificationPermission = model::notificationPermissionChanged,
            ) {
                model.back()
            }
            return
        }
    }
    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        bottomBar = { if (onboarding && !largeText) OnboardingAction(model) },
    ) { padding ->
        Box(
            Modifier.fillMaxSize().padding(padding).consumeWindowInsets(padding).imePadding(),
            contentAlignment = Alignment.TopCenter,
        ) {
            Column(
                Modifier.fillMaxHeight()
                    .widthIn(max = 680.dp)
                    .fillMaxWidth()
                    .padding(horizontal = 26.dp)
                    .verticalScroll(scrollState),
                verticalArrangement =
                    Arrangement.spacedBy(if (model.screen == Screen.LANGUAGE) 16.dp else 24.dp),
            ) {
                TopBar(model)
                when (model.screen) {
                    Screen.WELCOME -> Welcome(scrollState.isScrollInProgress, model.immersionMode)
                    Screen.LANGUAGE -> LanguageSelection(model, scrollState.isScrollInProgress)
                    Screen.TUTORIAL ->
                        ImmersionTutorialContent(
                            model.knownLanguage,
                            model.targetLanguage,
                            model.immersionMode,
                            onToggle = {
                                model.selectImmersionMode(
                                    if (model.immersionMode == ImmersionMode.NEW_WORD)
                                        ImmersionMode.FULL_MESSAGES
                                    else ImmersionMode.NEW_WORD
                                )
                            },
                            scrolling = scrollState.isScrollInProgress,
                            translatorFactory = model.translationFactory,
                        )
                    Screen.ACCOUNT -> AccountView()
                    Screen.SETTINGS -> SettingsView(model)
                    Screen.HELP -> NativeHelpContent(model::openTutorial)
                    Screen.NEW_CHAT -> Unit
                    Screen.LANGUAGE_DOWNLOAD -> DownloadView(model)
                    Screen.PROFILE -> ProfileSetupScreen(model)
                    Screen.DELETE_ACCOUNT -> DeleteAccountScreen { model.beginDeletion() }
                    Screen.HOME,
                    Screen.GROUPS,
                    Screen.CONVERSATION,
                    Screen.BACKUP,
                    Screen.LICENSES -> Unit
                }
                if (onboarding && largeText) OnboardingAction(model, inScroll = true)
                Spacer(Modifier.height(20.dp))
            }
        }
    }
}

@Composable
internal fun VipiMark(size: Int = 36) {
    val art =
        if (MaterialTheme.colorScheme.background.luminance() < .5f) R.drawable.vipi_mark_night
        else R.drawable.vipi_mark_day
    // Transparent optical artwork follows the selected app appearance. The
    // launcher owns its separate full-bleed asset; no in-app tile or clipping.
    androidx.compose.foundation.Image(
        painter = androidx.compose.ui.res.painterResource(art),
        contentDescription = null,
        modifier = Modifier.size(size.dp),
    )
}

@Composable
internal fun TopBar(model: VipiModel, trailing: (@Composable () -> Unit)? = null) {
    Row(
        Modifier.fillMaxWidth().padding(top = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (model.screen != Screen.WELCOME) {
            IconButton(onClick = { model.back() }) {
                Icon(Icons.AutoMirrored.Outlined.ArrowBack, stringResource(R.string.nav_back))
            }
        } else if (model.screen == Screen.WELCOME) {
            VipiMark(34)
            Spacer(Modifier.width(10.dp))
        }
        Text(
            stringResource(
                when (model.screen) {
                    Screen.NEW_CHAT -> R.string.nav_new_chat
                    Screen.SETTINGS -> R.string.settings_title
                    Screen.HELP -> R.string.nav_help
                    else -> R.string.ui_2f7e29fbc47d
                }
            ),
            fontSize = 27.sp,
            letterSpacing = (-1).sp,
            fontWeight = FontWeight.SemiBold,
            maxLines = 1,
            softWrap = false,
        )
        if (trailing == null) Spacer(Modifier.weight(1f))
        else
            BoxWithConstraints(Modifier.weight(1f), contentAlignment = Alignment.CenterEnd) {
                if (maxWidth >= 92.dp) trailing()
            }
        if (model.screen in setOf(Screen.LANGUAGE, Screen.ACCOUNT)) {
            val fullStep =
                if (model.screen == Screen.LANGUAGE) stringResource(R.string.ui_00e255330e43)
                else stringResource(R.string.ui_de6e21a278c4)
            val shortStep = if (model.screen == Screen.LANGUAGE) "1 / 2" else "2 / 2"
            Text(
                if (androidx.compose.ui.platform.LocalDensity.current.fontScale >= 1.5f) shortStep
                else fullStep,
                fontSize = 14.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.semantics { contentDescription = fullStep },
            )
        }
    }
}

@Composable
private fun Heading(eyebrow: String, title: String, detail: String) {
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text(title, fontSize = 34.sp, lineHeight = 39.sp, fontWeight = FontWeight.Bold)
        if (detail.isNotBlank())
            Text(
                detail,
                fontSize = 18.sp,
                lineHeight = 27.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
    }
}

@Composable
internal fun PrimaryButton(
    title: String,
    enabled: Boolean = true,
    busy: Boolean = false,
    onClick: () -> Unit,
) {
    Button(
        onClick = onClick,
        enabled = enabled && !busy,
        shape = RoundedCornerShape(18.dp),
        colors =
            ButtonDefaults.buttonColors(
                containerColor = MaterialTheme.colorScheme.primary,
                contentColor = MaterialTheme.colorScheme.onPrimary,
            ),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 17.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        if (busy)
            CircularProgressIndicator(
                Modifier.size(20.dp),
                color = MaterialTheme.colorScheme.onPrimary,
                strokeWidth = 2.dp,
            )
        else {
            Text(title, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.width(10.dp))
            Icon(Icons.AutoMirrored.Outlined.ArrowForward, null, Modifier.size(18.dp))
        }
    }
}

@Composable
private fun Welcome(scrolling: Boolean, mode: ImmersionMode) {
    Heading(
        "",
        stringResource(R.string.welcome_title_concise),
        stringResource(
            if (mode == ImmersionMode.FULL_MESSAGES) R.string.welcome_detail_full
            else R.string.welcome_detail_concise
        ),
    )
    ConversationPreview("en", "es", scrolling, mode)
}

@Composable
private fun LanguageSelection(model: VipiModel, scrolling: Boolean) {
    var targetMenu by remember { mutableStateOf(false) }
    var knownMenu by remember { mutableStateOf(false) }
    val uiLocale = androidx.compose.ui.platform.LocalConfiguration.current.locales[0]
    fun displayLanguage(code: String): String =
        java.util.Locale.forLanguageTag(code).getDisplayLanguage(uiLocale).replaceFirstChar {
            it.titlecase(uiLocale)
        }
    Heading("", stringResource(R.string.languages_title_concise), "")
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(
            stringResource(R.string.speak_concise),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontWeight = FontWeight.Medium,
        )
        Box {
            Row(
                Modifier.fillMaxWidth()
                    .background(MaterialTheme.colorScheme.surface, RoundedCornerShape(16.dp))
                    .clickable { knownMenu = true }
                    .padding(18.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(displayLanguage(model.knownLanguage))
                Spacer(Modifier.weight(1f))
                Icon(Icons.Outlined.ExpandMore, stringResource(R.string.ui_aae89a15c1be))
            }
            LanguageChoiceMenu(
                knownMenu,
                model.knownLanguage,
                translationLanguages,
                { knownMenu = false },
                model::selectKnown,
            ) {
                displayLanguage(it.code)
            }
        }
    }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(
            stringResource(R.string.learn_concise),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontWeight = FontWeight.Medium,
        )
        Box {
            Row(
                Modifier.fillMaxWidth()
                    .background(MaterialTheme.colorScheme.surface, RoundedCornerShape(16.dp))
                    .clickable { targetMenu = true }
                    .padding(18.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(displayLanguage(model.targetLanguage))
                Spacer(Modifier.weight(1f))
                Icon(Icons.Outlined.ExpandMore, stringResource(R.string.ui_0c574552109f))
            }
            if (targetMenu)
                LanguageChoiceMenu(
                    true,
                    model.targetLanguage,
                    rememberPracticeOptions().targets(model.knownLanguage, model.targetLanguage),
                    { targetMenu = false },
                    model::selectTarget,
                )
        }
    }
}

@Composable
private fun AccountView() {
    Heading(
        "",
        stringResource(R.string.account_title_concise),
        stringResource(R.string.account_detail_concise),
    )
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Icon(Icons.Outlined.Lock, null, tint = MaterialTheme.colorScheme.primary)
            Text(stringResource(R.string.account_private_title), fontWeight = FontWeight.SemiBold)
        }
        Text(
            stringResource(R.string.account_private_detail),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(stringResource(R.string.account_trial_concise), fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun OnboardingAction(model: VipiModel, inScroll: Boolean = false) {
    var accepted by rememberSaveable { mutableStateOf(false) }
    val context = LocalContext.current
    val largeText = androidx.compose.ui.platform.LocalDensity.current.fontScale >= 1.5f
    Box(
        Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.background),
        contentAlignment = Alignment.TopCenter,
    ) {
        Column(
            Modifier.widthIn(max = 680.dp)
                .fillMaxWidth()
                .then(if (inScroll) Modifier else Modifier.navigationBarsPadding())
                .padding(horizontal = if (inScroll) 0.dp else 26.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (model.screen == Screen.ACCOUNT) {
                Row(
                    Modifier.fillMaxWidth()
                        .heightIn(min = 48.dp)
                        .toggleable(
                            value = accepted,
                            role = Role.Checkbox,
                            onValueChange = { accepted = it },
                        ),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Checkbox(checked = accepted, onCheckedChange = null)
                    Text(
                        stringResource(R.string.ui_9ed65d7add5f),
                        fontSize = 16.sp,
                        lineHeight = 24.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                val legalLinks: @Composable () -> Unit = {
                    TextButton(
                        onClick = {
                            context.startActivity(
                                Intent(
                                    Intent.ACTION_VIEW,
                                    Uri.parse("https://mambovipi.app/terms.html"),
                                )
                            )
                        }
                    ) {
                        Text(stringResource(R.string.terms_service), fontSize = 15.sp)
                    }
                    TextButton(
                        onClick = {
                            context.startActivity(
                                Intent(
                                    Intent.ACTION_VIEW,
                                    Uri.parse("https://mambovipi.app/privacy.html"),
                                )
                            )
                        }
                    ) {
                        Text(stringResource(R.string.privacy_policy), fontSize = 15.sp)
                    }
                }
                if (largeText)
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) { legalLinks() }
                else Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) { legalLinks() }
                model.authentication.error?.let {
                    Text(
                        it,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }
            PrimaryButton(
                when (model.screen) {
                    Screen.WELCOME -> stringResource(R.string.choose_languages)
                    Screen.LANGUAGE,
                    Screen.TUTORIAL -> stringResource(R.string.continue_action)
                    else -> stringResource(R.string.continue_signin)
                },
                enabled = model.screen != Screen.ACCOUNT || accepted,
                busy = model.authentication.busy,
            ) {
                when (model.screen) {
                    Screen.WELCOME -> model.navigate(Screen.LANGUAGE)
                    Screen.LANGUAGE -> model.openTutorial()
                    Screen.TUTORIAL -> model.finishTutorial()
                    else -> model.authentication.signIn(context)
                }
            }
        }
    }
}

/**
 * Demand only previews intersecting the clipped window. Each row resolves its own conversation
 * language, while the encrypted owner is shared by pair.
 */
@Composable
internal fun HomeTranslationPreview(
    chat: ChatSession,
    peer: UUID,
    message: ChatItem,
    unread: Boolean,
) {
    InboxMessagePreview(
        chat,
        ConversationRef.Direct(peer),
        message.id.toString(),
        message.text,
        unread,
    )
}

@Composable
internal fun InboxMessagePreview(
    chat: ChatSession,
    ref: ConversationRef,
    id: String,
    text: String,
    unread: Boolean,
) {
    val owner = chat.translationFor(ref)
    var visible by remember(owner, id, text) { mutableStateOf(false) }
    DisposableEffect(owner, id, text, visible) {
        if (visible && owner != null) {
            owner.retain(id, text)
            owner.enqueue(id, text)
        }
        onDispose { if (visible) owner?.release(id, text) }
    }
    val state = owner?.state(id, text)
    val value = state?.value
    val preview = value?.let { it.practiceReading ?: it.practiceText } ?: text
    Text(
        preview,
        maxLines = 2,
        overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
        fontSize = 16.sp,
        lineHeight = 21.sp,
        fontWeight = if (unread) FontWeight.Medium else FontWeight.Normal,
        color = if (unread) vipiPalette().ink else vipiPalette().secondary,
        modifier =
            Modifier.testTag("home-message-preview-$id").onGloballyPositioned {
                val bounds = it.boundsInWindow()
                visible = bounds.width > 0f && bounds.height > 0f
            },
    )
}

@Composable
private fun DownloadView(model: VipiModel) {
    LanguageDownloadsScreen(model)
}
