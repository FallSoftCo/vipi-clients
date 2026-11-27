package co.fallsoft.vipi

import android.graphics.BitmapFactory
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts.PickVisualMedia
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import java.util.UUID
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

internal val LocalAvatarChat = staticCompositionLocalOf<ChatSession?> { null }

@Composable
internal fun ProfileAvatarEditor(chat: ChatSession, owner: UUID) {
    key(owner) {
        val context = LocalContext.current
        val scope = rememberCoroutineScope()
        var preview by remember { mutableStateOf<ByteArray?>(null) }
        var confirmRemoval by remember { mutableStateOf(false) }
        var failed by remember { mutableStateOf(false) }
        var loading by remember { mutableStateOf(false) }
        val hasAvatar = remember(chat, owner, chat.revision) { chat.avatar(owner)?.jpeg != null }
        val picker =
            rememberLauncherForActivityResult(PickVisualMedia()) { uri ->
                if (uri != null)
                    scope.launch {
                        loading = true
                        failed = false
                        try {
                            PickedPhoto.read(context, uri).use { photo ->
                                preview =
                                    withContext(Dispatchers.Default) {
                                        ProfileAvatar.crop(photo.preview)
                                    }
                            }
                        } catch (cancel: CancellationException) {
                            throw cancel
                        } catch (_: Exception) {
                            failed = true
                        } finally {
                            loading = false
                        }
                    }
            }
        TextButton(
            enabled = !loading,
            onClick = { picker.launch(PickVisualMediaRequest(PickVisualMedia.ImageOnly)) },
        ) {
            Text(stringResource(if (hasAvatar) R.string.avatar_change else R.string.avatar_choose))
        }
        if (hasAvatar)
            TextButton(onClick = { confirmRemoval = true }) {
                Text(stringResource(R.string.avatar_remove))
            }
        if (failed) Text(stringResource(R.string.avatar_error))
        val bytes = preview
        if (bytes != null || confirmRemoval)
            AlertDialog(
                onDismissRequest = {
                    preview = null
                    confirmRemoval = false
                },
                title = {
                    Text(
                        stringResource(
                            if (confirmRemoval) R.string.avatar_remove else R.string.avatar_preview
                        )
                    )
                },
                text = {
                    Column(horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally) {
                        bytes?.let {
                            Image(
                                remember(it) {
                                    BitmapFactory.decodeByteArray(it, 0, it.size).asImageBitmap()
                                },
                                stringResource(R.string.avatar_preview),
                                Modifier.size(96.dp).clip(CircleShape),
                            )
                        }
                        Text(stringResource(R.string.avatar_private))
                    }
                },
                confirmButton = {
                    TextButton(
                        onClick = {
                            try {
                                chat.setOwnAvatar(bytes)
                            } catch (_: Exception) {
                                failed = true
                            }
                            preview = null
                            confirmRemoval = false
                        }
                    ) {
                        Text(
                            stringResource(
                                if (confirmRemoval) R.string.avatar_remove else R.string.avatar_save
                            )
                        )
                    }
                },
                dismissButton = {
                    TextButton(
                        onClick = {
                            preview = null
                            confirmRemoval = false
                        }
                    ) {
                        Text(stringResource(android.R.string.cancel))
                    }
                },
            )
    }
}
