package co.fallsoft.vipi

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.Bundle
import android.text.Layout
import android.text.StaticLayout
import android.text.Spannable
import android.text.SpannableString
import android.text.style.BackgroundColorSpan
import android.view.MotionEvent
import android.view.View
import android.view.accessibility.AccessibilityNodeInfo
import android.widget.TextView
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.core.view.ViewCompat
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.LayoutCoordinates
import androidx.compose.ui.layout.boundsInWindow
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import co.fallsoft.vipi.core.SpeechSpan
import kotlin.math.ceil

/** One state for the whole conversation content. Native inputs/navigation sit
 * outside this gesture surface; moving/scrolling cancels the held reveal.
 */
internal class FullMessageGestures {
    var mode by mutableStateOf(ImmersionMode.NEW_WORD)
    var interactions by mutableIntStateOf(0); private set
    fun interacted() { interactions++ }
    var held by mutableStateOf(false)
    var accessibilityMeaning by mutableStateOf(false)
    var nativeScript by mutableStateOf(false)
    val meaning: Boolean get() = held || accessibilityMeaning
    private data class Hit(val bounds: Rect, val play: () -> Unit)
    private val messages = mutableMapOf<String, Hit>()
    private val alternateReadings = mutableStateMapOf<String, Boolean>()
    val canSwitchScript: Boolean get() = alternateReadings.values.any { it }
    fun register(id: String, bounds: Rect, play: () -> Unit) { messages[id] = Hit(bounds, play) }
    fun readingAvailable(id: String, available: Boolean) {
        if (alternateReadings[id] != available) alternateReadings[id] = available
    }
    fun remove(id: String) { messages.remove(id); alternateReadings.remove(id) }
    fun tap(position: Offset) { messages.values.lastOrNull { it.bounds.contains(position) }?.play?.invoke() }
    fun toggleScript() { if (canSwitchScript) { interacted(); nativeScript = !nativeScript } }
}

@Composable internal fun Modifier.fullMessageGestures(state: FullMessageGestures): Modifier {
    var coordinates by remember { mutableStateOf<LayoutCoordinates?>(null) }
    val reveal = stringResource(R.string.full_translation_meaning)
    val practice = stringResource(if (state.mode == ImmersionMode.FULL_MESSAGES) R.string.full_message_show_translation else R.string.full_translation_practice)
    val script = stringResource(R.string.full_translation_script)
    val reading = stringResource(R.string.full_translation_reading)
    DisposableEffect(state) { onDispose { state.held = false } }
    return onGloballyPositioned { coordinates = it }.semantics {
        customActions = buildList {
            add(CustomAccessibilityAction(reveal) { state.interacted(); state.accessibilityMeaning = true; true })
            add(CustomAccessibilityAction(practice) { state.accessibilityMeaning = false; state.held = false; true })
            if (state.canSwitchScript) add(CustomAccessibilityAction(if (state.nativeScript) reading else script) { state.toggleScript(); true })
        }
    }.pointerInput(state) {
        detectTapGestures(
            onPress = { try { tryAwaitRelease() } finally { state.held = false } },
            onLongPress = { state.interacted(); state.held = true },
            onDoubleTap = { state.toggleScript() },
            // detectTapGestures delays this until the double-tap window ends:
            // double/long press never also dispatches practice audio.
            onTap = { point -> coordinates?.takeIf { it.isAttached }?.let { state.tap(it.localToWindow(point)) } })
    }
}

/** One native paragraph with inline practice ranges. Reserve the largest real
 * source/script/reading layout so gestures do not move rows.
 */
internal class FullMessageTextView(context: Context) : TextView(context) {
    private var faces = emptyList<String>()
    private var rawOriginal = ""
    private var paintedRanges = emptyList<IntRange>()
    private var paintedColor = 0
    private var activePaint: BackgroundColorSpan? = null
    private var activeInk: android.text.style.ForegroundColorSpan? = null
    var highlightedWord: IntRange? = null
        private set
    private var activeColors: Pair<Int, Int>? = null
    var play: (() -> Unit)? = null
    val originalMessage: String get() = rawOriginal
    var playing = false
    var fullMode = false
    var showingNativeScript = false
    var readingUnavailable = false
        set(value) {
            if (field != value) {
                field = value
                ViewCompat.setStateDescription(this, if (value) context.getString(R.string.lookup_reading_unavailable) else null)
            }
        }
    var reveal: (() -> Unit)? = null
    var practice: (() -> Unit)? = null
    var script: (() -> Unit)? = null
    init {
        setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, 18f)
        includeFontPadding = false
        setLineSpacing(5 * resources.displayMetrics.density, 1f)
        setPadding(0, 0, 0, 0)
        textDirection = View.TEXT_DIRECTION_FIRST_STRONG
        setTextIsSelectable(false)
        isClickable = false; isLongClickable = false
        importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_YES
        layoutParams = android.view.ViewGroup.LayoutParams(android.view.ViewGroup.LayoutParams.WRAP_CONTENT,
            android.view.ViewGroup.LayoutParams.WRAP_CONTENT)
    }
    fun bind(displayed: String, original: String, variants: List<String>, color: Int, accessibilityContext: String? = null,
        highlights: List<IntRange> = emptyList(), highlightColor: Int = 0, spoken: IntRange? = null,
        spokenColor: Int = 0, spokenInk: Int = color) {
        rawOriginal = original
        val next = variants.distinct()
        if (faces != next) { faces = next; requestLayout() }
        setTextColor(color)
        if (text.toString() != displayed || paintedRanges != highlights || paintedColor != highlightColor) {
            paintedRanges = highlights; paintedColor = highlightColor
            activePaint = null
            activeInk = null
            highlightedWord = null
            setText(SpannableString(displayed).apply {
                highlights.forEach { range ->
                    require(range.first >= 0 && range.last < length)
                    setSpan(BackgroundColorSpan(highlightColor), range.first, range.last+1, Spannable.SPAN_EXCLUSIVE_EXCLUSIVE)
                }
            }, BufferType.SPANNABLE)
            requestLayout()
        }
        val visible = spoken?.takeIf { !it.isEmpty() && it.first >= 0 && it.last < displayed.length }
        if (visible != highlightedWord || activeColors != (spokenColor to spokenInk)) {
            val styled = text as? Spannable
            activePaint?.let { styled?.removeSpan(it) }
            activeInk?.let { styled?.removeSpan(it) }
            highlightedWord = visible
            activeColors = spokenColor to spokenInk
            if (visible != null && styled != null) {
                activePaint = BackgroundColorSpan(spokenColor).also { styled.setSpan(it, visible.first, visible.last + 1, Spannable.SPAN_EXCLUSIVE_EXCLUSIVE) }
                activeInk = android.text.style.ForegroundColorSpan(spokenInk).also { styled.setSpan(it, visible.first, visible.last + 1, Spannable.SPAN_EXCLUSIVE_EXCLUSIVE) }
            }
            invalidate()
        }
        contentDescription = listOfNotNull(displayed, accessibilityContext?.takeIf { it.isNotBlank() }).joinToString(". ")
    }
    // The enclosing Compose surface owns all pointer arbitration, including
    // blank background. Native accessibility actions remain available.
    override fun onTouchEvent(event: MotionEvent): Boolean = false
    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val available = (View.MeasureSpec.getSize(widthMeasureSpec) - totalPaddingLeft - totalPaddingRight).coerceAtLeast(1)
        val desired = ceil(faces.maxOfOrNull { Layout.getDesiredWidth(it, paint).toDouble() } ?: 1.0).toInt().coerceAtLeast(1)
        val width = if (View.MeasureSpec.getMode(widthMeasureSpec) == View.MeasureSpec.EXACTLY) available else minOf(available, desired)
        super.onMeasure(View.MeasureSpec.makeMeasureSpec(width + totalPaddingLeft + totalPaddingRight, View.MeasureSpec.EXACTLY), heightMeasureSpec)
        val contentWidth = (measuredWidth - totalPaddingLeft - totalPaddingRight).coerceAtLeast(1)
        val maximum = faces.maxOfOrNull { value ->
            StaticLayout.Builder.obtain(value, 0, value.length, paint, contentWidth).setIncludePad(false)
                .setLineSpacing(lineSpacingExtra, lineSpacingMultiplier).setUseLineSpacingFromFallbacks(isFallbackLineSpacing)
                .setBreakStrategy(breakStrategy).setHyphenationFrequency(hyphenationFrequency).build().height
        } ?: measuredHeight
        setMeasuredDimension(measuredWidth, maxOf(measuredHeight, maximum + totalPaddingTop + totalPaddingBottom))
    }
    override fun onInitializeAccessibilityNodeInfo(info: AccessibilityNodeInfo) {
        super.onInitializeAccessibilityNodeInfo(info)
        info.isClickable = play != null
        if (play != null) info.addAction(AccessibilityNodeInfo.AccessibilityAction(AccessibilityNodeInfo.ACTION_CLICK,
            context.getString(if (playing) R.string.ui_cae7d57bc067 else if (fullMode) R.string.lookup_play_message else R.string.full_translation_play)))
        info.addAction(AccessibilityNodeInfo.AccessibilityAction(REVEAL, context.getString(R.string.full_translation_meaning)))
        info.addAction(AccessibilityNodeInfo.AccessibilityAction(PRACTICE, context.getString(if (fullMode) R.string.full_message_show_translation else R.string.full_translation_practice)))
        if (script != null) info.addAction(AccessibilityNodeInfo.AccessibilityAction(SCRIPT, context.getString(if (showingNativeScript) R.string.full_translation_reading else R.string.full_translation_script)))
        info.addAction(AccessibilityNodeInfo.AccessibilityAction(AccessibilityNodeInfo.ACTION_COPY, context.getString(R.string.full_translation_copy_original)))
    }
    override fun performAccessibilityAction(action: Int, arguments: Bundle?): Boolean {
        when (action) {
            AccessibilityNodeInfo.ACTION_CLICK -> { val callback = play ?: return false; callback(); return true }
            REVEAL -> { reveal?.invoke(); return true }
            PRACTICE -> { practice?.invoke(); return true }
            SCRIPT -> { val callback = script ?: return false; callback(); return true }
            AccessibilityNodeInfo.ACTION_COPY -> {
                context.getSystemService(ClipboardManager::class.java).setPrimaryClip(ClipData.newPlainText("", rawOriginal)); return true
            }
        }
        return super.performAccessibilityAction(action, arguments)
    }
    companion object { private const val REVEAL = 0x02010001; private const val PRACTICE = 0x02010002; private const val SCRIPT = 0x02010003 }
}

@Composable internal fun FullMessageBubble(text: String, id: String, translation: ConversationTranslation,
    gestures: FullMessageGestures, audio: ConversationAutoplay, accessibilityContext: String? = null,
    metadata: @Composable () -> Unit) {
    val speech = audio.speech
    val state = translation.state(id, text)
    val value = state?.value
    val readingUnavailable = value?.readingStatus == FullMessageReadingStatus.UNAVAILABLE
    val showReadingFailure = readingUnavailable && !gestures.meaning && !gestures.nativeScript
    val alternateReading = value?.practiceReading?.let { it.isNotBlank() && it != value.practiceText } == true
    val ink = MaterialTheme.colorScheme.onSurface.toArgb()
    val activityColor = MaterialTheme.colorScheme.primary
    val spokenInk = MaterialTheme.colorScheme.onPrimary.toArgb()
    val wordColor = MaterialTheme.colorScheme.secondaryContainer.toArgb()
    LaunchedEffect(translation, id, text) { translation.enqueue(id, text) }
    val play = {
        if (value?.words?.isEmpty() != true) { gestures.interacted(); audio.manual(id, text) }
    }
    // Readings complete independently of stable paragraph geometry. Bounds
    // registration must never be the only trigger for action availability.
    SideEffect { gestures.mode = translation.mode; gestures.readingAvailable(id, alternateReading) }
    DisposableEffect(gestures, translation, id, text) {
        translation.retain(id, text)
        onDispose { gestures.remove(id); translation.release(id, text) }
    }
    Column(Modifier.widthIn(max = 520.dp).onGloballyPositioned {
        gestures.register(id, it.boundsInWindow(), play)
    }.drawWithContent {
        drawContent()
        if (speech.activeMessage == id || audio.manualMessage == id) drawLine(activityColor,
            Offset(15.dp.toPx(), size.height - 4.dp.toPx()), Offset(size.width - 15.dp.toPx(), size.height - 4.dp.toPx()), 2.dp.toPx())
    }.padding(horizontal = 15.dp, vertical = EmbeddedMessageVerticalPadding), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        val showingMeaning = gestures.meaning
        val showingScript = gestures.nativeScript
        val displayed = when {
            value == null -> text
            showingMeaning -> value.meaningText
            showingScript -> value.practiceText
            else -> value.practiceReading ?: value.practiceText
        }
        val faces = value?.let { listOfNotNull(it.practiceText, it.meaningText, it.practiceReading) } ?: listOf(text)
        AndroidView(factory = { FullMessageTextView(it) }, update = { view ->
            view.play = play.takeIf { value?.words?.isEmpty() != true }
            view.fullMode = translation.mode == ImmersionMode.FULL_MESSAGES
            view.showingNativeScript = showingScript
            view.readingUnavailable = showReadingFailure
            view.playing = speech.activeMessage == id || audio.manualMessage == id
            view.reveal = { gestures.interacted(); gestures.accessibilityMeaning = true }
            view.practice = { gestures.accessibilityMeaning = false; gestures.held = false }
            view.script = if (alternateReading) ({ gestures.toggleScript() }) else null
            val highlights = if (showingMeaning) emptyList() else value?.words?.let {
                WordReplacement.ranges(it, reading = !showingScript && value.practiceReading != null)
            }.orEmpty()
            val word = if (!showingMeaning && speech.activeMessage == id) speech.playingWord else null
            val spoken = if (showingScript || !alternateReading) word?.script else word?.reading
            view.bind(displayed, text, faces, ink, accessibilityContext, highlights, wordColor, spoken,
                activityColor.toArgb(), spokenInk)
        })
        if (value == null) {
            if (state?.phase == MessageTranslationPhase.FAILED) {
                Text(stringResource(if (translation.mode == ImmersionMode.FULL_MESSAGES) R.string.full_message_failed else R.string.full_translation_failed), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
                TextButton(onClick = { translation.enqueue(id, text, retry = true) }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.try_again)) }
            }
        }
        if (readingUnavailable) {
            // Keep this failure-only footprint across held meaning/script so
            // the row stays under the user's finger. Hidden copy has no AX.
            val retryable = value?.readingFailure == FullMessageReadingFailure.PRODUCER_FAILURE
            val retry = stringResource(R.string.try_again)
            val unavailable = stringResource(R.string.lookup_reading_unavailable)
            val feedbackLayout = if (retryable) Modifier.heightIn(min = 48.dp).wrapContentHeight() else Modifier
            val feedback = if (!showReadingFailure) feedbackLayout.alpha(0f).clearAndSetSemantics { }
                else if (retryable) Modifier.clickable(role = Role.Button, onClickLabel = retry) {
                    gestures.interacted(); translation.enqueue(id, text, retry = true)
                }.then(feedbackLayout) else feedbackLayout
            Text(if (retryable) "$unavailable $retry" else unavailable, modifier = feedback,
                style = MaterialTheme.typography.bodySmall,
                color = if (retryable) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant)
        }
        audio.failures[id]?.let {
            Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
        }
        metadata()
    }
}
