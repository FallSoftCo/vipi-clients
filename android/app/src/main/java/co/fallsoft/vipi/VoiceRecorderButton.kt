package co.fallsoft.vipi

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioManager
import android.media.AudioRecordingConfiguration
import android.media.MediaRecorder
import android.os.SystemClock
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.focusable
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.waitForUpOrCancellation
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Send
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.input.key.*
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.*
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.io.File
import java.util.UUID
import kotlin.math.abs
import kotlin.math.log10

internal fun captureFile(context: Context, account: UUID, suffix: String): File {
    val dir = File(context.cacheDir, "media-capture/$account").apply { check(isDirectory || mkdirs()) }
    dir.listFiles()?.filter { System.currentTimeMillis() - it.lastModified() > 86_400_000 }?.forEach { it.delete() }
    return File.createTempFile("capture-", suffix, dir)
}

private enum class RecordingPhase { IDLE, TIP, HELD, LOCKED, SAVING, PREVIEW, SENDING }

private class MicCapture(private val context: Context, private val account: UUID) {
    private var recorder: MediaRecorder? = null
    private var file: File? = null
    private var recordingCallback: AudioManager.AudioRecordingCallback? = null
    var startedAt = 0L
        private set
    fun start(onLimit: () -> Unit, onFailure: () -> Unit) {
        check(recorder == null && file == null)
        try {
            val path = captureFile(context, account, ".m4a")
            file = path
            @Suppress("DEPRECATION") val active = if (android.os.Build.VERSION.SDK_INT >= 31) MediaRecorder(context) else MediaRecorder()
            recorder = active
            active.setAudioSource(MediaRecorder.AudioSource.MIC)
            active.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            active.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            active.setAudioEncodingBitRate(64_000)
            active.setAudioSamplingRate(44100)
            active.setMaxDuration(179_000)
            active.setOutputFile(path.path)
            active.setOnInfoListener { source, what, _ -> if (source === recorder && what == MediaRecorder.MEDIA_RECORDER_INFO_MAX_DURATION_REACHED) onLimit() }
            active.setOnErrorListener { source, _, _ -> if (source === recorder) onFailure() }
            val monitor = object : AudioManager.AudioRecordingCallback() {
                override fun onRecordingConfigChanged(configs: MutableList<AudioRecordingConfiguration>?) {
                    if (recorder === active && active.activeRecordingConfiguration?.isClientSilenced == true) onFailure()
                }
            }
            active.registerAudioRecordingCallback(context.mainExecutor, monitor)
            recordingCallback = monitor
            active.prepare()
            active.start()
            startedAt = SystemClock.elapsedRealtime()
        } catch (failure: Exception) { finish(false); throw failure }
    }
    fun amplitude(): Float {
        val amplitude = runCatching { recorder?.maxAmplitude ?: 0 }.getOrDefault(0)
        return ((20.0 * log10(maxOf(1, amplitude) / 32767.0) + 60.0) / 60.0).coerceIn(0.0, 1.0).toFloat()
    }
    fun finish(keep: Boolean): File? {
        val path = file
        val active = recorder
        recorder = null
        recordingCallback?.let { active?.unregisterAudioRecordingCallback(it) }
        recordingCallback = null
        file = null
        val stopped = active != null && try { active.stop(); true } catch (_: RuntimeException) { false }
        finally { active.release() }
        if (stopped && keep && path != null && path.length() > 0) return path
        path?.delete()
        return null
    }
}

@Composable private fun VoiceLevels(levels: List<Float>, modifier: Modifier = Modifier) {
    val ink = MaterialTheme.colorScheme.primary
    Canvas(modifier.height(28.dp)) {
        val count = 28
        val step = size.width / count
        val width = minOf(3.dp.toPx(), step * .55f)
        repeat(count) { i ->
            val value = levels.getOrNull(i - count + levels.size) ?: 0f
            val half = maxOf(1.dp.toPx(), value * size.height * .44f)
            val x = step * (i + .5f)
            drawLine(ink, Offset(x, size.height / 2 - half), Offset(x, size.height / 2 + half), width, StrokeCap.Round)
        }
    }
}

@Composable internal fun VoiceComposer(drafts: VoiceDrafts, peer: UUID, enabled: Boolean,
                                      checkPeer: suspend () -> Unit, send: suspend (AttachmentManifest, () -> Unit) -> Unit,
                                      onActive: (Boolean) -> Unit, onError: (Exception) -> Unit) {
    val context = LocalContext.current
    val haptic = LocalHapticFeedback.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val view = LocalView.current
    val scope = rememberCoroutineScope()
    val activeChanged by rememberUpdatedState(onActive)
    val report by rememberUpdatedState(onError)
    val checkLatest by rememberUpdatedState(checkPeer)
    val sendLatest by rememberUpdatedState(send)
    val mic = remember(drafts, peer) { MicCapture(context, drafts.repository.account) }
    val restoring = remember(drafts, peer) { drafts.pending(peer) }
    var clip by remember(drafts, peer) { mutableStateOf(drafts.current(peer)) }
    var phase by remember(drafts, peer) { mutableStateOf(when {
        clip != null -> RecordingPhase.PREVIEW
        restoring != null -> RecordingPhase.SAVING
        else -> RecordingPhase.IDLE
    }) }
    var gestureGeneration by remember { mutableIntStateOf(0) }
    var duration by remember { mutableLongStateOf(clip?.durationMillis ?: 0L) }
    var sending by remember { mutableStateOf<Job?>(null) }
    val levels = remember { mutableStateListOf<Float>() }
    fun show(next: RecordingPhase) { phase = next; activeChanged(next != RecordingPhase.IDLE) }
    fun review(item: AttachmentManifest) {
        clip = item
        duration = requireNotNull(item.durationMillis)
        show(RecordingPhase.PREVIEW)
    }
    LaunchedEffect(drafts, peer) {
        activeChanged(phase != RecordingPhase.IDLE)
        try { restoring?.let { review(it.await()) } }
        catch (cancel: CancellationException) { throw cancel }
        catch (error: Exception) { show(RecordingPhase.IDLE); report(error) }
    }
    fun discard() {
        if (phase == RecordingPhase.SAVING) return
        gestureGeneration++
        sending?.cancel(); sending = null
        mic.finish(false)
        try {
            clip?.let { drafts.discard(peer, it) }
            clip = null
            levels.clear()
            show(RecordingPhase.IDLE)
        } catch (error: Exception) { report(error) }
    }
    fun dispatch() {
        val item = clip ?: return
        if (phase != RecordingPhase.PREVIEW || !enabled) return
        val issued = gestureGeneration
        show(RecordingPhase.SENDING)
        sending = scope.launch(Dispatchers.Main.immediate) {
            try {
                checkLatest()
                currentCoroutineContext().ensureActive()
                check(gestureGeneration == issued && phase == RecordingPhase.SENDING && clip == item &&
                    view.hasWindowFocus() && lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED))
                sendLatest(item) {
                    clip = null
                    sending = null
                    show(RecordingPhase.IDLE)
                }
            } catch (cancel: CancellationException) { throw cancel }
            catch (error: Exception) {
                if (clip == item) { show(RecordingPhase.PREVIEW); report(error) }
            }
        }
    }
    fun stop(sendImmediately: Boolean) {
        if (phase != RecordingPhase.HELD && phase != RecordingPhase.LOCKED) return
        duration = SystemClock.elapsedRealtime() - mic.startedAt
        val path = mic.finish(duration >= 350)
        if (path == null) {
            show(if (duration < 350 && sendImmediately) RecordingPhase.TIP else RecordingPhase.IDLE)
            if (duration >= 350) report(MediaActionFailure(R.string.media_recorder_error))
            return
        }
        val generation = gestureGeneration
        show(RecordingPhase.SAVING)
        val save = try { drafts.save(peer, path) } catch (error: Exception) {
            path.delete(); show(RecordingPhase.IDLE); report(error); return
        }
        scope.launch {
            try {
                review(save.await())
                if (sendImmediately && gestureGeneration == generation && view.hasWindowFocus() &&
                    lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) dispatch()
            } catch (cancel: CancellationException) { throw cancel }
            catch (error: Exception) { show(RecordingPhase.IDLE); report(error) }
        }
    }
    fun interrupt() {
        gestureGeneration++
        if (phase == RecordingPhase.HELD || phase == RecordingPhase.LOCKED) stop(false)
        else if (phase == RecordingPhase.SENDING) {
            sending?.cancel(); sending = null
            if (clip != null) show(RecordingPhase.PREVIEW)
        } else if (phase == RecordingPhase.TIP) show(RecordingPhase.IDLE)
    }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (!granted) report(MediaActionFailure(R.string.media_permission))
    }
    fun permitted(): Boolean {
        if (!enabled || !lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) return false
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) return true
        permission.launch(Manifest.permission.RECORD_AUDIO)
        return false
    }
    fun begin(locked: Boolean) {
        if (phase !in setOf(RecordingPhase.IDLE, RecordingPhase.TIP) || !permitted()) return
        try {
            stopInlineVoicePlayback()
            mic.start(onLimit = { stop(false) }, onFailure = { interrupt(); report(MediaActionFailure(R.string.media_recorder_error)) })
            duration = 0
            levels.clear()
            haptic.performHapticFeedback(HapticFeedbackType.LongPress)
            show(if (locked) RecordingPhase.LOCKED else RecordingPhase.HELD)
        } catch (_: Exception) { discard(); report(MediaActionFailure(R.string.media_recorder_error)) }
    }
    LaunchedEffect(enabled) { if (!enabled) interrupt() }
    DisposableEffect(lifecycle, view) {
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_PAUSE) interrupt() }
        val focus = android.view.ViewTreeObserver.OnWindowFocusChangeListener { focused -> if (!focused) interrupt() }
        view.viewTreeObserver.addOnWindowFocusChangeListener(focus)
        lifecycle.addObserver(observer)
        onDispose {
            lifecycle.removeObserver(observer)
            if (view.viewTreeObserver.isAlive) view.viewTreeObserver.removeOnWindowFocusChangeListener(focus)
            interrupt()
            activeChanged(false)
        }
    }
    BackHandler(enabled = phase == RecordingPhase.HELD || phase == RecordingPhase.LOCKED || phase == RecordingPhase.TIP) { interrupt() }
    val live = phase == RecordingPhase.HELD || phase == RecordingPhase.LOCKED
    LaunchedEffect(live) {
        while (live) {
            duration = SystemClock.elapsedRealtime() - mic.startedAt
            if (levels.size == 28) levels.removeAt(0)
            levels.add(mic.amplitude())
            delay(100)
        }
    }
    val rtl = LocalLayoutDirection.current == LayoutDirection.Rtl
    val anchor = when (phase) {
        RecordingPhase.LOCKED, RecordingPhase.PREVIEW -> R.string.voice_send_recording
        RecordingPhase.TIP -> R.string.voice_handsfree
        else -> R.string.media_record
    }
    val label = stringResource(anchor)
    fun activate() {
        when (phase) {
            RecordingPhase.IDLE, RecordingPhase.TIP -> begin(true)
            RecordingPhase.LOCKED -> stop(true)
            RecordingPhase.PREVIEW -> dispatch()
            else -> Unit
        }
    }
    val clock = android.text.format.DateUtils.formatElapsedTime(duration / 1000)
    Row(if (phase == RecordingPhase.IDLE) Modifier else Modifier.fillMaxWidth().testTag("voice-composer-active"),
        verticalAlignment = Alignment.CenterVertically) {
        if (phase != RecordingPhase.IDLE) {
            IconButton(onClick = ::discard, enabled = phase != RecordingPhase.SAVING, modifier = Modifier.testTag("voice-discard")) {
                Icon(if (phase == RecordingPhase.TIP) Icons.Outlined.Close else Icons.Outlined.DeleteOutline,
                    stringResource(if (phase == RecordingPhase.TIP) R.string.photo_close else R.string.voice_discard))
            }
            Column(modifier = Modifier.weight(1f).padding(horizontal = 4.dp)) {
                when (phase) {
                    RecordingPhase.HELD, RecordingPhase.LOCKED -> {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Icon(if (phase == RecordingPhase.LOCKED) Icons.Outlined.Lock else Icons.Outlined.Mic,
                                stringResource(R.string.media_recording), Modifier.size(18.dp), tint = MaterialTheme.colorScheme.error)
                            Text(clock, style = MaterialTheme.typography.labelLarge)
                            VoiceLevels(levels, Modifier.weight(1f))
                        }
                        Text(stringResource(if (phase == RecordingPhase.LOCKED) R.string.voice_locked else R.string.voice_gestures),
                            style = MaterialTheme.typography.labelSmall)
                    }
                    RecordingPhase.TIP -> Text(stringResource(R.string.voice_tap_hint), style = MaterialTheme.typography.bodySmall)
                    RecordingPhase.PREVIEW -> clip?.let { item ->
                        key(item.id) { InlineVoicePlayer(duration) { drafts.open(item) } }
                    }
                    RecordingPhase.SAVING -> CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                    RecordingPhase.SENDING -> Text(stringResource(R.string.photo_sending), style = MaterialTheme.typography.bodySmall)
                    else -> Unit
                }
            }
        }
        if (phase == RecordingPhase.LOCKED) {
            IconButton(onClick = { stop(false) }, modifier = Modifier.size(48.dp).testTag("voice-stop")) {
                Icon(Icons.Outlined.Stop, stringResource(R.string.media_stop))
            }
        }
        val actionEnabled = enabled && phase != RecordingPhase.SAVING && phase != RecordingPhase.SENDING
        val sendAction = phase == RecordingPhase.LOCKED || phase == RecordingPhase.PREVIEW
        val activeColor = if (sendAction) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.secondaryContainer
        val iconColor = if (sendAction) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSecondaryContainer
        Box(Modifier.size(48.dp).clip(CircleShape).background(activeColor).testTag("voice-action")
            .semantics {
                role = Role.Button; contentDescription = label
                if (!actionEnabled) disabled()
                onClick(label) { if (actionEnabled) activate(); actionEnabled }
            }.onKeyEvent { event ->
                val activation = event.key in setOf(Key.Enter, Key.NumPadEnter, Key.Spacebar, Key.DirectionCenter)
                if (activation && actionEnabled && event.type == KeyEventType.KeyUp) activate()
                activation && actionEnabled
            }.focusable(actionEnabled).pointerInput(enabled, rtl) {
                if (!enabled) return@pointerInput
                awaitEachGesture {
                    val down = awaitFirstDown()
                    down.consume()
                    if (phase != RecordingPhase.IDLE) {
                        if (waitForUpOrCancellation() != null) activate()
                        return@awaitEachGesture
                    }
                    if (!permitted()) return@awaitEachGesture
                    // Match the physical finger's clock, including when the view is otherwise idle.
                    val generation = gestureGeneration
                    val startRecording = Runnable {
                        if (generation == gestureGeneration && view.hasWindowFocus()) begin(false)
                    }
                    view.postDelayed(startRecording, 220L)
                    try {
                        while (generation == gestureGeneration && (phase == RecordingPhase.IDLE || phase == RecordingPhase.HELD)) {
                            val event = awaitPointerEvent()
                            if (generation != gestureGeneration) break
                            val change = event.changes.singleOrNull { it.id == down.id }
                            if (change == null || change.isConsumed || event.changes.size > 1) { interrupt(); break }
                            val horizontal = (change.position.x - down.position.x) * (if (rtl) -1 else 1)
                            val upward = down.position.y - change.position.y
                            change.consume()
                            if (horizontal <= -64.dp.toPx() && -horizontal >= upward) {
                                discard()
                                break
                            }
                            if (phase == RecordingPhase.HELD && upward >= 56.dp.toPx()) {
                                haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                                show(RecordingPhase.LOCKED)
                                break
                            }
                            if (!change.pressed) {
                                if (phase == RecordingPhase.HELD) stop(true) else show(RecordingPhase.TIP)
                                break
                            }
                        }
                    } finally {
                        view.removeCallbacks(startRecording)
                        if (phase == RecordingPhase.HELD) interrupt()
                    }
                }
            }, contentAlignment = Alignment.Center) {
            if (phase == RecordingPhase.SENDING) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
            else Icon(when (phase) {
                RecordingPhase.LOCKED, RecordingPhase.PREVIEW -> Icons.AutoMirrored.Outlined.Send
                RecordingPhase.TIP -> Icons.Outlined.Lock
                else -> Icons.Outlined.Mic
            }, null, tint = iconColor)
        }
    }
}
