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
    inputTag: String, sendTag: String, expected: String, evidence: String, requireContentDirection: Boolean = false, requireCompactTranscript: Boolean = false) {
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
        compose.onNodeWithTag("full-message-gesture-cue").assertDoesNotExist()
        File(f.output, "$evidence-cue-before-editor-focus.json").writeText(JSONObject()
            .put("orientation", "landscape").put("cue_absent_before_explicit_editor_focus", true)
            .put("font_scale", f.base.resources.configuration.fontScale.toDouble()).toString(2))
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
            .put("set_text_action_used", false).put("blink_refresh_native_keys", "KEYCODE_X then KEYCODE_DEL; exact draft retained").toString(2))
        if (selectionNeeded) assertEquals("Native end-selection action must be accepted", true, selectionAccepted)
        compose.waitUntil(5_000) { nativeEditor()?.let { it.textSelectionStart == expected.length && it.textSelectionEnd == expected.length } == true }
        // Accessibility selection may leave an insertion handle while hiding
        // the blinking cursor. A real reversible key edit dismisses that
        // native state without replacing text or changing the retained draft.
        assertTrue(f.device.pressKeyCode(android.view.KeyEvent.KEYCODE_X))
        compose.waitUntil(5_000) { compose.onNodeWithTag(inputTag).fetchSemanticsNode().config[SemanticsProperties.EditableText].text == expected + "x" }
        assertTrue(f.device.pressKeyCode(android.view.KeyEvent.KEYCODE_DEL))
        compose.waitUntil(5_000) { compose.onNodeWithTag(inputTag).fetchSemanticsNode().config[SemanticsProperties.EditableText].text == expected }
        compose.waitUntil(5_000) { nativeEditor()?.let { it.textSelectionStart == expected.length && it.textSelectionEnd == expected.length } == true }
        val layout = currentLayout()
        if (inputTag == "bot-message-input") compose.onNodeWithText(f.base.getString(R.string.ui_cc39ebccb529)).assertDoesNotExist()
        fun layoutEvidence(value: androidx.compose.ui.text.TextLayoutResult) = JSONObject()
            .put("full_text_style", value.layoutInput.style.toString())
            .put("density", value.layoutInput.density.density).put("font_scale", value.layoutInput.density.fontScale)
            .put("line_count", value.lineCount).put("measured_size", value.size.toString())
            .put("logical_end_cursor", value.getCursorRect(expected.length).toString())
            .put("lines", JSONArray((0 until value.lineCount).map { line -> JSONObject()
                .put("start", value.getLineStart(line)).put("end", value.getLineEnd(line))
                .put("top", value.getLineTop(line)).put("bottom", value.getLineBottom(line))
                .put("baseline", value.getLineBaseline(line)) }))
        File(f.output, "$evidence-typography.json").writeText(JSONObject()
            .put("portrait", layoutEvidence(portraitLayout)).put("landscape", layoutEvidence(layout))
            .put("method", "Exact full TextStyle and density; actual wrapped/single-line metrics retained. Trim.Both may change end-line cursor box; painted caret and grapheme containment checked independently.").toString(2))
        assertEquals("Landscape must retain every typography and line-height trim setting", portraitLayout.layoutInput.style, layout.layoutInput.style)
        assertEquals("Landscape must retain actual density and font scale", portraitLayout.layoutInput.density, layout.layoutInput.density)
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
                            // A combining mark can have zero advance. Measure the
                            // actual Unicode grapheme union, preserving every raw
                            // UTF16 box; a mark is not a separate positive-width glyph.
                            val rawBoxes = (start until end).associateWith { offset -> layout.getBoundingBox(offset).let { RectF(it.left + dx, it.top + dy, it.right + dx, it.bottom + dy) } }
                            val breaks = java.text.BreakIterator.getCharacterInstance(java.util.Locale.ROOT).apply { setText(expected) }
                            val clusters = mutableListOf<Pair<Int, Int>>()
                            var begin = breaks.first(); var finish = breaks.next()
                            while (finish != java.text.BreakIterator.DONE) {
                                if (finish > start && begin < end) clusters += maxOf(begin, start) to minOf(finish, end)
                                begin = finish; finish = breaks.next()
                            }
                            val boxes = clusters.map { (a, b) ->
                                RectF(requireNotNull(rawBoxes[a])).apply { for (offset in a + 1 until b) union(requireNotNull(rawBoxes[offset])) }
                            }
                            val visible = viewport.contains(field) && field.top >= topbar.bottom - 1 && viewport.contains(rendered) && field.contains(rendered) &&
                                boxes.all { !it.isEmpty && viewport.contains(it) && field.contains(it) } &&
                                viewport.contains(RectF(backBounds)) && backBounds.height() >= 48 * density - 1 &&
                                viewport.contains(RectF(send.left, send.top, send.right, send.bottom)) && send.height >= 48 * density - 1
                            if (visible) {
                                proof = JSONObject().put("editor", field.toString()).put("topbar", topbar.toShortString())
                                    .put("viewport", viewport.toString()).put("rendered_caret", rendered.toString()).put("layout_cursor", cursor.toString())
                                    .put("projected_glyph_boxes", JSONArray(boxes.map { it.toString() }))
                                    .put("raw_utf16_boxes", JSONArray(rawBoxes.map { (offset, box) -> JSONObject().put("offset", offset).put("box", box.toString()) }))
                                    .put("unicode_grapheme_ranges", JSONArray(clusters.map { (a,b) -> JSONArray().put(a).put(b) })).put("back", backBounds.toShortString()).put("send", send.toString())
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
        if (requireCompactTranscript) {
            compose.onNodeWithTag("conversation-compact-composing").assertExists()
            compose.onNodeWithTag("conversation-timeline").assertDoesNotExist()
            f.instrumentation.runOnMainSync { assertTrue("Compact composing must paint no clipped native paragraph", f.paragraphs().isEmpty()) }
        }
        f.capture(evidence)
        if (requireContentDirection) {
            val layout = currentLayout()
            val contentRtl = !java.text.Bidi(expected, java.text.Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT).baseIsLeftToRight()
            val diagnostics = JSONObject().put("source", expected).put("content_first_expected_rtl", contentRtl)
                .put("actual_paragraph_direction", layout.getParagraphDirection(0).toString())
                .put("actual_last_run_direction", layout.getBidiRunDirection(expected.length - 1).toString())
                .put("style_text_direction", layout.layoutInput.style.textDirection.toString())
                .put("logical_end_cursor", layout.getCursorRect(expected.length).toString())
                .put("logical_end_primary_horizontal", layout.getHorizontalPosition(expected.length, true))
                .put("logical_end_secondary_horizontal", layout.getHorizontalPosition(expected.length, false))
                .put("last_logical_character_box", layout.getBoundingBox(expected.length - 1).toString())
            // An actual hardware edit at the native-selected logical end tests
            // insertion order too. Restore with real Backspace before sending.
            assertTrue(f.device.pressKeyCode(android.view.KeyEvent.KEYCODE_X))
            compose.waitUntil(5_000) { compose.onNodeWithTag(inputTag).fetchSemanticsNode().config[SemanticsProperties.EditableText].text == expected + "x" }
            diagnostics.put("native_hardware_end_insert_exact_text", expected + "x")
            f.capture("$evidence-native-end-insertion")
            assertTrue(f.device.pressKeyCode(android.view.KeyEvent.KEYCODE_DEL))
            compose.waitUntil(5_000) { compose.onNodeWithTag(inputTag).fetchSemanticsNode().config[SemanticsProperties.EditableText].text == expected }
            File(f.output, "$evidence-direction-and-insertion.json").writeText(diagnostics.toString(2))
            assertEquals("Editor paragraph must follow actual first-strong content, independent of selected languages",
                if (contentRtl) androidx.compose.ui.text.style.ResolvedTextDirection.Rtl else androidx.compose.ui.text.style.ResolvedTextDirection.Ltr,
                layout.getParagraphDirection(0))
        }
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

/** Public native editable descendant; no injected editor or hidden text state. */
internal fun MainActivityJourneyFixture.focusedNativeEditor(expected: String): android.view.accessibility.AccessibilityNodeInfo? {
    fun find(node: android.view.accessibility.AccessibilityNodeInfo): android.view.accessibility.AccessibilityNodeInfo? {
        if (node.isEditable && node.isFocused && node.text?.toString() == expected) return node
        for (i in 0 until node.childCount) node.getChild(i)?.let { find(it)?.let { found -> return found } }
        return null
    }
    if (android.os.Build.VERSION.SDK_INT >= 33) instrumentation.uiAutomation.clearCache()
    return instrumentation.uiAutomation.windows.mapNotNull { it.root }
        .filter { it.packageName?.toString() == base.packageName }.firstNotNullOfOrNull(::find)
}

internal fun assertNativeDraftEndLine(compose: androidx.compose.ui.test.junit4.ComposeTestRule, f: MainActivityJourneyFixture,
    inputTag: String, expected: String, evidence: String, requireInternalScroll: Boolean) {
    compose.onNodeWithTag(inputTag).assertIsFocused().assert(SemanticsMatcher("Exact native caret draft") {
        it.config[SemanticsProperties.EditableText].text == expected
    })
    val layouts = mutableListOf<androidx.compose.ui.text.TextLayoutResult>()
    compose.onNodeWithTag(inputTag).performSemanticsAction(androidx.compose.ui.semantics.SemanticsActions.GetTextLayoutResult) {
        assertTrue(it(layouts))
    }
    val layout = layouts.single { it.layoutInput.text.text == expected }
    val visualLine = layout.getLineForOffset(expected.length)
    val start = layout.getLineStart(visualLine)
    val end = layout.getLineEnd(visualLine, visibleEnd = true)
    val cursor = layout.getCursorRect(expected.length)
    require(end > start && cursor.height > 0)
    File(f.output, "$evidence-layout.json").writeText(JSONObject()
        .put("full_text_style", layout.layoutInput.style.toString()).put("density", layout.layoutInput.density.density)
        .put("font_scale", layout.layoutInput.density.fontScale).put("line_count", layout.lineCount)
        .put("actual_visual_end_cursor", cursor.toString()).put("actual_layout_size", layout.size.toString())
        .put("require_actual_internal_scroll", requireInternalScroll).toString(2))
    var diagnostic = "No focused native editor"
    var nativeExtraDiagnostic: JSONObject? = null
    try {
        compose.waitUntil(5_000) {
            val editor = f.focusedNativeEditor(expected)
            if (editor?.isEditable != true || editor.text?.toString() != expected ||
                editor.textSelectionStart != expected.length || editor.textSelectionEnd != expected.length) {
                diagnostic = "Native editable descendant selection ${editor?.textSelectionStart}..${editor?.textSelectionEnd}, class=${editor?.className}, extras=${editor?.availableExtraData}"
                false
            } else {
                if (nativeExtraDiagnostic == null) {
                    val key = android.view.accessibility.AccessibilityNodeInfo.EXTRA_DATA_TEXT_CHARACTER_LOCATION_KEY
                    val args = android.os.Bundle().apply {
                        putInt(android.view.accessibility.AccessibilityNodeInfo.EXTRA_DATA_TEXT_CHARACTER_LOCATION_ARG_START_INDEX, start)
                        putInt(android.view.accessibility.AccessibilityNodeInfo.EXTRA_DATA_TEXT_CHARACTER_LOCATION_ARG_LENGTH, end - start)
                    }
                    val refreshed = editor.refreshWithExtraData(key, args)
                    @Suppress("DEPRECATION") val raw = editor.extras.getParcelableArray(key)
                    nativeExtraDiagnostic = JSONObject().put("available_keys", JSONArray(editor.availableExtraData))
                        .put("refresh_succeeded", refreshed).put("raw_count", raw?.size ?: 0)
                        .put("nonnull_count", raw?.count { it != null } ?: 0)
                }
                val bounds = android.graphics.Rect(); editor.getBoundsInScreen(bounds)
                val viewport = android.graphics.RectF(f.unobscuredWindow())
                val field = android.graphics.RectF(bounds)
                val bitmap = f.instrumentation.uiAutomation.takeScreenshot()
                if (bitmap == null) false else try {
                    val pixels = IntArray(bounds.width() * bounds.height())
                    bitmap.getPixels(pixels, 0, bounds.width(), bounds.left, bounds.top, bounds.width(), bounds.height())
                    fun pixel(x: Int, y: Int) = pixels[(y - bounds.top) * bounds.width() + x - bounds.left] and 0xFFFFFF
                    val colors = mutableMapOf<Int, Int>()
                    for (y in bounds.centerY() - 10 until bounds.centerY() + 10) for (x in bounds.left until bounds.left + 12) {
                        val color = pixel(x, y); val r = color ushr 16; val g = (color ushr 8) and 255; val b = color and 255
                        if (g - r >= 12 && g - b >= 12) colors[color] = (colors[color] ?: 0) + 1
                    }
                    val ink = colors.maxByOrNull { it.value }?.key
                    val runs = mutableListOf<android.graphics.Rect>()
                    if (ink != null) {
                        fun matches(color: Int) = kotlin.math.abs((color ushr 16) - (ink ushr 16)) <= 4 &&
                            kotlin.math.abs(((color ushr 8) and 255) - ((ink ushr 8) and 255)) <= 4 &&
                            kotlin.math.abs((color and 255) - (ink and 255)) <= 4
                        val margin = (12 * f.base.resources.displayMetrics.density).toInt()
                        for (x in bounds.left + margin until bounds.right - margin) {
                            var y = bounds.top + 4
                            while (y < bounds.bottom - 4) {
                                if (!matches(pixel(x, y))) { y++; continue }
                                val top = y
                                while (y < bounds.bottom - 4 && matches(pixel(x, y))) y++
                                if (kotlin.math.abs((y - top) - cursor.height) <= 4f) runs += android.graphics.Rect(x, top, x + 1, y)
                            }
                        }
                    }
                    val groups = mutableListOf<android.graphics.Rect>()
                    runs.forEach { run ->
                        val group = groups.lastOrNull()
                        if (group != null && run.left == group.right && kotlin.math.abs(run.top - group.top) <= 2 && kotlin.math.abs(run.bottom - group.bottom) <= 2)
                            group.union(run) else groups += android.graphics.Rect(run)
                    }
                    val carets = groups.filter { it.width() <= 4 * f.base.resources.displayMetrics.density }
                    diagnostic = "Rendered caret candidates=$carets, layout cursor=$cursor, field=$field, viewport=$viewport, native=$nativeExtraDiagnostic"
                    if (carets.size != 1) false else {
                        val rendered = android.graphics.RectF(carets.single())
                        val dx = rendered.centerX() - cursor.center.x
                        val dy = rendered.top - cursor.top
                        val boxes = (start until end).map { offset ->
                            val box = layout.getBoundingBox(offset)
                            android.graphics.RectF(box.left + dx, box.top + dy, box.right + dx, box.bottom + dy)
                        }
                        val visible = viewport.contains(rendered) && field.contains(rendered) && (!requireInternalScroll || dy < field.top) &&
                            boxes.all { !it.isEmpty && viewport.contains(it) && field.contains(it) }
                        if (visible) {
                            File(f.output, "$evidence.png").outputStream().use { bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }
                            File(f.output, "$evidence.json").writeText(JSONObject()
                                .put("method", "production_text_layout_translated_by_measured_native_rendered_caret")
                                .put("native_end_selection", editor.textSelectionEnd).put("native_character_api_diagnostic", nativeExtraDiagnostic)
                                .put("visual_line", expected.substring(start, end)).put("visual_line_offsets", "$start..$end")
                                .put("layout_cursor", cursor.toString()).put("rendered_caret", rendered.toString())
                                .put("translation_x", dx.toDouble()).put("translation_y", dy.toDouble())
                                .put("editor", field.toString()).put("unobscured_window", viewport.toString())
                                .put("projected_glyph_boxes", JSONArray(boxes.map { it.toString() }))
                                .put("native_glyph_api_proof_claimed", false).toString(2))
                        }
                        visible
                    }
                } finally { bitmap.recycle() }
            }
        }
    } catch (failure: ComposeTimeoutException) { throw AssertionError(diagnostic, failure) }
}

/** User-facing native selection action; completion requires observed selection,
 * independent of a transport boolean that may be false for a no-op. */
internal fun selectNativeDraftEnd(compose: androidx.compose.ui.test.junit4.ComposeTestRule,
    f: MainActivityJourneyFixture, expected: String, evidence: String) {
    f.instrumentation.uiAutomation.waitForIdle(100, 5_000)
    var node: android.view.accessibility.AccessibilityNodeInfo? = null
    compose.waitUntil(5_000) { node = f.focusedNativeEditor(expected); node != null }
    val native = requireNotNull(node)
    val already = native.textSelectionStart == expected.length && native.textSelectionEnd == expected.length
    val proof = JSONObject().put("expected_end", expected.length).put("native_start_before", native.textSelectionStart)
        .put("native_end_before", native.textSelectionEnd).put("already_at_end", already)
    val result = if (already) null else native.performAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_SET_SELECTION,
        android.os.Bundle().apply {
            putInt(android.view.accessibility.AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, expected.length)
            putInt(android.view.accessibility.AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, expected.length)
        })
    proof.put("native_action_result", result ?: JSONObject.NULL)
    File(f.output, "$evidence.json").writeText(proof.toString(2))
    compose.waitUntil(5_000) { f.focusedNativeEditor(expected)?.let {
        it.textSelectionStart == expected.length && it.textSelectionEnd == expected.length
    } == true }
    File(f.output, "$evidence.json").writeText(proof.put("native_end_observed", expected.length).toString(2))
}
