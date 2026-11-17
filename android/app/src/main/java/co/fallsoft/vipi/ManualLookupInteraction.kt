package co.fallsoft.vipi

import android.graphics.Rect
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.Stop
import androidx.compose.material.icons.outlined.VolumeUp
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.*
import androidx.compose.ui.window.Popup
import androidx.compose.ui.window.PopupPositionProvider
import androidx.compose.ui.window.PopupProperties
import co.fallsoft.vipi.core.ImmersionSpan
import co.fallsoft.vipi.core.SpeechSpan
import kotlinx.coroutines.*
import java.lang.ref.WeakReference

/** One transient, nonfocusable lookup. Native selection and Copy keep focus. */
internal class ManualLookupInteraction(
    private val immersion: ConversationImmersion, val speech: SpeechPlayback,
    private val messageID: String, private val original: String, private val scope: CoroutineScope
) {
    companion object {
        private var active: WeakReference<ManualLookupInteraction>? = null
        fun cancelActive() { active?.get()?.cancel() }
        fun textGestureBegan() { active?.get()?.haltForTouch() }
    }
    var request by mutableStateOf<ManualTranslationRequest?>(null); private set
    var outcome by mutableStateOf<ManualTranslationOutcome?>(null); private set
    var audioID by mutableStateOf<String?>(null); private set
    var audioError by mutableStateOf<String?>(null); private set
    var preparingAudio by mutableStateOf(false); private set
    var visible by mutableStateOf(false); private set
    var anchor by mutableStateOf(Rect()); private set
    var foreground = true
    var interactionPaused = false
    private var generation = 0L
    private var job: Job? = null
    private var view = WeakReference<StableImmersionText>(null)
    private var selected = 0 until 0
    private var covered: ImmersionSpan? = null
    private var coveredLanguage: String? = null
    private var stoppedRange: IntRange? = null
    private var stoppedAt = 0L
    val supportedPair get() = listOf(immersion.source, immersion.target).all { it in com.google.mlkit.nl.translate.TranslateLanguage.getAllLanguages() }
    private fun haltForTouch() {
        // Popup dismissal and the pass-through TextView DOWN can describe the
        // same gesture. The second notification must preserve its Stop token.
        if (!visible && !loading && !speaking && !preparingAudio) return
        val interrupted = loading || speaking || preparingAudio
        val previous = selected
        cancel()
        if (interrupted) { stoppedRange = previous; stoppedAt = android.os.SystemClock.uptimeMillis() }
    }
    fun dismissForTouch() { haltForTouch() }
    private fun hasPendingTouchStop(): Boolean {
        if (stoppedRange == null) return false
        if (android.os.SystemClock.uptimeMillis() - stoppedAt < 700) return true
        stoppedRange = null; return false
    }
    /** A footer Stop may receive UP after outside dismissal already halted
     * playback on DOWN. Consume that gesture instead of starting generic audio. */
    fun consumeTouchStop(): Boolean {
        if (!hasPendingTouchStop()) return false
        stoppedRange = null; return true
    }
    private fun consumedStop(range: IntRange): Boolean {
        if (!hasPendingTouchStop() || stoppedRange != range) return false
        stoppedRange = null; return true
    }
    val loading get() = request != null && outcome == null
    val speaking get() = audioID != null && speech.activeMessage == audioID
    val sourceText get() = outcome?.result?.sourceContextText ?: request?.let(ManualTranslationResolver::slice) ?: covered?.original.orEmpty()
    val targetText get() = outcome?.result?.targetText ?: covered?.translated
    val reading get() = outcome?.result?.let { if (it.sourceLanguage == it.request.learningLanguage) it.sourceReading?.text else it.reading?.text } ?: covered?.romanization
    val pronunciationText get() = outcome?.result?.let { if (it.sourceLanguage == it.request.learningLanguage) it.sourceContextText else it.targetText } ?: covered?.translated
    val pronunciationLanguage get() = outcome?.result?.request?.learningLanguage ?: coveredLanguage
    val meaningText get() = outcome?.result?.let { if (it.sourceLanguage == it.request.learningLanguage) it.targetText else it.sourceContextText } ?: sourceText
    val targetLanguage get() = outcome?.result?.targetLanguage ?: coveredLanguage
    val missingReading get() = pronunciationText != null && pronunciationLanguage in setOf("ar", "zh", "ja", "ko") && reading == null
    fun bind(native: StableImmersionText) { view = WeakReference(native) }
    fun cancel() {
        generation++; job?.cancel(); job = null
        if (audioID != null && speech.activeMessage == audioID) speech.stop()
        audioID = null; request = null; outcome = null; preparingAudio = false; audioError = null; visible = false
        covered = null; coveredLanguage = null; stoppedRange = null
        if (active?.get() === this) active = null
    }
    private fun activate() { active?.get()?.cancel(); cancel(); active = WeakReference(this); speech.stop() }
    fun beginWhole() {
        if (loading || speaking || preparingAudio) { cancel(); return }
        view.get()?.let { begin(0, original.length, it) }
    }
    fun begin(start: Int, end: Int, native: StableImmersionText) {
        if (consumedStop(start until end)) return
        if (request?.startUTF16 == start && request?.endUTF16 == end && (loading || speaking)) { cancel(); return }
        activate(); bind(native); selected = start until end
        val sameSource = original.toByteArray(Charsets.UTF_8).contentEquals(native.displayedOriginal.toByteArray(Charsets.UTF_8))
        anchor = if (sameSource) native.sourceRangeRect(start, end) else native.sourceRangeRect(0, native.displayedOriginal.length)
        val produced = immersion.makeManualRequest(messageID, original, start, end, generation)
        request = produced; visible = true
        job = scope.launch {
            val value = immersion.manualTranslation(produced)
            ensureActive()
            if (request != produced || !foreground) return@launch
            if (value.status == ManualTranslationStatus.STALE) { cancel(); return@launch }
            outcome = value
            value.result?.takeIf { it.request == produced }?.let {
                val text = if (it.sourceLanguage == it.request.learningLanguage) it.sourceContextText else it.targetText
                play(text, it.request.learningLanguage, generation)
            }
        }
    }
    fun coveredWord(word: ImmersionSpan, language: String, native: StableImmersionText?) {
        if (consumedStop(word.start until word.end)) return
        activate(); selected = word.start until word.end; native?.let { bind(it); anchor = it.sourceRangeRect(word.start, word.end) }
        covered = word; coveredLanguage = language
        val produced = generation
        job = scope.launch { play(word.translated, language, produced) }
    }
    private suspend fun play(text: String, language: String, produced: Long) {
        if (!foreground || interactionPaused || generation != produced) return
        audioError = null
        preparingAudio = speech.state == SpeechState.PREPARING
        for (attempt in 0 until 160) {
            currentCoroutineContext().ensureActive()
            if (generation != produced || !foreground || interactionPaused) return
            if (speech.state != SpeechState.PREPARING) break
            delay(50)
        }
        currentCoroutineContext().ensureActive()
        if (generation != produced || !foreground || interactionPaused) return
        preparingAudio = false
        if (speech.state == SpeechState.PREPARING || speech.state == SpeechState.UNAVAILABLE) {
            audioError = speech.error ?: ""; visible = true; return
        }
        val key = "manual-$messageID-$produced"; audioID = key
        // Only actual target script goes to synthesis, never the Latin guide.
        speech.toggle(key, listOf(SpeechSpan(text, language)))
        while (speech.activeMessage == key) {
            delay(80)
            if (generation != produced || !foreground || interactionPaused) return
        }
        currentCoroutineContext().ensureActive()
        if (generation == produced && foreground && !interactionPaused && speech.activeMessage == null) {
            speech.error?.let { audioError = it; visible = true }
        }
    }
    fun toggleAudio() {
        if (speaking || preparingAudio) { job?.cancel(); preparingAudio = false; speech.stop(); return }
        val text = pronunciationText ?: return; val language = pronunciationLanguage ?: return; val produced = generation
        job?.cancel(); job = scope.launch { play(text, language, produced) }
    }
    fun retry() { view.get()?.let { begin(selected.first, selected.last + 1, it) } }
}

@Composable internal fun ManualLookupPopup(interaction: ManualLookupInteraction, onDownload: (() -> Unit)? = null,
    onVoiceHelp: (() -> Unit)? = null, onChooseLanguage: (() -> Unit)? = null) {
    if (!interaction.visible) return
    BackHandler { interaction.cancel() }
    val configuration = LocalConfiguration.current
    val density = LocalDensity.current
    val gap = with(density) { 16.dp.roundToPx() }
    val clear = with(density) { 60.dp.roundToPx() }
    val position = remember(interaction.anchor, gap, clear) { object : PopupPositionProvider {
        override fun calculatePosition(anchorBounds: IntRect, windowSize: IntSize, layoutDirection: LayoutDirection, popupContentSize: IntSize): IntOffset {
            val selected = interaction.anchor
            val below = selected.bottom + clear
            val y = if (below + popupContentSize.height < windowSize.height - clear) below
                else (selected.top - popupContentSize.height - clear).coerceIn(gap, (windowSize.height - popupContentSize.height - clear).coerceAtLeast(gap))
            return IntOffset((windowSize.width - popupContentSize.width) / 2, y)
        }
    } }
    Popup(popupPositionProvider = position, onDismissRequest = { interaction.dismissForTouch() },
        properties = PopupProperties(focusable = false, dismissOnBackPress = false, dismissOnClickOutside = true)) {
        Surface(shape = androidx.compose.foundation.shape.RoundedCornerShape(20.dp), shadowElevation = 12.dp,
            tonalElevation = 0.dp, color = MaterialTheme.colorScheme.surface,
            modifier = Modifier.width((configuration.screenWidthDp - 24).coerceAtMost(460).dp)
                .heightIn(max = (configuration.screenHeightDp * .48f).dp)) {
            Column(Modifier.padding(horizontal = 16.dp).padding(bottom = 14.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Spacer(Modifier.weight(1f))
                    if (interaction.targetText != null) IconButton(onClick = interaction::toggleAudio) {
                        Icon(if (interaction.speaking || interaction.preparingAudio) Icons.Outlined.Stop else Icons.Outlined.VolumeUp,
                            stringResource(if (interaction.speaking || interaction.preparingAudio) R.string.ui_cae7d57bc067 else R.string.lookup_play_again))
                    }
                    IconButton(onClick = interaction::cancel) { Icon(Icons.Outlined.Close, stringResource(R.string.lookup_close)) }
                }
                Column(Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    androidx.compose.foundation.text.selection.SelectionContainer {
                        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            val learning = interaction.pronunciationText
                            if (learning != null) {
                                Text(learning, fontSize = 20.sp, lineHeight = 28.sp, fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold)
                                interaction.reading?.let { Text(it, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                                if (interaction.missingReading) Text(stringResource(R.string.lookup_reading_unavailable), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Text(interaction.meaningText, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            } else Text(interaction.sourceText, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                    if (interaction.loading || interaction.preparingAudio) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                        Text(stringResource(if (interaction.loading) R.string.lookup_translating else R.string.ui_58fd7deb0abe))
                    }
                    val failure = interaction.outcome?.status?.takeIf { it != ManualTranslationStatus.READY }
                    val error = when (failure) {
                        ManualTranslationStatus.MODEL_NOT_READY -> stringResource(if (interaction.supportedPair) R.string.lookup_download_needed else R.string.lookup_unsupported)
                        ManualTranslationStatus.INVALID_LANGUAGE -> stringResource(R.string.lookup_choose_language)
                        ManualTranslationStatus.TIMEOUT -> stringResource(R.string.lookup_timeout)
                        ManualTranslationStatus.INVALID_INPUT -> stringResource(R.string.lookup_select_word)
                        null -> interaction.audioError?.ifBlank { stringResource(R.string.lookup_unavailable) }
                        else -> stringResource(R.string.lookup_unavailable)
                    }
                    error?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                    if (failure == ManualTranslationStatus.MODEL_NOT_READY && interaction.supportedPair && onDownload != null)
                        TextButton(onClick = { interaction.cancel(); onDownload() }) { Text(stringResource(R.string.lookup_download)) }
                    else if (failure == ManualTranslationStatus.INVALID_LANGUAGE && onChooseLanguage != null)
                        TextButton(onClick = { interaction.cancel(); onChooseLanguage() }) { Text(stringResource(R.string.ui_cbf7e254a8c0)) }
                    else if (failure != null && failure != ManualTranslationStatus.MODEL_NOT_READY)
                        TextButton(onClick = interaction::retry) { Text(stringResource(R.string.ui_ed783fa140ed)) }
                    if (interaction.audioError != null && interaction.speech.state == SpeechState.UNAVAILABLE && onVoiceHelp != null)
                        TextButton(onClick = { interaction.cancel(); onVoiceHelp() }) { Text(stringResource(R.string.ui_f826885bfb23)) }
                }
            }
        }
    }
}
