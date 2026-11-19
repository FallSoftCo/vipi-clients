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
import kotlinx.coroutines.ensureActive
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
data class RenderedSpeech(val file: File, val milliseconds: Double, val sampleRate: Int, val channels: Int, val marks: List<SpeechMark> = emptyList(), val boundaryFrames: List<Int> = emptyList(), val rejectedMarks: Int = 0)

/** One prepared native generator for one language. No network voice fallback. */
class LocalVoice(context: Context, val language: String) : AutoCloseable {
    private val application = context.applicationContext
    private val ready = CompletableDeferred<Unit>()
    private val completions = ConcurrentHashMap<String, CompletableDeferred<Unit>>()
    private val markers = ConcurrentHashMap<String, MutableList<SpeechMark>>()
    private val mutex = Mutex()
    private val tts = TextToSpeech(context.applicationContext) { status ->
        if (status == TextToSpeech.SUCCESS) ready.complete(Unit)
        else ready.completeExceptionally(OfflineVoiceUnavailable(language))
    }
    private var selected: Voice? = null
    private var bundledFallback = false
    @Volatile private var fallbackJob: SwahiliSpeech.Job? = null
    @Volatile private var closed = false
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
        if (closed) throw kotlinx.coroutines.CancellationException("Voice closed")
        if (bundledFallback) return@withContext SwahiliSpeech.identifier(language)
        try { withTimeout(15_000) { ready.await() } }
        catch (error: Exception) {
            kotlinx.coroutines.currentCoroutineContext().ensureActive()
            if (SwahiliSpeech.supports(language)) return@withContext selectBundledFallback()
            throw error
        }
        selected?.let { return@withContext it.name }
        val desired = Locale.forLanguageTag(language)
        val voice = tts.voices.orEmpty().filter {
            it.locale.language == desired.language && !it.isNetworkConnectionRequired &&
                TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED !in it.features.orEmpty()
        }.sortedWith(compareByDescending<Voice> { it.locale.toLanguageTag() == desired.toLanguageTag() }
            .thenByDescending { it.quality }.thenBy { it.name }).firstOrNull() ?: return@withContext selectBundledFallback()
        if (tts.setVoice(voice) == TextToSpeech.ERROR) return@withContext selectBundledFallback()
        tts.setSpeechRate(1.0f)
        selected = voice
        voice.name
    }
    private suspend fun selectBundledFallback(): String {
        if (!SwahiliSpeech.supports(language)) throw OfflineVoiceUnavailable(language)
        val identifier = SwahiliSpeech.prepare(application, language)
        if (closed) throw kotlinx.coroutines.CancellationException("Voice closed")
        bundledFallback = true
        return identifier
    }
    private suspend fun renderBundled(text: String, destination: File): RenderedSpeech {
        val job = SwahiliSpeech.Job(); fallbackJob = job
        try { return withTimeout(30_000) { SwahiliSpeech.render(application, text, destination, job, language) } }
        finally { if (fallbackJob === job) fallbackJob = null }
    }

    suspend fun render(text: String, destination: File): RenderedSpeech = mutex.withLock {
        require(text.isNotBlank() && text.length < TextToSpeech.getMaxSpeechInputLength())
        select()
        if (bundledFallback) return@withLock renderBundled(text, destination)
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
                val reported = markers[id].orEmpty().toList()
                // A tested file-synthesis engine/platform returned frame values
                // as text offsets. Never guess a permutation or use invalid marks.
                val valid = reported.filter { it.start >= 0 && it.end > it.start && it.end <= text.length && it.frame >= 0 && it.frame < wav.samples.size / (wav.channels * 2) }
                RenderedSpeech(destination, wav.durationMs, wav.sampleRate, wav.channels, valid, rejectedMarks = reported.size - valid.size)
            }
        } catch (error: Exception) {
            withContext(kotlinx.coroutines.NonCancellable + Dispatchers.Main.immediate) { tts.stop() }
            destination.delete()
            kotlinx.coroutines.currentCoroutineContext().ensureActive()
            if (SwahiliSpeech.supports(language) && (error is OfflineVoiceUnavailable || error is kotlinx.coroutines.TimeoutCancellationException)) {
                withContext(Dispatchers.Main.immediate) { selectBundledFallback() }
                return@withLock renderBundled(text, destination)
            }
            throw error
        } finally { completions.remove(id); markers.remove(id) }
    }

    override fun close() {
        closed = true; fallbackJob?.cancel()
        tts.stop(); tts.shutdown()
        ready.cancel(); completions.values.forEach { it.cancel() }; completions.clear(); markers.clear()
    }
}

/** Owns the distinct requested voices; warm-up renders are silent, never played.
 * A practice-only session passes the same language in both positions. */
class LocalSpeechPair(context: Context, val source: String, val target: String) : AutoCloseable {
    private val voices = setOf(source, target).associateWith { LocalVoice(context, it) }
    private val mutex = Mutex()
    private var prepared = false
    private var voiceIDs = emptyMap<String, String>()
    private val cache = PrivateSpeechCache.register(context, files = true) { voices.values.forEach { it.close() } }

    suspend fun prepare(warmups: Map<String, String>) = cache.track { mutex.withLock {
        if (prepared) return@withLock
        voiceIDs = voices.mapValues { it.value.select() }
        for ((language, voice) in voices) {
            val temp = cache.access { File.createTempFile("warm-", ".wav", it) }
            try { voice.render(requireNotNull(warmups[language]), temp) } finally { temp.delete() }
        }
        // An advertised offline system voice can fail its first actual synthesis.
        voiceIDs = voices.mapValues { it.value.select() }
        prepared = true
    } }

    /** Render native voices, normalize their PCM formats, then play one joined file. */
    suspend fun render(spans: List<SpeechSpan>): RenderedSpeech = cache.track { mutex.withLock {
        check(prepared)
        require(spans.isNotEmpty() && spans.sumOf { it.text.length } <= 16_384)
        val normalized = mutableListOf<SpeechSpan>()
        for (span in spans) {
            require(span.language in voices)
            if (span.text.all { it.isWhitespace() || it in ".,!?;:。！？、؛،" }) {
                if (normalized.isNotEmpty()) normalized[normalized.lastIndex] = normalized.last().copy(text = normalized.last().text + span.text)
            } else if (normalized.lastOrNull()?.language == span.language) {
                normalized[normalized.lastIndex] = normalized.last().copy(text = normalized.last().text + span.text)
            } else normalized += span
        }
        val identity = "pcm24-mono-v1\u0000" + normalized.joinToString("\u0000") { it.language + "\u0000" + voiceIDs[it.language] + "\u0000" + it.text }
        val hash = MessageDigest.getInstance("SHA-256").digest(identity.toByteArray()).joinToString("") { "%02x".format(it) }
        val result = cache.access { File(it, "$hash.wav") }
        if (result.exists()) {
            val wave = withContext(Dispatchers.IO) { PcmWave.read(result) }
            return@withLock RenderedSpeech(result, wave.durationMs, wave.sampleRate, wave.channels)
        }
        // Chunk boundaries can isolate punctuation between spoken text. It is
        // a separator, not a missing voice/render failure: retain a short PCM
        // pause so streaming continues to the genuine following utterance.
        if (normalized.isEmpty()) {
            val temporary = cache.access { File.createTempFile("pause-", ".wav", it) }
            try {
                withContext(Dispatchers.IO) { PcmWave(24_000, 1, ByteArray(4_800)).write(temporary) }
                cache.access { check(temporary.renameTo(result)) }
            } finally { temporary.delete() }
            return@withLock RenderedSpeech(result, 100.0, 24_000, 1)
        }
        val pieces = mutableListOf<File>()
        try {
            for (span in normalized) {
                val temp = cache.access { File.createTempFile("span-", ".wav", it) }
                pieces += temp
                voices.getValue(span.language).render(span.text, temp)
            }
            withContext(Dispatchers.IO) {
                val waves = pieces.map { PcmNormalization.normalize(PcmWave.read(it)) { ensureActive() } }
                require(waves.isNotEmpty())
                val total = waves.sumOf { it.samples.size }
                require(total <= 32 * 1024 * 1024)
                val bytes = ByteArray(total)
                var offset = 0
                val boundaries = mutableListOf<Int>()
                for (wave in waves) { if (offset > 0) boundaries += offset / (wave.channels * 2); wave.samples.copyInto(bytes, offset); offset += wave.samples.size }
                val joined = PcmWave(waves.first().sampleRate, waves.first().channels, bytes)
                val temporary = cache.access { File.createTempFile("joined-", ".wav", it) }
                try { joined.write(temporary); cache.access { check(temporary.renameTo(result)) } } finally { temporary.delete() }
                // Only disposable synthesized audio, never original messages.
                cache.access { root ->
                  var size = root.listFiles().orEmpty().sumOf { it.length() }
                  for (old in root.listFiles().orEmpty().filter { it != result && it.name.matches(Regex("[a-f0-9]{64}\\.wav")) }.sortedBy { it.lastModified() }) {
                    if (size <= 64 * 1024 * 1024) break
                    val length = old.length(); if (old.delete()) size -= length
                  }
                }
                RenderedSpeech(result, joined.durationMs, joined.sampleRate, joined.channels, boundaryFrames = boundaries)
            }
        } finally { pieces.forEach { it.delete() } }
    } }
    override fun close() { cache.close() }
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
