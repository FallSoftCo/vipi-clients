package co.fallsoft.vipi

import kotlin.math.abs
import kotlin.math.roundToInt
import kotlin.math.sqrt

/** UTF-16 ranges in the spoken script, frame offsets in the unmodified PCM. */
internal data class DeepCue(val frame: Int, val range: IntRange?, val native: Boolean = false)

internal object DeepSpeechTiming {
    fun cues(text: String, words: List<IntRange>, wave: PcmWave): List<DeepCue> {
        val frames = wave.samples.size / (2 * wave.channels)
        if (words.isEmpty() || frames == 0) return emptyList()
        val sound = audibleRuns(wave, frames)
        if (sound.isEmpty()) return emptyList()
        fun lexical(start: Int, end: Int) =
            text.substring(start, end).codePoints().anyMatch(Character::isLetterOrDigit)
        val marks =
            wave.marks.filter {
                it.frame in 0 until frames &&
                    it.start in 0 until it.end &&
                    it.end <= text.length &&
                    lexical(it.start, it.end)
            }
        // Duplicate or reversed offsets cannot serve as independent observations.
        fun ordered(a: SpeechMark, b: SpeechMark) = a.end <= b.start && a.frame < b.frame
        val candidates = marks.sortedBy { it.start }
        val anchors =
            candidates
                .filterIndexed { i, mark ->
                    (i == 0 || ordered(candidates[i - 1], mark)) &&
                        (i == candidates.lastIndex || ordered(mark, candidates[i + 1]))
                }
                .takeIf { kept -> kept.zipWithNext().all { (a, b) -> ordered(a, b) } }
                .orEmpty()
        val complete =
            anchors.isNotEmpty() &&
                !lexical(0, anchors.first().start) &&
                !lexical(anchors.last().end, text.length) &&
                anchors.zipWithNext().all { (a, b) -> !lexical(a.end, b.start) }
        val result =
            if (complete) anchors.map { DeepCue(it.frame, it.start until it.end, true) }
            else interpolate(text, words, sound, anchors)
        // Clear active ink when the recorded voice is quiet. An engine can
        // place a true word onset just inside the lead-in to a voice segment.
        val changes = result.toMutableList()
        for (run in sound) changes += DeepCue(run.last + 1, null)
        return changes.sortedWith(compareBy<DeepCue> { it.frame }.thenBy { it.range != null })
    }

    private fun interpolate(
        text: String,
        words: List<IntRange>,
        runs: List<IntRange>,
        native: List<SpeechMark>,
    ): List<DeepCue> {
        // Map a fraction onto voiced frames. Long pauses and the WAV's leading
        // and trailing silence consume no share of a word's duration.
        fun position(frame: Int) = runs.sumOf {
            (frame - it.first).coerceIn(0, it.last - it.first + 1)
        }
        fun frameAt(position: Int): Int {
            var left = position
            for (run in runs) {
                val length = run.last - run.first + 1
                if (left < length) return run.first + left
                left -= length
            }
            return runs.last().last
        }
        val weight = DoubleArray(words.size + 1)
        val times = IntArray(words.size + 1) { -1 }
        val measured = BooleanArray(words.size)
        for ((i, range) in words.withIndex()) {
            // A longer word generally takes more time, but not one syllable per letter.
            weight[i + 1] =
                weight[i] + sqrt(text.codePointCount(range.first, range.last + 1).toDouble())
            native
                .singleOrNull { it.start == range.first && it.end <= range.last + 1 }
                ?.let {
                    times[i] = it.frame
                    measured[i] = true
                }
        }
        if (times[0] < 0) times[0] = runs.first().first
        times[words.size] = maxOf(runs.last().last + 1, times.max() + 1)
        val gaps = runs.drop(1).map { it.first }
        val fixed = times.indices.filter { times[it] >= 0 }
        for ((lo, hi) in fixed.zipWithNext()) {
            var start = lo
            fun predict(i: Int): Int {
                val fraction = (weight[i] - weight[start]) / (weight[hi] - weight[start])
                return frameAt(
                    (position(times[start]) +
                            fraction * (position(times[hi]) - position(times[start])))
                        .roundToInt()
                )
            }
            // A material pause near a written clause boundary is stronger
            // evidence for the next word than proportional timing alone.
            for (i in lo + 1 until hi) {
                val punctuation = text.substring(words[i - 1].last + 1, words[i].first)
                if (punctuation.none { it in ".,!?;:،؛。！？、，：；…\n" }) continue
                val predicted = predict(i)
                val gap =
                    gaps
                        .filter { it > times[start] && it < times[hi] }
                        .minByOrNull { abs(it - predicted) } ?: continue
                if (
                    abs(position(gap) - position(predicted)) >
                        (position(times[hi]) - position(times[start])) / 5
                )
                    continue
                val end = position(gap)
                for (j in start + 1 until i) {
                    val share = (weight[j] - weight[start]) / (weight[i] - weight[start])
                    times[j] =
                        frameAt(
                            (position(times[start]) + share * (end - position(times[start])))
                                .roundToInt()
                        )
                }
                times[i] = gap
                start = i
            }
            for (i in start + 1 until hi) times[i] = predict(i)
        }
        return words.indices.map { DeepCue(times[it], words[it], measured[it]) }
    }

    private fun audibleRuns(wave: PcmWave, frames: Int): List<IntRange> {
        val step = maxOf(1, wave.sampleRate / 100) // 10 ms mean absolute amplitude.
        val levels =
            IntArray((frames + step - 1) / step) { block ->
                val first = block * step * wave.channels
                val last = minOf((block + 1) * step, frames) * wave.channels
                var sum = 0L
                for (sample in first until last) {
                    val i = sample * 2
                    sum +=
                        abs(
                            (wave.samples[i + 1].toInt() shl 8) or (wave.samples[i].toInt() and 255)
                        )
                }
                (sum / (last - first)).toInt()
            }
        val peak = levels.max()
        if (peak == 0) return emptyList()
        val threshold = maxOf(1, peak / 45)
        return buildList {
            var first = -1
            var last = -1
            for (i in levels.indices) if (levels[i] >= threshold) {
                if (first < 0) first = i
                else if (i - last > 16) {
                    add(first * step until (last + 1) * step)
                    first = i
                }
                last = i
            }
            add(first * step until minOf((last + 1) * step, frames))
        }
    }
}
