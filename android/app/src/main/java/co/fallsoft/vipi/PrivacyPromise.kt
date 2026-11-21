package co.fallsoft.vipi

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp

@Composable internal fun PrivacyPromise() {
    val art = if (MaterialTheme.colorScheme.surface.luminance() < .5f)
        R.drawable.vipi_privacy_promise_dark else R.drawable.vipi_privacy_promise_light
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
        Image(painterResource(art), contentDescription = "Certified Zucker Free",
            modifier = Modifier.width(114.dp).aspectRatio(792f / 304f))
        Text(stringResource(R.string.privacy_promise_fallsoft), Modifier.weight(1f),
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
