package co.fallsoft.vipi

import java.util.concurrent.ConcurrentHashMap
import kotlin.math.*

/**
 * PCM16 conversion for one native player: mono, 24 kHz. Windowed-sinc low-pass filtering precedes
 * decimation; interpolation alone would alias higher-rate voices.
 */
internal object PcmNormalization {
    private const val RATE = 24000
    private const val PHASES = 256

    private data class Kernel(val radius: Int, val weights: Array<DoubleArray>)

    private val kernels = ConcurrentHashMap<Int, Kernel>()

    private fun kernel(rate: Int): Kernel =
        kernels.getOrPut(rate) {
            val radius = ceil(24.0 * max(1.0, rate.toDouble() / RATE)).toInt()
            val cutoff = min(1.0, RATE.toDouble() / rate) * .95
            Kernel(
                radius,
                Array(PHASES) { phase ->
                    val values =
                        DoubleArray(radius * 2) { index ->
                            val x = index - radius + 1 - phase.toDouble() / PHASES
                            if (abs(x) >= radius) 0.0
                            else {
                                val z = Math.PI * x * cutoff
                                val sinc = if (abs(z) < 1e-12) 1.0 else sin(z) / z
                                cutoff *
                                    sinc *
                                    (.42 +
                                        .5 * cos(Math.PI * x / radius) +
                                        .08 * cos(2 * Math.PI * x / radius))
                            }
                        }
                    val total = values.sum()
                    require(total.isFinite() && total > 0)
                    values.apply { indices.forEach { this[it] /= total } }
                },
            )
        }

    fun normalize(input: PcmWave, checkCancelled: () -> Unit = {}): PcmWave {
        require(input.sampleRate in 8000..96000 && input.channels in 1..2)
        require(input.samples.isNotEmpty() && input.samples.size % (input.channels * 2) == 0)
        if (input.sampleRate == RATE && input.channels == 1) {
            checkCancelled()
            return input
        }
        val frames = input.samples.size / (2 * input.channels)
        val count = (frames.toDouble() * RATE / input.sampleRate).roundToLong()
        require(count in 1..16_777_216)
        val result = ByteArray(count.toInt() * 2)
        fun mono(index: Int): Double {
            val offset = index.coerceIn(0, frames - 1) * input.channels * 2
            fun sample(at: Int) =
                ((input.samples[at].toInt() and 255) or (input.samples[at + 1].toInt() shl 8))
                    .toShort()
                    .toInt()
            return if (input.channels == 1) sample(offset).toDouble()
            else (sample(offset) + sample(offset + 2)) / 2.0
        }
        val filter = if (input.sampleRate == RATE) null else kernel(input.sampleRate)
        for (index in 0 until count.toInt()) {
            if (index % 1024 == 0) checkCancelled()
            val value =
                if (filter == null) mono(index)
                else {
                    val position = index.toDouble() * input.sampleRate / RATE
                    var base = floor(position).toInt()
                    var phase = ((position - base) * PHASES).roundToInt()
                    if (phase == PHASES) {
                        base++
                        phase = 0
                    }
                    val weights = filter.weights[phase]
                    var sum = 0.0
                    for (tap in weights.indices) sum +=
                        mono(base + tap - filter.radius + 1) * weights[tap]
                    sum
                }
            val quantized = value.roundToInt().coerceIn(-32768, 32767)
            result[index * 2] = quantized.toByte()
            result[index * 2 + 1] = (quantized shr 8).toByte()
        }
        checkCancelled()
        return PcmWave(RATE, 1, result)
    }
}
