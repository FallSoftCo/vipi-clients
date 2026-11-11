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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
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
import co.fallsoft.vipi.core.ImmersionResult
import co.fallsoft.vipi.core.SpeechSpan
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.compose.foundation.text.KeyboardOptions
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
        if (intent.action == Intent.ACTION_VIEW) intent.data?.let { uri -> lifecycleScope.launch { model.authentication.complete(uri) } }
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
    val colors = if (dark) darkColorScheme(
        primary = Color(0xFFB0D9A3), onPrimary = Color(0xFF132D22), background = Color(0xFF111412),
        surface = Color(0xFF1F2420), surfaceVariant = Color(0xFF2E4233), onSurface = Color(0xFFF0F0E7),
        onBackground = Color(0xFFF0F0E7), onSurfaceVariant = Color(0xFFB8BFB6),
        primaryContainer = Color(0xFF2E4233), onPrimaryContainer = Color(0xFFDEEFBE),
        secondary = Color(0xFFB8CBB2), onSecondary = Color(0xFF233526), secondaryContainer = Color(0xFF324536), onSecondaryContainer = Color(0xFFD5E8CE),
        tertiary = Color(0xFFC0CCA5), onTertiary = Color(0xFF2C351E), tertiaryContainer = Color(0xFF424C33), onTertiaryContainer = Color(0xFFDDE9C0),
        surfaceContainerLowest = Color(0xFF0B100C), surfaceContainerLow = Color(0xFF171D18), surfaceContainer = Color(0xFF1D231E),
        surfaceContainerHigh = Color(0xFF272E28), surfaceContainerHighest = Color(0xFF323A33), surfaceTint = Color(0xFFB0D9A3),
        outline = Color(0xFF8A958B), outlineVariant = Color(0xFF404A41), inversePrimary = Color(0xFF2B6142),
        inverseSurface = Color(0xFFE6EAE0), inverseOnSurface = Color(0xFF2B322B)
    ) else lightColorScheme(
        primary = Color(0xFF2B6142), onPrimary = Color.White, background = Color(0xFFF9F7F2),
        surface = Color.White, surfaceVariant = Color(0xFFE0EDD4), onSurface = Color(0xFF18251D),
        onBackground = Color(0xFF18251D), onSurfaceVariant = Color(0xFF646C64),
        primaryContainer = Color(0xFFE0EDD4), onPrimaryContainer = Color(0xFF18351F),
        secondary = Color(0xFF50644D), onSecondary = Color.White, secondaryContainer = Color(0xFFD3E8CE), onSecondaryContainer = Color(0xFF142311),
        tertiary = Color(0xFF5B6447), onTertiary = Color.White, tertiaryContainer = Color(0xFFDFE9C7), onTertiaryContainer = Color(0xFF1A230A),
        surfaceContainerLowest = Color.White, surfaceContainerLow = Color(0xFFF4F4EC), surfaceContainer = Color(0xFFEEEEE5),
        surfaceContainerHigh = Color(0xFFE8E9DF), surfaceContainerHighest = Color(0xFFE2E3D9), surfaceTint = Color(0xFF2B6142),
        outline = Color(0xFF737E73), outlineVariant = Color(0xFFC3CCBF), inversePrimary = Color(0xFFB0D9A3),
        inverseSurface = Color(0xFF2B322B), inverseOnSurface = Color(0xFFF0F0E7)
    )
    MaterialTheme(colorScheme = colors, content = content)
}

@Composable private fun VipiApp(model: VipiModel) {
    LaunchedEffect(model.authentication.userID, model.authentication.signInRevision, model.deletion.active) {
        if (model.deletion.active) model.deletion.resume()
        else if (model.authentication.userID != null) model.activateChats()
    }
    if (model.deletion.active) { AccountDeletionProgress(model.deletion, model.authentication) { model.navigate(Screen.WELCOME) }; return }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val syncScope = rememberCoroutineScope()
    LaunchedEffect(model.subscriptions) { model.subscriptions?.refresh() }
    LaunchedEffect(model.subscriptions?.access?.base?.usable()) {
        if (model.subscriptions?.access?.base?.usable() == true) model.chat?.synchronize()
    }
    DisposableEffect(lifecycle, model.chat, model.subscriptions) {
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_RESUME) {
            androidx.core.app.NotificationManagerCompat.from(model.getApplication()).cancel(1)
            syncScope.launch { model.chat?.synchronize() }
            syncScope.launch { model.subscriptions?.refresh() }
        } }
        lifecycle.addObserver(observer); onDispose { lifecycle.removeObserver(observer) }
    }
    DisposableEffect(lifecycle, model.chat, model.chat?.ready, model.chat?.needsReauthentication, model.authentication.userID) {
        val chat = model.chat
        val events = chat?.takeIf { it.ready && !it.needsReauthentication && it.userID == model.authentication.userID }?.let {
            ForegroundInboxEvents(syncScope, { rejected -> model.authentication.accessToken(it.userID, rejected) },
                it::eventDevice, {
                    it.synchronize()
                    if (!it.lastSyncComplete) throw java.io.IOException("Inbox synchronization incomplete")
                }, onDeviceRevoked = it::noteDeviceRevoked)
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
    if (model.screen == Screen.BOT && model.bot != null) { BotConversationScreen(model, model.bot!!); return }
    if (model.screen == Screen.BACKUP && model.chat != null) { HistoryBackupScreen(model.chat!!) { model.back() }; return }
    if (model.screen == Screen.LICENSES) { LegalNoticesScreen { model.back() }; return }
    if (model.screen == Screen.CONVERSATION) {
        val chat = model.chat; val peer = model.selectedPeer
        if (chat != null && peer != null) { FriendConversationScreen(chat, peer, model.knownLanguage, model.targetLanguage,
            model.density, onLanguages = { model.navigate(Screen.LANGUAGE_DOWNLOAD) }, onPlan = { model.navigate(Screen.PLANS) }) { model.back() }; return }
    }
    Scaffold(containerColor = MaterialTheme.colorScheme.background,
        bottomBar = { if (onboarding && !largeText) OnboardingAction(model) }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).widthIn(max = 680.dp).padding(horizontal = 26.dp).verticalScroll(scrollState), verticalArrangement = Arrangement.spacedBy(28.dp)) {
            TopBar(model)
            when (model.screen) {
                Screen.WELCOME -> Welcome(scrollState.isScrollInProgress)
                Screen.LANGUAGE -> LanguageSelection(model, scrollState.isScrollInProgress)
                Screen.ACCOUNT -> AccountView()
                Screen.HOME -> HomeView(model)
                Screen.SETTINGS -> SettingsView(model)
                Screen.NEW_CHAT -> NewChatView(model)
                Screen.BOT -> BotView(model)
                Screen.BOT_PLAN -> BotView(model)
                Screen.PLANS -> SubscriptionScreen(model)
                Screen.LANGUAGE_DOWNLOAD -> DownloadView(model)
                Screen.PROFILE -> ProfileSetupScreen(model)
                Screen.DELETE_ACCOUNT -> DeleteAccountScreen { model.beginDeletion() }
                Screen.CONVERSATION, Screen.BACKUP, Screen.LICENSES -> Unit
            }
            if (onboarding && largeText) OnboardingAction(model, inScroll = true)
            Spacer(Modifier.height(20.dp))
        }
    }
}

@Composable private fun VipiMark(size: Int = 36) {
    Box(Modifier.size(size.dp).background(Color(0xFF234E3D), RoundedCornerShape((size * .28).dp))) {
        androidx.compose.foundation.Image(
            painter = androidx.compose.ui.res.painterResource(R.drawable.vipi_icon_foreground),
            contentDescription = null, modifier = Modifier.fillMaxSize())
    }
}

@Composable private fun TopBar(model: VipiModel) {
    Row(Modifier.fillMaxWidth().padding(top = 20.dp), verticalAlignment = Alignment.CenterVertically) {
        if (model.screen !in setOf(Screen.WELCOME, Screen.HOME)) {
            IconButton(onClick = { model.back() }) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, "Back") }
        } else { VipiMark(34); Spacer(Modifier.width(10.dp)) }
        Text("vipi", fontSize = 27.sp, letterSpacing = (-1).sp, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.weight(1f))
        if (model.screen == Screen.HOME) IconButton(onClick = { model.navigate(Screen.SETTINGS) }) { Icon(Icons.Outlined.AccountCircle, "Your profile and settings") }
        if (model.screen in setOf(Screen.LANGUAGE, Screen.ACCOUNT)) Text(if (model.screen == Screen.LANGUAGE) "Language · 1 of 2" else "Account · 2 of 2", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable private fun Heading(eyebrow: String, title: String, detail: String) {
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        if (androidx.compose.ui.platform.LocalDensity.current.fontScale < 1.5f) {
            Text(eyebrow.uppercase(), color = MaterialTheme.colorScheme.primary, fontSize = 11.sp, letterSpacing = 1.6.sp, fontWeight = FontWeight.SemiBold)
        }
        Text(title, fontSize = 36.sp, lineHeight = 41.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.Medium)
        Text(detail, fontSize = 16.sp, lineHeight = 24.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable internal fun PrimaryButton(title: String, enabled: Boolean = true, busy: Boolean = false, onClick: () -> Unit) {
    Button(onClick = onClick, enabled = enabled && !busy, shape = RoundedCornerShape(18.dp),
        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary, contentColor = MaterialTheme.colorScheme.onPrimary),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 17.dp), modifier = Modifier.fillMaxWidth()) {
        if (busy) CircularProgressIndicator(Modifier.size(20.dp), color = MaterialTheme.colorScheme.onPrimary, strokeWidth = 2.dp)
        else { Text(title, fontSize = 16.sp, fontWeight = FontWeight.SemiBold); Spacer(Modifier.width(10.dp)); Icon(Icons.AutoMirrored.Outlined.ArrowForward, null, Modifier.size(18.dp)) }
    }
}

@Composable private fun Welcome(scrolling: Boolean) {
    var mode by rememberSaveable { mutableStateOf(ReadingMode.IMMERSED) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val speech = remember { SpeechPlayback(context, "en", "es", scope) }
    val owner = LocalLifecycleOwner.current
    val warmups = remember { mapOf("en" to "Hello.", "es" to "Hola.") }
    LaunchedEffect(speech) { speech.prepare(warmups) }
    DisposableEffect(speech, owner) {
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_STOP) speech.stop() }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer); speech.close() }
    }
    Heading("Language learning through chat", "Chat with friends.\nLearn new words.", "Selected words and short phrases switch between your language and the language you choose. Word order and grammar stay the same.")
    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = .48f), RoundedCornerShape(28.dp)).padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("EXAMPLE: ENGLISH AND SPANISH", fontSize = 10.sp, letterSpacing = 1.2.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, fontWeight = FontWeight.SemiBold)
        ImmersionBubble(immersionPreview, mode, speech = speech, interactionPaused = scrolling)
        if (speech.state == SpeechState.UNAVAILABLE) {
            Text(speech.error ?: "Voices aren’t ready.", fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Row {
                TextButton(onClick = { runCatching { context.startActivity(Intent("com.android.settings.TTS_SETTINGS")) } }) { Text("Speech settings") }
                TextButton(onClick = { speech.prepare(warmups) }) { Text("Retry") }
            }
        } else speech.error?.let { Text(it, fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        Text("Watch the highlighted words switch in place. Tap Pause to stop them or Listen to hear pronunciation.", fontSize = 13.sp, lineHeight = 19.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        TextButton(onClick = { mode = if (mode == ReadingMode.ORIGINAL) ReadingMode.IMMERSED else ReadingMode.ORIGINAL }, contentPadding = PaddingValues(0.dp)) {
            Icon(Icons.Outlined.Sync, null, Modifier.size(17.dp)); Spacer(Modifier.width(8.dp))
            Text(if (mode == ReadingMode.ORIGINAL) "Resume Spanish words" else "Show original message", fontSize = 13.sp)
        }
    }
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Icon(Icons.Outlined.Spa, null, tint = MaterialTheme.colorScheme.primary)
        Text("This is an example. In your chats, only supported words and phrases switch. The rest stays unchanged.", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp, lineHeight = 21.sp)
    }
}

@Composable private fun LanguageSelection(model: VipiModel, scrolling: Boolean) {
    var targetMenu by remember { mutableStateOf(false) }
    var knownMenu by remember { mutableStateOf(false) }
    Heading("Language settings", "Choose your\nlanguages.", "Choose the language you know and the one you want to learn. You can change these later.")
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("I already speak", color = MaterialTheme.colorScheme.onSurfaceVariant, fontWeight = FontWeight.Medium)
        Box {
            Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, RoundedCornerShape(16.dp)).clickable { knownMenu = true }.padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(languageName(model.knownLanguage)); Spacer(Modifier.weight(1f)); Icon(Icons.Outlined.ExpandMore, "Choose the language you know")
            }
            DropdownMenu(expanded = knownMenu, onDismissRequest = { knownMenu = false }) {
                initialLanguages.forEach { language -> DropdownMenuItem(text = { Text(language.name) }, onClick = { model.selectKnown(language.code); knownMenu = false }) }
            }
        }
    }
    Text("I want to learn", color = MaterialTheme.colorScheme.onSurfaceVariant, fontWeight = FontWeight.Medium)
    Box {
        Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, RoundedCornerShape(16.dp)).clickable { targetMenu = true }.padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(languageName(model.targetLanguage)); Spacer(Modifier.weight(1f)); Icon(Icons.Outlined.ExpandMore, "Choose the language you want to learn")
        }
        DropdownMenu(expanded = targetMenu, onDismissRequest = { targetMenu = false }) {
            initialLanguages.filter { it.code != model.knownLanguage }.forEach { language -> DropdownMenuItem(text = { Text("${language.name} · ${language.localName}") }, onClick = { model.selectTarget(language.code); targetMenu = false }) }
        }
    }
    key(model.knownLanguage, model.targetLanguage) { ConversationPreview(model.knownLanguage, model.targetLanguage, scrolling) }
    Text("Available words and phrases vary by language. Pronunciation may need a voice download.", fontSize = 13.sp, lineHeight = 19.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable private fun AccountView() {
    Heading("Your account", "Sign in to\nchat with friends.", "Create an account or sign in to an existing one. Friends find you by username, not your email.")
    Column(Modifier.background(MaterialTheme.colorScheme.surface, RoundedCornerShape(22.dp)).padding(22.dp), verticalArrangement = Arrangement.spacedBy(20.dp)) {
        Text("Find friends by username."); Text("Your email is not shown to friends."); Text("Chats with friends are end-to-end encrypted.")
    }
}

@Composable private fun OnboardingAction(model: VipiModel, inScroll: Boolean = false) {
    var accepted by rememberSaveable { mutableStateOf(false) }
    val context = LocalContext.current
    val largeText = androidx.compose.ui.platform.LocalDensity.current.fontScale >= 1.5f
    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.background).then(if (inScroll) Modifier else Modifier.navigationBarsPadding()).padding(horizontal = if (inScroll) 0.dp else 26.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        if (model.screen == Screen.ACCOUNT) {
            Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(checked = accepted, onCheckedChange = { accepted = it }); Text("I agree to the Terms of Service and have read the Privacy Policy.", fontSize = 12.sp, lineHeight = 18.sp, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            val legalLinks: @Composable () -> Unit = {
                TextButton(onClick = { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://api.mambovipi.app/terms"))) }) { Text("Terms of Service", fontSize = 12.sp) }
                TextButton(onClick = { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://api.mambovipi.app/privacy"))) }) { Text("Privacy Policy", fontSize = 12.sp) }
            }
            if (largeText) Column(verticalArrangement = Arrangement.spacedBy(4.dp)) { legalLinks() }
            else Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) { legalLinks() }
            model.authentication.error?.let { Text(it, fontSize = 13.sp, color = MaterialTheme.colorScheme.error) }
        }
        PrimaryButton(when (model.screen) { Screen.WELCOME -> "Choose languages"; Screen.LANGUAGE -> "Continue with ${languageName(model.targetLanguage)}"; else -> "Continue to sign in" }, enabled = model.screen != Screen.ACCOUNT || accepted, busy = model.authentication.busy) {
            when (model.screen) { Screen.WELCOME -> model.navigate(Screen.LANGUAGE); Screen.LANGUAGE -> model.navigate(Screen.ACCOUNT); else -> model.authentication.signIn(context) }
        }
        if (model.screen == Screen.WELCOME && !largeText) Text("No account needed to try this example.", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.align(Alignment.CenterHorizontally))
    }
}

@Composable private fun HomeView(model: VipiModel) {
    val chat = model.chat
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    if (chat?.needsReauthentication == true && !chat.needsDeviceRecovery) ReauthenticationCard(chat, model.authentication.busy, model.authentication.error) { expected -> model.authentication.signIn(context, expectedUser = expected) }
    if (chat?.needsDeviceRecovery == true) DeviceRecoveryCard(chat) { model.authentication.signIn(context, expectedUser = chat.userID) }
    if (model.authentication.userID != null && chat?.needsDeviceRecovery != true && chat?.needsReauthentication != true && (chat?.ready != true || model.chatError != null)) {
        Text("Connecting to your chats", fontFamily = FontFamily.Serif, fontSize = 30.sp)
        Text(model.chatError ?: chat?.notice ?: "Your conversations stay on your device.", color = MaterialTheme.colorScheme.onSurfaceVariant)
        if (chat?.busy == true) CircularProgressIndicator()
        else PrimaryButton("Try again") { scope.launch { model.activateChats() } }
        return
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text("Chats", fontFamily = FontFamily.Serif, fontSize = 34.sp, modifier = Modifier.weight(1f))
        IconButton(onClick = { model.navigate(Screen.NEW_CHAT) }, enabled = chat?.ready == true) { Icon(Icons.Outlined.Edit, "New chat") }
    }
    if (chat != null && chat.threads.isNotEmpty()) {
        chat.threads.forEach { thread ->
            Row(Modifier.fillMaxWidth().clickable { model.openConversation(thread.peer) }.padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                Box(Modifier.size(48.dp).background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(24.dp)), contentAlignment = Alignment.Center) { Text(chat.name(thread.peer).take(1), fontSize = 24.sp) }
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    Text(chat.name(thread.peer), fontWeight = if (thread.unread > 0) FontWeight.SemiBold else FontWeight.Medium)
                    Text(thread.latest.text, maxLines = 1, fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                if (thread.unread > 0) Badge { Text(thread.unread.toString()) }
            }
        }
    } else Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, RoundedCornerShape(28.dp)).padding(26.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
        VipiMark(54)
        Text("Start a chat\nwith a friend.", fontFamily = FontFamily.Serif, fontSize = 28.sp, lineHeight = 35.sp)
        Text("Find a friend by username and send a message. Supported words and phrases will switch into ${languageName(model.targetLanguage)} as you read.", lineHeight = 24.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        PrimaryButton("Start a conversation") { model.navigate(Screen.NEW_CHAT) }
    }
    chat?.notice?.let { Text(it, fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    if (chat?.ready == true && chat.threads.isNotEmpty()) NotificationSetup()
    Row(Modifier.fillMaxWidth().clickable { model.openBot() }.padding(vertical = 12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        Icon(Icons.Outlined.AutoAwesome, null, Modifier.size(50.dp).background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(18.dp)).padding(13.dp), tint = MaterialTheme.colorScheme.primary)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(5.dp)) { Text("vBot", fontWeight = FontWeight.SemiBold); Text("Chat with a chatbot. Requires the separate Bot mini plan.", fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        Icon(Icons.Outlined.ChevronRight, null)
    }
}

@Composable private fun NewChatView(model: VipiModel) {
    var username by rememberSaveable { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    Heading("Find a friend", "Start a conversation.", "Enter their exact Vipi username. Your phone contacts stay private.")
    OutlinedTextField(value = username, onValueChange = { username = it }, label = { Text("Friend’s username") }, singleLine = true,
        keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None, autoCorrectEnabled = false), modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(16.dp))
    PrimaryButton("Find friend", enabled = username.isNotBlank(), busy = busy) {
        val chat = model.chat
        if (chat == null) error = "Sign in to find your friends."
        else scope.launch {
            busy = true; error = null
            try { model.openConversation(chat.find(username).id) }
            catch (failure: kotlinx.coroutines.CancellationException) { throw failure }
            catch (failure: Exception) { error = ChatSession.explanation(failure) }
            finally { busy = false }
        }
    }
    error?.let { Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant) }
}

@Composable private fun BotView(model: VipiModel) {
    SubscriptionScreen(model, SubscriptionPlan.BOT_MINI)
}

@Composable private fun SettingsView(model: VipiModel) {
    val uri = androidx.compose.ui.platform.LocalUriHandler.current
    var linkError by remember { mutableStateOf<String?>(null) }
    Text("Settings", fontFamily = FontFamily.Serif, fontSize = 34.sp)
    Text("Words in your chats", fontWeight = FontWeight.SemiBold)
    TextButton(onClick = { model.navigate(Screen.PLANS) }) { Text("Your plan") }
    if (model.chat?.profile != null) TextButton(onClick = { model.navigate(Screen.BACKUP) }) { Text("Chat backup") }
    Row(Modifier.fillMaxWidth().clickable { model.navigate(Screen.LANGUAGE_DOWNLOAD) }.padding(vertical = 14.dp)) { Text("Languages & downloads"); Spacer(Modifier.weight(1f)); Text(languageName(model.targetLanguage), color = MaterialTheme.colorScheme.onSurfaceVariant) }
    Column {
        Row { Text("How many words change"); Spacer(Modifier.weight(1f)); Text("${(model.density * 100).toInt()}%") }
        Slider(value = model.density.toFloat(), onValueChange = { model.changeDensity(it.toDouble()) }, valueRange = 0f..0.75f, steps = 14, modifier = Modifier.semantics { contentDescription = "Amount of words to switch" })
        Text("Choose how much of each message you want to switch. The amount shown depends on available words and phrases.", fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    Text("Appearance", fontWeight = FontWeight.SemiBold)
    Appearance.entries.forEach { appearance ->
        Row(Modifier.fillMaxWidth().clickable { model.changeAppearance(appearance) }.semantics { role = Role.RadioButton; selected = model.appearance == appearance }, verticalAlignment = Alignment.CenterVertically) {
            RadioButton(selected = model.appearance == appearance, onClick = { model.changeAppearance(appearance) }); Text(appearance.name.lowercase().replaceFirstChar { it.uppercase() })
        }
    }
    Text("Made by FallSoft.Co", fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    TextButton(onClick = { model.navigate(Screen.LICENSES) }) { Text("Licenses and notices") }
    Row {
        listOf("Terms" to "terms", "Privacy" to "privacy", "Help" to "help").forEach { (title, path) ->
            TextButton(onClick = { runCatching { uri.openUri("https://api.mambovipi.app/$path") }.onFailure { linkError = "This page couldn’t open. Please try again." } }) { Text(title) }
        }
    }
    linkError?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
    if (model.chat?.profile != null) TextButton(onClick = { model.navigate(Screen.DELETE_ACCOUNT) }) {
        Text("Delete account", color = MaterialTheme.colorScheme.error)
    }
}

@Composable private fun DownloadView(model: VipiModel) { LanguageDownloadsScreen(model) }
