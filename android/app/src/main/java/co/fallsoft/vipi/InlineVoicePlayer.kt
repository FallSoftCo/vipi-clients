package co.fallsoft.vipi

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.media.MediaPlayer
import android.os.ParcelFileDescriptor
import android.text.format.DateUtils
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Pause
import androidx.compose.material.icons.outlined.PlayArrow
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private enum class NoteState { IDLE, LOADING, PLAYING, PAUSED, FINISHED, FAILED }

/** Only the current row owns a decoder or requests audio focus. All callbacks run on main. */
private class NotePlayback(context: Context, private val scope: CoroutineScope) {
    companion object { private var active: NotePlayback? = null }
    var state by mutableStateOf(NoteState.IDLE)
        private set
    var position by mutableLongStateOf(0L)
        private set
    var actualDuration by mutableLongStateOf(0L)
        private set
    private val audio = context.getSystemService(AudioManager::class.java)
    private val attributes = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build()
    private val focus = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
        .setAudioAttributes(attributes).setWillPauseWhenDucked(true)
        .setOnAudioFocusChangeListener { if (it < 0) yieldPlayback() }.build()
    private var player: MediaPlayer? = null
    private var opening: Job? = null
    private var serial = 0

    fun samplePosition() {
        val current = player ?: return
        if (state == NoteState.PLAYING) position = current.currentPosition.toLong().coerceIn(0, actualDuration)
    }

    private fun release() {
        serial++
        opening?.cancel(); opening = null
        player?.release(); player = null
        audio.abandonAudioFocusRequest(focus)
        if (active === this) active = null
    }

    fun yieldPlayback() {
        if (state == NoteState.PLAYING) {
            samplePosition()
            state = NoteState.PAUSED
        } else if (state == NoteState.LOADING) {
            state = if (position > 0) NoteState.PAUSED else NoteState.IDLE
        }
        release()
    }

    private fun fail() { release(); state = NoteState.FAILED }

    private fun play(media: MediaPlayer) {
        try {
            if (audio.requestAudioFocus(focus) != AudioManager.AUDIOFOCUS_REQUEST_GRANTED) { fail(); return }
            media.start()
            state = NoteState.PLAYING
        } catch (_: IllegalStateException) { fail() }
    }

    fun activate(open: suspend () -> ParcelFileDescriptor) {
        if (state == NoteState.LOADING) return
        if (state == NoteState.PLAYING) {
            samplePosition()
            player?.pause(); state = NoteState.PAUSED
            audio.abandonAudioFocusRequest(focus)
            return
        }
        if (active !== this) active?.yieldPlayback()
        active = this
        if (state == NoteState.FINISHED) position = 0
        player?.let { play(it); return }
        val token = ++serial
        state = NoteState.LOADING
        opening = scope.launch {
            try {
                open().use { descriptor ->
                    if (token != serial) return@launch
                    val media = MediaPlayer()
                    player = media
                    media.setAudioAttributes(attributes)
                    media.setDataSource(descriptor.fileDescriptor)
                    media.setOnPreparedListener {
                        if (token != serial) return@setOnPreparedListener
                        actualDuration = media.duration.toLong()
                        if (actualDuration <= 0) { fail(); return@setOnPreparedListener }
                        if (position > 0) media.seekTo(position.coerceAtMost(actualDuration), MediaPlayer.SEEK_CLOSEST)
                        play(media)
                    }
                    media.setOnCompletionListener {
                        if (token == serial) { position = actualDuration; release(); state = NoteState.FINISHED }
                    }
                    media.setOnErrorListener { _, _, _ -> if (token == serial) fail(); true }
                    media.prepareAsync()
                }
            } catch (cancel: CancellationException) {
                if (token == serial) { release(); state = NoteState.IDLE }
                throw cancel
            } catch (_: Exception) { if (token == serial) fail() }
        }
    }
}

@Composable internal fun InlineVoicePlayer(duration: Long, open: suspend () -> ParcelFileDescriptor) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val scope = rememberCoroutineScope()
    val note = remember(context, scope) { NotePlayback(context.applicationContext, scope) }
    val latestOpen by rememberUpdatedState(open)
    DisposableEffect(lifecycle, note) {
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_PAUSE) note.yieldPlayback() }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer); note.yieldPlayback() }
    }
    LaunchedEffect(note.state) {
        while (note.state == NoteState.PLAYING) { note.samplePosition(); delay(200) }
    }
    val total = if (note.actualDuration > 0) note.actualDuration else duration.coerceAtLeast(0)
    val action = when (note.state) {
        NoteState.PLAYING -> R.string.media_pause
        NoteState.FAILED -> R.string.try_again
        else -> R.string.media_open_voice
    }
    Column(Modifier.widthIn(min = 150.dp, max = 216.dp).testTag("inline-voice-player")) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = {
                if (lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) note.activate { latestOpen() }
            }, enabled = note.state != NoteState.LOADING) {
                if (note.state == NoteState.LOADING) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                else Icon(when (note.state) {
                    NoteState.PLAYING -> Icons.Outlined.Pause
                    NoteState.FAILED -> Icons.Outlined.Refresh
                    else -> Icons.Outlined.PlayArrow
                }, stringResource(action))
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                LinearProgressIndicator(progress = { if (total > 0) (note.position.toFloat() / total).coerceIn(0f, 1f) else 0f },
                    modifier = Modifier.fillMaxWidth())
                Text(DateUtils.formatElapsedTime(note.position / 1000) + " / " + DateUtils.formatElapsedTime(total / 1000),
                    modifier = Modifier.testTag("voice-playback-position"), style = MaterialTheme.typography.labelSmall)
            }
        }
        if (note.state == NoteState.FAILED) Text(stringResource(R.string.media_open_error),
            Modifier.semantics { liveRegion = LiveRegionMode.Polite }, style = MaterialTheme.typography.labelSmall)
    }
}
