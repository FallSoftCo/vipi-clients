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
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp

@Composable
internal fun PrivacyPromise() {
    val art =
        if (MaterialTheme.colorScheme.surface.luminance() < .5f)
            R.drawable.vipi_privacy_promise_dark
        else R.drawable.vipi_privacy_promise_light
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Image(
            painterResource(art),
            contentDescription = "Certified Zucker Free",
            modifier = Modifier.width(114.dp).aspectRatio(792f / 304f),
        )
        Text(
            stringResource(R.string.privacy_promise_fallsoft),
            Modifier.weight(1f),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
internal fun SettingsPrivacyPromise() {
    val sticker =
        if (MaterialTheme.colorScheme.surface.luminance() < .5f)
            R.drawable.vipi_privacy_sticker_dark
        else R.drawable.vipi_privacy_sticker_light
    Column(
        modifier =
            Modifier.fillMaxWidth().padding(vertical = 12.dp).semantics(mergeDescendants = true) {},
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Image(
            painterResource(sticker),
            contentDescription = "Certified Zucker Free",
            modifier = Modifier.widthIn(max = 224.dp).fillMaxWidth().aspectRatio(1280f / 896f),
        )
        Spacer(Modifier.height(8.dp))
        Text(
            stringResource(R.string.privacy_promise_fallsoft),
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(4.dp))
        Text(
            stringResource(R.string.privacy_claim_chat_sale),
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurface,
            textAlign = TextAlign.Center,
        )
    }
}
