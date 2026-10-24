package co.fallsoft.vipi

import android.content.Context
import android.graphics.Typeface
import android.text.Layout
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.StaticLayout
import android.text.style.ForegroundColorSpan
import android.text.style.StyleSpan
import android.text.style.ClickableSpan
import android.text.TextPaint
import android.view.MotionEvent
import android.view.View
import android.widget.TextView
import co.fallsoft.vipi.core.ImmersionResult

/** Natural native text shaping and selection. Reserve paragraph height, never
 * pad individual words: punctuation and word spacing remain ordinary prose. */
internal class StableImmersionText(context: Context) : TextView(context) {
    var onWord: ((Int) -> Unit)? = null
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
    private fun render(revealed: Set<Int>, showScript: Boolean): CharSequence {
        val value = result ?: return ""
        return SpannableStringBuilder().apply {
            var cursor = 0
            value.spans.forEach { word ->
                append(value.original.substring(cursor, word.start))
                val start = length
                append(if (word.id in revealed) word.original else if (showScript) word.translated else word.displayedTarget)
                setSpan(ForegroundColorSpan(accent), start, length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                setSpan(StyleSpan(Typeface.BOLD), start, length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                setSpan(WordLink(word.id, accent) { onWord?.invoke(it) }, start, length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                cursor = word.end
            }
            append(value.original.substring(cursor))
        }
    }
    fun bind(value: ImmersionResult, revealed: Set<Int>, showScript: Boolean, color: Int, bodyColor: Int) {
        val changed = result != value || originals != revealed || script != showScript || accent != color
        result = value; originals = revealed; script = showScript; accent = color
        setTextColor(bodyColor)
        if (changed || text.isEmpty()) {
            val current = render(revealed, showScript)
            variants = listOf(render(value.spans.map { it.id }.toSet(), false), render(emptySet(), false), render(emptySet(), true), current).distinctBy { it.toString() }
            text = current
            contentDescription = current.toString()
            requestLayout()
        }
    }
    fun visibleText() = text.toString()
    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
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
