package co.fallsoft.vipi

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.os.Handler
import android.os.Looper
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import co.fallsoft.vipi.core.SpeechSpan
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout

enum class SpeechState {
    PREPARING,
    READY,
    RENDERING,
    PLAYING,
    UNAVAILABLE,
}

/**
 * Small playback boundary for ownership/error tests; production always uses SpeechPlayback with the
 * actual local voice and PCM player.
 */
internal interface ConversationSpeech {
    val state: SpeechState
    val error: String?
    val activeMessage: String?
    val interruption: Long
    val playingWord: PlayingWord?
        get() = null

    fun toggle(message: String, spans: List<SpeechSpan>)

    fun toggleTranslation(message: String, value: FullMessageTranslation) {
        val text = value.words?.joinToString(" ") { it.target } ?: value.practiceText
        toggle(message, listOf(SpeechSpan(text, value.practiceLanguage)))
    }

    fun stop()

    fun showMutedVolumeControl()

    fun failureMessage(): String
}

/** Conversation-scoped: one prepared pair, one player, never a player per word. */
internal class SpeechPlayback(
    context: Context,
    private val target: String,
    private val scope: CoroutineScope,
) : AutoCloseable, ConversationSpeech {
    private val context = context.applicationContext
    private var pair = LocalSpeechPair(context, target, target)
    private val audio = context.getSystemService(AudioManager::class.java)
    private val attributes =
        AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_MEDIA)
            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
            .build()
    private var focusRequest: AudioFocusRequest? = null

    private fun requestFocus(request: Int): Boolean {
        val focus =
            AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
                .setAudioAttributes(attributes)
                .setWillPauseWhenDucked(true)
                .setOnAudioFocusChangeListener(
                    { change ->
                        if (request == epoch && change != AudioManager.AUDIOFOCUS_GAIN)
                            interrupted()
                    },
                    Handler(Looper.getMainLooper()),
                )
                .build()
        // AudioManager registers the listener before deciding whether to grant focus.
        focusRequest = focus
        return audio.requestAudioFocus(focus) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED
    }

    private val noisy =
        object : BroadcastReceiver() {
            override fun onReceive(context: Context?, intent: Intent?) {
                if (intent?.action == AudioManager.ACTION_AUDIO_BECOMING_NOISY) interrupted()
            }
        }
    override var state by mutableStateOf(SpeechState.PREPARING)
        private set

    override var error by mutableStateOf<String?>(null)
        private set

    override var interruption by mutableLongStateOf(0L)
        private set

    private fun interrupted() {
        interruption++
        stop()
    }

    private var ready = false
    private var closed = false
    private var epoch = 0
    private var preparation: Job? = null
    private var rendering: Job? = null
    private var player: PcmSpeechPlayer? = null
    var outputUnderruns = 0
        private set

    var endOfStreamUnderruns = 0
        private set

    override var activeMessage by mutableStateOf<String?>(null)
        private set

    private val audioLifetime = PrivateSpeechCache.register(context, files = false) { close() }

    init {
        androidx.core.content.ContextCompat.registerReceiver(
            this.context,
            noisy,
            IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY),
            androidx.core.content.ContextCompat.RECEIVER_NOT_EXPORTED,
        )
    }

    fun prepare(warmups: Map<String, String>) {
        check(Looper.myLooper() == Looper.getMainLooper())
        if (closed || ready || preparation?.isActive == true) return
        if (state == SpeechState.UNAVAILABLE) {
            pair.close()
            pair = LocalSpeechPair(context, target, target)
        }
        state = SpeechState.PREPARING
        error = null
        preparation =
            scope.launch(Dispatchers.Main.immediate) {
                try {
                    withTimeout(120_000) { pair.prepare(warmups) }
                    ready = true
                    state = SpeechState.READY
                } catch (_: TimeoutCancellationException) {
                    error = context.getString(R.string.voices_not_ready)
                    state = SpeechState.UNAVAILABLE
                } catch (cancelled: CancellationException) {
                    throw cancelled
                } catch (missing: OfflineVoiceUnavailable) {
                    error =
                        context.getString(
                            R.string.voice_download_needed,
                            languageName(missing.language),
                        )
                    state = SpeechState.UNAVAILABLE
                } catch (_: Exception) {
                    error = context.getString(R.string.voices_not_ready)
                    state = SpeechState.UNAVAILABLE
                }
            }
    }

    internal var qualificationInput: ((String, List<SpeechSpan>) -> Unit)? = null
        set(value) {
            require(BuildConfig.DEBUG)
            field = value
        }

    override fun failureMessage(): String = error ?: context.getString(R.string.audio_play_failed)

    override fun showMutedVolumeControl() {
        if (audio.getStreamVolume(AudioManager.STREAM_MUSIC) == 0)
            audio.adjustStreamVolume(
                AudioManager.STREAM_MUSIC,
                AudioManager.ADJUST_SAME,
                AudioManager.FLAG_SHOW_UI,
            )
    }

    override var playingWord by mutableStateOf<PlayingWord?>(null)
        private set

    override fun toggleTranslation(message: String, value: FullMessageTranslation) {
        val text = value.words?.joinToString(" ") { it.target } ?: value.practiceText
        play(message, listOf(SpeechSpan(text, value.practiceLanguage)), value)
    }

    override fun toggle(message: String, spans: List<SpeechSpan>) = play(message, spans, null)

    private fun play(message: String, spans: List<SpeechSpan>, value: FullMessageTranslation?) {
        check(Looper.myLooper() == Looper.getMainLooper())
        require(spans.all { it.language == target }) {
            "Message playback uses only the practice language"
        }
        MessageAudioQualification.emit(
            "speech_request",
            message,
            "closed" to closed,
            "ready" to ready,
            "practice_language" to target,
            "practice_text" to spans.joinToString("") { it.text },
        )
        if (closed || !ready) return
        if (activeMessage == message) {
            stop()
            return
        }
        if (BuildConfig.DEBUG) qualificationInput?.invoke(message, spans)
        stop()
        val request = epoch
        activeMessage = message
        state = SpeechState.RENDERING
        error = null
        rendering =
            scope.launch(Dispatchers.Main.immediate) {
                try {
                    coroutineScope {
                        val queue = Channel<TimedPcm>(capacity = 2)
                        launch(Dispatchers.IO) {
                            try {
                                val projection = value?.let { SpeechProjection.build(context, it) }
                                val renderer =
                                    TimedSpeech(
                                        pair,
                                        target,
                                        projection,
                                        fullUtterance = value?.words == null,
                                    ) { rendered ->
                                        MessageAudioQualification.emit(
                                            "speech_rendered",
                                            message,
                                            "path" to rendered.file.absolutePath,
                                            "sample_rate" to rendered.sampleRate,
                                            "channels" to rendered.channels,
                                            "duration_ms" to rendered.milliseconds,
                                        )
                                    }
                                val chunks =
                                    if (value != null) MessageSpeech.pieces(value)
                                    else
                                        SpeechChunks.plan(spans).map { chunk ->
                                            SpeechPiece(chunk.joinToString("") { it.text }, 0)
                                        }
                                for (chunk in chunks) renderer.enqueue(chunk, queue)
                            } finally {
                                queue.close()
                            }
                        }
                        val first = queue.receive()
                        if (closed || request != epoch)
                            throw CancellationException("Playback stopped")
                        if (!requestFocus(request)) {
                            stop()
                            error = context.getString(R.string.audio_busy)
                            return@coroutineScope
                        }
                        val next =
                            PcmSpeechPlayer(first.wave.sampleRate, first.wave.channels, attributes)
                        player = next
                        outputUnderruns = 0
                        endOfStreamUnderruns = 0
                        val timeline = PlaybackWords()
                        val observe = launch {
                            while (request == epoch) {
                                if (state == SpeechState.PLAYING)
                                    playingWord = timeline.at(next.playedFrames)
                                kotlinx.coroutines.delay(16)
                            }
                        }
                        try {
                            withContext(Dispatchers.IO) {
                                timeline.append(first)
                                next.append(first.wave) {
                                    withContext(Dispatchers.Main.immediate) {
                                        if (request == epoch) {
                                            state = SpeechState.PLAYING
                                            MessageAudioQualification.emit("pcm_started", message)
                                        }
                                    }
                                }
                                for (piece in queue) {
                                    timeline.append(piece)
                                    next.append(piece.wave) {}
                                }
                                withContext(Dispatchers.Main.immediate) {
                                    if (request == epoch) outputUnderruns = next.underruns
                                }
                                next.finish()
                                if (request == epoch)
                                    endOfStreamUnderruns = next.underruns - outputUnderruns
                            }
                        } finally {
                            observe.cancel()
                        }
                    }
                    if (request == epoch) {
                        MessageAudioQualification.emit("pcm_completed", message)
                        stop()
                    }
                } catch (_: TimeoutCancellationException) {
                    if (request == epoch) {
                        stop()
                        error = context.getString(R.string.audio_play_failed)
                    }
                } catch (cancelled: CancellationException) {
                    if (request == epoch) stop()
                    throw cancelled
                } catch (failure: Exception) {
                    MessageAudioQualification.emit(
                        "speech_failure",
                        message,
                        "failure" to failure.javaClass.name,
                    )
                    if (request == epoch) {
                        stop()
                        error = context.getString(R.string.audio_play_failed)
                    }
                }
            }
    }

    /** Reading changes, navigation and interruptions invalidate pending audio too. */
    override fun stop() {
        activeMessage?.let {
            MessageAudioQualification.emit("speech_stopped", it, "state" to state.name)
        }
        epoch++
        rendering?.cancel()
        rendering = null
        try {
            player?.close()
        } finally {
            player = null
            focusRequest?.let { audio.abandonAudioFocusRequest(it) }
            focusRequest = null
        }
        playingWord = null
        activeMessage = null
        if (ready) state = SpeechState.READY
    }

    override fun close() {
        if (closed) return
        closed = true
        stop()
        preparation?.cancel()
        preparation = null
        context.unregisterReceiver(noisy)
        pair.close()
        audioLifetime.close()
    }
}
