package co.fallsoft.vipi

import co.fallsoft.vipi.core.SpeechSpan
import kotlinx.coroutines.channels.SendChannel
import java.util.ArrayDeque

internal data class WordCue(val frame: Int, val word: PlayingWord?)
internal data class TimedPcm(val wave: PcmWave, val cues: List<WordCue>)
internal class PlaybackWords {
    private val changes = ArrayDeque<Pair<Long, PlayingWord?>>()
    private var written = 0L
    private var current: PlayingWord? = null
    @Synchronized fun append(piece: TimedPcm) {
        changes.addLast(written to null)
        for (cue in piece.cues) changes.addLast((written + cue.frame) to cue.word)
        written += piece.wave.samples.size / (2 * piece.wave.channels)
        changes.addLast(written to null)
    }
    @Synchronized fun at(frame: Long): PlayingWord? {
        while (changes.isNotEmpty() && changes.first.first <= frame) current = changes.removeFirst().second
        return current
    }
}

/** The same PCM heard by the listener owns its highlights. Deep never renders
 * individual words to manufacture timings missing from a sentence. */
internal class TimedSpeech(private val pair: LocalSpeechPair, private val language: String,
    private val projection: SpeechProjection?, private val fullUtterance: Boolean = false,
    private val onFirstRender: (RenderedSpeech) -> Unit = {}) {
    private var first = true
    private suspend fun render(text: String): PcmWave {
        val rendered = pair.render(listOf(SpeechSpan(text, language)))
        if (first) { first = false; onFirstRender(rendered) }
        return PcmWave.read(rendered.file)
    }

    suspend fun enqueue(piece: SpeechPiece, output: SendChannel<TimedPcm>) {
        if (piece.pauseBefore) {
            val silence = PcmWave(24_000, 1, ByteArray(24_000 * MessageSpeech.GAP_MS / 1000 * 2))
            output.send(TimedPcm(silence, emptyList()))
        }
        val wave = render(piece.text)
        val words = if (projection == null) emptyList() else MessageSpeech.lexicalRanges(piece.text, language)
        if (words.isEmpty()) { output.send(TimedPcm(wave, emptyList())); return }
        fun word(range: IntRange) = projection!!.word(piece.start + range.first..piece.start + range.last)
        val frames = wave.samples.size / (wave.channels * 2)
        val marks = wave.marks.filter { it.frame in 0 until frames && it.start >= 0 && it.end <= piece.text.length && it.start < it.end }
        if (fullUtterance) {
            val cues = DeepSpeechTiming.cues(piece.text, words, wave).map { WordCue(it.frame, it.range?.let(::word)) }
            output.send(TimedPcm(wave, cues))
            return
        }
        val firstFrames = words.map { range ->
            marks.firstOrNull { it.start in range || range.first in it.start until it.end }?.frame
        }
        val timestamps = firstFrames.filterNotNull()
        if (timestamps.size == words.size && timestamps.zipWithNext().all { (a, b) -> a < b }) {
            output.send(TimedPcm(wave, words.mapIndexed { i, range -> WordCue(timestamps[i], word(range)) }))
            return
        }
        for ((index, range) in words.withIndex()) {
            val start = if (index == 0) 0 else range.first
            val end = words.getOrNull(index + 1)?.first ?: piece.text.length
            val single = if (words.size == 1) wave else render(piece.text.substring(start, end))
            output.send(TimedPcm(single, listOf(WordCue(0, word(range)))))
        }
    }
}
