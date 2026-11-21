package co.fallsoft.vipi

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.MediaRecorder
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Mic
import androidx.compose.material.icons.outlined.Stop
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.*
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import java.io.File

internal fun captureFile(context: Context, account: java.util.UUID, suffix: String): File {
    val dir = File(context.cacheDir, "media-capture/$account").apply { check(isDirectory || mkdirs()) }
    // Clean incomplete captures left by a process death. Never remove an active selection.
    dir.listFiles()?.filter { System.currentTimeMillis() - it.lastModified() > 86_400_000 }?.forEach { it.delete() }
    return File.createTempFile("capture-", suffix, dir)
}

@Composable internal fun VoiceRecorderButton(account: java.util.UUID, enabled: Boolean, onRecording: (File) -> Unit, onProblem: (Int) -> Unit) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val deliver by rememberUpdatedState(onRecording)
    val problem by rememberUpdatedState(onProblem)
    var recorder by remember { mutableStateOf<MediaRecorder?>(null) }
    var file by remember { mutableStateOf<File?>(null) }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (!granted) problem(R.string.media_permission)
    }
    fun finish(keep: Boolean) {
        val active = recorder ?: return
        recorder = null
        val captured = file
        file = null
        val complete = try { active.stop(); true } catch (_: RuntimeException) { false }
        finally { active.release() }
        if (complete && keep && captured != null && captured.length() > 0) deliver(captured)
        else { captured?.delete(); if (keep) problem(R.string.media_short) }
    }
    fun start(): Boolean {
        if (!enabled || recorder != null) return false
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            permission.launch(Manifest.permission.RECORD_AUDIO)
            return false
        }
        try {
            val path = captureFile(context, account, ".m4a")
            file = path
            @Suppress("DEPRECATION") val active = if (android.os.Build.VERSION.SDK_INT >= 31) MediaRecorder(context) else MediaRecorder()
            try {
                active.setAudioSource(MediaRecorder.AudioSource.MIC)
                active.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
                active.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                active.setAudioEncodingBitRate(64_000)
                active.setAudioSamplingRate(44100)
                active.setMaxDuration(179_000)
                active.setOutputFile(path.path)
                active.setOnInfoListener { source, what, _ -> if (source === recorder && what == MediaRecorder.MEDIA_RECORDER_INFO_MAX_DURATION_REACHED) finish(true) }
                active.setOnErrorListener { source, _, _ -> if (source === recorder) { finish(false); problem(R.string.media_recorder_error) } }
                active.prepare()
                active.start()
                recorder = active
                return true
            } catch (failure: Exception) { active.release(); throw failure }
        } catch (_: Exception) {
            file?.delete(); file = null
            problem(R.string.media_recorder_error)
            return false
        }
    }
    DisposableEffect(lifecycle, enabled) {
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_PAUSE) finish(false) }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer); finish(false) }
    }
    val recording = recorder != null
    var seconds by remember { mutableLongStateOf(0L) }
    LaunchedEffect(recording) {
        seconds = 0
        if (recording) {
            val start = android.os.SystemClock.elapsedRealtime()
            while (true) {
                kotlinx.coroutines.delay(250)
                seconds = (android.os.SystemClock.elapsedRealtime() - start) / 1000
            }
        }
    }
    val recordingLabel = stringResource(R.string.media_recording)
    val label = stringResource(if (recording) R.string.media_stop else R.string.media_record)
    Box(Modifier.size(48.dp).semantics {
        role = Role.Button
        contentDescription = label
        if (recording) stateDescription = recordingLabel
        if (!enabled) disabled()
        onClick(label) { if (recording) { finish(true); true } else start() }
    }.pointerInput(enabled) {
        if (enabled) detectTapGestures(onPress = {
            if (start()) {
                try { finish(tryAwaitRelease()) } finally { finish(false) }
            }
        })
    }, contentAlignment = Alignment.Center) {
        if (recording) Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(Icons.Outlined.Stop, null, Modifier.size(18.dp), tint = MaterialTheme.colorScheme.error)
            Text(android.text.format.DateUtils.formatElapsedTime(seconds), style = MaterialTheme.typography.labelSmall, maxLines = 1)
        } else Icon(Icons.Outlined.Mic, null, tint = MaterialTheme.colorScheme.onSurface)
    }
}
