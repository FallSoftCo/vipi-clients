package co.fallsoft.vipi

import androidx.compose.foundation.Image
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowForward
import androidx.compose.material.icons.outlined.ArrowUpward
import androidx.compose.material.icons.outlined.Mic
import androidx.compose.material.icons.outlined.DeleteOutline
import androidx.compose.material.icons.outlined.StopCircle
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.KeyboardArrowDown
import androidx.compose.material.icons.outlined.KeyboardArrowUp
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.collapse
import androidx.compose.ui.semantics.expand
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp

private enum class HelpTopic(val title: Int, val picture: Int?, val first: Int, val second: Int) {
    FRIENDS(R.string.help_friends_title, R.drawable.vipi_help_friends, R.string.help_friends_step1, R.string.help_friends_step2),
    GROUPS(R.string.help_groups_title, R.drawable.vipi_help_groups, R.string.help_groups_step1, R.string.help_groups_step2),
    LANGUAGES(R.string.help_languages_title, R.drawable.vipi_help_languages, R.string.help_languages_step1, R.string.help_languages_step2),
    READING(R.string.help_reading_title, R.drawable.vipi_help_reading, R.string.help_reading_step1, R.string.help_reading_step2),
    VOICE(R.string.help_voice_title, null, R.string.help_voice_step1, R.string.help_voice_step2),
    STATUS(R.string.help_status_title, null, R.string.help_status_step1, R.string.help_status_step2),
    NOTIFICATIONS(R.string.help_notifications_title, R.drawable.vipi_help_notifications, R.string.help_notifications_step1, R.string.help_notifications_step2),
    SAFETY(R.string.help_safety_title, R.drawable.vipi_help_safety, R.string.help_safety_step1, R.string.help_safety_step2),
    BACKUP(R.string.help_backup_title, R.drawable.vipi_help_backup, R.string.help_backup_step1, R.string.help_backup_step2),
    ACCOUNT(R.string.help_account_title, R.drawable.vipi_help_account, R.string.help_account_step1, R.string.help_account_step2)
}

@Composable internal fun NativeHelpContent(openTutorial: () -> Unit) {
    val uri = androidx.compose.ui.platform.LocalUriHandler.current
    var emailFailed by rememberSaveable { mutableStateOf(false) }
    var expanded by rememberSaveable { mutableStateOf<HelpTopic?>(null) }
    Card(
        onClick = openTutorial, modifier = Modifier.fillMaxWidth().testTag("tutorial-reentry"),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
    ) {
        Row(Modifier.padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(stringResource(R.string.tutorial_reentry), style = MaterialTheme.typography.titleLarge)
                Text(stringResource(R.string.help_guide_intro), style = MaterialTheme.typography.bodyMedium)
            }
            Spacer(Modifier.width(12.dp))
            Icon(Icons.AutoMirrored.Outlined.ArrowForward, null)
        }
    }
    Column(Modifier.fillMaxWidth()) {
        Text(stringResource(R.string.help_guides), Modifier.padding(bottom = 8.dp).semantics { heading() },
            style = MaterialTheme.typography.titleMedium)
        for (topic in HelpTopic.entries) {
            val open = expanded == topic
            Row(Modifier.fillMaxWidth().testTag("help-topic-${topic.name}")
                .semantics {
                    if (open) collapse { expanded = null; true }
                    else expand { expanded = topic; true }
                }
                .clickable(role = Role.Button) { expanded = if (open) null else topic }
                .heightIn(min = 56.dp).padding(vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(topic.title), Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
                Icon(if (open) Icons.Outlined.KeyboardArrowUp else Icons.Outlined.KeyboardArrowDown, null)
            }
            if (open) {
                Column(Modifier.fillMaxWidth().testTag("help-detail-${topic.name}").padding(bottom = 20.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    if (topic == HelpTopic.VOICE) {
                        for ((icon, label) in listOf(Icons.Outlined.Mic to R.string.help_voice_hold,
                            Icons.AutoMirrored.Outlined.ArrowBack to R.string.help_voice_cancel,
                            Icons.Outlined.ArrowUpward to R.string.help_voice_lock)) {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                Icon(icon, null)
                                Text(stringResource(label), style = MaterialTheme.typography.labelLarge)
                            }
                        }
                    } else if (topic.picture == null) {
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            for ((state, label) in listOf("accepted" to R.string.delivery_sent,
                                "delivered" to R.string.delivery_delivered, "read" to R.string.delivery_read)) {
                                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                    ChatDeliveryIcon(state, null)
                                    Text(stringResource(label), style = MaterialTheme.typography.labelLarge)
                                }
                            }
                        }
                    } else {
                        val picture = painterResource(topic.picture)
                        Image(picture, null, Modifier.fillMaxWidth().aspectRatio(picture.intrinsicSize.width / picture.intrinsicSize.height)
                            .clip(RoundedCornerShape(12.dp)))
                    }
                    Text(stringResource(topic.first), style = MaterialTheme.typography.bodyLarge)
                    if (topic == HelpTopic.VOICE) {
                        Row(horizontalArrangement = Arrangement.spacedBy(26.dp)) {
                            Icon(Icons.Outlined.DeleteOutline, null)
                            Icon(Icons.Outlined.StopCircle, null)
                            Icon(Icons.Outlined.ArrowUpward, null, tint = MaterialTheme.colorScheme.primary)
                        }
                    }
                    Text(stringResource(topic.second), style = MaterialTheme.typography.bodyLarge)
                }
            }
            HorizontalDivider()
        }
    }
    TextButton(onClick = { emailFailed = runCatching { uri.openUri("mailto:one@fallsoft.co") }.isFailure }) {
        Text(stringResource(R.string.help_email))
    }
    if (emailFailed) {
        androidx.compose.foundation.text.selection.SelectionContainer { Text("one@fallsoft.co") }
    }

}
