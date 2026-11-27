package co.fallsoft.vipi

import android.Manifest
import android.content.Intent
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner

@Composable
internal fun NotificationSetup() {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var allowed by remember { mutableStateOf(PushDelivery.allowed(context)) }
    var unavailable by remember { mutableStateOf(false) }
    val prefs = remember { context.getSharedPreferences("preferences", 0) }
    var asked by remember { mutableStateOf(prefs.getBoolean("notificationAsked", false)) }
    DisposableEffect(lifecycle, context) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) allowed = PushDelivery.allowed(context)
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }
    val permission =
        rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
            allowed = PushDelivery.allowed(context)
            if (allowed) PushDelivery.request(context, registration = true)
        }
    SettingsAction(
        stringResource(R.string.settings_delivery),
        value = stringResource(if (allowed) R.string.settings_on else R.string.settings_off),
    ) {
        if (Build.VERSION.SDK_INT >= 33 && !PushDelivery.permissionGranted(context) && !asked) {
            prefs.edit().putBoolean("notificationAsked", true).apply()
            asked = true
            permission.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else
            runCatching {
                context.startActivity(
                    Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                        .putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName)
                )
            }
                .onFailure { unavailable = true }
    }
    if (unavailable)
        Text(stringResource(R.string.ui_d75c6cdd950a), style = MaterialTheme.typography.bodySmall)
}

@Composable
internal fun NotificationPrompt(asked: Boolean, unavailable: Boolean, onClick: () -> Unit) {
    Column {
        Text(stringResource(R.string.ui_71c971aaf02d), style = MaterialTheme.typography.bodySmall)
        TextButton(onClick = onClick) {
            Text(
                if (asked) stringResource(R.string.ui_63568f0582af)
                else stringResource(R.string.ui_682be64ae780)
            )
        }
        if (unavailable)
            Text(
                stringResource(R.string.ui_d75c6cdd950a),
                style = MaterialTheme.typography.bodySmall,
            )
    }
}
