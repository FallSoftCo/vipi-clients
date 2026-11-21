package co.fallsoft.vipi

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts.PickVisualMedia
import android.graphics.Bitmap
import androidx.compose.foundation.clickable
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.PhotoCamera
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

@Composable internal fun MediaComposer(
    repository: AttachmentRepository, recipient: String, caption: String, enabled: Boolean,
    checkPeer: suspend () -> Unit,
    send: suspend (AttachmentManifest, () -> Unit) -> Unit, onError: (Exception) -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var chosen by remember { mutableStateOf<AttachmentManifest?>(null) }
    var menu by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var cameraFile by androidx.compose.runtime.saveable.rememberSaveable { mutableStateOf<String?>(null) }
    val sendLatest by rememberUpdatedState(send)
    val errorLatest by rememberUpdatedState(onError)
    val staging = remember(repository) { repository.newPreview() }
    fun discard() { chosen?.let(staging::discard); chosen = null }
    fun preview(uri: android.net.Uri, kind: AttachmentKind, owned: java.io.File? = null) {
        if (busy || chosen != null) { owned?.delete(); return }
        busy = true
        scope.launch {
            try { checkPeer(); chosen = staging.prepare(uri, kind) }
            catch (cancel: CancellationException) { throw cancel }
            catch (failure: Exception) {
                errorLatest(if (failure is IllegalArgumentException && failure !is PhotoTooLarge) MediaActionFailure(R.string.media_invalid) else failure)
            } finally { owned?.delete(); busy = false }
        }
    }
    DisposableEffect(Unit) { onDispose { discard(); staging.closePreview() } }
    val camera = rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.TakePicture()) { ok ->
        val path = cameraFile?.let(::javaFile)
        cameraFile = null
        if (path != null) {
            if (ok) preview(android.net.Uri.fromFile(path), AttachmentKind.PHOTO, path) else path.delete()
        }
    }
    val picker = rememberLauncherForActivityResult(PickVisualMedia()) { uri ->
        if (uri != null) {
            val kind = if (context.contentResolver.getType(uri)?.startsWith("video/") == true) AttachmentKind.VIDEO else AttachmentKind.PHOTO
            preview(uri, kind)
        }
    }
    val available = enabled && !busy && chosen == null
    Box {
        IconButton(enabled = available, onClick = { menu = true }) {
            if (busy) CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.dp)
            else Icon(Icons.Outlined.PhotoCamera, stringResource(R.string.media_attach))
        }
        DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
            DropdownMenuItem(text = { Text(stringResource(R.string.media_camera)) }, onClick = {
                menu = false
                try {
                    val file = captureFile(context, repository.account, ".jpg")
                    cameraFile = file.path
                    val uri = androidx.core.content.FileProvider.getUriForFile(context, context.packageName + ".captures", file)
                    camera.launch(uri)
                } catch (_: Exception) {
                    cameraFile?.let(::javaFile)?.delete()
                    cameraFile = null
                    errorLatest(MediaActionFailure(R.string.media_camera_error))
                }
            })
            DropdownMenuItem(text = { Text(stringResource(R.string.media_gallery)) }, onClick = {
                menu = false
                try { picker.launch(PickVisualMediaRequest(PickVisualMedia.ImageAndVideo)) }
                catch (failure: Exception) { errorLatest(failure) }
            })
        }
    }
    chosen?.let { item ->
        val thumb by produceState<Bitmap?>(null, item) { value = staging.localPhotoThumbnail(item) }
        AlertDialog(onDismissRequest = { if (!busy) discard() },
            title = { Text(stringResource(if (item.kind == AttachmentKind.PHOTO) R.string.photo_recipient else R.string.media_recipient, recipient)) },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    thumb?.let { Image(it.asImageBitmap(), stringResource(R.string.photo_preview),
                        Modifier.fillMaxWidth().heightIn(max = 280.dp), contentScale = ContentScale.Fit) }
                    if (item.kind != AttachmentKind.PHOTO) {
                        Text(stringResource(item.kind.mediaLabel()) + " · " + android.text.format.DateUtils.formatElapsedTime((item.durationMillis ?: 0L) / 1000))
                        PrivateMediaPlayback(item.kind) { staging.openLocal(item) }
                    }
                    if (caption.isNotBlank()) Text(caption)
                }
            },
            dismissButton = { TextButton(enabled = !busy, onClick = ::discard) { Text(stringResource(android.R.string.cancel)) } },
            confirmButton = { Button(enabled = enabled && !busy, onClick = {
                if (busy || chosen !== item) return@Button
                busy = true
                scope.launch {
                    try {
                        checkPeer()
                        repository.adopt(staging, item) { committed ->
                            sendLatest(item) { committed(); discard() }
                        }
                    }
                    catch (cancel: CancellationException) { throw cancel }
                    catch (failure: Exception) { errorLatest(failure) }
                    finally { busy = false }
                }
            }) { Text(stringResource(if (item.kind == AttachmentKind.PHOTO) R.string.photo_send else R.string.media_send)) } })
    }
}

private fun javaFile(path: String) = java.io.File(path)
internal class MediaActionFailure(val label: Int) : Exception()
internal fun AttachmentKind.mediaLabel() = when (this) {
    AttachmentKind.VIDEO -> R.string.media_video
    AttachmentKind.VOICE -> R.string.media_voice
    else -> R.string.photo_message
}

@Composable
internal fun ConversationPhoto(repository: AttachmentRepository, attachment: AttachmentManifest,
                               enabled: Boolean, open: suspend () -> Bitmap) {
    val thumbnail by produceState<Bitmap?>(null, repository, attachment.id) {
        try { value = repository.localPhotoThumbnail(attachment) }
        catch (cancel: CancellationException) { throw cancel }
        catch (_: Exception) { value = null }
    }
    var showing by remember(enabled) { mutableStateOf(false) }
    val small = thumbnail
    if (small == null) {
        TextButton(enabled = enabled, onClick = { showing = true }) { Text(stringResource(R.string.photo_open)) }
    } else {
        Image(small.asImageBitmap(), stringResource(R.string.photo_message),
            Modifier.clickable(enabled = enabled, onClickLabel = stringResource(R.string.photo_open)) { showing = true }
                .widthIn(max = 208.dp).heightIn(max = 180.dp), contentScale = ContentScale.Fit)
    }
    if (!showing || !enabled) return
    var attempt by remember { mutableIntStateOf(0) }
    var image by remember { mutableStateOf<Bitmap?>(null) }
    var error by remember { mutableIntStateOf(0) }
    val currentOpen by rememberUpdatedState(open)
    LaunchedEffect(attempt) {
        error = 0
        try { image = currentOpen() }
        catch (cancel: CancellationException) { throw cancel }
        catch (failure: Exception) {
            error = when {
                failure is PhotoTooLarge -> R.string.photo_too_large
                failure is ServiceFailure && failure.status in setOf(403, 404, 410) -> R.string.photo_unavailable
                else -> R.string.photo_open_error
            }
        }
    }
    AlertDialog(
        onDismissRequest = { showing = false },
        text = {
            val opened = image
            when {
                opened != null -> Image(opened.asImageBitmap(), stringResource(R.string.photo_viewed),
                    Modifier.fillMaxWidth().heightIn(max = 520.dp), contentScale = ContentScale.Fit)
                error != 0 -> Text(stringResource(error))
                else -> Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.dp)
                    Text(stringResource(R.string.photo_opening))
                }
            }
        },
        dismissButton = {
            if (error == R.string.photo_open_error) TextButton(onClick = { attempt++ }) { Text(stringResource(R.string.photo_retry)) }
        },
        confirmButton = {
            TextButton(onClick = { showing = false }) { Text(stringResource(R.string.photo_close)) }
        }
    )
}
