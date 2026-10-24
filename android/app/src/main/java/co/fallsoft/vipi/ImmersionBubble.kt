package co.fallsoft.vipi

import android.view.accessibility.AccessibilityManager
import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
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
import co.fallsoft.vipi.core.ImmersionResult
import co.fallsoft.vipi.core.SpeechSpan
import kotlinx.coroutines.delay

/** Continuous, lifecycle-owned alternation. No per-word timer or network work. */
@Composable internal fun ImmersionBubble(
    result: ImmersionResult, mode: ReadingMode, speech: SpeechPlayback? = null,
    source: String = "en", target: String = "es", messageID: String = "onboarding-example",
    interactionPaused: Boolean = false, targetDwellMs: Long = 4500, meaningDwellMs: Long = 3000, fullReading: String? = null
) {
    var originalPhase by remember(result) { mutableStateOf(false) }
    var overrides by remember(result) { mutableStateOf(mapOf<Int, Boolean>()) }
    var paused by remember(result) { mutableStateOf(false) }
    var script by remember(result) { mutableStateOf(false) }
    var selecting by remember { mutableStateOf(false) }
    var visible by remember { mutableStateOf(false) }
    var resumed by remember { mutableStateOf(false) }
    var menu by remember { mutableStateOf(false) }
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
    val eligible = visible && resumed && !paused && !selecting && !interactionPaused && !active && !screenReader && mode == ReadingMode.IMMERSED && result.spans.isNotEmpty()
    val revealed = result.spans.filter { overrides[it.id] ?: originalPhase }.map { it.id }.toSet()
    LaunchedEffect(eligible, result, revision, pace) {
        if (eligible) while (true) {
            val dwell = if (originalPhase) meaningDwellMs else targetDwellMs
            delay(when (pace) { "relaxed" -> dwell * 2; "brisk" -> dwell / 2; else -> dwell })
            originalPhase = !originalPhase; overrides = emptyMap()
        }
    }
    LaunchedEffect(result, mode) { speech?.stop(); overrides = emptyMap(); revision++ }
    val accent = MaterialTheme.colorScheme.primary.toArgb()
    val ink = MaterialTheme.colorScheme.onSurface.toArgb()
    val canShowScript = fullReading != null || result.spans.any { it.romanization != null }
    fun reveal(id: Int) {
        speech?.stop(); overrides = overrides + (id to !(overrides[id] ?: originalPhase)); revision++
    }
    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, RoundedCornerShape(23.dp))
        .padding(start = 20.dp, end = 12.dp, top = 20.dp, bottom = 6.dp)
        .onGloballyPositioned {
            val bounds = it.boundsInWindow()
            visible = bounds.width > 0 && bounds.height > 0 && bounds.bottom > 0 && bounds.top < root.height && bounds.right > 0 && bounds.left < root.width
        }) {
        if (mode == ReadingMode.IMMERSED) {
            AndroidView(factory = { StableImmersionText(it) }, modifier = Modifier.fillMaxWidth().semantics {
                customActions = result.spans.map { word -> CustomAccessibilityAction("Switch ${word.original} and ${word.displayedTarget}") { reveal(word.id); true } }
            }, update = {
                it.onWord = { id -> reveal(id) }; it.onSelection = { value -> selecting = value }
                it.bind(result, revealed, script, accent, ink)
            })
        } else {
            androidx.compose.foundation.text.selection.SelectionContainer {
                Text(if (mode == ReadingMode.ORIGINAL) result.original else if (script) result.translation else (fullReading ?: result.translation), fontSize = 17.sp, lineHeight = 27.sp)
            }
        }
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            if (mode == ReadingMode.IMMERSED && result.spans.isNotEmpty()) {
                IconButton(onClick = { paused = !paused; revision++ }, modifier = Modifier.size(44.dp)) {
                    Icon(if (paused) Icons.Outlined.PlayArrow else Icons.Outlined.Pause, if (paused) "Resume word switching" else "Pause word switching", Modifier.size(18.dp))
                }
            }
            if (result.spans.isNotEmpty() || fullReading != null) {
                Box {
                    IconButton(onClick = { menu = true }, modifier = Modifier.size(44.dp)) { Icon(Icons.Outlined.MoreHoriz, "Reading options", Modifier.size(18.dp)) }
                    DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                        listOf("relaxed" to "Relaxed pace", "balanced" to "Balanced pace", "brisk" to "Brisk pace").forEach { (key, title) ->
                            DropdownMenuItem(text = { Text(title) }, leadingIcon = { if (pace == key) Icon(Icons.Outlined.Check, null) },
                                onClick = { preferences.edit().putString("readingPace", key).apply(); menu = false })
                        }
                        if (canShowScript) DropdownMenuItem(text = { Text(if (script) "Show transliteration" else "Show original script") }, onClick = { script = !script; menu = false; revision++ })
                        if (mode == ReadingMode.IMMERSED) DropdownMenuItem(text = { Text("Show meanings now") }, onClick = { speech?.stop(); originalPhase = true; overrides = emptyMap(); revision++; menu = false })
                        DropdownMenuItem(text = { Text("Copy original message") }, onClick = {
                            (context.getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager).setPrimaryClip(android.content.ClipData.newPlainText("Message", result.original)); menu = false
                        })
                    }
                }
            }
            Spacer(Modifier.weight(1f))
            if (speech != null) TextButton(onClick = {
                val spans = when (mode) {
                    ReadingMode.ORIGINAL -> listOf(SpeechSpan(result.original, source))
                    ReadingMode.TRANSLATION -> listOf(SpeechSpan(result.translation, target))
                    ReadingMode.IMMERSED -> result.speech(source, target, revealed)
                }
                speech.toggle(messageID, spans)
            }, enabled = speech.state !in setOf(SpeechState.PREPARING, SpeechState.UNAVAILABLE)) {
                if (speech.state == SpeechState.PREPARING || (active && speech.state == SpeechState.RENDERING)) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                else Icon(if (active) Icons.Outlined.Stop else Icons.Outlined.VolumeUp, null, Modifier.size(18.dp))
                Spacer(Modifier.width(7.dp)); Text(if (active) "Stop" else if (speech.state == SpeechState.PREPARING) "Preparing voices" else "Listen", fontSize = 13.sp)
            }
        }
    }
}
