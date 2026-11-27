package co.fallsoft.vipi

import android.graphics.Rect
import android.graphics.RectF
import android.view.Choreographer
import androidx.compose.ui.test.junit4.ComposeTestRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import java.io.File
import java.util.concurrent.atomic.AtomicInteger
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertTrue

/**
 * Native paragraph, actual timeline/editor and OS IME geometry. Stable frames plus retained pixels
 * are required; semantics presence alone is insufficient.
 */
internal fun MainActivityJourneyFixture.assertIncomingAboveComposer(
    compose: ComposeTestRule,
    original: String,
    name: String,
) {
    val frames = AtomicInteger()
    val ticker =
        object : Choreographer.FrameCallback {
            override fun doFrame(frameTimeNanos: Long) {
                frames.incrementAndGet()
                Choreographer.getInstance().postFrameCallback(this)
            }
        }
    val samples = JSONArray()
    var nativePaint: android.graphics.Bitmap? = null
    fun observe(): Pair<Boolean, String> {
        val viewport = unobscuredWindow()
        val timeline =
            compose.onNodeWithTag("conversation-timeline").fetchSemanticsNode().boundsInWindow
        val editor = compose.onNodeWithTag("message-input").fetchSemanticsNode().boundsInWindow
        var ok = false
        var geometry = "Incoming native paragraph absent"
        val sample =
            JSONObject()
                .put("frame", frames.get())
                .put("uptime_ms", android.os.SystemClock.uptimeMillis())
                .put("viewport", viewport.toShortString())
                .put("timeline", timeline.toString())
                .put("editor", editor.toString())
        instrumentation.runOnMainSync {
            paragraphs()
                .singleOrNull { it.originalMessage == original }
                ?.let { paragraph ->
                    val screen = IntArray(2)
                    val window = IntArray(2)
                    paragraph.getLocationOnScreen(screen)
                    paragraph.getLocationInWindow(window)
                    val dx = screen[0] - window[0]
                    val dy = screen[1] - window[1]
                    val full =
                        Rect(
                            screen[0],
                            screen[1],
                            screen[0] + paragraph.width,
                            screen[1] + paragraph.height,
                        )
                    val list =
                        RectF(
                            timeline.left + dx,
                            timeline.top + dy,
                            timeline.right + dx,
                            timeline.bottom + dy,
                        )
                    val input =
                        RectF(
                            editor.left + dx,
                            editor.top + dy,
                            editor.right + dx,
                            editor.bottom + dy,
                        )
                    // The native and Compose origins may round a blank leading
                    // pixel differently. Measure every actually painted glyph/slot
                    // from THIS real TextView, with no geometry tolerance or text copy.
                    val before =
                        listOf(
                            paragraph.originalMessage,
                            paragraph.text.toString(),
                            paragraph.text.toString(),
                            paragraph.selectionStart,
                            paragraph.selectionEnd,
                            paragraph.scrollX,
                            paragraph.scrollY,
                            paragraph.width,
                            paragraph.height,
                            paragraph.layout,
                        )
                    val bitmap =
                        android.graphics.Bitmap.createBitmap(
                            paragraph.width,
                            paragraph.height,
                            android.graphics.Bitmap.Config.ARGB_8888,
                        )
                    paragraph.draw(android.graphics.Canvas(bitmap))
                    val pixels = IntArray(bitmap.width * bitmap.height)
                    bitmap.getPixels(pixels, 0, bitmap.width, 0, 0, bitmap.width, bitmap.height)
                    var left = bitmap.width
                    var top = bitmap.height
                    var right = -1
                    var bottom = -1
                    var paintedPixels = 0
                    pixels.forEachIndexed { index, color ->
                        if (android.graphics.Color.alpha(color) > 0) {
                            val x = index % bitmap.width
                            val y = index / bitmap.width
                            left = minOf(left, x)
                            top = minOf(top, y)
                            right = maxOf(right, x)
                            bottom = maxOf(bottom, y)
                            paintedPixels++
                        }
                    }
                    val after =
                        listOf(
                            paragraph.originalMessage,
                            paragraph.text.toString(),
                            paragraph.text.toString(),
                            paragraph.selectionStart,
                            paragraph.selectionEnd,
                            paragraph.scrollX,
                            paragraph.scrollY,
                            paragraph.width,
                            paragraph.height,
                            paragraph.layout,
                        )
                    check(before == after) { "Native bitmap draw changed actual paragraph state" }
                    check(paintedPixels in 1 until pixels.size) {
                        "Requires nonempty native paint over a transparent background"
                    }
                    val localInk = Rect(left, top, right + 1, bottom + 1)
                    val ink = Rect(localInk).apply { offset(screen[0], screen[1]) }
                    nativePaint?.recycle()
                    nativePaint = bitmap
                    val layout = paragraph.layout
                    val completeLayout =
                        layout != null &&
                            layout.lineCount > 0 &&
                            layout.getLineEnd(layout.lineCount - 1) == paragraph.text.length &&
                            (0 until layout.lineCount).all { layout.getEllipsisCount(it) == 0 } &&
                            paragraph.totalPaddingTop - paragraph.scrollY +
                                layout.getLineBottom(layout.lineCount - 1) <=
                                paragraph.height - paragraph.totalPaddingBottom
                    val reportedVisible = Rect()
                    val nativeInkVisible =
                        paragraph.isShown &&
                            paragraph.hasWindowFocus() &&
                            paragraph.getGlobalVisibleRect(reportedVisible) &&
                            reportedVisible.contains(ink)
                    ok =
                        completeLayout &&
                            nativeInkVisible &&
                            paragraph.alpha == 1f &&
                            viewport.contains(ink) &&
                            list.contains(RectF(ink)) &&
                            ink.bottom <= input.top &&
                            paragraph.text.toString().isNotBlank()
                    geometry =
                        "native=$full ink=$ink face=${paragraph.text.toString()} pixels=${pixels.contentHashCode()} timeline=$list editor=$input viewport=$viewport"
                    val baselines = JSONArray()
                    paragraph.layout?.let { layout ->
                        repeat(layout.lineCount) { line ->
                            baselines.put(
                                screen[1] + paragraph.totalPaddingTop - paragraph.scrollY +
                                    layout.getLineBaseline(line)
                            )
                        }
                    }
                    sample
                        .put("original", original)
                        .put("drawn", paragraph.text.toString())
                        .put("full_bounds", full.toShortString())
                        .put("native_global_ink_visible", nativeInkVisible)
                        .put("native_container_inside_timeline", list.contains(RectF(full)))
                        .put("paint_local_bounds", localInk.toShortString())
                        .put("paint_screen_bounds", ink.toShortString())
                        .put("painted_pixels", paintedPixels)
                        .put("paint_hash", pixels.contentHashCode())
                        .put("native_baselines", baselines)
                        .put("native_draw_preserved_state", before == after)
                        .put(
                            "native_layout_complete_without_ellipsis_or_internal_bottom_clip",
                            completeLayout,
                        )
                        .put("geometric_tolerance_px", 0)
                }
        }
        sample.put("complete_native_paint_inside_timeline_above_composer_and_IME", ok)
        if (samples.length() >= 24) samples.remove(0)
        samples.put(sample)
        return ok to geometry
    }
    instrumentation.runOnMainSync { Choreographer.getInstance().postFrameCallback(ticker) }
    var last = ""
    var lastFrame = -1
    var stableFrames = 0
    var since = 0L
    var accepted = ""
    try {
        compose.waitUntil(8_000) {
            val (visible, geometry) = observe()
            val frame = frames.get()
            if (!visible || geometry != last) {
                stableFrames = 0
                since = android.os.SystemClock.uptimeMillis()
            }
            if (visible && frame != lastFrame) stableFrames++
            last = geometry
            lastFrame = frame
            (visible && stableFrames >= 3 && android.os.SystemClock.uptimeMillis() - since >= 80)
                .also { if (it) accepted = geometry }
        }
        File(output, "$name-native-paint.png").outputStream().use { stream ->
            check(
                requireNotNull(nativePaint)
                    .compress(android.graphics.Bitmap.CompressFormat.PNG, 100, stream)
            )
        }
        capture(name)
        val after = observe()
        assertTrue(
            "Incoming position changed across capture: $accepted -> ${after.second}",
            after.first && after.second == accepted,
        )
    } catch (failure: Throwable) {
        runCatching { capture("$name-failure") }.onFailure { failure.addSuppressed(it) }
        runCatching { recordLayoutDiagnostics(compose, name, original = original) }
            .onFailure { failure.addSuppressed(it) }
        throw AssertionError("Incoming paragraph must remain fully readable: $last", failure)
    } finally {
        instrumentation.runOnMainSync { Choreographer.getInstance().removeFrameCallback(ticker) }
        nativePaint?.recycle()
        File(output, "$name-observations.json")
            .writeText(
                JSONObject()
                    .put("observations", samples)
                    .put("root_pixel_review_required", true)
                    .put("semantics_only_visibility_claimed", false)
                    .toString(2)
            )
    }
}

/**
 * Native AX containment against the actual OS IME window, with pixels retained separately. Does not
 * claim character/glyph-layout evidence from AX bounds.
 */
internal fun MainActivityJourneyFixture.assertNativeTextInViewport(
    compose: ComposeTestRule,
    text: String,
    name: String,
    minimumHeightDp: Int = 0,
    requireClickOwner: Boolean = false,
) {
    var last =
        JSONObject()
            .put("text", text)
            .put("minimum_height_dp", minimumHeightDp)
            .put("require_native_click_owner", requireClickOwner)
    fun matches(
        node: android.view.accessibility.AccessibilityNodeInfo
    ): List<android.view.accessibility.AccessibilityNodeInfo> = buildList {
        if (node.text?.toString() == text) add(node)
        for (index in 0 until node.childCount) node.getChild(index)?.let { addAll(matches(it)) }
    }
    try {
        compose.waitUntil(5_000) {
            if (android.os.Build.VERSION.SDK_INT >= 33) instrumentation.uiAutomation.clearCache()
            val viewport = unobscuredWindow()
            val labels =
                instrumentation.uiAutomation.windows
                    .mapNotNull { it.root }
                    .filter { it.packageName?.toString() == base.packageName }
                    .flatMap(::matches)
            val label = labels.singleOrNull()
            var target = label
            if (requireClickOwner) {
                while (
                    target != null &&
                        !(target.isClickable &&
                            target.actionList.any {
                                it.id ==
                                    android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK
                            })
                ) target = target.parent
            }
            val labelBounds = Rect()
            label?.getBoundsInScreen(labelBounds)
            val fullBounds = Rect()
            target?.getBoundsInScreen(fullBounds)
            val click =
                target?.actionList?.any {
                    it.id == android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK
                } == true
            val accepted =
                label != null &&
                    target != null &&
                    target.packageName?.toString() == base.packageName &&
                    label.isVisibleToUser &&
                    target.isVisibleToUser &&
                    target.isEnabled &&
                    !fullBounds.isEmpty &&
                    viewport.contains(labelBounds) &&
                    viewport.contains(fullBounds) &&
                    fullBounds.height() >=
                        minimumHeightDp * base.resources.displayMetrics.density &&
                    (!requireClickOwner || (target.isClickable && click))
            last =
                JSONObject()
                    .put("text", text)
                    .put("label_bounds", labelBounds.toString())
                    .put("native_owner_bounds", fullBounds.toString())
                    .put("unobscured_window", viewport.toString())
                    .put("label_matches", labels.size)
                    .put("owner_class", target?.className?.toString())
                    .put("owner_clickable", target?.isClickable)
                    .put("owner_ACTION_CLICK", click)
                    .put("minimum_height_dp", minimumHeightDp)
                    .put("require_native_click_owner", requireClickOwner)
                    .put("accepted", accepted)
                    .put("character_geometry_proof_claimed", false)
            accepted
        }
    } finally {
        File(output, "$name-native-bounds.json").writeText(last.toString(2))
        if (!last.optBoolean("accepted"))
            runCatching { recordLayoutDiagnostics(compose, name, label = text) }
                .onFailure {
                    File(output, "$name-layout-diagnostic-error.json")
                        .writeText(JSONObject().put("error", it.toString()).toString(2))
                }
    }
}

/**
 * Production Compose text-layout geometry, not a copied text render. Every non-whitespace glyph
 * must fit the actual status scroll viewport and OS IME. This is scoped to a normal portrait window
 * where the full recovery sentence must fit; smaller viewports retain the existing bounded scroll
 * interaction.
 */
internal fun MainActivityJourneyFixture.assertCompleteComposeStatus(
    compose: ComposeTestRule,
    text: String,
    name: String,
) {
    var last = JSONObject()
    try {
        compose.waitUntil(5_000) {
            val node = compose.onNodeWithText(text).fetchSemanticsNode()
            val results = mutableListOf<androidx.compose.ui.text.TextLayoutResult>()
            val action =
                node.config[androidx.compose.ui.semantics.SemanticsActions.GetTextLayoutResult]
                    .action
            check(action?.invoke(results) == true && results.size == 1)
            val layout = results.single()
            val status =
                compose.onNodeWithTag("bot-access-consent").fetchSemanticsNode().boundsInWindow
            val origin = node.positionInWindow
            var dx = 0
            var dy = 0
            instrumentation.runOnMainSync {
                val anchor = paragraphs().first()
                val screen = IntArray(2)
                val window = IntArray(2)
                anchor.getLocationOnScreen(screen)
                anchor.getLocationInWindow(window)
                dx = screen[0] - window[0]
                dy = screen[1] - window[1]
            }
            val viewport = unobscuredWindow()
            val bounds = JSONArray()
            val complete =
                !layout.hasVisualOverflow &&
                    text.indices
                        .filter { !text[it].isWhitespace() }
                        .all { index ->
                            val glyph = layout.getBoundingBox(index).translate(origin)
                            val inside =
                                glyph.left >= status.left &&
                                    glyph.top >= status.top &&
                                    glyph.right <= status.right &&
                                    glyph.bottom <= status.bottom &&
                                    glyph.left + dx >= viewport.left &&
                                    glyph.top + dy >= viewport.top &&
                                    glyph.right + dx <= viewport.right &&
                                    glyph.bottom + dy <= viewport.bottom
                            if (!inside)
                                bounds.put(
                                    JSONObject()
                                        .put("index", index)
                                        .put("glyph_window", glyph.toString())
                                )
                            inside
                        }
            last =
                JSONObject()
                    .put("text", text)
                    .put("production_layout_text", layout.layoutInput.text.text)
                    .put("layout_lines", layout.lineCount)
                    .put("layout_visual_overflow", layout.hasVisualOverflow)
                    .put("text_origin_window", origin.toString())
                    .put("actual_status_viewport_window", status.toString())
                    .put("actual_native_unobscured_window", viewport.toShortString())
                    .put("window_to_screen", "$dx,$dy")
                    .put("outside_glyphs", bounds)
                    .put("all_non_whitespace_glyphs_visible", complete)
                    .put("geometry_tolerance_px", 0)
                    .put("native_character_location_api_claimed", false)
            complete && layout.layoutInput.text.text == text
        }
    } finally {
        File(output, "$name.json").writeText(last.toString(2))
    }
}

/**
 * Current dedicated API34 emulator's observed Gboard action key. This presses the actual OS IME
 * button; it does not invoke the app's lookup callback or the Compose OnImeAction semantics
 * directly. Other keyboard packages are not claimed.
 */
internal fun MainActivityJourneyFixture.tapNativeGboardSearch(
    compose: ComposeTestRule,
    name: String,
) {
    var key: androidx.test.uiautomator.UiObject2? = null
    compose.waitUntil(5_000) {
        if (android.os.Build.VERSION.SDK_INT >= 33) instrumentation.uiAutomation.clearCache()
        key =
            device.findObject(
                androidx.test.uiautomator.By.res(
                    "com.google.android.inputmethod.latin:id/key_pos_ime_action"
                )
            )
        key?.let {
            it.isEnabled &&
                it.isClickable &&
                it.contentDescription == "Search" &&
                !it.visibleBounds.isEmpty
        } == true
    }
    val action = requireNotNull(key)
    val bounds = action.visibleBounds
    File(output, "$name.json")
        .writeText(
            JSONObject()
                .put("keyboard_package", action.applicationPackage)
                .put("resource", action.resourceName)
                .put("native_label", action.contentDescription)
                .put("native_bounds", bounds.toShortString())
                .put("native_touch_dispatch", true)
                .put("app_callback_or_compose_ime_semantics_invoked_directly", false)
                .toString(2)
        )
    capture(name)
    check(device.click(bounds.centerX(), bounds.centerY()))
}

/**
 * A constrained error footer need not show an entire long message at once, but a real reading
 * gesture must expose a complete painted native line.
 */
internal fun MainActivityJourneyFixture.assertNativeBotMessageLineAboveComposer(
    compose: ComposeTestRule,
    original: String,
    name: String,
) {
    val listMatcher =
        androidx.compose.ui.test.SemanticsMatcher("Actual Bot LazyColumn") {
            it.config.contains(androidx.compose.ui.semantics.SemanticsActions.ScrollToIndex)
        }
    var evidence: JSONObject? = null
    compose.waitUntil(5_000) {
        val timeline = compose.onNode(listMatcher).fetchSemanticsNode().boundsInWindow
        val editor = compose.onNodeWithTag("bot-message-input").fetchSemanticsNode().boundsInWindow
        val viewport = unobscuredWindow()
        instrumentation.runOnMainSync {
            paragraphs()
                .singleOrNull { it.originalMessage == original }
                ?.let { paragraph ->
                    val layout = paragraph.layout ?: return@let
                    val screen = IntArray(2)
                    val window = IntArray(2)
                    paragraph.getLocationOnScreen(screen)
                    paragraph.getLocationInWindow(window)
                    val dx = screen[0] - window[0]
                    val dy = screen[1] - window[1]
                    val actualList =
                        RectF(
                            timeline.left + dx,
                            timeline.top + dy,
                            timeline.right + dx,
                            timeline.bottom + dy,
                        )
                    val inputTop = editor.top + dy
                    val before =
                        listOf(
                            paragraph.text.toString(),
                            paragraph.text.toString(),
                            paragraph.scrollY,
                            paragraph.layout,
                        )
                    val bitmap =
                        android.graphics.Bitmap.createBitmap(
                            paragraph.width,
                            paragraph.height,
                            android.graphics.Bitmap.Config.ARGB_8888,
                        )
                    try {
                        paragraph.draw(android.graphics.Canvas(bitmap))
                        val pixels = IntArray(bitmap.width * bitmap.height)
                        bitmap.getPixels(pixels, 0, bitmap.width, 0, 0, bitmap.width, bitmap.height)
                        check(
                            before ==
                                listOf(
                                    paragraph.text.toString(),
                                    paragraph.text.toString(),
                                    paragraph.scrollY,
                                    paragraph.layout,
                                )
                        )
                        val nativeVisible = Rect()
                        val shown =
                            paragraph.isShown &&
                                paragraph.alpha == 1f &&
                                paragraph.getGlobalVisibleRect(nativeVisible)
                        for (line in 0 until layout.lineCount) {
                            val a =
                                paragraph.totalPaddingTop - paragraph.scrollY +
                                    layout.getLineTop(line)
                            val b =
                                paragraph.totalPaddingTop - paragraph.scrollY +
                                    layout.getLineBottom(line)
                            if (
                                a < paragraph.totalPaddingTop ||
                                    b > bitmap.height - paragraph.totalPaddingBottom
                            )
                                continue
                            var left = bitmap.width
                            var top = bitmap.height
                            var right = -1
                            var bottom = -1
                            for (y in a until b) for (x in 0 until bitmap.width) if (
                                android.graphics.Color.alpha(pixels[y * bitmap.width + x]) > 0
                            ) {
                                left = minOf(left, x)
                                right = maxOf(right, x)
                                top = minOf(top, y)
                                bottom = maxOf(bottom, y)
                            }
                            if (right < left) continue
                            val ink =
                                Rect(
                                    left + screen[0],
                                    top + screen[1],
                                    right + screen[0] + 1,
                                    bottom + screen[1] + 1,
                                )
                            if (
                                shown &&
                                    nativeVisible.contains(ink) &&
                                    actualList.contains(RectF(ink)) &&
                                    viewport.contains(ink) &&
                                    ink.bottom <= inputTop &&
                                    layout.getEllipsisCount(line) == 0
                            ) {
                                File(output, "$name-native-paint.png").outputStream().use {
                                    check(
                                        bitmap.compress(
                                            android.graphics.Bitmap.CompressFormat.PNG,
                                            100,
                                            it,
                                        )
                                    )
                                }
                                evidence =
                                    JSONObject()
                                        .put(
                                            "method",
                                            "actual_native_paragraph_draw_one_complete_line_after_real_reading_scroll",
                                        )
                                        .put("original", original)
                                        .put("drawn", paragraph.text.toString())
                                        .put("line", line)
                                        .put(
                                            "source_offsets",
                                            "${layout.getLineStart(line)}..${layout.getLineEnd(line)}",
                                        )
                                        .put("native_line_paint", ink.toShortString())
                                        .put("timeline", actualList.toString())
                                        .put("editor_top", inputTop)
                                        .put("unobscured_window", viewport.toShortString())
                                        .put("geometric_tolerance_px", 0)
                                        .put("native_draw_preserved_state", true)
                                break
                            }
                        }
                    } finally {
                        bitmap.recycle()
                    }
                }
        }
        evidence != null
    }
    File(output, "$name.json").writeText(requireNotNull(evidence).toString(2))
    capture(name)
}

/**
 * Bounded read-only diagnostic for actual layout coordinates. Never invokes a scroll/click callback
 * or writes captured state. No guessed fallback state.
 */
private fun MainActivityJourneyFixture.recordLayoutDiagnostics(
    compose: ComposeTestRule,
    name: String,
    label: String? = null,
    original: String? = null,
) {
    val result =
        JSONObject()
            .put("read_only", true)
            .put("action_invocations", 0)
            .put("unobscured_window", unobscuredWindow().toShortString())
    if (label != null) {
        val parents = JSONArray()
        var node: androidx.compose.ui.semantics.SemanticsNode? =
            compose.onNodeWithText(label).fetchSemanticsNode()
        while (node != null && parents.length() < 8) {
            val current = node
            parents.put(
                JSONObject()
                    .put("id", current.id)
                    .put("position_in_window", current.positionInWindow.toString())
                    .put("measured_size", current.size.toString())
                    .put("clipped_bounds_in_window", current.boundsInWindow.toString())
                    .put(
                        "has_OnClick",
                        current.config.contains(
                            androidx.compose.ui.semantics.SemanticsActions.OnClick
                        ),
                    )
            )
            node = current.parent
        }
        result.put("actual_label_semantics_and_ancestors", parents)
    }
    val matches = compose.onAllNodesWithTag("conversation-timeline").fetchSemanticsNodes()
    if (matches.size == 1) {
        val timeline = matches.single()
        result.put("timeline_semantics", timeline.boundsInWindow.toString())
        val callback =
            timeline.config[androidx.compose.ui.semantics.SemanticsActions.ScrollToIndex].action
        if (callback != null) {
            val fields =
                callback.javaClass.declaredFields.filter {
                    androidx.compose.foundation.lazy.LazyListState::class
                        .java
                        .isAssignableFrom(it.type)
                }
            result
                .put("callback_class", callback.javaClass.name)
                .put("exact_LazyListState_field_count", fields.size)
                .put(
                    "callback_field_types",
                    JSONArray(callback.javaClass.declaredFields.map { it.type.name }),
                )
            if (fields.size == 1) {
                val field = fields.single().apply { isAccessible = true }
                val state = field.get(callback) as? androidx.compose.foundation.lazy.LazyListState
                if (state != null)
                    compose.runOnIdle {
                        val layout = state.layoutInfo
                        result.put(
                            "actual_captured_lazy_state",
                            JSONObject()
                                .put("viewport_size", layout.viewportSize.toString())
                                .put("viewport_start_offset", layout.viewportStartOffset)
                                .put("viewport_end_offset", layout.viewportEndOffset)
                                .put("before_content_padding", layout.beforeContentPadding)
                                .put("after_content_padding", layout.afterContentPadding)
                                .put("first_visible_item_index", state.firstVisibleItemIndex)
                                .put(
                                    "first_visible_item_scroll_offset",
                                    state.firstVisibleItemScrollOffset,
                                )
                                .put("total_items_count", layout.totalItemsCount)
                                .put(
                                    "rows",
                                    JSONArray(
                                        layout.visibleItemsInfo.map { row ->
                                            JSONObject()
                                                .put("index", row.index)
                                                .put("offset", row.offset)
                                                .put("size", row.size)
                                        }
                                    ),
                                ),
                        )
                    }
                else result.put("captured_state_missing", true)
            } else result.put("captured_state_missing_or_ambiguous", true)
        } else result.put("scroll_callback_missing", true)
    } else result.put("timeline_match_count", matches.size)
    instrumentation.runOnMainSync {
        val roots = JSONArray()
        android.view.inspector.WindowInspector.getGlobalWindowViews().forEach { view ->
            val xy = IntArray(2)
            view.getLocationOnScreen(xy)
            val insets = view.rootWindowInsets
            val frame = Rect()
            view.getWindowVisibleDisplayFrame(frame)
            roots.put(
                JSONObject()
                    .put("class", view.javaClass.name)
                    .put("screen_origin", "${xy[0]},${xy[1]}")
                    .put("size", "${view.width}x${view.height}")
                    .put("visible_display_frame", frame.toShortString())
                    .put(
                        "ime_insets",
                        insets?.getInsets(android.view.WindowInsets.Type.ime()).toString(),
                    )
                    .put(
                        "navigation_insets",
                        insets
                            ?.getInsets(android.view.WindowInsets.Type.navigationBars())
                            .toString(),
                    )
                    .put(
                        "system_insets",
                        insets?.getInsets(android.view.WindowInsets.Type.systemBars()).toString(),
                    )
            )
        }
        result.put("native_roots", roots)
        val bodies = JSONArray()
        paragraphs()
            .filter { original == null || it.originalMessage == original }
            .forEach { view ->
                val xy = IntArray(2)
                view.getLocationOnScreen(xy)
                bodies.put(
                    JSONObject()
                        .put("original", view.originalMessage)
                        .put("origin", "${xy[0]},${xy[1]}")
                        .put("size", "${view.width}x${view.height}")
                        .put("scroll_y", view.scrollY)
                )
            }
        result.put("native_paragraphs", bodies)
    }
    File(output, "$name-layout-diagnostic.json").writeText(result.toString(2))
}
