package co.fallsoft.vipi

import android.view.accessibility.AccessibilityManager
import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.ui.res.stringResource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.layout.boundsInWindow
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.semantics.*
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import co.fallsoft.vipi.core.ImmersionPresentation
import co.fallsoft.vipi.core.ImmersionSpan
import co.fallsoft.vipi.core.ImmersionStatus
import co.fallsoft.vipi.core.SpeechSpan
import kotlinx.coroutines.delay

private data class InlineReadingIdentity(val original: String, val spans: List<ImmersionSpan>, val source: String, val target: String)
private data class WholeReadingIdentity(val mode: ReadingMode, val text: String, val language: String)

/** Continuous, lifecycle-owned alternation. No per-word timer or network work. */
@Composable internal fun ImmersionBubble(
    result: ImmersionPresentation, mode: ReadingMode, speech: SpeechPlayback? = null,
    source: String = "en", target: String = "es", messageID: String = "onboarding-example",
    interactionPaused: Boolean = false, targetDwellMs: Long = 4500, meaningDwellMs: Long = 3000, fullReading: String? = null,
    embedded: Boolean = false, onModeChange: ((ReadingMode) -> Unit)? = null, metadata: (@Composable () -> Unit)? = null,
    onVoiceHelp: (() -> Unit)? = null,
    originalMessage: String? = null, inputLanguage: String? = null, onInputLanguage: ((String?) -> Unit)? = null,
    onInteractionChange: ((Boolean) -> Unit)? = null, onReport: (() -> Unit)? = null,
    onFullTranslation: (() -> Unit)? = null, fullTranslationLoading: Boolean = false,
    fullTranslationError: ImmersionStatus? = null, onCancelFullTranslation: (() -> Unit)? = null,
    onTranslationSetup: (() -> Unit)? = null, contextualActions: Boolean = false,
    onExposure: ((List<co.fallsoft.vipi.core.ImmersionSpan>) -> Unit)? = null
) {
    val readingOptionsDescription = stringResource(R.string.ui_e52b25aa61b5)
    val translatingDescription = stringResource(R.string.ui_f1c94d2fa211)
    require(!contextualActions || BuildConfig.DEBUG)
    val nativeActions = contextualActions && embedded
    // A partial result has no full-target text. Do not expose empty/mixed text as translation.
    val completeTranslation = result.translation
    val effectiveMode = if (mode == ReadingMode.TRANSLATION && completeTranslation == null) ReadingMode.IMMERSED else mode
    // Attaching a hidden complete reference must not restart the visible slots,
    // erase a chosen face, or interrupt mixed-language speech.
    val inlineIdentity = InlineReadingIdentity(result.original, result.spans, source, target)
    val visibleIdentity: Any = when (effectiveMode) {
        ReadingMode.IMMERSED -> inlineIdentity
        ReadingMode.ORIGINAL -> WholeReadingIdentity(effectiveMode, result.original, source)
        ReadingMode.TRANSLATION -> WholeReadingIdentity(effectiveMode, requireNotNull(completeTranslation), target)
    }
    var originalPhase by remember(inlineIdentity) { mutableStateOf(false) }
    var overrides by remember(inlineIdentity) { mutableStateOf(mapOf<Int, Boolean>()) }
    var paused by remember(inlineIdentity) { mutableStateOf(false) }
    var choosingWord by remember(inlineIdentity) { mutableStateOf(false) }
    var choosingPace by remember(inlineIdentity) { mutableStateOf(false) }
    var script by remember(inlineIdentity) { mutableStateOf(false) }
    var selecting by remember { mutableStateOf(false) }
    var selectText by remember(visibleIdentity) { mutableStateOf(false) }
    var visible by remember { mutableStateOf(false) }
    var exposureVisible by remember { mutableStateOf(false) }
    var resumed by remember { mutableStateOf(false) }
    var menu by remember { mutableStateOf(false) }
    var chooseLanguage by remember { mutableStateOf(false) }
    SideEffect { onInteractionChange?.invoke(menu || chooseLanguage || selecting || selectText || choosingWord || choosingPace) }
    var revision by remember { mutableIntStateOf(0) }
    val context = LocalContext.current
    val preferences = remember { context.getSharedPreferences("preferences", 0) }
    var pace by remember { mutableStateOf(preferences.getString("readingPace", "balanced") ?: "balanced") }
    DisposableEffect(preferences) {
        val listener = android.content.SharedPreferences.OnSharedPreferenceChangeListener { value, key -> if (key == "readingPace") pace = value.getString(key, "balanced") ?: "balanced" }
        preferences.registerOnSharedPreferenceChangeListener(listener)
        onDispose { preferences.unregisterOnSharedPreferenceChangeListener(listener) }
    }
    val owner = LocalLifecycleOwner.current
    val root = LocalView.current
    val accessibility = remember { context.getSystemService(Context.ACCESSIBILITY_SERVICE) as AccessibilityManager }
    var screenReader by remember { mutableStateOf(accessibility.isTouchExplorationEnabled) }
    DisposableEffect(owner, accessibility) {
        resumed = owner.lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)
        val lifecycle = LifecycleEventObserver { _, _ ->
            resumed = owner.lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)
            if (!resumed && speech?.activeMessage == messageID) speech.stop()
        }
        val listener = AccessibilityManager.TouchExplorationStateChangeListener { screenReader = it }
        owner.lifecycle.addObserver(lifecycle); accessibility.addTouchExplorationStateChangeListener(listener)
        onDispose { owner.lifecycle.removeObserver(lifecycle); accessibility.removeTouchExplorationStateChangeListener(listener); if (speech?.activeMessage == messageID) speech.stop() }
    }
    val active = speech?.activeMessage == messageID
    val eligible = visible && resumed && !paused && !selecting && !selectText && !choosingWord && !choosingPace && !menu && !chooseLanguage && !interactionPaused && speech?.activeMessage == null && !screenReader && effectiveMode == ReadingMode.IMMERSED && result.spans.isNotEmpty()
    // Opt-in local QA diagnostics contain no message text or account identifiers.
    if (BuildConfig.DEBUG && android.util.Log.isLoggable("VipiFlip", android.util.Log.DEBUG)) {
        val reasons = "visible=$visible resumed=$resumed paused=$paused selecting=$selecting word=$choosingWord pace=$choosingPace menu=$menu language=$chooseLanguage interaction=$interactionPaused speaking=${speech?.activeMessage != null} reader=$screenReader mode=$effectiveMode spans=${result.spans.size}"
        LaunchedEffect(messageID, eligible, reasons) {
            android.util.Log.d("VipiFlip", "row=${messageID.hashCode()} eligible=$eligible $reasons")
        }
    }
    val revealed = result.spans.filter { overrides[it.id] ?: originalPhase }.map { it.id }.toSet()
    LaunchedEffect(eligible, exposureVisible, inlineIdentity, revision, pace) {
        if (!eligible) return@LaunchedEffect
        if (embedded) delay((messageID.hashCode().toLong() and 0xffffffffL) % 1200)
        while (true) {
            val dwell = if (originalPhase) meaningDwellMs else targetDwellMs
            delay(when (pace) { "relaxed" -> dwell * 2; "brisk" -> dwell / 2; else -> dwell })
            if (!originalPhase && exposureVisible) onExposure?.invoke(result.spans.filter { overrides[it.id] != true })
            originalPhase = !originalPhase; overrides = emptyMap()
        }
    }
    LaunchedEffect(visibleIdentity) { if (speech?.activeMessage == messageID) speech.stop(); overrides = emptyMap(); revision++ }
    val accent = MaterialTheme.colorScheme.primary.toArgb()
    val ink = MaterialTheme.colorScheme.onSurface.toArgb()
    val canShowScript = (effectiveMode == ReadingMode.TRANSLATION && fullReading != null) ||
        (effectiveMode == ReadingMode.IMMERSED && result.spans.any { it.romanization != null })
    fun reveal(id: Int) {
        speech?.stop(); overrides = overrides + (id to !(overrides[id] ?: originalPhase)); revision++
    }
    fun messageActions() { onInteractionChange?.invoke(true); menu = true }
    fun listen() {
        val spans = when (effectiveMode) {
            ReadingMode.ORIGINAL -> listOf(SpeechSpan(result.original, source))
            ReadingMode.TRANSLATION -> listOf(SpeechSpan(requireNotNull(completeTranslation), target))
            ReadingMode.IMMERSED -> result.speech(source, target, revealed)
        }
        speech?.toggle(messageID, spans)
    }
    Column(Modifier.fillMaxWidth().background(if (embedded) androidx.compose.ui.graphics.Color.Transparent else MaterialTheme.colorScheme.surface, RoundedCornerShape(23.dp))
        .padding(start = if (embedded) 0.dp else 20.dp, end = if (embedded) 0.dp else 12.dp, top = if (embedded) 0.dp else 20.dp, bottom = if (embedded) 0.dp else 6.dp)
        .onGloballyPositioned {
            val bounds = it.boundsInWindow()
            visible = bounds.width > 0 && bounds.height > 0 && bounds.bottom > 0 && bounds.top < root.height && bounds.right > 0 && bounds.left < root.width
            // boundsInWindow is clipped by ancestors: compare with measured size
            // before treating a partially scrolled bubble as a complete exposure.
            exposureVisible = visible && bounds.width >= it.size.width - 1 && bounds.height >= it.size.height - 1 &&
                bounds.top >= 0 && bounds.bottom <= root.height && bounds.left >= 0 && bounds.right <= root.width
        }) {
        if (effectiveMode == ReadingMode.IMMERSED) {
            AndroidView(factory = { StableImmersionText(it) }, modifier = Modifier.fillMaxWidth(), update = {
                it.onWord = { id -> reveal(id) }; it.onSelection = { value -> selecting = value }
                it.onChooseWord = { choosingWord = true }
                it.bind(result, revealed, script, accent, ink)
                it.configureMessageActions(if (nativeActions) ::messageActions else null, selectText) { selectText = false; selecting = false; revision++ }
            })
        } else if (nativeActions) {
            val displayed = if (effectiveMode == ReadingMode.ORIGINAL) result.original else if (script) requireNotNull(completeTranslation) else (fullReading ?: requireNotNull(completeTranslation))
            val plain = remember(displayed) { object : ImmersionPresentation {
                override val original = displayed
                override val translation: String? = null
                override val spans = emptyList<ImmersionSpan>()
            } }
            AndroidView(factory = { StableImmersionText(it).apply {
                setLineHeight(android.util.TypedValue.applyDimension(android.util.TypedValue.COMPLEX_UNIT_SP, 27f, resources.displayMetrics).toInt())
            } }, modifier = Modifier.fillMaxWidth(), update = {
                it.onWord = null; it.onChooseWord = null; it.onSelection = { value -> selecting = value }
                it.bind(plain, emptySet(), false, accent, ink)
                it.configureMessageActions(::messageActions, selectText) { selectText = false; selecting = false; revision++ }
            })
        } else {
            androidx.compose.foundation.text.selection.SelectionContainer {
                Text(if (effectiveMode == ReadingMode.ORIGINAL) result.original else if (script) requireNotNull(completeTranslation) else (fullReading ?: requireNotNull(completeTranslation)), fontSize = 17.sp, lineHeight = 27.sp)
            }
        }
        if (choosingWord) AlertDialog(onDismissRequest = { choosingWord = false },
            title = { Text(stringResource(R.string.ui_4a3ddf33db23)) },
            text = { LazyColumn { items(result.spans, key = { it.id }) { word ->
                TextButton(onClick = { reveal(word.id); choosingWord = false }, modifier = Modifier.fillMaxWidth()) {
                    Text("${word.original} · ${word.displayedTarget}")
                }
            } } }, confirmButton = { TextButton(onClick = { choosingWord = false }) { Text(stringResource(R.string.ui_11a6767d5674)) } })
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            if (embedded) { Box(Modifier.weight(1f)) { metadata?.invoke() } }
            if (embedded && active && speech != null) {
                TextButton(onClick = { speech.stop() }) {
                    Icon(Icons.Outlined.Stop, null, Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text(stringResource(R.string.ui_cae7d57bc067))
                }
            }
            if (!embedded && effectiveMode == ReadingMode.IMMERSED && result.spans.isNotEmpty() && !screenReader) {
                IconButton(onClick = { paused = !paused; revision++ }, modifier = Modifier.size(44.dp)) {
                    Icon(if (paused) Icons.Outlined.PlayArrow else Icons.Outlined.Pause, if (paused) stringResource(R.string.ui_cc245f2e3a71) else stringResource(R.string.ui_37f6135c049a), Modifier.size(18.dp))
                }
            }
            if (result.spans.isNotEmpty() || fullReading != null || onModeChange != null) {
                Box {
                    if (!nativeActions) IconButton(onClick = { onInteractionChange?.invoke(true); menu = true }, modifier = Modifier.size(44.dp).semantics {
                        if (fullTranslationLoading) stateDescription = translatingDescription
                    }) {
                        if (fullTranslationLoading) CircularProgressIndicator(Modifier.size(18.dp).semantics { contentDescription = readingOptionsDescription }, strokeWidth = 2.dp)
                        else Icon(Icons.Outlined.MoreHoriz, stringResource(R.string.ui_e52b25aa61b5), Modifier.size(18.dp))
                    }
                    DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                        if (embedded) {
                            if (speech != null) DropdownMenuItem(text = { Text(if (active) stringResource(R.string.ui_94fa9b236332) else if (speech.state == SpeechState.PREPARING) stringResource(R.string.ui_f4cfeca151e1) else if (speech.state == SpeechState.UNAVAILABLE) stringResource(R.string.ui_f826885bfb23) else stringResource(R.string.ui_225d29f6201e)) },
                                enabled = speech.state != SpeechState.PREPARING && (speech.state != SpeechState.UNAVAILABLE || onVoiceHelp != null),
                                onClick = { if (speech.state == SpeechState.UNAVAILABLE) onVoiceHelp?.invoke() else listen(); menu = false })
                            if (effectiveMode == ReadingMode.IMMERSED && result.spans.isNotEmpty() && !screenReader) DropdownMenuItem(text = { Text(if (paused) stringResource(R.string.ui_cc245f2e3a71) else stringResource(R.string.ui_37f6135c049a)) },
                                onClick = { paused = !paused; revision++; menu = false })
                        }
                        if (onModeChange != null) ReadingMode.entries.filter { it != ReadingMode.TRANSLATION || completeTranslation != null || onFullTranslation != null }.forEach { value ->
                            val missingFull = value == ReadingMode.TRANSLATION && completeTranslation == null
                            val title = when {
                                missingFull && fullTranslationLoading -> stringResource(R.string.translating_language, languageName(target))
                                missingFull && fullTranslationError == ImmersionStatus.MODEL_NOT_READY -> stringResource(R.string.full_translation_download)
                                missingFull && fullTranslationError != null -> stringResource(R.string.full_translation_retry)
                                value == ReadingMode.IMMERSED -> stringResource(R.string.reading_word_switching)
                                value == ReadingMode.ORIGINAL -> stringResource(R.string.reading_original)
                                else -> stringResource(R.string.reading_full)
                            }
                            DropdownMenuItem(text = { Text(title) }, leadingIcon = { if (effectiveMode == value) Icon(Icons.Outlined.Check, null) },
                                enabled = !missingFull || !fullTranslationLoading,
                                onClick = {
                                    if (missingFull && fullTranslationError == ImmersionStatus.MODEL_NOT_READY && onTranslationSetup != null) onTranslationSetup()
                                    else if (missingFull) onFullTranslation?.invoke()
                                    else onModeChange(value)
                                    menu = false
                                })
                        }
                        if (fullTranslationLoading && onCancelFullTranslation != null)
                            DropdownMenuItem(text = { Text(stringResource(R.string.ui_4bc6d965deeb)) }, onClick = { onCancelFullTranslation(); menu = false })
                        if (completeTranslation == null && fullTranslationError != null) Text(when (fullTranslationError) {
                            ImmersionStatus.MODEL_NOT_READY -> stringResource(R.string.translation_pair_download_needed)
                            ImmersionStatus.TIMEOUT -> stringResource(R.string.translation_timeout)
                            ImmersionStatus.INVALID_LANGUAGE -> stringResource(R.string.translation_language_needed)
                            else -> stringResource(R.string.translation_failed)
                        }, modifier = Modifier.widthIn(max = 280.dp).padding(horizontal = 16.dp, vertical = 12.dp),
                            style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        else if (completeTranslation == null && onFullTranslation == null)
                            DropdownMenuItem(text = { Text(stringResource(R.string.ui_78ff037cf508)) }, enabled = false, onClick = {})
                        if (canShowScript) DropdownMenuItem(text = { Text(if (script) stringResource(R.string.ui_93acaeeabd13) else stringResource(R.string.ui_127a78a187bd)) }, onClick = { script = !script; menu = false; revision++ })
                        if (effectiveMode == ReadingMode.IMMERSED && result.spans.isNotEmpty() && !screenReader) DropdownMenuItem(text = { Text(stringResource(R.string.ui_5de398810247)) }, onClick = { choosingPace = true; menu = false })
                        if (effectiveMode == ReadingMode.IMMERSED && result.spans.isNotEmpty()) DropdownMenuItem(text = { Text(stringResource(R.string.ui_0c42f5497c0b)) }, onClick = { speech?.stop(); originalPhase = true; overrides = emptyMap(); revision++; menu = false })
                        if (onInputLanguage != null) DropdownMenuItem(text = { Text(stringResource(R.string.ui_cbf7e254a8c0)) }, onClick = { chooseLanguage = true; menu = false })
                        if (nativeActions) DropdownMenuItem(text = { Text(stringResource(R.string.ui_3370146d6d46)) }, onClick = { selectText = true; menu = false })
                        DropdownMenuItem(text = { Text(stringResource(R.string.ui_b0f88f29b4b2)) }, onClick = {
                            (context.getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager).setPrimaryClip(android.content.ClipData.newPlainText(context.getString(R.string.message_hint), originalMessage ?: result.original)); menu = false
                        })
                        if (onReport != null) DropdownMenuItem(text = { Text(stringResource(R.string.ui_5480a088185c)) }, onClick = { menu = false; onReport() })
                    }
                }
            }
            if (!embedded) Spacer(Modifier.weight(1f))
            if (!embedded && speech != null) TextButton(onClick = { listen() }, enabled = speech.state !in setOf(SpeechState.PREPARING, SpeechState.UNAVAILABLE), colors = ButtonDefaults.textButtonColors(disabledContentColor = MaterialTheme.colorScheme.onSurfaceVariant)) {
                if (speech.state == SpeechState.PREPARING || (active && speech.state == SpeechState.RENDERING)) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                else Icon(if (active) Icons.Outlined.Stop else Icons.Outlined.VolumeUp, null, Modifier.size(18.dp))
                Spacer(Modifier.width(7.dp)); Text(if (active) stringResource(R.string.ui_cae7d57bc067) else if (speech.state == SpeechState.PREPARING) stringResource(R.string.ui_58fd7deb0abe) else stringResource(R.string.ui_225d29f6201e), fontSize = 13.sp)
            }
        }
    }
    if (chooseLanguage && onInputLanguage != null) MessageLanguageDialog(source, target, inputLanguage,
        onSelect = { speech?.stop(); onInputLanguage(it); chooseLanguage = false }, dismiss = { chooseLanguage = false })
    if (choosingPace) AlertDialog(onDismissRequest = { choosingPace = false }, title = { Text(stringResource(R.string.ui_5de398810247)) },
        text = { Column {
            listOf("relaxed" to R.string.reading_slower, "balanced" to R.string.reading_standard, "brisk" to R.string.reading_faster).forEach { (key, title) ->
                TextButton(onClick = { preferences.edit().putString("readingPace", key).apply(); choosingPace = false },
                    modifier = Modifier.fillMaxWidth().semantics { selected = pace == key }) {
                    if (pace == key) Icon(Icons.Outlined.Check, null, modifier = Modifier.padding(end = 8.dp))
                    Text(stringResource(title))
                }
            }
        } }, confirmButton = { TextButton(onClick = { choosingPace = false }) { Text(stringResource(R.string.cancel_action)) } })
}

@Composable internal fun MessageLanguageDialog(source: String, target: String, selected: String?, onSelect: (String?) -> Unit, dismiss: () -> Unit) {
    AlertDialog(onDismissRequest = dismiss, title = { Text(stringResource(R.string.ui_cbf7e254a8c0)) },
        text = { Column {
            listOf<String?>(null, source, target).forEach { code ->
                val isSelected = code == selected
                TextButton(onClick = { onSelect(code) }, modifier = Modifier.fillMaxWidth().semantics { this.selected = isSelected }) {
                    if (code == selected) Icon(Icons.Outlined.Check, null, modifier = Modifier.padding(end = 8.dp))
                    Text(code?.let(::languageName) ?: stringResource(R.string.language_detect_automatically))
                }
            }
        } }, confirmButton = { TextButton(onClick = dismiss) { Text(stringResource(R.string.cancel_action)) } })
}

@Composable internal fun UntranslatedMessageActions(text: String, source: String, target: String, selected: String?,
    onLanguage: (String?) -> Unit, metadata: @Composable () -> Unit) {
    val context = LocalContext.current
    var menu by remember { mutableStateOf(false) }; var choose by remember { mutableStateOf(false) }
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.weight(1f)) { metadata() }
        Box {
            IconButton(onClick = { menu = true }, modifier = Modifier.size(44.dp)) { Icon(Icons.Outlined.MoreHoriz, stringResource(R.string.ui_e52b25aa61b5), Modifier.size(18.dp)) }
            DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                DropdownMenuItem(text = { Text(stringResource(R.string.ui_cbf7e254a8c0)) }, onClick = { choose = true; menu = false })
                DropdownMenuItem(text = { Text(stringResource(R.string.ui_b0f88f29b4b2)) }, onClick = {
                    (context.getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager)
                        .setPrimaryClip(android.content.ClipData.newPlainText(context.getString(R.string.message_hint), text)); menu = false
                })
            }
        }
    }
    if (choose) MessageLanguageDialog(source, target, selected, onSelect = { onLanguage(it); choose = false }, dismiss = { choose = false })
}
