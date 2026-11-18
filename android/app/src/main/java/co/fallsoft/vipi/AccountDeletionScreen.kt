package co.fallsoft.vipi

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch

@Composable internal fun DeleteAccountScreen(onDelete: () -> Unit) {
    val context = LocalContext.current
    var confirm by rememberSaveable { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    Text(stringResource(R.string.ui_a2e20a335700), fontSize = 32.sp, modifier = Modifier.semantics { heading() })
    Text(stringResource(R.string.ui_8def6a81a73d))
    Text(stringResource(R.string.deletion_fallsoft_retained))
    Text(stringResource(R.string.ui_fd5e205fa654))
    Text(stringResource(R.string.ui_c3297f5bde81))
    SubscriptionManagement()
    Button(onClick = { confirm = true }, colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error)) { Text(stringResource(R.string.ui_a2e20a335700)) }
    error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
    if (confirm) AlertDialog(onDismissRequest = { confirm = false }, title = { Text(stringResource(R.string.ui_03fdb0dfc1b8)) },
        text = { Text(stringResource(R.string.ui_c26d4e55137b)) },
        dismissButton = { TextButton(onClick = { confirm = false }) { Text(stringResource(R.string.cancel_action)) } },
        confirmButton = { TextButton(modifier = Modifier.testTag("delete-confirm"), onClick = {
            confirm = false
            try { onDelete() }
            catch (_: Exception) { error = context.getString(R.string.deletion_prepare_failed) }
        }) { Text(stringResource(R.string.ui_a2e20a335700), color = MaterialTheme.colorScheme.error) } })
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
            Text(if (finished) stringResource(R.string.ui_5d670c14e5b1) else if (accepted) stringResource(R.string.ui_33a2ae335a6b) else stringResource(R.string.ui_7ab60595358e),
                fontSize = 32.sp, modifier = Modifier.semantics { heading() })
            Text(if (finished) stringResource(R.string.deletion_completed)
                else if (accepted) stringResource(R.string.deletion_accepted)
                else stringResource(R.string.deletion_pending))
            deletion.notice?.let { Text(stringResource(it)) }
            if (deletion.needsSignIn) authentication.error?.let { Text(it) }
            if (deletion.busy) { CircularProgressIndicator(); Text(stringResource(R.string.ui_6416c5a47450)) }
            else if (finished) Button(onClick = { deletion.finish(); if (!deletion.active) onFinished() }) { Text(stringResource(R.string.ui_11a6767d5674)) }
            else if (!deletion.loadFailed) {
                if (deletion.needsSignIn && record != null) Button(onClick = { authentication.signIn(context, expectedUser = record.userID) }, enabled = !authentication.busy) { Text(stringResource(R.string.ui_9d2dbb5de070)) }
                OutlinedButton(onClick = { scope.launch { deletion.resume() } }) { Text(if (accepted) stringResource(R.string.ui_69cd3590300a) else stringResource(R.string.ui_eb55b8291994)) }
            }
            Text(stringResource(R.string.deletion_fallsoft_retained), style = MaterialTheme.typography.bodySmall)
            Text(stringResource(R.string.ui_0cd8734d2fcd), style = MaterialTheme.typography.bodySmall)
            SubscriptionManagement()
        }
    }
}
@Composable private fun SubscriptionManagement() {
    val uri = LocalUriHandler.current
    var unavailable by remember { mutableStateOf(false) }
    TextButton(onClick = { try { uri.openUri("https://play.google.com/store/account/subscriptions") } catch (_: Exception) { unavailable = true } }) { Text(stringResource(R.string.ui_24a3f4314e5c)) }
    if (unavailable) Text(stringResource(R.string.ui_273afa09966b), style = MaterialTheme.typography.bodySmall)
}
