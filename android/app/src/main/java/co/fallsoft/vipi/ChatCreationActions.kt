package co.fallsoft.vipi

import androidx.annotation.DrawableRes
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowRight
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.dp

@Composable internal fun ChatCreationActions(model: VipiModel) {
    Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp)) {
        val chat = stringResource(R.string.nav_new_chat)
        val group = stringResource(R.string.new_group_action)
        val style = MaterialTheme.typography.titleMedium
        val density = LocalDensity.current
        val measurer = rememberTextMeasurer()
        val longestLabel = with(density) {
            maxOf(measurer.measure(chat, style, softWrap = false).size.width,
                measurer.measure(group, style, softWrap = false).size.width).toDp()
        }
        BoxWithConstraints(Modifier.fillMaxWidth()) {
            // Each compact action needs its illustration, side insets, gap and the complete local label.
            val fitsPair = density.fontScale < 1.4f && (maxWidth - 8.dp) / 2 >= 80.dp + longestLabel
            if (fitsPair) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    IllustratedChatAction(chat, R.drawable.vipi_spot_new_chat, "inbox-compose", Modifier.weight(1f),
                        compact = true) { model.navigate(Screen.NEW_CHAT) }
                    IllustratedChatAction(group, R.drawable.vipi_spot_new_group, "new-group-action", Modifier.weight(1f),
                        compact = true) { model.openGroups(create = true) }
                }
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    IllustratedChatAction(chat, R.drawable.vipi_spot_new_chat, "inbox-compose") { model.navigate(Screen.NEW_CHAT) }
                    NewGroupAction { model.openGroups(create = true) }
                }
            }
        }
        TextButton(onClick = { model.openGroups(create = false) }, modifier = Modifier.testTag("open-groups")) {
            Text(stringResource(R.string.groups_and_invitations))
        }
    }
}

@Composable internal fun NewGroupAction(onClick: () -> Unit) {
    IllustratedChatAction(stringResource(R.string.new_group_action), R.drawable.vipi_spot_new_group,
        "new-group-action", onClick = onClick)
}

@Composable private fun IllustratedChatAction(label: String, @DrawableRes art: Int, tag: String, modifier: Modifier = Modifier,
    compact: Boolean = false, onClick: () -> Unit) {
    Surface(onClick = onClick, shape = MaterialTheme.shapes.medium,
        color = MaterialTheme.colorScheme.surfaceContainerLow,
        modifier = modifier.fillMaxWidth().testTag(tag).semantics { role = Role.Button }) {
        Row(Modifier.heightIn(min = if (compact) 56.dp else 70.dp).padding(horizontal = if (compact) 10.dp else 16.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(if (compact) 6.dp else 12.dp)) {
            Image(painterResource(art), contentDescription = null, modifier = if (compact) Modifier.size(54.dp, 36.dp) else Modifier.size(80.dp, 48.dp))
            Text(label, Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
            if (!compact) Icon(Icons.AutoMirrored.Outlined.KeyboardArrowRight, contentDescription = null,
                tint = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
