package co.fallsoft.vipi

import androidx.annotation.DrawableRes
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp

/** Decorative artwork gives way to the form when space is needed for typing or larger text. */
@Composable internal fun ScreenSpot(@DrawableRes art: Int, editing: Boolean = false) {
    val configuration = LocalConfiguration.current
    val density = LocalDensity.current
    if (editing || density.fontScale >= 1.5f || configuration.screenWidthDp < 360 ||
        configuration.screenHeightDp < 480 || WindowInsets.ime.getBottom(density) > 0) return
    Image(painterResource(art), contentDescription = null, modifier = Modifier.size(80.dp, 48.dp).testTag("screen-spot"))
}
