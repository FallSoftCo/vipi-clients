package co.fallsoft.vipi

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowRight
import androidx.compose.material.icons.outlined.Edit
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp

@Composable
internal fun NewChatFab(onClick: () -> Unit) {
    ExtendedFloatingActionButton(
        onClick = onClick,
        modifier = Modifier.testTag("inbox-compose"),
        containerColor = MaterialTheme.colorScheme.primary,
        contentColor = MaterialTheme.colorScheme.onPrimary,
    ) {
        Icon(Icons.Outlined.Edit, contentDescription = null)
        Spacer(Modifier.width(10.dp))
        Text(stringResource(R.string.compose_new_action))
    }
}

@Composable
internal fun NewGroupAction(onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        shape = MaterialTheme.shapes.medium,
        color = MaterialTheme.colorScheme.surfaceContainerLow,
        modifier =
            Modifier.fillMaxWidth().testTag("new-group-action").semantics { role = Role.Button },
    ) {
        Row(
            Modifier.heightIn(min = 70.dp).padding(horizontal = 16.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Image(
                painterResource(R.drawable.vipi_spot_new_group),
                contentDescription = null,
                modifier = Modifier.size(80.dp, 48.dp),
            )
            Text(
                stringResource(R.string.new_group_action),
                Modifier.weight(1f),
                style = MaterialTheme.typography.titleMedium,
            )
            Icon(
                Icons.AutoMirrored.Outlined.KeyboardArrowRight,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
