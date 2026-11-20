package co.fallsoft.vipi

import android.app.UiModeManager
import android.os.Build
import androidx.annotation.RequiresApi
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.runtime.*
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext

/** Semantic roles shared by Compose and native paragraphs. Concrete values are
 * supplied by VipiTheme, so message states never depend on a screen's own hex. */
internal data class VipiPalette(
    val canvas: Color, val surface: Color, val incoming: Color, val outgoing: Color,
    val ink: Color, val secondary: Color, val action: Color, val onAction: Color,
    val read: Color, val failed: Color, val focus: Color, val outline: Color,
    val separator: Color, val practiceFill: Color, val practiceInk: Color,
    val spokenFill: Color, val spokenInk: Color, val subdued: Color,
    val avatars: List<Color>, val avatarInk: Color,
    val outgoingInk: Color = ink, val outgoingSecondary: Color = secondary,
    val outgoingRead: Color = read, val outgoingFailed: Color = failed,
    val outgoingFocus: Color = focus
)

internal val LocalVipiPalette = staticCompositionLocalOf<VipiPalette?> { null }

/** Keeps reusable paragraph components compatible with a plain MaterialTheme;
 * the application always provides the complete, reviewed brand palette. */
@Composable internal fun vipiPalette(): VipiPalette {
    LocalVipiPalette.current?.let { return it }
    val c = MaterialTheme.colorScheme
    return remember(c) {
        VipiPalette(c.background, c.surface, c.surface, c.primaryContainer,
            c.onSurface, c.onSurfaceVariant, c.primary, c.onPrimary,
            c.tertiary, c.error, c.primary, c.outline, c.outlineVariant,
            c.secondaryContainer, c.onSecondaryContainer, c.primary, c.onPrimary,
            c.surfaceVariant, listOf(c.primaryContainer, c.secondaryContainer, c.tertiaryContainer, c.surfaceVariant), c.onSurface)
    }
}

@Composable internal fun vipiTextFieldColors() = vipiPalette().let { p ->
    OutlinedTextFieldDefaults.colors(
        focusedTextColor = p.ink, unfocusedTextColor = p.ink,
        focusedContainerColor = p.surface, unfocusedContainerColor = p.surface,
        focusedBorderColor = p.focus, unfocusedBorderColor = p.outline,
        focusedLabelColor = p.focus, unfocusedLabelColor = p.secondary,
        focusedPlaceholderColor = p.secondary, unfocusedPlaceholderColor = p.secondary,
        cursorColor = p.focus, errorCursorColor = p.failed,
        errorTextColor = p.ink, errorContainerColor = p.surface,
        errorBorderColor = p.failed, errorLabelColor = p.failed
    )
}

/** Public contrast preference arrived in API34; older supported Android versions
 * retain the already contrast-checked standard palette without hidden settings. */
@Composable internal fun prefersIncreasedContrast(): Boolean =
    if (Build.VERSION.SDK_INT >= 34) increasedContrastApi34() else false

@RequiresApi(34)
@Composable private fun increasedContrastApi34(): Boolean {
    val context = LocalContext.current.applicationContext
    val manager = remember(context) { context.getSystemService(UiModeManager::class.java) }
    var contrast by remember(manager) { mutableFloatStateOf(manager.contrast) }
    DisposableEffect(manager, context) {
        val listener = UiModeManager.ContrastChangeListener { contrast = it }
        manager.addContrastChangeListener(context.mainExecutor, listener)
        onDispose { manager.removeContrastChangeListener(listener) }
    }
    return contrast > 0f
}

/** Use checked opaque roles for every Material surface and state. Elevation
 * remains physical; tonal overlays do not alter the measured text backgrounds. */
internal fun VipiPalette.materialColors(dark: Boolean): ColorScheme =
    (if (dark) darkColorScheme() else lightColorScheme()).copy(
        primary = action, onPrimary = onAction,
        primaryContainer = outgoing, onPrimaryContainer = outgoingInk,
        secondary = focus, onSecondary = canvas,
        secondaryContainer = practiceFill, onSecondaryContainer = practiceInk,
        tertiary = read, onTertiary = canvas,
        tertiaryContainer = subdued, onTertiaryContainer = ink,
        background = canvas, onBackground = ink,
        surface = surface, onSurface = ink,
        surfaceVariant = subdued, onSurfaceVariant = secondary,
        surfaceTint = Color.Transparent,
        inverseSurface = ink, inverseOnSurface = canvas, inversePrimary = canvas,
        error = failed, onError = canvas, errorContainer = surface, onErrorContainer = failed,
        outline = outline, outlineVariant = separator, scrim = Color.Black,
        surfaceBright = incoming, surfaceDim = canvas,
        surfaceContainerLowest = canvas, surfaceContainerLow = surface,
        surfaceContainer = surface, surfaceContainerHigh = incoming,
        surfaceContainerHighest = subdued
    )

internal fun VipiPalette.onOutgoing() = copy(
    ink = outgoingInk, secondary = outgoingSecondary, read = outgoingRead,
    failed = outgoingFailed, focus = outgoingFocus, action = outgoingFocus,
    onAction = spokenInk
)
