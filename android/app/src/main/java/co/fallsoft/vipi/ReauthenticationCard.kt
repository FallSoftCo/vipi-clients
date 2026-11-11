package co.fallsoft.vipi

import androidx.compose.runtime.Composable
import androidx.compose.material3.Text

@Composable internal fun ReauthenticationCard(chat: ChatSession, busy: Boolean, error: String?, signIn: (String) -> Unit) {
    Text("Sign in again to reconnect. Your saved conversations stay on this device.")
    PrimaryButton("Sign in again", busy = busy) { signIn(chat.userID) }
    error?.let { Text(it) }
}
