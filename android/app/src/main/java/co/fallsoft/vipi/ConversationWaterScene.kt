package co.fallsoft.vipi

import android.animation.ValueAnimator
import android.database.ContentObserver
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.snap
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.*
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlin.math.sin

/** Original King mackerel geometry shared with the CSS study. Decoration only:
 * no pointer handler or semantics node, and no work while the app is backgrounded.
 * [motionEnabled] is a persisted Appearance preference, independent of immersion.
 */
@Composable internal fun ConversationWaterScene(
    mode: ImmersionMode,
    motionEnabled: Boolean,
    modifier: Modifier = Modifier,
    plainBackground: Boolean = false,
    listSurface: Boolean = false,
) {
    val palette = vipiPalette()
    val dark = palette.canvas.luminance() < .5f
    val deep = mode == ImmersionMode.FULL_MESSAGES
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var foreground by remember(lifecycle) { mutableStateOf(lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) }
    var systemMotion by remember { mutableStateOf(ValueAnimator.areAnimatorsEnabled()) }
    DisposableEffect(lifecycle, context) {
        val observer = LifecycleEventObserver { _, _ ->
            foreground = lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)
        }
        val settingsObserver = object : ContentObserver(Handler(Looper.getMainLooper())) {
            override fun onChange(selfChange: Boolean) { systemMotion = ValueAnimator.areAnimatorsEnabled() }
        }
        lifecycle.addObserver(observer)
        context.contentResolver.registerContentObserver(
            Settings.Global.getUriFor(Settings.Global.ANIMATOR_DURATION_SCALE), false, settingsObserver)
        onDispose { lifecycle.removeObserver(observer); context.contentResolver.unregisterContentObserver(settingsObserver) }
    }
    var seconds by remember { mutableFloatStateOf(18f) }
    val running = foreground && motionEnabled && systemMotion && !plainBackground
    LaunchedEffect(running) {
        if (!running) return@LaunchedEffect
        var prior = 0L
        while (isActive) {
            withFrameNanos { now ->
                if (prior != 0L) seconds += ((now - prior) / 1_000_000_000f).coerceIn(0f, .1f)
                prior = now
            }
            // Slow decorative movement does not need display-refresh-rate updates.
            delay(32)
        }
    }
    val depth by animateFloatAsState(if (deep) 1f else 0f,
        animationSpec = if (running) tween(320) else snap(), label = "Water depth")
    val (shallowWater, deepWater) = remember(listSurface, dark) {
        when {
            listSurface && dark -> listOf(Color(0xFF221B22), Color(0xFF27212A), Color(0xFF292530)) to
                listOf(Color(0xFF221B22), Color(0xFF25212A), Color(0xFF24232D))
            listSurface -> listOf(Color(0xFFFFF8EF), Color(0xFFF7EFE6), Color(0xFFF0E5DA)) to
                listOf(Color(0xFFFFF8EF), Color(0xFFF4EEE6), Color(0xFFEDE8E0))
            dark -> listOf(Color(0xFF221B22), Color(0xFF292934), Color(0xFF273C45)) to
                listOf(Color(0xFF24202C), Color(0xFF243542), Color(0xFF142C3A))
            else -> listOf(Color(0xFFFFF8EF), Color(0xFFF3E9DF), Color(0xFFD5DEDB)) to
                listOf(Color(0xFFF4F0E7), Color(0xFFDBE2DF), Color(0xFFC1D1D1))
        }
    }
    // Each layer has its own display list. Only the middle layer reads the clock.
    Box(modifier.clipToBounds()) {
        Canvas(Modifier.matchParentSize().graphicsLayer()) {
            drawRect(palette.canvas)
            if (plainBackground) return@Canvas
            drawRect(Brush.verticalGradient(shallowWater.indices.map { lerp(shallowWater[it], deepWater[it], depth) }))
            if (listSurface) {
                // A single continuous print/water texture, including the first rows.
                // Fixed geometry keeps the texture tactile even with motion paused.
                val pigment = if (dark) Color(0xFFC294A4) else Color(0xFF9A6370)
                repeat(17) { i ->
                    val center = Offset(size.width * (((i * 37 + 13) % 101) / 100f), size.height * (((i * 29 + 7) % 103) / 102f))
                    val radius = (70 + (i * 17 % 60)).dp.toPx()
                    drawCircle(Brush.radialGradient(listOf(pigment.copy(alpha = .055f), Color.Transparent), center, radius), radius, center)
                }
                repeat(9) { i ->
                    val y = size.height * (i + .35f) / 9f
                    val ripple = Path().apply {
                        moveTo(-size.width * .1f, y)
                        cubicTo(size.width * .24f, y - 18.dp.toPx(), size.width * .62f, y + 20.dp.toPx(), size.width * 1.1f, y - 5.dp.toPx())
                    }
                    drawPath(ripple, pigment.copy(alpha = .10f), style = Stroke(.7.dp.toPx()))
                }
            }
        }
        if (!plainBackground) {
            Canvas(Modifier.matchParentSize().graphicsLayer()) {
                val ray = (sin(seconds / 20f) * size.width * .05f)
                repeat(3) { i ->
                    val x = size.width * (i * .43f - .3f) + ray
                    val p = Path().apply {
                        moveTo(x, 0f); lineTo(x + size.width * .22f, 0f)
                        lineTo(x + size.width * .7f, size.height); lineTo(x + size.width * .38f, size.height); close()
                    }
                    drawPath(p, Color.White.copy(alpha = if (dark) .015f else .04f))
                }
                // Inbox text has no bubble backplate: constrain the scene's luminance
                // rather than placing opaque cards over the shared conversation canvas.
                val opacity = if (listSurface) { if (dark) .17f else .12f } else androidx.compose.ui.util.lerp(if (dark) .29f else .27f, .36f, depth)
                val fishWidths = listOf(size.width * .76f, size.width * .51f, size.width * .35f)
                val cycles = listOf(39f, 51f, 62f)
                val offsets = listOf(0f, 23f, 38f)
                val levels = listOf(.79f, .36f, .82f)
                fishWidths.forEachIndexed { i, rawWidth ->
                    val width = rawWidth.coerceAtMost(360.dp.toPx())
                    val progress = ((seconds + offsets[i]) % cycles[i]) / cycles[i]
                    val x = -width + progress * (size.width + width)
                    val y = size.height * levels[i] + sin(seconds / 5f + i) * 5.dp.toPx()
                    val scale = width / 640f
                    withTransform({ translate(x, y); scale(scale, scale, Offset.Zero) }) {
                        drawKingMackerel(opacity * if (i == 0) 1f else if (i == 1) .58f else .45f, seconds)
                    }
                }
                val bubbleColor = if (dark) Color(0xFFBBD0D2) else Color(0xFF8B8A8C)
                listOf(.13f, .86f, .72f, .41f).forEachIndexed { i, x ->
                    val duration = listOf(17f, 23f, 27f, 29f)[i]
                    val fraction = ((seconds + i * 7) % duration) / duration
                    val radius = listOf(3.5f, 2.5f, 4.5f, 2f)[i].dp.toPx()
                    val center = Offset(size.width * x + sin(fraction * 3f) * 9.dp.toPx(), size.height * (1f - fraction))
                    val alpha = (sin(fraction * Math.PI).toFloat() * (if (listSurface) .12f else .3f)).coerceIn(0f, .3f)
                    drawCircle(bubbleColor.copy(alpha = alpha), radius, center, style = Stroke(.65.dp.toPx()))
                }
            }
            Canvas(Modifier.matchParentSize().graphicsLayer()) {
                // Fixed deterministic grain, independent of the animation clock.
                val step = (if (listSurface) 7 else 12).dp.toPx()
                var row = 0; var y = 0f
                while (y < size.height) {
                    var column = 0; var x = 0f
                    while (x < size.width) {
                        val jitter = ((row * 31 + column * 17) % 13) / 13f
                        drawCircle(palette.ink.copy(alpha = if (listSurface) .055f else .025f), (if (listSurface) .32f else .22f).dp.toPx(), Offset(x + jitter * step, y + (1f - jitter) * step))
                        column++; x += step
                    }
                    row++; y += step
                }
            }
        }
    }
}

private data class FishPart(val path: Path, val color: Color = Color.Unspecified,
    val brush: Brush? = null, val stroke: Float = 0f, val alpha: Float = 1f, val tail: Boolean = false)
private fun path(value: String): Path = PathParser().parsePathString(value).toPath()
private val silver = Brush.verticalGradient(listOf(Color(0xFF56656C), Color(0xFF91A6AB), Color(0xFFE4E9E4), Color(0xFFB5C7C7), Color(0xFF728F95)), 38f, 128f)
private val fin = Brush.verticalGradient(listOf(Color(0xFF526D77), Color(0xFFA5BABD)), 45f, 122f)
private val fishParts = listOf(
FishPart(path("M137 81C103 65 81 37 49 20L76 78L43 148C84 126 110 104 138 97L161 89Z"), brush = fin, alpha = 1.0f, tail = true),
FishPart(path("M55 28L91 84L49 142M91 84L139 89"), color = Color(0xFFD6E3DF), stroke = 2f, alpha = 0.45f, tail = true),
FishPart(path("M238 48L276 11L298 49M346 48L377 31L390 53M340 119L368 144L380 116"), brush = fin, alpha = 1.0f, tail = false),
FishPart(path("M132 81C193 65 230 43 326 43C427 42 495 54 557 72L603 89L566 101C497 124 405 130 315 124C238 119 182 101 133 97L111 89Z"), brush = silver, alpha = 1.0f, tail = false),
FishPart(path("M132 81C193 65 230 43 326 43C427 42 495 54 557 72L603 89L566 101C497 124 405 130 315 124C238 119 182 101 133 97L111 89Z"), color = Color(0xFF5E7880), stroke = 1.5f, alpha = 1.0f, tail = false),
FishPart(path("M159 81C229 67 277 52 335 53C427 51 500 62 555 77"), color = Color(0xFFD7E6E2), stroke = 2f, alpha = 0.5f, tail = false),
FishPart(path("M544 70C529 77 526 98 538 108M550 76C542 85 541 95 548 102"), color = Color(0xFF5D7881), stroke = 2f, alpha = 1.0f, tail = false),
FishPart(path("M533 93L465 105L496 82Z"), color = Color(0xFF5D7881), alpha = 0.8f, tail = false),
FishPart(path("M533 78C491 71 461 70 430 70C411 69 405 72 391 75C378 79 368 78 357 88C344 102 329 107 305 107C251 104 207 94 155 90"), color = Color(0xFF405E6B), stroke = 2.5f, alpha = 1.0f, tail = false),
FishPart(path("M453 51L462 41L472 55M427 48L435 39L444 50M404 47L412 38L421 49M438 122L447 132L456 119M411 126L419 136L429 124M385 126L392 135L401 125"), color = Color(0xFF647F89), alpha = 1.0f, tail = false),
FishPart(path("M572 93L600 89"), color = Color(0xFF526D77), stroke = 2f, alpha = 1.0f, tail = false),
)
private fun DrawScope.drawKingMackerel(alpha: Float, seconds: Float) {
    fishParts.forEach { part ->
        fun DrawScope.paint() {
            val style = if (part.stroke > 0) Stroke(part.stroke, cap = StrokeCap.Round) else Fill
            if (part.brush != null) drawPath(part.path, part.brush, alpha = alpha * part.alpha, style = style)
            else drawPath(part.path, part.color, alpha = alpha * part.alpha, style = style)
        }
        if (part.tail) withTransform({ scale(.91f + sin(seconds * 3.7f) * .09f, 1f, Offset(138f, 88f)) }) { paint() }
        else paint()
    }
    drawCircle(Color(0xFF243E4B), 5f, Offset(560f, 79f), alpha = alpha)
    drawCircle(Color(0xFFF6F5E9), 1.8f, Offset(561f, 78f), alpha = alpha)
}
