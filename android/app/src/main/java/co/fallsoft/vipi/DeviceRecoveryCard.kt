package co.fallsoft.vipi

import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import kotlinx.coroutines.launch

@Composable internal fun DeviceRecoveryCard(chat: ChatSession, signIn: () -> Unit) {
    val scope = rememberCoroutineScope()
    var confirm by remember { mutableStateOf(false) }
    Text("Connect this device", style = MaterialTheme.typography.titleLarge)
    Text(chat.notice ?: "Your account is active on another device. Saved conversations are still available here.")
    if (chat.busy) CircularProgressIndicator()
    else if (chat.recoveryNeedsSignIn) Button(onClick = signIn) { Text("Sign in again") }
    else Button(onClick = { confirm = true }) { Text("Use this device") }
    if (confirm) AlertDialog(onDismissRequest = { confirm = false },
        title = { Text("Use Vipi on this device?") },
        text = { Text("This signs out whichever other device is active. Chats already on this device stay here. Waiting messages cannot move between devices and will stop. Your encryption keys change; friends will need to approve them and compare security numbers again.",
            modifier = Modifier.verticalScroll(rememberScrollState())) },
        confirmButton = { TextButton(onClick = { confirm = false; scope.launch { chat.confirmDeviceReplacement() } }) { Text("Use this device") } },
        dismissButton = { TextButton(onClick = { confirm = false }) { Text("Cancel") } })
}
