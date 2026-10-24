package co.fallsoft.vipi

import android.content.Context
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.speech.tts.Voice
import co.fallsoft.vipi.core.SpeechSpan
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.MessageDigest
import java.util.Locale
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.Collections

class OfflineVoiceUnavailable(val language: String) : Exception("Offline voice unavailable")
data class SpeechMark(val start: Int, val end: Int, val frame: Int)
data class RenderedSpeech(val file: File, val milliseconds: Double, val sampleRate: Int, val channels: Int, val marks: List<SpeechMark> = emptyList())

/** One prepared native generator for one language. No network voice fallback. */
class LocalVoice(context: Context, val language: String) : AutoCloseable {
    private val ready = CompletableDeferred<Unit>()
    private val completions = ConcurrentHashMap<String, CompletableDeferred<Unit>>()
    private val markers = ConcurrentHashMap<String, MutableList<SpeechMark>>()
    private val mutex = Mutex()
    private val tts = TextToSpeech(context.applicationContext) { status ->
        if (status == TextToSpeech.SUCCESS) ready.complete(Unit)
        else ready.completeExceptionally(OfflineVoiceUnavailable(language))
    }
    private var selected: Voice? = null
    init {
        tts.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(id: String) = Unit
            override fun onDone(id: String) { completions.remove(id)?.complete(Unit) }
            @Deprecated("Legacy callback") override fun onError(id: String) { onError(id, TextToSpeech.ERROR) }
            override fun onError(id: String, code: Int) { completions.remove(id)?.completeExceptionally(OfflineVoiceUnavailable(language)) }
            override fun onStop(id: String, interrupted: Boolean) { completions.remove(id)?.cancel() }
            override fun onRangeStart(id: String, start: Int, end: Int, frame: Int) {
                markers[id]?.add(SpeechMark(start, end, frame))
            }
        })
    }

    suspend fun select(): String = withContext(Dispatchers.Main.immediate) {
        withTimeout(15_000) { ready.await() }
        selected?.let { return@withContext it.name }
        val desired = Locale.forLanguageTag(language)
        val voice = tts.voices.orEmpty().filter {
            it.locale.language == desired.language && !it.isNetworkConnectionRequired &&
                TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED !in it.features.orEmpty()
        }.sortedWith(compareByDescending<Voice> { it.locale.toLanguageTag() == desired.toLanguageTag() }
            .thenByDescending { it.quality }.thenBy { it.name }).firstOrNull() ?: throw OfflineVoiceUnavailable(language)
        if (tts.setVoice(voice) == TextToSpeech.ERROR) throw OfflineVoiceUnavailable(language)
        tts.setSpeechRate(1.0f)
        selected = voice
        voice.name
    }

    suspend fun render(text: String, destination: File): RenderedSpeech = mutex.withLock {
        require(text.isNotBlank() && text.length < TextToSpeech.getMaxSpeechInputLength())
        select()
        val id = UUID.randomUUID().toString()
        val done = CompletableDeferred<Unit>()
        completions[id] = done
        markers[id] = Collections.synchronizedList(mutableListOf())
        try {
            withContext(Dispatchers.Main.immediate) {
                if (tts.synthesizeToFile(text, Bundle(), destination, id) == TextToSpeech.ERROR) throw OfflineVoiceUnavailable(language)
            }
            withTimeout(30_000) { done.await() }
            withContext(Dispatchers.IO) {
                val wav = PcmWave.read(destination)
                RenderedSpeech(destination, wav.samples.size * 1000.0 / (wav.sampleRate * wav.channels * 2), wav.sampleRate, wav.channels, markers[id].orEmpty().toList())
            }
        } catch (error: Exception) {
            withContext(kotlinx.coroutines.NonCancellable + Dispatchers.Main.immediate) { tts.stop() }
            destination.delete()
            throw error
        } finally { completions.remove(id); markers.remove(id) }
    }

    override fun close() {
        tts.stop(); tts.shutdown()
        ready.cancel(); completions.values.forEach { it.cancel() }; completions.clear(); markers.clear()
    }
}

/** A pair owns two generators; warm-up renders are silent, never played. */
class LocalSpeechPair(context: Context, val source: String, val target: String) : AutoCloseable {
    private val root = File(context.cacheDir, "vipi-speech").apply { mkdirs() }
    private val voices = mapOf(source to LocalVoice(context, source), target to LocalVoice(context, target))
    private val mutex = Mutex()
    private var prepared = false
    private var voiceIDs = emptyMap<String, String>()

    suspend fun prepare(warmups: Map<String, String>) = mutex.withLock {
        if (prepared) return@withLock
        require(source != target)
        voiceIDs = voices.mapValues { it.value.select() }
        for ((language, voice) in voices) {
            val temp = File.createTempFile("warm-", ".wav", root)
            try { voice.render(requireNotNull(warmups[language]), temp) } finally { temp.delete() }
        }
        prepared = true
    }

    /** Fully renders one PCM file before playback; latency is measured by QA.
     * Different PCM formats fail explicitly until a qualified resampler exists.
     */
    suspend fun render(spans: List<SpeechSpan>): RenderedSpeech = mutex.withLock {
        check(prepared)
        require(spans.isNotEmpty() && spans.sumOf { it.text.length } <= 16_384)
        val normalized = mutableListOf<SpeechSpan>()
        for (span in spans) {
            require(span.language in voices)
            if (span.text.isBlank()) {
                if (normalized.isNotEmpty()) normalized[normalized.lastIndex] = normalized.last().copy(text = normalized.last().text + span.text)
            } else if (normalized.lastOrNull()?.language == span.language) {
                normalized[normalized.lastIndex] = normalized.last().copy(text = normalized.last().text + span.text)
            } else normalized += span
        }
        val identity = normalized.joinToString("\u0000") { it.language + "\u0000" + voiceIDs[it.language] + "\u0000" + it.text }
        val hash = MessageDigest.getInstance("SHA-256").digest(identity.toByteArray()).joinToString("") { "%02x".format(it) }
        val result = File(root, "$hash.wav")
        if (result.exists()) {
            val wave = withContext(Dispatchers.IO) { PcmWave.read(result) }
            return@withLock RenderedSpeech(result, wave.durationMs, wave.sampleRate, wave.channels)
        }
        val pieces = mutableListOf<File>()
        try {
            for (span in normalized) {
                val temp = File.createTempFile("span-", ".wav", root)
                pieces += temp
                voices.getValue(span.language).render(span.text, temp)
            }
            withContext(Dispatchers.IO) {
                val waves = pieces.map(PcmWave::read)
                require(waves.isNotEmpty() && waves.all { it.sampleRate == waves.first().sampleRate && it.channels == waves.first().channels }) { "Voice PCM formats differ" }
                val total = waves.sumOf { it.samples.size }
                require(total <= 32 * 1024 * 1024)
                val bytes = ByteArray(total)
                var offset = 0
                for (wave in waves) { wave.samples.copyInto(bytes, offset); offset += wave.samples.size }
                val joined = PcmWave(waves.first().sampleRate, waves.first().channels, bytes)
                val temporary = File.createTempFile("joined-", ".wav", root)
                try { joined.write(temporary); check(temporary.renameTo(result)) } finally { temporary.delete() }
                // Only disposable synthesized audio, never original messages.
                var size = root.listFiles().orEmpty().sumOf { it.length() }
                for (old in root.listFiles().orEmpty().filter { it != result && it.name.matches(Regex("[a-f0-9]{64}\\.wav")) }.sortedBy { it.lastModified() }) {
                    if (size <= 64 * 1024 * 1024) break
                    val length = old.length(); if (old.delete()) size -= length
                }
                RenderedSpeech(result, joined.durationMs, joined.sampleRate, joined.channels)
            }
        } finally { pieces.forEach { it.delete() } }
    }
    override fun close() { voices.values.forEach { it.close() } }
}

internal data class PcmWave(val sampleRate: Int, val channels: Int, val samples: ByteArray) {
    val durationMs get() = samples.size * 1000.0 / (sampleRate * channels * 2)
    fun write(file: File) {
        val header = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
        header.put("RIFF".toByteArray()).putInt(36 + samples.size).put("WAVEfmt ".toByteArray()).putInt(16)
            .putShort(1).putShort(channels.toShort()).putInt(sampleRate).putInt(sampleRate * channels * 2)
            .putShort((channels * 2).toShort()).putShort(16).put("data".toByteArray()).putInt(samples.size)
        file.outputStream().use { it.write(header.array()); it.write(samples); it.fd.sync() }
    }
    companion object {
        fun read(file: File): PcmWave {
            require(file.length() in 44..33_554_432)
            val bytes = file.readBytes()
            val b = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
            require(String(bytes, 0, 4) == "RIFF" && String(bytes, 8, 4) == "WAVE")
            var offset = 12; var rate = 0; var channels = 0; var data: ByteArray? = null
            while (offset + 8 <= bytes.size) {
                val kind = String(bytes, offset, 4)
                val size = b.getInt(offset + 4)
                require(size >= 0 && size <= bytes.size - offset - 8)
                if (kind == "fmt ") {
                    require(size >= 16 && b.getShort(offset + 8).toInt() == 1 && b.getShort(offset + 22).toInt() == 16)
                    channels = b.getShort(offset + 10).toInt(); rate = b.getInt(offset + 12)
                    require(channels in 1..2 && rate in 8_000..96_000)
                } else if (kind == "data") data = bytes.copyOfRange(offset + 8, offset + 8 + size)
                offset += 8 + size + size % 2
            }
            require(rate > 0 && channels > 0 && data != null && data.isNotEmpty() && data.size % (channels * 2) == 0)
            return PcmWave(rate, channels, data)
        }
    }
}
