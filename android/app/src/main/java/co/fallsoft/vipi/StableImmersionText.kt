package co.fallsoft.vipi

import android.content.Context
import android.graphics.Typeface
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Rect
import android.graphics.Path
import android.view.MenuInflater
import java.text.BreakIterator
import java.util.Locale
import android.text.Layout
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.StaticLayout
import android.text.style.ClickableSpan
import android.text.style.ReplacementSpan
import android.text.TextPaint
import android.view.MotionEvent
import android.view.View
import android.view.KeyEvent
import android.view.ActionMode
import android.view.Menu
import android.view.MenuItem
import android.os.Bundle
import android.view.accessibility.AccessibilityNodeInfo
import androidx.core.view.accessibility.AccessibilityNodeInfoCompat
import android.widget.TextView
import androidx.core.view.ViewCompat
import co.fallsoft.vipi.core.ImmersionPresentation
import co.fallsoft.vipi.core.ImmersionText

/** Native paragraphs with stable inline vocabulary blocks. The underlying source
 * ranges stay fixed for bidi/layout; drawing, accessibility and copy use the face. */
internal class StableImmersionText(context: Context) : TextView(context) {
    var onWord: ((Int) -> Unit)? = null
    var onChooseWord: (() -> Unit)? = null
    var onSelection: ((Boolean) -> Unit)? = null
    var onPlainWord: ((Int, Int, StableImmersionText) -> Unit)? = null
    var onReleasedSelection: ((Int, Int, StableImmersionText) -> Unit)? = null
    var onSelectionGestureBegan: (() -> Unit)? = null
    var onCopyRequested: (() -> Unit)? = null
    var onWhitespace: ((StableImmersionText) -> Unit)? = null
    var onPlayMessage: (() -> Unit)? = null
    private var translationCallbacks = false
    private var selectionGesture = false
    private var selectionChangedDuringGesture = false
    private var selectionRevision = 0
    private var deliveredSelection: Pair<Int, Int>? = null
    private val releasedSelection = Runnable {
        if (!selectionGesture && hasSelection()) {
            val start = minOf(selectionStart, selectionEnd); val end = maxOf(selectionStart, selectionEnd)
            if (deliveredSelection != (start to end)) {
                deliveredSelection = start to end
                onReleasedSelection?.invoke(start, end, this)
            }
        }
    }
    private fun beginSelectionGesture() {
        // Editor also calls ActionMode.hide for every native handle MOVE.
        // Keep changes accumulated earlier in this same drag until hide(0)
        // signals release; repeated MOVE notifications are not new gestures.
        if (selectionGesture) { removeCallbacks(releasedSelection); return }
        selectionGesture = true; selectionChangedDuringGesture = false; deliveredSelection = null
        removeCallbacks(releasedSelection); onSelectionGestureBegan?.invoke()
    }
    private fun endSelectionGesture(cancelled: Boolean = false) {
        val changed = selectionChangedDuringGesture
        selectionGesture = false
        selectionChangedDuringGesture = false
        if (cancelled) {
            removeCallbacks(releasedSelection); deliveredSelection = null
            return
        }
        if (changed && hasSelection()) {
            removeCallbacks(releasedSelection); postDelayed(releasedSelection, 180)
        }
    }
    override fun onDetachedFromWindow() {
        removeCallbacks(releasedSelection)
        selectionGesture = false; selectionChangedDuringGesture = false; deliveredSelection = null
        super.onDetachedFromWindow()
    }
    /** Android's public floating ActionMode hide/show calls bracket native
     * handle drags, including their separate PopupWindow touch stream. */
    override fun startActionMode(callback: ActionMode.Callback, type: Int): ActionMode? {
        val actual = super.startActionMode(callback, type) ?: return null
        if (type != ActionMode.TYPE_FLOATING || onReleasedSelection == null || actual is LookupObservedActionMode) return actual
        return LookupObservedActionMode(actual) { hidden ->
            if (hidden) beginSelectionGesture() else endSelectionGesture()
        }
    }
    fun sourceRangeRect(start: Int, end: Int): Rect {
        val paragraph = layout ?: return Rect()
        val path = Path(); paragraph.getSelectionPath(start.coerceIn(0, text.length), end.coerceIn(0, text.length), path)
        val bounds = RectF(); path.computeBounds(bounds, true)
        val location = IntArray(2); getLocationOnScreen(location)
        bounds.offset(location[0] + totalPaddingLeft - scrollX.toFloat(), location[1] + totalPaddingTop - scrollY.toFloat())
        return Rect(bounds.left.toInt(), bounds.top.toInt(), kotlin.math.ceil(bounds.right).toInt(), kotlin.math.ceil(bounds.bottom).toInt())
    }
    private fun plainWordAt(offset: Int, x: Float, y: Float): Pair<Int, Int>? {
        val original = result?.original ?: return null
        val words = BreakIterator.getWordInstance(Locale.getDefault()).apply { setText(original) }
        val location = IntArray(2); getLocationOnScreen(location)
        for (position in listOf(offset, offset - 1).filter { it in original.indices }) {
            val start = if (words.isBoundary(position)) position else words.preceding(position)
            val end = words.following(position)
            if (start < 0 || end <= start || !original.substring(start, end).any { it.isLetterOrDigit() }) continue
            if (sourceRangeRect(start, end).contains((location[0] + x).toInt(), (location[1] + y).toInt())) return start to end
        }
        return null
    }
    val displayedOriginal: String get() = result?.original.orEmpty()
    private var result: ImmersionPresentation? = null
    private var originals = emptySet<Int>()
    private var script = false
    private var accent = 0
    private var variants = emptyList<CharSequence>()
    private var downX = 0f
    private var downY = 0f
    private var downTime = 0L
    private var reserveKey = ""
    private var reserveHeight = 0
    private var measurementContext = ""
    private var tokenWidth = 10000
    private val tokenSpans = mutableListOf<WordSlot>()
    private var wordActions = emptyList<Int>()
    private var messageActions: (() -> Unit)? = null
    private var selectionFinished: (() -> Unit)? = null
    private var explicitSelection = false
    private var pendingSelection = false
    private var menuSelectionPending = false
    private var nativeSelectionMode: ActionMode? = null
    init {
        setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, 18f)
        setPadding(0, 0, 0, 0); includeFontPadding = false
        setLineSpacing(5 * resources.displayMetrics.density, 1f)
        setTextIsSelectable(true)
        accessibilityLiveRegion = ACCESSIBILITY_LIVE_REGION_NONE
        tag = "immersionText"
    }
    /** Message gestures leave short word taps intact. Explicit selection gives
     * native TextView its normal handles and copy action mode. */
    fun configureMessageActions(action: (() -> Unit)?, selectText: Boolean, finished: () -> Unit) {
        val hasTranslation = onPlainWord != null || onReleasedSelection != null
        val changed = (messageActions == null) != (action == null) || explicitSelection != selectText || translationCallbacks != hasTranslation
        messageActions = action; selectionFinished = finished; translationCallbacks = hasTranslation
        if (!changed) return
        val enteringSelection = action != null && selectText && !explicitSelection
        explicitSelection = selectText
        if (!selectText) pendingSelection = false
        customSelectionActionModeCallback = if (action == null && !hasTranslation) null else object : ActionMode.Callback {
            override fun onCreateActionMode(mode: ActionMode, menu: Menu): Boolean {
                nativeSelectionMode = mode
                if (action != null) menu.add(Menu.NONE, Menu.FIRST + 281, Menu.NONE, context.getString(R.string.ui_e52b25aa61b5))
                return true
            }
            override fun onPrepareActionMode(mode: ActionMode, menu: Menu) = false
            override fun onActionItemClicked(mode: ActionMode, item: MenuItem): Boolean {
                if (item.itemId != Menu.FIRST + 281) return false
                onCopyRequested?.invoke(); messageActions?.invoke(); return true
            }
            override fun onDestroyActionMode(mode: ActionMode) {
                nativeSelectionMode = null; removeCallbacks(releasedSelection)
                post { if (explicitSelection) selectionFinished?.invoke() }
            }
        }
        setTextIsSelectable(true)
        setOnLongClickListener(null)
        result?.let(::updateAccessibilityActions)
        if (action != null) { isFocusable = true; isFocusableInTouchMode = true; isLongClickable = true }
        // Keep the native long-click action provided by the listener. AndroidX
        // reuses actions by label, so labelling that standard action "Message
        // actions" would alias the distinct custom action below to its ID.
        ViewCompat.removeAccessibilityAction(this, AccessibilityNodeInfoCompat.ACTION_LONG_CLICK)
        result?.let(::updateAccessibilityActions)
        if (enteringSelection) { pendingSelection = true; beginPendingSelection() }
    }
    fun selectTextFromMenu() {
        onCopyRequested?.invoke()
        removeCallbacks(releasedSelection); selectionChangedDuringGesture = false
        pendingSelection = true; menuSelectionPending = true; beginPendingSelection()
    }
    private fun beginPendingSelection() {
        // A focused popup is still being dismissed when its action updates this
        // view. Starting ActionMode before window focus returns immediately loses
        // the selection. Resume on the real window-focus event, without polling.
        post {
            if (pendingSelection && (explicitSelection || menuSelectionPending) && isAttachedToWindow && hasWindowFocus()) {
                pendingSelection = false; menuSelectionPending = false; requestFocus()
                // Public TextView selection action starts its native ActionMode
                // without requiring stale touch offsets from before selection
                // was enabled. Handles let the user narrow this initial range.
                performAccessibilityAction(AccessibilityNodeInfo.ACTION_SET_SELECTION, Bundle().apply {
                    putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, 0)
                    putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, text.length)
                })
            }
        }
    }
    override fun onWindowFocusChanged(hasWindowFocus: Boolean) {
        super.onWindowFocusChanged(hasWindowFocus)
        if (hasWindowFocus && pendingSelection) beginPendingSelection()
    }
    private fun updateAccessibilityActions(value: ImmersionPresentation) {
        wordActions.forEach { ViewCompat.removeAccessibilityAction(this, it) }
        val cap = 27
        val repeated = value.spans.groupingBy { it.original to it.displayedTarget }.eachCount()
        wordActions = value.spans.take(cap).mapIndexed { index, word ->
            val label = if (repeated.getValue(word.original to word.displayedTarget) > 1) {
                val locale = context.resources.configuration.locales[0]
                context.getString(R.string.access_switch_repeated, word.original, word.displayedTarget,
                    java.text.NumberFormat.getIntegerInstance(locale).format(index + 1))
            } else context.getString(R.string.access_switch_word, word.original, word.displayedTarget)
            ViewCompat.addAccessibilityAction(this, label) { _, _ -> onWord?.invoke(word.id); true }
        } + if (value.spans.size > cap) listOf(ViewCompat.addAccessibilityAction(this, context.getString(R.string.access_choose_word)) { _, _ -> onChooseWord?.invoke(); true }) else emptyList()
        if (onWhitespace != null) wordActions += ViewCompat.addAccessibilityAction(this, context.getString(R.string.lookup_translate_message)) { _, _ -> onWhitespace?.invoke(this); true }
        if (onPlayMessage != null) wordActions += ViewCompat.addAccessibilityAction(this, context.getString(R.string.lookup_play_message)) { _, _ -> onPlayMessage?.invoke(); true }
        if (messageActions != null) wordActions += ViewCompat.addAccessibilityAction(this, context.getString(R.string.access_message_actions)) { _, _ -> messageActions?.invoke(); true }
    }
    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        if (messageActions != null && (keyCode == KeyEvent.KEYCODE_MENU || (keyCode == KeyEvent.KEYCODE_F10 && event.isShiftPressed))) {
            messageActions?.invoke(); return true
        }
        if (explicitSelection && keyCode == KeyEvent.KEYCODE_ESCAPE) { nativeSelectionMode?.finish(); return true }
        return super.onKeyDown(keyCode, event)
    }
    private class WordLink(val id: Int, val color: Int, val action: (Int) -> Unit) : ClickableSpan() {
        override fun onClick(widget: View) { action(id) }
        override fun updateDrawState(ds: TextPaint) { ds.color = color; ds.isUnderlineText = false }
    }
    private class WordSlot(val displayed: String, val forms: List<String>, val color: Int, val density: Float, val trailing: String) : ReplacementSpan() {
        var maximumWidth = 10000
        private var key = ""
        private var width = 0
        private var ascent = 0
        private var descent = 0
        private lateinit var drawing: StaticLayout
        private fun measure(paint: Paint) {
            val next = "$maximumWidth|${paint.textSize}|${paint.typeface}"
            if (key == next) return
            key = next
            val textPaint = TextPaint(paint).apply { typeface = Typeface.create(typeface, Typeface.BOLD); this.color = this@WordSlot.color }
            val padding = 4 * density
            val punctuation = if (trailing.isEmpty()) 0 else kotlin.math.ceil(paint.measureText(trailing)).toInt() + 1
            val available = maximumWidth - minOf(maximumWidth / 4, punctuation)
            width = minOf(available, kotlin.math.ceil(forms.maxOf { Layout.getDesiredWidth(it, textPaint) } + padding * 2).toInt()).coerceAtLeast(1)
            val inner = (width - padding * 2).toInt().coerceAtLeast(1)
            fun layout(text: String) = StaticLayout.Builder.obtain(text, 0, text.length, textPaint, inner)
                .setAlignment(Layout.Alignment.ALIGN_CENTER).setIncludePad(false).setUseLineSpacingFromFallbacks(true).build()
            val layouts = forms.distinct().map(::layout)
            ascent = -layouts.maxOf { it.getLineBaseline(0) } - (2 * density).toInt()
            descent = layouts.maxOf { it.height - it.getLineBaseline(0) } + (2 * density).toInt()
            drawing = layout(displayed)
        }
        override fun getSize(paint: Paint, text: CharSequence, start: Int, end: Int, fm: Paint.FontMetricsInt?): Int {
            measure(paint)
            fm?.let { it.ascent = minOf(it.ascent, ascent); it.top = minOf(it.top, ascent); it.descent = maxOf(it.descent, descent); it.bottom = maxOf(it.bottom, descent) }
            return width
        }
        override fun draw(canvas: Canvas, text: CharSequence, start: Int, end: Int, x: Float, top: Int, y: Int, bottom: Int, paint: Paint) {
            measure(paint)
            val background = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = this@WordSlot.color; alpha = 28 }
            canvas.drawRoundRect(RectF(x, y + ascent.toFloat(), x + width, y + descent.toFloat()), 2.5f * density, 2.5f * density, background)
            canvas.save(); canvas.translate(x + (width - drawing.width) / 2f, (y - drawing.getLineBaseline(0)).toFloat()); drawing.draw(canvas); canvas.restore()
        }
    }
    private fun display(word: co.fallsoft.vipi.core.ImmersionSpan, revealed: Set<Int>, showScript: Boolean) =
        if (word.id in revealed) word.original else if (showScript) word.translated else word.displayedTarget
    private fun render(revealed: Set<Int>, showScript: Boolean): CharSequence {
        val value = result ?: return ""
        return SpannableStringBuilder(value.original).apply {
            value.spans.forEach { word ->
                val trailing = value.original.substring(word.end).takeWhile { it in ".,!?;:…؟。！？；，、)]}’”\"" }.take(8)
                val slot = WordSlot(display(word, revealed, showScript), listOf(word.original, word.displayedTarget, word.translated), accent, resources.displayMetrics.density, trailing)
                slot.maximumWidth = tokenWidth; tokenSpans += slot
                setSpan(slot, word.start, word.end, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                setSpan(WordLink(word.id, accent) { onWord?.invoke(it) }, word.start, word.end, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            }
        }
    }
    fun bind(value: ImmersionPresentation, revealed: Set<Int>, showScript: Boolean, color: Int, bodyColor: Int) {
        if (result != value) {
            // AndroidView's Compose semantics do not reach this native node.
            // Register on TextView itself. Android supports 32 custom actions;
            // longer messages expose a chooser for every remaining word.
            updateAccessibilityActions(value)
        }
        val changed = result != value || originals != revealed || script != showScript || accent != color
        result = value; originals = revealed; script = showScript; accent = color
        setTextColor(bodyColor)
        if (changed || text.isEmpty()) {
            tokenSpans.clear()
            val current = render(revealed, showScript)
            variants = listOf(current)
            text = current
            contentDescription = visibleText()
            reserveKey = ""
            requestLayout()
        }
    }
    fun visibleText(start: Int = 0, end: Int = result?.original?.length ?: 0): String {
        val value = result ?: return ""
        return ImmersionText.project(value, originals, script, start, end)
    }

    override fun onTextContextMenuItem(id: Int): Boolean {
        if (id == android.R.id.selectAll || id == android.R.id.copy) {
            removeCallbacks(releasedSelection); selectionChangedDuringGesture = false; deliveredSelection = selectionStart to selectionEnd
            onCopyRequested?.invoke()
        }
        if (id == android.R.id.copy && hasSelection()) {
            (context.getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager)
                .setPrimaryClip(android.content.ClipData.newPlainText(context.getString(R.string.message_hint), visibleText(minOf(selectionStart, selectionEnd), maxOf(selectionStart, selectionEnd))))
            if (messageActions != null) nativeSelectionMode?.finish()
            return true
        }
        return super.onTextContextMenuItem(id)
    }
    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val available = (View.MeasureSpec.getSize(widthMeasureSpec) - totalPaddingLeft - totalPaddingRight).coerceAtLeast(1)
        if (available != tokenWidth) { tokenWidth = available; tokenSpans.forEach { it.maximumWidth = available }; reserveKey = "" }
        super.onMeasure(widthMeasureSpec, heightMeasureSpec)
        val width = (measuredWidth - totalPaddingLeft - totalPaddingRight).coerceAtLeast(1)
        val context = "$width|$textSize|${result}"
        if (measurementContext != context) { measurementContext = context; reserveHeight = 0; reserveKey = "" }
        val key = "$width|$textSize|${variants.map { it.toString() }}"
        if (key != reserveKey) {
            reserveKey = key
            reserveHeight = maxOf(reserveHeight, variants.maxOfOrNull {
                StaticLayout.Builder.obtain(it, 0, it.length, paint, width).setIncludePad(false)
                    .setLineSpacing(lineSpacingExtra, lineSpacingMultiplier).setUseLineSpacingFromFallbacks(isFallbackLineSpacing).setBreakStrategy(breakStrategy)
                    .setHyphenationFrequency(hyphenationFrequency).build().height
            } ?: measuredHeight)
        }
        setMeasuredDimension(measuredWidth, maxOf(measuredHeight, reserveHeight + totalPaddingTop + totalPaddingBottom))
    }
    override fun onSelectionChanged(start: Int, end: Int) {
        super.onSelectionChanged(start, end)
        selectionRevision++
        removeCallbacks(releasedSelection)
        if (selectionGesture) selectionChangedDuringGesture = true
        onSelection?.invoke(start >= 0 && end > start)
    }
    private fun finishManualTap(event: MotionEvent) {
        // Native selection receives DOWN so long press remains available. A
        // short tap handled here must also end that native touch sequence.
        val cancel = MotionEvent.obtain(event).apply { action = MotionEvent.ACTION_CANCEL }
        try { super.onTouchEvent(cancel) } finally { cancel.recycle() }
        nativeSelectionMode?.finish()
        (text as? android.text.Spannable)?.let { android.text.Selection.removeSelection(it) }
        endSelectionGesture()
    }
    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (event.actionMasked == MotionEvent.ACTION_DOWN) { downX = event.x; downY = event.y; downTime = event.eventTime; beginSelectionGesture() }
        if (event.actionMasked == MotionEvent.ACTION_UP && !hasSelection() && event.eventTime - downTime < 400 &&
            kotlin.math.abs(event.x - downX) < 12 * resources.displayMetrics.density &&
            kotlin.math.abs(event.y - downY) < 12 * resources.displayMetrics.density) {
            val offset = getOffsetForPosition(event.x, event.y)
            val link = (text as? Spanned)?.getSpans(offset, offset, WordLink::class.java)?.firstOrNull()
            val spanned = text as? Spanned
            val location = IntArray(2); getLocationOnScreen(location)
            if (link != null && spanned != null && sourceRangeRect(spanned.getSpanStart(link), spanned.getSpanEnd(link)).contains((location[0] + event.x).toInt(), (location[1] + event.y).toInt())) {
                finishManualTap(event); link.onClick(this); performClick(); return true
            }
            plainWordAt(offset, event.x, event.y)?.let { (start, end) ->
                if (onPlainWord != null) { finishManualTap(event); onPlainWord?.invoke(start, end, this); performClick(); return true }
            }
            if (onWhitespace != null) { finishManualTap(event); onWhitespace?.invoke(this); performClick(); return true }
        }
        val handled = super.onTouchEvent(event)
        if (event.actionMasked == MotionEvent.ACTION_UP) endSelectionGesture()
        if (event.actionMasked == MotionEvent.ACTION_CANCEL) endSelectionGesture(cancelled = true)
        return handled
    }
    override fun performClick(): Boolean { super.performClick(); return true }
}


private class LookupObservedActionMode(private val actual: ActionMode, private val visibility: (Boolean) -> Unit) : ActionMode() {
    override fun hide(duration: Long) { visibility(duration != 0L); actual.hide(duration) }
    override fun finish() = actual.finish()
    override fun invalidate() = actual.invalidate()
    override fun invalidateContentRect() = actual.invalidateContentRect()
    override fun onWindowFocusChanged(hasWindowFocus: Boolean) = actual.onWindowFocusChanged(hasWindowFocus)
    override fun getType() = actual.type
    override fun setType(type: Int) = actual.setType(type)
    override fun getTitle() = actual.title
    override fun setTitle(title: CharSequence?) = actual.setTitle(title)
    override fun setTitle(resId: Int) = actual.setTitle(resId)
    override fun getSubtitle() = actual.subtitle
    override fun setSubtitle(subtitle: CharSequence?) = actual.setSubtitle(subtitle)
    override fun setSubtitle(resId: Int) = actual.setSubtitle(resId)
    override fun getCustomView() = actual.customView
    override fun setCustomView(view: View?) = actual.setCustomView(view)
    override fun getMenu() = actual.menu
    override fun getMenuInflater(): MenuInflater = actual.menuInflater
    override fun getTag() = actual.tag
    override fun setTag(tag: Any?) = actual.setTag(tag)
    override fun getTitleOptionalHint() = actual.titleOptionalHint
    override fun setTitleOptionalHint(titleOptional: Boolean) = actual.setTitleOptionalHint(titleOptional)
    override fun isTitleOptional() = actual.isTitleOptional
}
