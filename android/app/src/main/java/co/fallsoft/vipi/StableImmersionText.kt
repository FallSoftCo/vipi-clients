package co.fallsoft.vipi

import android.content.Context
import android.graphics.Typeface
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.text.Layout
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.StaticLayout
import android.text.style.ClickableSpan
import android.text.style.ReplacementSpan
import android.text.TextPaint
import android.view.MotionEvent
import android.view.View
import android.widget.TextView
import androidx.core.view.ViewCompat
import co.fallsoft.vipi.core.ImmersionResult
import co.fallsoft.vipi.core.ImmersionText

/** Native paragraphs with stable inline vocabulary blocks. The underlying source
 * ranges stay fixed for bidi/layout; drawing, accessibility and copy use the face. */
internal class StableImmersionText(context: Context) : TextView(context) {
    var onWord: ((Int) -> Unit)? = null
    var onChooseWord: (() -> Unit)? = null
    var onSelection: ((Boolean) -> Unit)? = null
    private var result: ImmersionResult? = null
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
    init {
        setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, 17f)
        setPadding(0, 0, 0, 0); includeFontPadding = false
        setLineSpacing(5 * resources.displayMetrics.density, 1f)
        setTextIsSelectable(true)
        accessibilityLiveRegion = ACCESSIBILITY_LIVE_REGION_NONE
        tag = "immersionText"
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
    fun bind(value: ImmersionResult, revealed: Set<Int>, showScript: Boolean, color: Int, bodyColor: Int) {
        if (result != value) {
            wordActions.forEach { ViewCompat.removeAccessibilityAction(this, it) }
            // AndroidView's Compose semantics do not reach this native node.
            // Register on TextView itself. Android supports 32 custom actions;
            // longer messages expose a chooser for every remaining word.
            val repeated = value.spans.groupingBy { it.original to it.displayedTarget }.eachCount()
            wordActions = value.spans.take(31).mapIndexed { index, word ->
                val occurrence = if (repeated.getValue(word.original to word.displayedTarget) > 1) ", word ${index + 1}" else ""
                ViewCompat.addAccessibilityAction(this, "Switch ${word.original} and ${word.displayedTarget}$occurrence") { _, _ ->
                    onWord?.invoke(word.id); true
                }
            } + if (value.spans.size > 31) listOf(ViewCompat.addAccessibilityAction(this, "Choose a word to switch") { _, _ ->
                onChooseWord?.invoke(); true
            }) else emptyList()
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
        if (id == android.R.id.copy && hasSelection()) {
            (context.getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager)
                .setPrimaryClip(android.content.ClipData.newPlainText("Message", visibleText(minOf(selectionStart, selectionEnd), maxOf(selectionStart, selectionEnd))))
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
        onSelection?.invoke(start >= 0 && end > start)
    }
    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (event.actionMasked == MotionEvent.ACTION_DOWN) { downX = event.x; downY = event.y; downTime = event.eventTime }
        if (event.actionMasked == MotionEvent.ACTION_UP && !hasSelection() && event.eventTime - downTime < 400 &&
            kotlin.math.abs(event.x - downX) < 12 * resources.displayMetrics.density &&
            kotlin.math.abs(event.y - downY) < 12 * resources.displayMetrics.density) {
            val offset = getOffsetForPosition(event.x, event.y)
            val link = (text as? Spanned)?.getSpans(offset, offset, WordLink::class.java)?.firstOrNull()
            if (link != null) { link.onClick(this); performClick(); return true }
        }
        return super.onTouchEvent(event)
    }
    override fun performClick(): Boolean { super.performClick(); return true }
}
