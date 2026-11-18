package co.fallsoft.vipi

import android.graphics.Rect
import android.graphics.RectF
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.ComposeTestRule
import androidx.core.view.WindowInsetsCompat
import androidx.test.uiautomator.By
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import java.io.File

/** Real activity, Gboard/window insets and rendered text/caret. No substitute editor. */
internal fun exerciseShortLandscapeComposer(compose: ComposeTestRule, f: MainActivityJourneyFixture,
    inputTag: String, sendTag: String, expected: String, evidence: String) {
    val originalSize = f.device.executeShellCommand("wm size").trim()
    val override = Regex("Override size: ([0-9]+x[0-9]+)").find(originalSize)?.groupValues?.get(1)
    val rotation = f.device.displayRotation
    val userRotation = f.device.executeShellCommand("settings --user current get system user_rotation").trim()
    val accelerometer = f.device.executeShellCommand("settings --user current get system accelerometer_rotation").trim()
    check(rotation == 0) { "Qualification starts in its recorded portrait orientation" }
    check(f.base.resources.displayMetrics.densityDpi == 420) { "Requires the dedicated420dpi qualification device" }
    var completed = false
    fun currentLayout(): androidx.compose.ui.text.TextLayoutResult {
        val results = mutableListOf<androidx.compose.ui.text.TextLayoutResult>()
        compose.onNodeWithTag(inputTag).performSemanticsAction(SemanticsActions.GetTextLayoutResult) { assertTrue(it(results)) }
        return results.single { it.layoutInput.text.text == expected }
    }
    val portraitLayout = currentLayout()
    fun imeVisible(): Boolean {
        var visible = false
        f.instrumentation.runOnMainSync {
            visible = android.view.inspector.WindowInspector.getGlobalWindowViews().any { view ->
                view.rootWindowInsets?.let { WindowInsetsCompat.toWindowInsetsCompat(it).isVisible(WindowInsetsCompat.Type.ime()) } == true
            }
        }
        return visible
    }
    try {
        // Fix the physical qualification case independently of a surrounding
        // narrow-width run, retaining its font scale and restoring its size.
        f.device.executeShellCommand("wm size 1080x1920")
        f.device.setOrientationLeft()
        compose.waitUntil(10_000) { f.device.displayWidth == 1920 && f.device.displayHeight == 1080 }
        compose.onNodeWithTag(inputTag).performTouchInput { click() }
        compose.waitUntil(8_000) { imeVisible() }
        compose.onNodeWithTag(inputTag).assertIsFocused().assert(SemanticsMatcher("Exact landscape draft") {
            it.config[SemanticsProperties.EditableText].text == expected
        })
        f.instrumentation.uiAutomation.waitForIdle(100, 5_000)
        fun nativeEditor(): android.view.accessibility.AccessibilityNodeInfo? {
            if (android.os.Build.VERSION.SDK_INT >= 33) f.instrumentation.uiAutomation.clearCache()
            fun focused(node: android.view.accessibility.AccessibilityNodeInfo): android.view.accessibility.AccessibilityNodeInfo? {
                if (node.isEditable && node.isFocused && node.text?.toString() == expected) return node
                for (i in 0 until node.childCount) node.getChild(i)?.let { focused(it)?.let { found -> return found } }
                return null
            }
            return f.instrumentation.uiAutomation.windows.mapNotNull { it.root }
                .filter { it.packageName?.toString() == f.base.packageName }.firstNotNullOfOrNull(::focused)
        }
        var initialEditor: android.view.accessibility.AccessibilityNodeInfo? = null
        compose.waitUntil(5_000) { initialEditor = nativeEditor(); initialEditor != null }
        val native = requireNotNull(initialEditor)
        val selectionNeeded = native.textSelectionStart != expected.length || native.textSelectionEnd != expected.length
        val selectionAccepted = if (selectionNeeded) native.performAction(
            android.view.accessibility.AccessibilityNodeInfo.ACTION_SET_SELECTION, android.os.Bundle().apply {
                putInt(android.view.accessibility.AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, expected.length)
                putInt(android.view.accessibility.AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, expected.length)
            }) else null
        File(f.output, "$evidence-selection.json").writeText(JSONObject().put("before_start", native.textSelectionStart)
            .put("before_end", native.textSelectionEnd).put("requested_end", expected.length)
            .put("native_end_action_needed", selectionNeeded).put("native_end_action_accepted", selectionAccepted ?: JSONObject.NULL)
            .put("set_text_action_used", false).toString(2))
        if (selectionNeeded) assertEquals("Native end-selection action must be accepted", true, selectionAccepted)
        compose.waitUntil(5_000) { nativeEditor()?.let { it.textSelectionStart == expected.length && it.textSelectionEnd == expected.length } == true }
        val layout = currentLayout()
        assertEquals("Landscape must retain the user's text size", portraitLayout.layoutInput.style.fontSize, layout.layoutInput.style.fontSize)
        assertEquals("Landscape must retain the user's line height", portraitLayout.layoutInput.style.lineHeight, layout.layoutInput.style.lineHeight)
        assertEquals("Landscape must retain actual scaled cursor height", portraitLayout.getCursorRect(expected.length).height,
            layout.getCursorRect(expected.length).height, 1f)
        val line = layout.getLineForOffset(expected.length)
        val start = layout.getLineStart(line)
        val end = layout.getLineEnd(line, visibleEnd = true)
        val cursor = layout.getCursorRect(expected.length)
        check(end > start && cursor.height > 0)
        val density = f.base.resources.displayMetrics.density
        val backIcon = requireNotNull(f.device.findObject(By.desc(f.base.getString(R.string.nav_back)).pkg(f.base.packageName)))
        val back = generateSequence(backIcon) { it.parent }.first { it.isClickable }
        val backBounds = back.visibleBounds
        // Public native accessibility exposes the actual full-width topbar
        // parent, including its padding, rather than guessing from icon size.
        val bar = generateSequence(back.parent) { it.parent }.first { it.visibleBounds.width() >= f.device.displayWidth - 4 }
        val topbar = bar.visibleBounds
        val send = compose.onNodeWithTag(sendTag).fetchSemanticsNode().boundsInRoot
        var diagnostic = "No full rendered native caret"
        var proof: JSONObject? = null
        try {
            compose.waitUntil(6_000) {
                val editor = nativeEditor()
                if (editor == null || editor.textSelectionEnd != expected.length || editor.textSelectionStart != expected.length) false else {
                    val bounds = Rect(); editor.getBoundsInScreen(bounds)
                    val field = RectF(bounds); val viewport = RectF(f.unobscuredWindow())
                    val bitmap = f.instrumentation.uiAutomation.takeScreenshot()
                    if (bitmap == null) false else try {
                        val pixels = IntArray(bounds.width() * bounds.height())
                        bitmap.getPixels(pixels, 0, bounds.width(), bounds.left, bounds.top, bounds.width(), bounds.height())
                        fun pixel(x: Int, y: Int) = pixels[(y - bounds.top) * bounds.width() + x - bounds.left] and 0xFFFFFF
                        val colors = mutableMapOf<Int, Int>()
                        for (y in bounds.centerY() - 10 until bounds.centerY() + 10) for (x in bounds.left until bounds.left + 12) {
                            val c = pixel(x, y); val r = c ushr 16; val g = (c ushr 8) and 255; val b = c and 255
                            if (g - r >= 12 && g - b >= 12) colors[c] = (colors[c] ?: 0) + 1
                        }
                        val ink = colors.maxByOrNull { it.value }?.key
                        val runs = mutableListOf<Rect>()
                        if (ink != null) {
                            fun matches(c: Int) = kotlin.math.abs((c ushr 16) - (ink ushr 16)) <= 4 &&
                                kotlin.math.abs(((c ushr 8) and 255) - ((ink ushr 8) and 255)) <= 4 &&
                                kotlin.math.abs((c and 255) - (ink and 255)) <= 4
                            val margin = (12 * density).toInt()
                            for (x in bounds.left + margin until bounds.right - margin) {
                                var y = bounds.top + 4
                                while (y < bounds.bottom - 4) {
                                    if (!matches(pixel(x, y))) { y++; continue }
                                    val first = y
                                    while (y < bounds.bottom - 4 && matches(pixel(x, y))) y++
                                    if (kotlin.math.abs(y - first - cursor.height) <= 4f) runs += Rect(x, first, x + 1, y)
                                }
                            }
                        }
                        val groups = mutableListOf<Rect>()
                        for (run in runs) {
                            val last = groups.lastOrNull()
                            if (last != null && run.left == last.right && kotlin.math.abs(run.top - last.top) <= 2 && kotlin.math.abs(run.bottom - last.bottom) <= 2) last.union(run)
                            else groups += Rect(run)
                        }
                        val carets = groups.filter { it.width() <= 4 * density }
                        diagnostic = "carets=$carets layoutCursor=$cursor editor=$field topbar=$topbar viewport=$viewport send=$send"
                        if (carets.size != 1) false else {
                            val rendered = RectF(carets.single()); val dx = rendered.centerX() - cursor.center.x; val dy = rendered.top - cursor.top
                            val boxes = (start until end).map { offset -> layout.getBoundingBox(offset).let { RectF(it.left + dx, it.top + dy, it.right + dx, it.bottom + dy) } }
                            val visible = viewport.contains(field) && field.top >= topbar.bottom - 1 && viewport.contains(rendered) && field.contains(rendered) &&
                                boxes.all { !it.isEmpty && viewport.contains(it) && field.contains(it) } &&
                                viewport.contains(RectF(backBounds)) && backBounds.height() >= 48 * density - 1 &&
                                viewport.contains(RectF(send.left, send.top, send.right, send.bottom)) && send.height >= 48 * density - 1
                            if (visible) {
                                proof = JSONObject().put("editor", field.toString()).put("topbar", topbar.toShortString())
                                    .put("viewport", viewport.toString()).put("rendered_caret", rendered.toString()).put("layout_cursor", cursor.toString())
                                    .put("projected_glyph_boxes", JSONArray(boxes.map { it.toString() })).put("back", backBounds.toShortString()).put("send", send.toString())
                                    .put("font_scale", f.base.resources.configuration.fontScale.toDouble()).put("no_font_shrinking", true)
                                    .put("native_glyph_api_claimed", false).put("method", "native_rendered_caret_and_actual_production_text_layout")
                            }
                            visible
                        }
                    } finally { bitmap.recycle() }
                }
            }
        } catch (failure: Throwable) { throw AssertionError("Short landscape composer clipped/overlapping: $diagnostic", failure) }
        File(f.output, "$evidence-geometry.json").writeText(requireNotNull(proof).toString(2))
        f.capture(evidence)
        completed = true
    } catch (failure: Throwable) {
        runCatching { f.capture("$evidence-failed-before-restore") }.onFailure { failure.addSuppressed(it) }
        throw failure
    } finally {
        f.device.setOrientationNatural()
        f.device.executeShellCommand("wm size ${override ?: "reset"}")
        f.device.unfreezeRotation()
        for ((name, value) in listOf("user_rotation" to userRotation, "accelerometer_rotation" to accelerometer)) {
            f.device.executeShellCommand(if (value == "null") "settings --user current delete system $name" else "settings --user current put system $name $value")
        }
        compose.waitUntil(10_000) { f.device.displayRotation == rotation && f.device.displayWidth < f.device.displayHeight }
        assertEquals(originalSize, f.device.executeShellCommand("wm size").trim())
        assertEquals(userRotation, f.device.executeShellCommand("settings --user current get system user_rotation").trim())
        assertEquals(accelerometer, f.device.executeShellCommand("settings --user current get system accelerometer_rotation").trim())
        if (completed) {
            compose.onNodeWithTag(inputTag).performTouchInput { click() }
            compose.waitUntil(8_000) { imeVisible() }
            compose.onNodeWithTag(inputTag).assert(SemanticsMatcher("Draft retained after landscape restoration") { it.config[SemanticsProperties.EditableText].text == expected })
        }
    }
}
