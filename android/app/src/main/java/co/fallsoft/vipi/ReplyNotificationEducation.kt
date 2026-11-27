package co.fallsoft.vipi

import android.Manifest
import android.content.Context
import android.content.Intent
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp

/**
 * Device-local education, claimed only after a new user Send commits locally. This uses the model's
 * Application, including its isolated QA preference owner.
 */
internal class ReplyNotificationEducation(val context: Context) {
    private val preferences = context.getSharedPreferences("preferences", Context.MODE_PRIVATE)
    var friend by mutableStateOf<String?>(null)
        private set

    var settingsUnavailable by mutableStateOf(false)
        private set

    fun failedSettings() {
        settingsUnavailable = true
    }

    val shownOrHandled: Boolean
        get() = preferences.getBoolean("replyNotificationEducationHandled", false)

    var permissionAsked: Boolean
        get() = preferences.getBoolean("notificationAsked", false)
        private set(value) {
            check(preferences.edit().putBoolean("notificationAsked", value).commit())
        }

    fun committedUserSend(name: String) {
        if (shownOrHandled) return
        // Claim before presentation so relaunch/retry/import can never redisplay it.
        if (!preferences.edit().putBoolean("replyNotificationEducationHandled", true).commit())
            return
        if (!PushDelivery.allowed(context)) friend = name
    }

    fun dismiss() {
        friend = null
        settingsUnavailable = false
    }

    fun markPermissionAsked() {
        permissionAsked = true
    }
}

@Composable
internal fun ReplyNotificationCard(
    education: ReplyNotificationEducation,
    showSenderAndMessage: Boolean,
    permissionChanged: () -> Unit,
) {
    val permission =
        rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
            permissionChanged()
        }
    val friend = education.friend
    if (friend == null) {
        if (education.settingsUnavailable)
            Text(
                stringResource(R.string.ui_d75c6cdd950a),
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.error,
            )
        return
    }
    Surface(
        color = MaterialTheme.colorScheme.surfaceContainer,
        shape = MaterialTheme.shapes.medium,
        modifier =
            Modifier.fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 6.dp)
                .testTag("reply-notification-card"),
    ) {
        Column(Modifier.padding(horizontal = 14.dp, vertical = 8.dp)) {
            val prompt =
                if (showSenderAndMessage) R.string.notification_reply_prompt
                else R.string.notification_reply_prompt_private
            Text(stringResource(prompt, friend), style = MaterialTheme.typography.bodyLarge)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                TextButton(
                    onClick = { education.dismiss() },
                    modifier = Modifier.heightIn(min = 48.dp).testTag("reply-notification-later"),
                ) {
                    Text(stringResource(R.string.notification_reply_later))
                }
                TextButton(
                    onClick = {
                        education.dismiss()
                        if (PushDelivery.allowed(education.context)) {
                            permissionChanged()
                            return@TextButton
                        }
                        if (
                            Build.VERSION.SDK_INT >= 33 &&
                                !PushDelivery.permissionGranted(education.context) &&
                                !education.permissionAsked
                        ) {
                            education.markPermissionAsked()
                            permission.launch(Manifest.permission.POST_NOTIFICATIONS)
                        } else
                            runCatching {
                                education.context.startActivity(
                                    Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                                        .putExtra(
                                            Settings.EXTRA_APP_PACKAGE,
                                            education.context.packageName,
                                        )
                                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                                )
                            }
                                .onFailure { education.failedSettings() }
                    },
                    modifier = Modifier.heightIn(min = 48.dp).testTag("reply-notification-allow"),
                ) {
                    Text(stringResource(R.string.notification_reply_allow))
                }
            }
            if (education.settingsUnavailable)
                Text(
                    stringResource(R.string.ui_d75c6cdd950a),
                    color = MaterialTheme.colorScheme.error,
                )
        }
    }
}
