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

class MainActivity : ComponentActivity() {
    private val model: VipiModel by viewModels()
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        handleCallback(intent)
        if (BuildConfig.DEBUG) {
            when (intent.getStringExtra("vipi_screen")) {
                "welcome" -> model.navigate(Screen.WELCOME)
                "language" -> model.navigate(Screen.LANGUAGE)
                "home" -> model.navigate(Screen.HOME)
                "translation" -> model.navigate(Screen.LANGUAGE_DOWNLOAD)
            }
        }
        setContent { VipiTheme(model.appearance) { VipiApp(model) } }
    }
    override fun onNewIntent(intent: Intent) { super.onNewIntent(intent); setIntent(intent); handleCallback(intent) }
    private fun handleCallback(intent: Intent) {
        if (intent.action == Intent.ACTION_VIEW) intent.data?.let { uri -> lifecycleScope.launch { model.authentication.complete(uri) } }
    }
}

private val Green = Color(0xFF33644F)
@Composable private fun VipiTheme(appearance: Appearance, content: @Composable () -> Unit) {
    val dark = appearance == Appearance.DARK || (appearance == Appearance.SYSTEM && isSystemInDarkTheme())
    val colors = if (dark) darkColorScheme(
        primary = Color(0xFFB0D9A3), onPrimary = Color(0xFF132D22), background = Color(0xFF111412),
        surface = Color(0xFF1F2420), surfaceVariant = Color(0xFF2E4233), onSurface = Color(0xFFF0F0E7),
        onBackground = Color(0xFFF0F0E7), onSurfaceVariant = Color(0xFFB8BFB6)
    ) else lightColorScheme(
        primary = Color(0xFF2B6142), onPrimary = Color.White, background = Color(0xFFF9F7F2),
        surface = Color.White, surfaceVariant = Color(0xFFE0EDD4), onSurface = Color(0xFF18251D),
        onBackground = Color(0xFF18251D), onSurfaceVariant = Color(0xFF646C64)
    )
    MaterialTheme(colorScheme = colors, content = content)
}

@Composable private fun VipiApp(model: VipiModel) {
    LaunchedEffect(model.authentication.userID) { if (model.authentication.userID != null) model.navigate(Screen.HOME) }
    val onboarding = model.screen in setOf(Screen.WELCOME, Screen.LANGUAGE, Screen.ACCOUNT)
    BackHandler(enabled = model.screen != Screen.WELCOME && model.screen != Screen.HOME) { model.back() }
    Scaffold(containerColor = MaterialTheme.colorScheme.background,
        bottomBar = { if (onboarding) OnboardingAction(model) }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).widthIn(max = 680.dp).padding(horizontal = 26.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(28.dp)) {
            TopBar(model)
            when (model.screen) {
                Screen.WELCOME -> Welcome()
                Screen.LANGUAGE -> LanguageSelection(model)
                Screen.ACCOUNT -> AccountView()
                Screen.HOME -> HomeView(model)
                Screen.SETTINGS -> SettingsView(model)
                Screen.NEW_CHAT -> NewChatView()
                Screen.BOT -> BotView()
                Screen.LANGUAGE_DOWNLOAD -> DownloadView(model)
            }
            Spacer(Modifier.height(20.dp))
        }
    }
}

@Composable private fun VipiMark(size: Int = 36) {
    Box(Modifier.size(size.dp).background(Green, RoundedCornerShape((size * .32).dp)), contentAlignment = Alignment.Center) {
        Icon(Icons.Outlined.ChatBubble, null, tint = Color(0xFFDEEFBE), modifier = Modifier.size((size * .73).dp))
        Text("v", color = Color(0xFFDEEFBE), fontWeight = FontWeight.Bold, fontSize = (size * .4).sp, modifier = Modifier.offset(y = (-size * .06).dp))
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
        if (model.screen in setOf(Screen.LANGUAGE, Screen.ACCOUNT)) Text(if (model.screen == Screen.LANGUAGE) "1 of 2" else "2 of 2", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable private fun Heading(eyebrow: String, title: String, detail: String) {
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text(eyebrow.uppercase(), color = MaterialTheme.colorScheme.primary, fontSize = 11.sp, letterSpacing = 1.6.sp, fontWeight = FontWeight.SemiBold)
        Text(title, fontSize = 36.sp, lineHeight = 41.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.Medium)
        Text(detail, fontSize = 16.sp, lineHeight = 24.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable private fun PrimaryButton(title: String, enabled: Boolean = true, busy: Boolean = false, onClick: () -> Unit) {
    Button(onClick = onClick, enabled = enabled && !busy, shape = RoundedCornerShape(18.dp),
        colors = ButtonDefaults.buttonColors(containerColor = Green, contentColor = Color.White),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 17.dp), modifier = Modifier.fillMaxWidth()) {
        if (busy) CircularProgressIndicator(Modifier.size(20.dp), color = Color.White, strokeWidth = 2.dp)
        else { Text(title, fontSize = 16.sp, fontWeight = FontWeight.SemiBold); Spacer(Modifier.width(10.dp)); Icon(Icons.AutoMirrored.Outlined.ArrowForward, null, Modifier.size(18.dp)) }
    }
}

@Composable private fun Welcome() {
    var mode by rememberSaveable { mutableStateOf(ReadingMode.IMMERSED) }
    Heading("A little more language. A lot more life.", "Your conversations.\nA new language.", "Chat about what matters to you. Pick up another language along the way.")
    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = .48f), RoundedCornerShape(28.dp)).padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("TRY A LITTLE SPANISH", fontSize = 10.sp, letterSpacing = 1.2.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, fontWeight = FontWeight.SemiBold)
        ImmersionBubble(immersionPreview, mode)
        Text("Tap an underlined word. Its meaning is right there.", fontSize = 13.sp, lineHeight = 19.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        TextButton(onClick = { mode = if (mode == ReadingMode.TRANSLATION) ReadingMode.IMMERSED else ReadingMode.TRANSLATION }, contentPadding = PaddingValues(0.dp)) {
            Icon(Icons.Outlined.Sync, null, Modifier.size(17.dp)); Spacer(Modifier.width(8.dp))
            Text(if (mode == ReadingMode.TRANSLATION) "Back to a little Spanish" else "See the whole thought in Spanish", fontSize = 13.sp)
        }
    }
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Icon(Icons.Outlined.Spa, null, tint = MaterialTheme.colorScheme.primary)
        Text("No lessons to finish. No streak to keep. Just the words in your world.", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp, lineHeight = 21.sp)
    }
}

@Composable private fun ImmersionBubble(result: ImmersionResult, mode: ReadingMode) {
    var revealed by remember(result.original) { mutableStateOf(setOf<Int>()) }
    val color = MaterialTheme.colorScheme.primary
    val text = buildAnnotatedString {
        when (mode) {
            ReadingMode.ORIGINAL -> append(result.original)
            ReadingMode.TRANSLATION -> append(result.translation)
            ReadingMode.IMMERSED -> {
                var cursor = 0
                for (span in result.spans) {
                    append(result.original.substring(cursor, span.start))
                    withLink(LinkAnnotation.Clickable("word-${span.id}", styles = TextLinkStyles(style = SpanStyle(color = color, fontWeight = FontWeight.SemiBold, textDecoration = TextDecoration.Underline)), linkInteractionListener = {
                        revealed = if (span.id in revealed) revealed - span.id else revealed + span.id
                    })) { append(if (span.id in revealed) span.original else span.translated) }
                    cursor = span.end
                }
                append(result.original.substring(cursor))
            }
        }
    }
    Text(text, fontSize = 17.sp, lineHeight = 27.sp, modifier = Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, RoundedCornerShape(23.dp)).padding(20.dp))
}

@Composable private fun LanguageSelection(model: VipiModel) {
    var knownMenu by remember { mutableStateOf(false) }
    Heading("Make it your world", "What language\nwill you live in?", "Start with one. You can change it whenever you like.")
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
    Text("I want to pick up", color = MaterialTheme.colorScheme.onSurfaceVariant, fontWeight = FontWeight.Medium)
    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, RoundedCornerShape(20.dp))) {
        initialLanguages.filter { it.code != model.knownLanguage }.forEachIndexed { index, language ->
            Row(Modifier.fillMaxWidth().clickable { model.selectTarget(language.code) }.semantics { selected = language.code == model.targetLanguage; role = Role.RadioButton }.padding(horizontal = 18.dp, vertical = 14.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(verticalArrangement = Arrangement.spacedBy(3.dp)) { Text(language.name, fontWeight = FontWeight.Medium); Text(language.localName, fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                Spacer(Modifier.weight(1f))
                Icon(if (language.code == model.targetLanguage) Icons.Outlined.CheckCircle else Icons.Outlined.RadioButtonUnchecked, null, tint = if (language.code == model.targetLanguage) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline)
            }
            if (index < initialLanguages.size - 2) HorizontalDivider(Modifier.padding(start = 18.dp), color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = .4f))
        }
    }
    Text("Language downloads stay on your phone. You choose when to download them.", fontSize = 13.sp, lineHeight = 19.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable private fun AccountView() {
    Heading("A place for your people", "Say hello\nas yourself.", "Create an account or sign in. Your email stays private; friends will find you by your username.")
    Column(Modifier.background(MaterialTheme.colorScheme.surface, RoundedCornerShape(22.dp)).padding(22.dp), verticalArrangement = Arrangement.spacedBy(20.dp)) {
        Text("Your chats belong to you."); Text("Your immersion happens on your phone."); Text("You decide who can reach you.")
    }
}

@Composable private fun OnboardingAction(model: VipiModel) {
    var accepted by rememberSaveable { mutableStateOf(false) }
    val context = LocalContext.current
    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.background).navigationBarsPadding().padding(horizontal = 26.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        if (model.screen == Screen.ACCOUNT) {
            Row(verticalAlignment = Alignment.CenterVertically) { Checkbox(checked = accepted, onCheckedChange = { accepted = it }); Text("I agree to the Terms of Service and have read the Privacy Policy.", fontSize = 12.sp, lineHeight = 18.sp, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                TextButton(onClick = { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://fallsoft.co/terms-of-service"))) }) { Text("Terms of Service", fontSize = 12.sp) }
                TextButton(onClick = { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://fallsoft.co/privacy-policy"))) }) { Text("Privacy Policy", fontSize = 12.sp) }
            }
            model.authentication.error?.let { Text(it, fontSize = 13.sp, color = MaterialTheme.colorScheme.error) }
        }
        PrimaryButton(when (model.screen) { Screen.WELCOME -> "Find your language"; Screen.LANGUAGE -> "Continue with ${languageName(model.targetLanguage)}"; else -> "Continue to sign in" }, enabled = model.screen != Screen.ACCOUNT || accepted, busy = model.authentication.busy) {
            when (model.screen) { Screen.WELCOME -> model.navigate(Screen.LANGUAGE); Screen.LANGUAGE -> model.navigate(Screen.ACCOUNT); else -> model.authentication.signIn(context) }
        }
        if (model.screen == Screen.WELCOME) Text("Learn through life, one conversation at a time.", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.align(Alignment.CenterHorizontally))
    }
}

@Composable private fun HomeView(model: VipiModel) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text("Chats", fontFamily = FontFamily.Serif, fontSize = 34.sp, modifier = Modifier.weight(1f))
        IconButton(onClick = { model.navigate(Screen.NEW_CHAT) }) { Icon(Icons.Outlined.Edit, "New chat") }
    }
    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, RoundedCornerShape(28.dp)).padding(26.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
        VipiMark(54)
        Text("Your world,\none conversation away.", fontFamily = FontFamily.Serif, fontSize = 28.sp, lineHeight = 35.sp)
        Text("Bring a friend. Make plans. Talk about your day. A little ${languageName(model.targetLanguage)} will find its way in.", lineHeight = 24.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        PrimaryButton("Start a conversation") { model.navigate(Screen.NEW_CHAT) }
    }
    Row(Modifier.fillMaxWidth().clickable { model.navigate(Screen.BOT) }.padding(vertical = 12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        Icon(Icons.Outlined.AutoAwesome, null, Modifier.size(50.dp).background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(18.dp)).padding(13.dp), tint = MaterialTheme.colorScheme.primary)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(5.dp)) { Text("vBot", fontWeight = FontWeight.SemiBold); Text("A conversation whenever you feel like one.", fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        Icon(Icons.Outlined.ChevronRight, null)
    }
}

@Composable private fun NewChatView() {
    var username by rememberSaveable { mutableStateOf("") }
    var error by remember { mutableStateOf(false) }
    Heading("Your people", "Start a conversation.", "Enter their exact Vipi username. Your phone contacts stay private.")
    OutlinedTextField(value = username, onValueChange = { username = it }, label = { Text("Friend’s username") }, singleLine = true, modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(16.dp))
    PrimaryButton("Find friend", enabled = username.isNotBlank()) { error = true }
    if (error) Text("We couldn’t connect. Check your connection and try again.", color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable private fun BotView() {
    Icon(Icons.Outlined.AutoAwesome, null, Modifier.size(44.dp), tint = MaterialTheme.colorScheme.primary)
    Heading("Meet vBot", "Something\non your mind?", "Talk about your day, follow a curiosity, or make a plan. vBot keeps the conversation going while your chosen language becomes more familiar.")
    Text("vBot is powered by DeepSeek. Messages in this conversation are sent to Vipi and DeepSeek to generate replies. Your conversations with friends are never included automatically.", fontSize = 13.sp, lineHeight = 21.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    Text("Available with Bot mini", fontWeight = FontWeight.SemiBold)
}

@Composable private fun SettingsView(model: VipiModel) {
    Text("Your Vipi", fontFamily = FontFamily.Serif, fontSize = 34.sp)
    Text("Your immersion", fontWeight = FontWeight.SemiBold)
    Row(Modifier.fillMaxWidth().clickable { model.navigate(Screen.LANGUAGE_DOWNLOAD) }.padding(vertical = 14.dp)) { Text("Languages & downloads"); Spacer(Modifier.weight(1f)); Text(languageName(model.targetLanguage), color = MaterialTheme.colorScheme.onSurfaceVariant) }
    Column {
        Row { Text("A little or a little more"); Spacer(Modifier.weight(1f)); Text("${(model.density * 100).toInt()}%") }
        Slider(value = model.density.toFloat(), onValueChange = { model.changeDensity(it.toDouble()) }, valueRange = 0f..0.75f, steps = 14, modifier = Modifier.semantics { contentDescription = "Immersion amount" })
        Text("The amount of unfamiliar vocabulary you see. You can always reveal the original.", fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    Text("Appearance", fontWeight = FontWeight.SemiBold)
    Appearance.entries.forEach { appearance ->
        Row(Modifier.fillMaxWidth().clickable { model.changeAppearance(appearance) }.semantics { role = Role.RadioButton; selected = model.appearance == appearance }, verticalAlignment = Alignment.CenterVertically) {
            RadioButton(selected = model.appearance == appearance, onClick = { model.changeAppearance(appearance) }); Text(appearance.name.lowercase().replaceFirstChar { it.uppercase() })
        }
    }
    Text("Made by FallSoft.Co", fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable private fun DownloadView(model: VipiModel) {
    var cellular by rememberSaveable { mutableStateOf(false) }
    var text by rememberSaveable { mutableStateOf("Coffee tomorrow? I know a little place by the river.") }
    Heading("On your phone", languageName(model.targetLanguage), "Download this language once to translate without a connection. Models are usually around 30 MB per language.")
    Row(verticalAlignment = Alignment.CenterVertically) { Switch(checked = cellular, onCheckedChange = { cellular = it }); Spacer(Modifier.width(12.dp)); Text("Allow mobile data") }
    PrimaryButton("Download language", busy = model.modelBusy) { model.downloadLanguage(cellular) }
    model.modelMessage?.let { Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    OutlinedTextField(value = text, onValueChange = { text = it }, label = { Text("Try a sentence") }, modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(16.dp))
    TextButton(onClick = { model.translate(text) }, enabled = !model.modelBusy && text.isNotBlank()) { Text("Translate on this phone") }
    model.translatedText?.let { Text(it, Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, RoundedCornerShape(20.dp)).padding(20.dp), lineHeight = 25.sp) }
    Text("Translation by Google. Translations can be imperfect.", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
}
