package co.fallsoft.vipi

import android.view.accessibility.AccessibilityManager
import android.content.Context
import androidx.compose.foundation.background
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
import co.fallsoft.vipi.core.SpeechSpan
import kotlinx.coroutines.delay

/** Continuous, lifecycle-owned alternation. No per-word timer or network work. */
@Composable internal fun ImmersionBubble(
    result: ImmersionPresentation, mode: ReadingMode, speech: SpeechPlayback? = null,
    source: String = "en", target: String = "es", messageID: String = "onboarding-example",
    interactionPaused: Boolean = false, targetDwellMs: Long = 4500, meaningDwellMs: Long = 3000, fullReading: String? = null,
    embedded: Boolean = false, onModeChange: ((ReadingMode) -> Unit)? = null, metadata: (@Composable () -> Unit)? = null,
    onVoiceHelp: (() -> Unit)? = null,
    originalMessage: String? = null, inputLanguage: String? = null, onInputLanguage: ((String?) -> Unit)? = null,
    onInteractionChange: ((Boolean) -> Unit)? = null, onReport: (() -> Unit)? = null
) {
    // A partial result has no full-target text. Do not expose empty/mixed text as translation.
    val completeTranslation = result.translation
    val effectiveMode = if (mode == ReadingMode.TRANSLATION && completeTranslation == null) ReadingMode.IMMERSED else mode
    var originalPhase by remember(result) { mutableStateOf(false) }
    var overrides by remember(result) { mutableStateOf(mapOf<Int, Boolean>()) }
    var paused by remember(result) { mutableStateOf(false) }
    var choosingWord by remember(result) { mutableStateOf(false) }
    var choosingPace by remember(result) { mutableStateOf(false) }
    var script by remember(result) { mutableStateOf(false) }
    var selecting by remember { mutableStateOf(false) }
    var visible by remember { mutableStateOf(false) }
    var resumed by remember { mutableStateOf(false) }
    var menu by remember { mutableStateOf(false) }
    var chooseLanguage by remember { mutableStateOf(false) }
    SideEffect { onInteractionChange?.invoke(menu || chooseLanguage || selecting || choosingWord || choosingPace) }
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
    val eligible = visible && resumed && !paused && !selecting && !choosingWord && !choosingPace && !menu && !chooseLanguage && !interactionPaused && speech?.activeMessage == null && !screenReader && effectiveMode == ReadingMode.IMMERSED && result.spans.isNotEmpty()
    val revealed = result.spans.filter { overrides[it.id] ?: originalPhase }.map { it.id }.toSet()
    LaunchedEffect(eligible, result, revision, pace) {
        if (!eligible) return@LaunchedEffect
        if (embedded) delay((messageID.hashCode().toLong() and 0xffffffffL) % 1200)
        while (true) {
            val dwell = if (originalPhase) meaningDwellMs else targetDwellMs
            delay(when (pace) { "relaxed" -> dwell * 2; "brisk" -> dwell / 2; else -> dwell })
            originalPhase = !originalPhase; overrides = emptyMap()
        }
    }
    LaunchedEffect(result, effectiveMode) { if (speech?.activeMessage == messageID) speech.stop(); overrides = emptyMap(); revision++ }
    val accent = MaterialTheme.colorScheme.primary.toArgb()
    val ink = MaterialTheme.colorScheme.onSurface.toArgb()
    val canShowScript = (effectiveMode == ReadingMode.TRANSLATION && fullReading != null) ||
        (effectiveMode == ReadingMode.IMMERSED && result.spans.any { it.romanization != null })
    fun reveal(id: Int) {
        speech?.stop(); overrides = overrides + (id to !(overrides[id] ?: originalPhase)); revision++
    }
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
        }) {
        if (effectiveMode == ReadingMode.IMMERSED) {
            AndroidView(factory = { StableImmersionText(it) }, modifier = Modifier.fillMaxWidth(), update = {
                it.onWord = { id -> reveal(id) }; it.onSelection = { value -> selecting = value }
                it.onChooseWord = { choosingWord = true }
                it.bind(result, revealed, script, accent, ink)
            })
        } else {
            androidx.compose.foundation.text.selection.SelectionContainer {
                Text(if (effectiveMode == ReadingMode.ORIGINAL) result.original else if (script) requireNotNull(completeTranslation) else (fullReading ?: requireNotNull(completeTranslation)), fontSize = 17.sp, lineHeight = 27.sp)
            }
        }
        if (choosingWord) AlertDialog(onDismissRequest = { choosingWord = false },
            title = { Text("Switch a word") },
            text = { LazyColumn { items(result.spans, key = { it.id }) { word ->
                TextButton(onClick = { reveal(word.id); choosingWord = false }, modifier = Modifier.fillMaxWidth()) {
                    Text("${word.original} · ${word.displayedTarget}")
                }
            } } }, confirmButton = { TextButton(onClick = { choosingWord = false }) { Text("Done") } })
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            if (embedded) { Box(Modifier.weight(1f)) { metadata?.invoke() } }
            if (!embedded && effectiveMode == ReadingMode.IMMERSED && result.spans.isNotEmpty() && !screenReader) {
                IconButton(onClick = { paused = !paused; revision++ }, modifier = Modifier.size(44.dp)) {
                    Icon(if (paused) Icons.Outlined.PlayArrow else Icons.Outlined.Pause, if (paused) "Resume word switching" else "Pause word switching", Modifier.size(18.dp))
                }
            }
            if (result.spans.isNotEmpty() || fullReading != null || onModeChange != null) {
                Box {
                    IconButton(onClick = { onInteractionChange?.invoke(true); menu = true }, modifier = Modifier.size(44.dp)) { Icon(Icons.Outlined.MoreHoriz, "Reading options", Modifier.size(18.dp)) }
                    DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                        if (embedded) {
                            if (speech != null) DropdownMenuItem(text = { Text(if (active) "Stop listening" else if (speech.state == SpeechState.PREPARING) "Preparing voices…" else if (speech.state == SpeechState.UNAVAILABLE) "Set up voices" else "Listen") },
                                enabled = speech.state != SpeechState.PREPARING && (speech.state != SpeechState.UNAVAILABLE || onVoiceHelp != null),
                                onClick = { if (speech.state == SpeechState.UNAVAILABLE) onVoiceHelp?.invoke() else listen(); menu = false })
                            if (effectiveMode == ReadingMode.IMMERSED && result.spans.isNotEmpty() && !screenReader) DropdownMenuItem(text = { Text(if (paused) "Resume word switching" else "Pause word switching") },
                                onClick = { paused = !paused; revision++; menu = false })
                        }
                        if (onModeChange != null) ReadingMode.entries.filter { it != ReadingMode.TRANSLATION || completeTranslation != null }.forEach { value ->
                            val title = if (!embedded || value == ReadingMode.IMMERSED) value.label else languageName(if (value == ReadingMode.ORIGINAL) source else target)
                            DropdownMenuItem(text = { Text(title) }, leadingIcon = { if (effectiveMode == value) Icon(Icons.Outlined.Check, null) },
                                onClick = { onModeChange(value); menu = false })
                        }
                        if (completeTranslation == null) DropdownMenuItem(text = { Text("Full translation isn’t ready") }, enabled = false, onClick = {})
                        if (canShowScript) DropdownMenuItem(text = { Text(if (script) "Show transliteration" else "Show original script") }, onClick = { script = !script; menu = false; revision++ })
                        if (effectiveMode == ReadingMode.IMMERSED && result.spans.isNotEmpty() && !screenReader) DropdownMenuItem(text = { Text("Switching pace") }, onClick = { choosingPace = true; menu = false })
                        if (effectiveMode == ReadingMode.IMMERSED && result.spans.isNotEmpty()) DropdownMenuItem(text = { Text("Show meanings now") }, onClick = { speech?.stop(); originalPhase = true; overrides = emptyMap(); revision++; menu = false })
                        if (onInputLanguage != null) DropdownMenuItem(text = { Text("Message language") }, onClick = { chooseLanguage = true; menu = false })
                        DropdownMenuItem(text = { Text("Copy original message") }, onClick = {
                            (context.getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager).setPrimaryClip(android.content.ClipData.newPlainText("Message", originalMessage ?: result.original)); menu = false
                        })
                        if (onReport != null) DropdownMenuItem(text = { Text("Report reply") }, onClick = { menu = false; onReport() })
                    }
                }
            }
            if (!embedded) Spacer(Modifier.weight(1f))
            if (!embedded && speech != null) TextButton(onClick = { listen() }, enabled = speech.state !in setOf(SpeechState.PREPARING, SpeechState.UNAVAILABLE)) {
                if (speech.state == SpeechState.PREPARING || (active && speech.state == SpeechState.RENDERING)) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                else Icon(if (active) Icons.Outlined.Stop else Icons.Outlined.VolumeUp, null, Modifier.size(18.dp))
                Spacer(Modifier.width(7.dp)); Text(if (active) "Stop" else if (speech.state == SpeechState.PREPARING) "Preparing voices" else "Listen", fontSize = 13.sp)
            }
        }
    }
    if (chooseLanguage && onInputLanguage != null) MessageLanguageDialog(source, target, inputLanguage,
        onSelect = { speech?.stop(); onInputLanguage(it); chooseLanguage = false }, dismiss = { chooseLanguage = false })
    if (choosingPace) AlertDialog(onDismissRequest = { choosingPace = false }, title = { Text("Switching pace") },
        text = { Column {
            listOf("relaxed" to "Relaxed", "balanced" to "Balanced", "brisk" to "Brisk").forEach { (key, title) ->
                TextButton(onClick = { preferences.edit().putString("readingPace", key).apply(); choosingPace = false },
                    modifier = Modifier.fillMaxWidth().semantics { selected = pace == key }) {
                    if (pace == key) Icon(Icons.Outlined.Check, null, modifier = Modifier.padding(end = 8.dp))
                    Text(title)
                }
            }
        } }, confirmButton = { TextButton(onClick = { choosingPace = false }) { Text("Cancel") } })
}

@Composable internal fun MessageLanguageDialog(source: String, target: String, selected: String?, onSelect: (String?) -> Unit, dismiss: () -> Unit) {
    AlertDialog(onDismissRequest = dismiss, title = { Text("Message language") },
        text = { Column {
            listOf<String?>(null, source, target).forEach { code ->
                val isSelected = code == selected
                TextButton(onClick = { onSelect(code) }, modifier = Modifier.fillMaxWidth().semantics { this.selected = isSelected }) {
                    if (code == selected) Icon(Icons.Outlined.Check, null, modifier = Modifier.padding(end = 8.dp))
                    Text(code?.let(::languageName) ?: "Detect automatically")
                }
            }
        } }, confirmButton = { TextButton(onClick = dismiss) { Text("Cancel") } })
}

@Composable internal fun UntranslatedMessageActions(text: String, source: String, target: String, selected: String?,
    onLanguage: (String?) -> Unit, metadata: @Composable () -> Unit) {
    val context = LocalContext.current
    var menu by remember { mutableStateOf(false) }; var choose by remember { mutableStateOf(false) }
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.weight(1f)) { metadata() }
        Box {
            IconButton(onClick = { menu = true }, modifier = Modifier.size(44.dp)) { Icon(Icons.Outlined.MoreHoriz, "Reading options", Modifier.size(18.dp)) }
            DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                DropdownMenuItem(text = { Text("Message language") }, onClick = { choose = true; menu = false })
                DropdownMenuItem(text = { Text("Copy original message") }, onClick = {
                    (context.getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager)
                        .setPrimaryClip(android.content.ClipData.newPlainText("Message", text)); menu = false
                })
            }
        }
    }
    if (choose) MessageLanguageDialog(source, target, selected, onSelect = { onLanguage(it); choose = false }, dismiss = { choose = false })
}
