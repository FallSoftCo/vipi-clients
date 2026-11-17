package co.fallsoft.vipi

import androidx.compose.foundation.rememberScrollState
import androidx.compose.ui.res.stringResource
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import kotlinx.coroutines.launch

@Composable internal fun DeviceRecoveryCard(chat: ChatSession, signIn: () -> Unit) {
    val scope = rememberCoroutineScope()
    var confirm by remember { mutableStateOf(false) }
    Text(stringResource(R.string.ui_fa3d530cf72d), style = MaterialTheme.typography.titleLarge)
    Text(chat.notice ?: "Your account is active on another device. Saved conversations are still available here.")
    if (chat.busy) CircularProgressIndicator()
    else if (chat.recoveryNeedsSignIn) Button(onClick = signIn) { Text(stringResource(R.string.ui_51fbe1dc8a73)) }
    else Button(onClick = { confirm = true }) { Text(stringResource(R.string.ui_e48800c742a6)) }
    if (confirm) AlertDialog(onDismissRequest = { confirm = false },
        title = { Text(stringResource(R.string.ui_db2b1ef64bbf)) },
        text = { Text(stringResource(R.string.ui_2b338821b42c),
            modifier = Modifier.verticalScroll(rememberScrollState())) },
        confirmButton = { TextButton(onClick = { confirm = false; scope.launch { chat.confirmDeviceReplacement() } }) { Text(stringResource(R.string.ui_e48800c742a6)) } },
        dismissButton = { TextButton(onClick = { confirm = false }) { Text(stringResource(R.string.cancel_action)) } })
}
