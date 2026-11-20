package co.fallsoft.vipi

import android.content.Context
import android.util.AtomicFile
import androidx.annotation.Keep
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** Pinned offline fallback. C state has exactly one serialized owner. */
@Keep internal object SwahiliSpeech {
    const val IDENTIFIER = "espeak-ng-699e7969-sw"
    private const val ASSETS = "speech/espeak-ng-699e7969"
    private val mutex = Mutex()
    private var ready = false
    private val voiceNames = mapOf("en" to "en", "es" to "es", "fr" to "fr", "de" to "de",
        "it" to "it", "pt" to "pt", "ja" to "ja", "ko" to "ko", "zh" to "cmn", "ar" to "ar", "sw" to "sw")
    fun supports(language: String) = language in voiceNames
    @Keep class Job {
        private val cancelled = AtomicBoolean(false)
        private val frames = AtomicInteger(0)
        fun cancel() { cancelled.set(true) }
        fun isCancelled() = cancelled.get()
        fun onFrames(count: Int) { frames.addAndGet(count) }
        fun generatedFrames() = frames.get()
    }
    init { System.loadLibrary("vipi_speech") }
    @JvmStatic private external fun prepareNative(root: String): Int
    @JvmStatic private external fun renderNative(text: ByteArray, destination: String, job: Job, language: String): IntArray
    fun identifier(language: String) = "espeak-ng-699e7969-$language"

    suspend fun prepare(context: Context, language: String = "sw"): String = mutex.withLock {
        require(supports(language))
        withContext(Dispatchers.IO) {
            if (!ready) {
                val manifest = JSONObject(context.assets.open("$ASSETS/manifest.json").bufferedReader().use { it.readText() })
                val root = File(context.noBackupFilesDir, "speech/$IDENTIFIER").apply { mkdirs() }
                val files = manifest.getJSONArray("files")
                for (index in 0 until files.length()) {
                    ensureActive()
                    val row = files.getJSONObject(index); val name = row.getString("path")
                    require(name.startsWith("espeak-ng-data/") && name.split('/').none { it in setOf("", ".", "..") })
                    val file = File(root, name)
                    fun matches() = file.isFile && file.length() == row.getLong("bytes") && file.inputStream().use { stream ->
                        val digest = MessageDigest.getInstance("SHA-256"); val buffer = ByteArray(65536)
                        while (true) { ensureActive(); val count = stream.read(buffer); if (count < 0) break; digest.update(buffer, 0, count) }
                        digest.digest().joinToString("") { "%02x".format(it) } == row.getString("sha256")
                    }
                    if (!matches()) {
                        file.parentFile!!.mkdirs(); val atomic = AtomicFile(file); val output = atomic.startWrite()
                        try {
                            context.assets.open("$ASSETS/$name").use { input ->
                                val buffer = ByteArray(65536); var total = 0L
                                while (true) { ensureActive(); val count = input.read(buffer); if (count < 0) break
                                    total += count; require(total <= row.getLong("bytes")); output.write(buffer, 0, count) }
                            }
                            atomic.finishWrite(output)
                        } catch (error: Throwable) { atomic.failWrite(output); throw error }
                        require(matches()) { "Bundled speech data failed verification" }
                    }
                    check(file.setWritable(false, true))
                }
                check(prepareNative(root.path) > 0); ready = true
            }
            identifier(language)
        }
    }
    suspend fun render(context: Context, text: String, destination: File, job: Job, language: String = "sw"): RenderedSpeech {
        require(text.isNotBlank() && '\u0000' !in text)
        prepare(context, language)
        return mutex.withLock {
            try { withContext(Dispatchers.IO) {
                ensureActive(); if (job.isCancelled()) throw CancellationException("Speech cancelled")
                suspendCancellableCoroutine { continuation ->
                    continuation.invokeOnCancellation { job.cancel() }
                    try {
                        val japanese = if (language == "ja") JapaneseSpeechReading.pronunciation(text) else null
                        val spoken = japanese?.first ?: text
                        ensureActive()
                        val result = renderNative(spoken.toByteArray(Charsets.UTF_8), destination.path, job, voiceNames.getValue(language))
                        if (job.isCancelled()) throw CancellationException("Speech cancelled")
                        val count = spoken.codePointCount(0, spoken.length)
                        val marks = buildList {
                            for (i in 2 until result.size step 3) {
                                val start = result[i]
                                val length = result[i + 1]
                                if (start !in 0 until count || length !in 1..(count - start)) continue
                                val range = spoken.offsetByCodePoints(0, start) until spoken.offsetByCodePoints(0, start + length)
                                val surface = if (japanese == null) range else japanese.second.word(range).reading ?: continue
                                val frame = result[i + 2]
                                if (frame in 0 until result[1]) add(SpeechMark(surface.first, surface.last + 1, frame))
                            }
                        }
                        val speech = RenderedSpeech(destination, result[1] * 1000.0 / result[0], result[0], 1, marks)
                        if (continuation.isActive) continuation.resume(speech) else destination.delete()
                    } catch (error: Throwable) {
                        destination.delete()
                        val failure = if (job.isCancelled()) CancellationException("Speech cancelled").apply { initCause(error) } else error
                        if (continuation.isActive) continuation.resumeWithException(failure)
                    }
                }
            } } catch (error: Throwable) { job.cancel(); destination.delete(); throw error }
        }
    }
}
