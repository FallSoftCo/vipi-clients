package co.fallsoft.vipi

import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.media.MediaPlayer
import android.view.SurfaceHolder
import android.view.SurfaceView
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import java.io.File
import kotlinx.coroutines.CancellationException

@Composable
internal fun PrivateMediaPlayback(kind: AttachmentKind, open: suspend () -> File) {
    var showing by remember { mutableStateOf(false) }
    val label =
        stringResource(
            if (kind == AttachmentKind.VOICE) R.string.media_open_voice
            else R.string.media_open_video
        )
    TextButton(onClick = { showing = true }) { Text(label) }
    if (!showing) return
    val latestOpen by rememberUpdatedState(open)
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val audio = remember { context.getSystemService(AudioManager::class.java) }
    val attributes = remember {
        AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_MEDIA)
            .setContentType(
                if (kind == AttachmentKind.VOICE) AudioAttributes.CONTENT_TYPE_SPEECH
                else AudioAttributes.CONTENT_TYPE_MOVIE
            )
            .build()
    }
    var player by remember { mutableStateOf<MediaPlayer?>(null) }
    var ready by remember { mutableStateOf(false) }
    var playing by remember { mutableStateOf(false) }
    var failed by remember { mutableStateOf(false) }
    var aspect by remember { mutableFloatStateOf(16f / 9f) }
    var display by remember { mutableStateOf<SurfaceHolder?>(null) }
    val focus = remember {
        AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
            .setAudioAttributes(attributes)
            .setOnAudioFocusChangeListener { change ->
                if (change < 0 && playing) {
                    player?.pause()
                    playing = false
                }
            }
            .build()
    }
    fun play() {
        if (audio.requestAudioFocus(focus) != AudioManager.AUDIOFOCUS_REQUEST_GRANTED) return
        player?.start()
        playing = true
    }
    LaunchedEffect(Unit) {
        try {
            val file = latestOpen()
            try {
                val media = MediaPlayer()
                player = media
                media.setAudioAttributes(attributes)
                file.inputStream().use { media.setDataSource(it.fd) }
                media.setDisplay(display)
                media.setOnVideoSizeChangedListener { _, width, height ->
                    if (width > 0 && height > 0) aspect = width.toFloat() / height
                }
                media.setOnPreparedListener {
                    ready = true
                    if (lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) play()
                }
                media.setOnCompletionListener {
                    playing = false
                    audio.abandonAudioFocusRequest(focus)
                }
                media.setOnErrorListener { _, _, _ ->
                    failed = true
                    playing = false
                    audio.abandonAudioFocusRequest(focus)
                    true
                }
                media.prepareAsync()
            } finally {
                file.delete()
            }
        } catch (cancel: CancellationException) {
            throw cancel
        } catch (_: Exception) {
            failed = true
        }
    }
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_PAUSE) showing = false
        }
        lifecycle.addObserver(observer)
        onDispose {
            lifecycle.removeObserver(observer)
            player?.release()
            player = null
            audio.abandonAudioFocusRequest(focus)
        }
    }
    AlertDialog(
        onDismissRequest = { showing = false },
        title = { Text(stringResource(kind.mediaLabel())) },
        text = {
            Column {
                if (kind == AttachmentKind.VIDEO && !failed)
                    AndroidView(
                        factory = { ctx ->
                            SurfaceView(ctx).also { surface ->
                                surface.holder.addCallback(
                                    object : SurfaceHolder.Callback {
                                        override fun surfaceCreated(holder: SurfaceHolder) {
                                            display = holder
                                            player?.setDisplay(holder)
                                        }

                                        override fun surfaceDestroyed(holder: SurfaceHolder) {
                                            display = null
                                            player?.setDisplay(null)
                                        }

                                        override fun surfaceChanged(
                                            holder: SurfaceHolder,
                                            format: Int,
                                            width: Int,
                                            height: Int,
                                        ) = Unit
                                    }
                                )
                            }
                        },
                        modifier = Modifier.heightIn(max = 300.dp).aspectRatio(aspect),
                    )
                if (failed) Text(stringResource(R.string.media_open_error))
                else if (!ready) CircularProgressIndicator(Modifier.size(24.dp))
                else
                    TextButton(
                        onClick = {
                            if (playing) {
                                player?.pause()
                                playing = false
                                audio.abandonAudioFocusRequest(focus)
                            } else play()
                        }
                    ) {
                        Text(
                            stringResource(
                                if (playing) R.string.media_pause else R.string.media_play
                            )
                        )
                    }
            }
        },
        confirmButton = {
            TextButton(onClick = { showing = false }) { Text(stringResource(R.string.photo_close)) }
        },
    )
}
