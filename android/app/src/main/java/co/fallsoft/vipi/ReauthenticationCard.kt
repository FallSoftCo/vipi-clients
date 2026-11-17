package co.fallsoft.vipi

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import androidx.compose.material3.Text

@Composable internal fun ReauthenticationCard(chat: ChatSession, busy: Boolean, error: String?, signIn: (String) -> Unit) {
    Text(stringResource(R.string.ui_0cb9c0cf3bb1))
    PrimaryButton(stringResource(R.string.ui_51fbe1dc8a73), busy = busy) { signIn(chat.userID) }
    error?.let { Text(it) }
}
