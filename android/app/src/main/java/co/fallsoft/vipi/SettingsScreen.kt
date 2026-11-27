package co.fallsoft.vipi

import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowForward
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp

@Composable
internal fun SettingsView(model: VipiModel) {
    val context = LocalContext.current
    val uri = androidx.compose.ui.platform.LocalUriHandler.current
    var linkError by remember { mutableStateOf<String?>(null) }
    val chat = model.chat
    val profile = chat?.profile
    val secondary = MaterialTheme.colorScheme.onSurfaceVariant
    val appearanceTitle =
        when (model.appearance) {
            Appearance.SYSTEM -> R.string.appearance_system
            Appearance.LIGHT -> R.string.appearance_light
            Appearance.DARK -> R.string.appearance_dark
        }
    var appearancePicker by rememberSaveable { mutableStateOf(false) }
    if (profile != null) {
        Column {
            Row(
                Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                ContactAvatar(profile.displayName, profile.id, diameter = 52.dp)
                Column(Modifier.weight(1f)) {
                    Text(profile.displayName, style = MaterialTheme.typography.titleLarge)
                    Text(
                        "@" + profile.username,
                        style = MaterialTheme.typography.bodyMedium,
                        color = secondary,
                    )
                }
                ScreenSpot(R.drawable.vipi_spot_settings)
            }
            ProfileAvatarEditor(chat, profile.id)
            InviteFriendButton(model, settings = true)
        }
    }
    SettingsGroup(stringResource(R.string.ui_339484dc1f78)) {
        LanguageSettingsLink(languageName(model.targetLanguage)) {
            model.navigate(Screen.LANGUAGE_DOWNLOAD)
        }
        SettingsAction(
            stringResource(R.string.mambo_reentry),
            Modifier.testTag("settings-mambo-guide"),
        ) {
            model.openGuide()
        }
        SettingsAction(stringResource(R.string.nav_help), Modifier.testTag("settings-help")) {
            model.navigate(Screen.HELP)
        }
        if (profile != null)
            SettingsAction(stringResource(R.string.ui_24f13e3dc8e4)) {
                model.navigate(Screen.BACKUP)
            }
    }
    SettingsGroup(stringResource(R.string.ui_3907fa7f8072)) {
        SettingsAction(
            stringResource(R.string.settings_theme),
            value = stringResource(appearanceTitle),
        ) {
            appearancePicker = true
        }
        SettingsSwitch(
            stringResource(R.string.animate_conversation_background),
            model.animateConversationBackground,
            "settings-conversation-motion",
            model::changeConversationAnimation,
        )
    }
    if (appearancePicker)
        AlertDialog(
            onDismissRequest = { appearancePicker = false },
            title = { Text(stringResource(R.string.settings_theme)) },
            text = {
                Column {
                    Appearance.entries.forEach { choice ->
                        val label =
                            when (choice) {
                                Appearance.SYSTEM -> R.string.appearance_system
                                Appearance.LIGHT -> R.string.appearance_light
                                Appearance.DARK -> R.string.appearance_dark
                            }
                        Row(
                            Modifier.fillMaxWidth()
                                .clickable(role = Role.RadioButton) {
                                    model.changeAppearance(choice)
                                    appearancePicker = false
                                }
                                .semantics { selected = model.appearance == choice }
                                .heightIn(min = 52.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            RadioButton(model.appearance == choice, onClick = null)
                            Spacer(Modifier.width(12.dp))
                            Text(stringResource(label))
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { appearancePicker = false }) {
                    Text(stringResource(android.R.string.cancel))
                }
            },
        )
    if (chat?.ready == true)
        SettingsGroup(stringResource(R.string.settings_notifications)) {
            NotificationSetup()
            var previewError by remember(chat) { mutableStateOf(false) }
            SettingsSwitch(
                stringResource(R.string.settings_message_previews),
                chat.notificationPreviews,
                "settings-message-previews",
            ) { enabled ->
                previewError = runCatching { chat.changeNotificationPreviews(enabled) }.isFailure
            }
            if (previewError)
                Text(
                    stringResource(R.string.settings_save_failed),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                )
            Column(
                Modifier.fillMaxWidth()
                    .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(12.dp))
                    .semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite }
                    .padding(14.dp)
            ) {
                Text(
                    stringResource(R.string.settings_example),
                    style = MaterialTheme.typography.labelMedium,
                    color = secondary,
                )
                Text(
                    if (chat.notificationPreviews) stringResource(R.string.settings_sample_sender)
                    else stringResource(R.string.ui_0882ca640d5a),
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(
                    stringResource(
                        if (chat.notificationPreviews) R.string.settings_sample_message
                        else R.string.ui_3abeae7a3bed
                    ),
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
            Text(
                stringResource(R.string.settings_preview_lockscreen),
                style = MaterialTheme.typography.bodySmall,
                color = secondary,
            )
        }
    chat?.streakVault?.let { vault ->
        SettingsGroup(stringResource(R.string.message_auto_links)) {
            var auto by remember(vault) { mutableStateOf(vault.autoLinks()) }
            SettingsSwitch(
                stringResource(R.string.message_auto_links),
                auto,
                "settings-auto-links",
            ) { value ->
                vault.transaction {
                    vault.put("local", "auto-link-preview", byteArrayOf(if (value) 1 else 0))
                }
                auto = value
            }
            Text(
                stringResource(R.string.message_link_consent),
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
    SettingsGroup(stringResource(R.string.settings_about)) {
        listOf(R.string.nav_privacy to "privacy", R.string.nav_terms to "terms").forEach {
            (title, path) ->
            if (title == R.string.nav_privacy) SettingsPrivacyPromise()
            SettingsAction(stringResource(title)) {
                runCatching { uri.openUri("https://mambovipi.app/$path.html") }
                    .onFailure { linkError = context.getString(R.string.settings_page_open_failed) }
            }
        }
        linkError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        SettingsAction(stringResource(R.string.ui_2a6b4d12ccfb)) { model.navigate(Screen.LICENSES) }
        Text(
            stringResource(R.string.ui_380f81884c22),
            style = MaterialTheme.typography.bodySmall,
            color = secondary,
        )
    }
    if (profile != null)
        SettingsGroup(stringResource(R.string.settings_account)) {
            if (model.authentication.canLinkFallsoft) {
                SettingsAction(
                    stringResource(R.string.fallsoft_link_title),
                    Modifier.testTag("fallsoft-link-start"),
                    enabled = !model.authentication.busy && chat.eventDevice() != null,
                ) {
                    model.beginFallsoftLink(context)
                }
                Text(
                    stringResource(R.string.fallsoft_link_detail),
                    style = MaterialTheme.typography.bodySmall,
                    color = secondary,
                )
                model.authentication.error?.let {
                    Text(it, color = MaterialTheme.colorScheme.error)
                }
            }
            SettingsAction(stringResource(R.string.ui_a2e20a335700), destructive = true) {
                model.navigate(Screen.DELETE_ACCOUNT)
            }
        }
}

@Composable
private fun SettingsGroup(title: String, rows: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxWidth()) {
        Text(
            title,
            style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(bottom = 4.dp).semantics { heading() },
        )
        HorizontalDivider()
        rows()
    }
}

@Composable
internal fun SettingsAction(
    title: String,
    modifier: Modifier = Modifier,
    value: String? = null,
    enabled: Boolean = true,
    destructive: Boolean = false,
    action: () -> Unit,
) {
    val color =
        if (destructive) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface
    Row(
        modifier
            .fillMaxWidth()
            .clickable(enabled = enabled, role = Role.Button, onClick = action)
            .heightIn(min = 52.dp)
            .padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (value != null && androidx.compose.ui.platform.LocalDensity.current.fontScale >= 1.3f) {
            Column(Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.bodyLarge, color = color)
                Text(
                    value,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        } else {
            Text(
                title,
                Modifier.weight(1f),
                style = MaterialTheme.typography.bodyLarge,
                color = color.copy(alpha = if (enabled) 1f else .55f),
            )
            value?.let {
                Text(
                    it,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        Icon(
            Icons.AutoMirrored.Outlined.ArrowForward,
            contentDescription = null,
            modifier = Modifier.size(16.dp),
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun SettingsSwitch(
    title: String,
    checked: Boolean,
    tag: String,
    change: (Boolean) -> Unit,
) {
    Row(
        Modifier.fillMaxWidth()
            .testTag(tag)
            .toggleable(checked, role = Role.Switch, onValueChange = change)
            .heightIn(min = 52.dp)
            .padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(title, Modifier.weight(1f), style = MaterialTheme.typography.bodyLarge)
        Switch(checked, onCheckedChange = null)
    }
}

@Composable
internal fun LanguageSettingsLink(language: String, onClick: () -> Unit) =
    SettingsAction(stringResource(R.string.ui_e7cde359a05e), value = language, action = onClick)

@Composable
internal fun InviteFriendButton(model: VipiModel, settings: Boolean = false) {
    val username = model.chat?.profile?.username ?: return
    val context = LocalContext.current
    val inviteTitle = stringResource(R.string.nav_invite)
    var error by remember { mutableStateOf(false) }
    val share = {
        val invitation =
            Intent(Intent.ACTION_SEND).apply {
                type = "text/plain"
                putExtra(Intent.EXTRA_TEXT, friendInviteText(context, username))
            }
        try {
            context.startActivity(Intent.createChooser(invitation, inviteTitle))
            error = false
        } catch (_: android.content.ActivityNotFoundException) {
            error = true
        }
    }
    if (settings) SettingsAction(inviteTitle, action = share)
    else {
        TextButton(onClick = share) { Text(inviteTitle) }
    }
    if (error)
        Text(stringResource(R.string.ui_e5bd91ac481d), style = MaterialTheme.typography.bodySmall)
}
