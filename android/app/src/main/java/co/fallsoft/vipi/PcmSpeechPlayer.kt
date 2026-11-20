package co.fallsoft.vipi

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withTimeout
import java.util.concurrent.atomic.AtomicBoolean

/** One stream for all language spans. Native backpressure bounds queued PCM. */
internal class PcmSpeechPlayer(rate: Int, private val channels: Int, attributes: AudioAttributes) : AutoCloseable {
    private val channelMask = if (channels == 1) AudioFormat.CHANNEL_OUT_MONO else AudioFormat.CHANNEL_OUT_STEREO
    private val minimum = AudioTrack.getMinBufferSize(rate, channelMask, AudioFormat.ENCODING_PCM_16BIT).also { require(it > 0) }
    private val track = AudioTrack.Builder().setAudioAttributes(attributes)
        .setAudioFormat(AudioFormat.Builder().setSampleRate(rate).setChannelMask(channelMask).setEncoding(AudioFormat.ENCODING_PCM_16BIT).build())
        .setTransferMode(AudioTrack.MODE_STREAM).setBufferSizeInBytes(minimum * 4).build()
    private val closed = AtomicBoolean(false)
    private var started = false
    private var frames = 0L
    val playedFrames get() = if (closed.get()) 0L else track.playbackHeadPosition.toLong() and 0xffffffffL
    val underruns get() = if (closed.get()) 0 else track.underrunCount
    init { check(track.state == AudioTrack.STATE_INITIALIZED) }

    suspend fun append(wave: PcmWave, onStart: suspend () -> Unit) {
        require(wave.sampleRate == track.sampleRate && wave.channels == channels)
        var offset = 0
        while (offset < wave.samples.size) {
            currentCoroutineContext().ensureActive(); check(!closed.get())
            // Prime a bounded amount before starting, then let the native output
            // apply backpressure. No independent players or inserted join gaps.
            val count = minOf(if (started) minimum else minimum * 4, wave.samples.size - offset)
            val written = track.write(wave.samples, offset, count, AudioTrack.WRITE_BLOCKING)
            check(written > 0) { "PCM output failed" }
            offset += written; frames += written / (channels * 2)
            if (!started) { track.play(); started = true; onStart() }
        }
    }
    suspend fun finish() = withTimeout(10_000) {
        while ((track.playbackHeadPosition.toLong() and 0xffffffffL) < frames) {
            currentCoroutineContext().ensureActive(); check(!closed.get()); delay(10)
        }
    }
    override fun close() {
        if (!closed.compareAndSet(false, true)) return
        if (track.playState == AudioTrack.PLAYSTATE_PLAYING) track.stop()
        track.release()
    }
}
