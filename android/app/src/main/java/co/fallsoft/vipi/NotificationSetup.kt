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
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner

@Composable internal fun NotificationSetup() {
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
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        allowed = PushDelivery.allowed(context); PushDelivery.request(context, registration = true)
    }
    if (!allowed) Column {
        Text("Know when friends reply. Notifications hide message text.", style = MaterialTheme.typography.bodySmall)
        TextButton(onClick = {
            if (Build.VERSION.SDK_INT >= 33 && !asked) {
                prefs.edit().putBoolean("notificationAsked", true).apply(); asked = true
                permission.launch(Manifest.permission.POST_NOTIFICATIONS)
            } else runCatching { context.startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName)) }
                .onFailure { unavailable = true }
        }) { Text(if (asked) "Notification settings" else "Enable notifications") }
        if (unavailable) Text("Open Vipi’s notification settings in Android Settings.", style = MaterialTheme.typography.bodySmall)
    }
}
