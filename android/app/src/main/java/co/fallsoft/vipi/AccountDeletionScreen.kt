package co.fallsoft.vipi

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch

@Composable internal fun DeleteAccountScreen(onDelete: () -> Unit) {
    var confirm by rememberSaveable { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    Text("Delete account", fontFamily = FontFamily.Serif, fontSize = 32.sp, modifier = Modifier.semantics { heading() })
    Text("Your profile and messages waiting for delivery will be removed from Vipi. Saved chats on this device will also be erased.")
    Text("This won’t erase friends’ copies or backups you saved elsewhere.")
    Text("Deleting your account won’t cancel a Google Play subscription. You can cancel it separately to stop future renewals.")
    SubscriptionManagement()
    Button(onClick = { confirm = true }, colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error)) { Text("Delete account") }
    error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
    if (confirm) AlertDialog(onDismissRequest = { confirm = false }, title = { Text("Delete your Vipi account?") },
        text = { Text("Your account and chats on this device will be permanently deleted. This can’t be undone.") },
        dismissButton = { TextButton(onClick = { confirm = false }) { Text("Cancel") } },
        confirmButton = { TextButton(modifier = Modifier.testTag("delete-confirm"), onClick = {
            confirm = false
            try { onDelete() }
            catch (_: Exception) { error = "Deletion couldn’t be prepared. Close and reopen Vipi to try again." }
        }) { Text("Delete account", color = MaterialTheme.colorScheme.error) } })
}

@Composable internal fun AccountDeletionProgress(deletion: AccountDeletion, authentication: Authentication, onFinished: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val record = deletion.pending
    val finished = record?.phase == DeletionRecord.Phase.COMPLETED && record.localErased
    val accepted = record != null && record.phase != DeletionRecord.Phase.PREPARED
    Scaffold(containerColor = MaterialTheme.colorScheme.background) { insets ->
        Column(Modifier.fillMaxSize().padding(insets).verticalScroll(rememberScrollState()).widthIn(max = 560.dp).padding(28.dp),
            verticalArrangement = Arrangement.spacedBy(24.dp)) {
            Text(if (finished) "Account deleted" else if (accepted) "Deletion requested" else "Delete your account",
                fontFamily = FontFamily.Serif, fontSize = 32.sp, modifier = Modifier.semantics { heading() })
            Text(if (finished) "Your Vipi account and chats on this device have been removed."
                else if (accepted) "Vipi has accepted your request. We’re finishing deletion. You can close the app and check back later."
                else "We’ll confirm the request and remove your saved chats from this device. Vipi saves your progress if the connection drops.")
            deletion.notice?.let { Text(it) }
            if (deletion.needsSignIn) authentication.error?.let { Text(it) }
            if (deletion.busy) { CircularProgressIndicator(); Text("Checking deletion…") }
            else if (finished) Button(onClick = { deletion.finish(); if (!deletion.active) onFinished() }) { Text("Done") }
            else if (!deletion.loadFailed) {
                if (deletion.needsSignIn && record != null) Button(onClick = { authentication.signIn(context, expectedUser = record.userID) }, enabled = !authentication.busy) { Text("Sign in to confirm") }
                OutlinedButton(onClick = { scope.launch { deletion.resume() } }) { Text(if (accepted) "Check status" else "Continue deletion") }
            }
            Text("Subscriptions are managed separately. Friends’ copies and backups saved elsewhere remain.", style = MaterialTheme.typography.bodySmall)
            SubscriptionManagement()
        }
    }
}
@Composable private fun SubscriptionManagement() {
    val uri = LocalUriHandler.current
    var unavailable by remember { mutableStateOf(false) }
    TextButton(onClick = { try { uri.openUri("https://play.google.com/store/account/subscriptions") } catch (_: Exception) { unavailable = true } }) { Text("Manage subscriptions") }
    if (unavailable) Text("Open Google Play → Payments & subscriptions → Subscriptions.", style = MaterialTheme.typography.bodySmall)
}
