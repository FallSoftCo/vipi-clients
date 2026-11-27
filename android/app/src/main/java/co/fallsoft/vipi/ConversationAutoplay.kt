package co.fallsoft.vipi

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import java.util.ArrayDeque
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

/**
 * Foreground conversation-owned playback. Only durable NEW-message events are offered here; history
 * loading/cache changes never enqueue speech.
 */
internal class ConversationAutoplay(
    private val translation: ConversationTranslation,
    val speech: ConversationSpeech,
    private val scope: CoroutineScope,
    private val voiceHelp: () -> Unit,
) : AutoCloseable {
    private data class Message(
        val id: String,
        val load: () -> String?,
        var loadedText: String? = null,
    )

    private val queue = ArrayDeque<Message>()
    private val offered = mutableSetOf<String>()
    private var automatic: Job? = null
    private var manual: Job? = null
    private var currentAutomatic: Message? = null
    private var closed = false
    private var generation = 0L
    // Retained by the conversation, not the recycled row or next speech job.
    val failures = mutableStateMapOf<String, String>()
    private var seenInterruption = speech.interruption

    private fun consumeInterruption() {
        if (speech.interruption != seenInterruption) {
            seenInterruption = speech.interruption
            enabled = false
            stopAll()
        }
    }

    var enabled by mutableStateOf(false)
        private set

    var speakingFace by mutableStateOf<FullMessageTranslation?>(null)
        private set

    var manualMessage by mutableStateOf<String?>(null)
        private set

    private val voiceObservation =
        scope.launch(Dispatchers.Main.immediate) {
            snapshotFlow { speech.state to enabled }
                .collect { (state, _) ->
                    if (
                        !closed &&
                            state == SpeechState.UNAVAILABLE &&
                            (enabled || automatic?.isActive == true || manual?.isActive == true)
                    ) {
                        (manualMessage ?: currentAutomatic?.id)?.let {
                            failures[it] = speech.failureMessage()
                        }
                        enabled = false
                        stopAll()
                        voiceHelp()
                    }
                }
        }
    private val interruptionObservation =
        scope.launch(Dispatchers.Main.immediate) {
            snapshotFlow { speech.interruption }.collect { consumeInterruption() }
        }

    fun setAutoplayEnabled(value: Boolean) {
        consumeInterruption()
        if (closed) return
        // OFF is also an explicit stop/cancel boundary for manual playback,
        // including a pending request while autoplay was already disabled.
        if (!value) {
            enabled = false
            stopAll()
            return
        }
        if (enabled) return
        if (value && speech.state == SpeechState.UNAVAILABLE) {
            enabled = false
            stopAll()
            voiceHelp()
            return
        }
        enabled = value
        queue.clear()
        offered.clear()
        speech.showMutedVolumeControl()
    }

    fun offer(id: String, text: String) = offerStored(id) { text }

    fun offerStored(id: String, load: () -> String?) {
        MessageAudioQualification.emit(
            "offer",
            id,
            "enabled" to enabled,
            "closed" to closed,
            "duplicate" to (id in offered),
        )
        if (closed || !enabled || !offered.add(id)) return
        queue.addLast(Message(id, load))
        drain()
    }

    private suspend fun play(
        message: Message,
        automatic: Boolean,
        presented: FullMessageTranslation? = null,
    ) {
        MessageAudioQualification.emit("translation_wait", message.id, "automatic" to automatic)
        val text = kotlinx.coroutines.withContext(Dispatchers.IO) { message.load() } ?: return
        kotlinx.coroutines.currentCoroutineContext().ensureActive()
        message.loadedText = text
        val value =
            presented
                ?: translation.resolve(
                    message.id,
                    text,
                    retry =
                        !automatic &&
                            translation.state(message.id, text)?.phase ==
                                MessageTranslationPhase.FAILED,
                )
        if (value.words?.isEmpty() == true || value.practiceText.isBlank()) return
        MessageAudioQualification.emit(
            "translation_ready",
            message.id,
            "automatic" to automatic,
            "practice_language" to value.practiceLanguage,
        )
        MessageAudioQualification.emit("voice_wait", message.id, "state" to speech.state.name)
        if (speech.state == SpeechState.PREPARING)
            snapshotFlow { speech.state }.first { it != SpeechState.PREPARING }
        MessageAudioQualification.emit("voice_state", message.id, "state" to speech.state.name)
        if (speech.state == SpeechState.UNAVAILABLE) {
            speech.error?.let { failures[message.id] = it }
            enabled = false
            queue.clear()
            offered.clear()
            voiceHelp()
            return
        }
        // A model/voice await may finish before the snapshot observer handles
        // an OS interruption. Consume it synchronously before requesting sound.
        consumeInterruption()
        kotlinx.coroutines.currentCoroutineContext().ensureActive()
        if (!automatic) speech.showMutedVolumeControl()
        speakingFace = value
        speech.toggleTranslation(message.id, value)
        snapshotFlow { speech.activeMessage }.first { it != message.id }
        speech.error?.let { failures[message.id] = it }
            ?: if (!automatic) failures.remove(message.id) else Unit
    }

    private fun drain() {
        consumeInterruption()
        if (!enabled || closed || automatic?.isActive == true || manual?.isActive == true) return
        automatic =
            scope.launch(Dispatchers.Main.immediate) {
                val token = generation
                while (
                    enabled &&
                        !closed &&
                        generation == token &&
                        speech.interruption == seenInterruption &&
                        queue.isNotEmpty()
                ) {
                    val message = queue.removeFirst()
                    currentAutomatic = message
                    try {
                        play(message, automatic = true)
                    } catch (cancelled: CancellationException) {
                        throw cancelled
                    } catch (failure: Exception) {
                        MessageAudioQualification.emit(
                            "auto_failure",
                            message.id,
                            "failure" to failure.javaClass.name,
                        )
                        if (
                            message.loadedText?.let { translation.state(message.id, it)?.phase } !=
                                MessageTranslationPhase.FAILED
                        )
                            failures[message.id] = speech.failureMessage()
                    } finally {
                        message.loadedText = null
                        if (generation == token) currentAutomatic = null
                    }
                }
            }
    }

    /**
     * Manual intent wins over current automatic playback; the interrupted queue item is consumed,
     * so it cannot replay after the manual request.
     */
    fun manual(id: String, text: String, presented: FullMessageTranslation? = null) {
        require(presented == null || presented.original == text)
        consumeInterruption()
        if (closed) return
        val stop =
            speech.activeMessage == id ||
                (manual?.isActive == true && manualMessage == id) ||
                (automatic?.isActive == true && currentAutomatic?.id == id)
        if (stop) {
            enabled = false
            stopAll()
            return
        }
        val token = ++generation
        automatic?.cancel()
        automatic = null
        currentAutomatic = null
        manual?.cancel()
        manual = null
        speech.stop()
        queue.removeAll { it.id == id }
        manualMessage = id
        manual =
            scope.launch(Dispatchers.Main.immediate) {
                try {
                    play(Message(id, load = { text }), automatic = false, presented = presented)
                } catch (cancelled: CancellationException) {
                    throw cancelled
                } catch (failure: Exception) {
                    MessageAudioQualification.emit(
                        "manual_failure",
                        id,
                        "failure" to failure.javaClass.name,
                    )
                    if (translation.state(id, text)?.phase != MessageTranslationPhase.FAILED)
                        failures[id] = speech.failureMessage()
                } finally {
                    if (generation == token) {
                        manualMessage = null
                        manual = null
                        if (!closed) drain()
                    }
                }
            }
    }

    private fun stopAll() {
        generation++
        automatic?.cancel()
        automatic = null
        manual?.cancel()
        manual = null
        manualMessage = null
        currentAutomatic = null
        queue.clear()
        offered.clear()
        speech.stop()
    }

    fun background() {
        enabled = false
        stopAll()
    }

    override fun close() {
        closed = true
        enabled = false
        stopAll()
        voiceObservation.cancel()
        interruptionObservation.cancel()
        failures.clear()
    }
}
