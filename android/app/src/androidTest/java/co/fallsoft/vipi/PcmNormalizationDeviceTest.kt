package co.fallsoft.vipi

import org.junit.Assert.*
import org.junit.Test
import kotlin.math.*

class PcmNormalizationDeviceTest {
    private fun tone(rate: Int, frequency: Double, channels: Int = 1, opposite: Boolean = false): PcmWave {
        val data = ByteArray(rate / 2 * channels * 2)
        for (frame in 0 until rate / 2) for (channel in 0 until channels) {
            val sample = (12000 * sin(2 * Math.PI * frequency * frame / rate) * if (opposite && channel == 1) -1 else 1).roundToInt()
            val at = (frame * channels + channel) * 2; data[at] = sample.toByte(); data[at + 1] = (sample shr 8).toByte()
        }
        return PcmWave(rate, channels, data)
    }
    private fun values(wave: PcmWave) = DoubleArray(wave.samples.size / 2) { index ->
        ((wave.samples[index * 2].toInt() and 255) or (wave.samples[index * 2 + 1].toInt() shl 8)).toShort().toDouble()
    }
    private fun rms(wave: PcmWave): Double {
        val samples = values(wave).drop(200).dropLast(200); return sqrt(samples.sumOf { it * it } / samples.size)
    }
    @Test fun preservesSpeechBandDurationAndStereoDownmixAcrossNativeRates() {
        for (rate in listOf(8000, 16000, 22050, 24000, 44100, 48000, 96000)) {
            val converted = PcmNormalization.normalize(tone(rate, 440.0, 2))
            assertEquals(24000, converted.sampleRate); assertEquals(1, converted.channels); assertEquals(24000, converted.samples.size)
            assertEquals(12000 / sqrt(2.0), rms(converted), 120.0)
            val actual = values(converted)
            val error = sqrt((200 until actual.size - 200).sumOf { index ->
                val difference = actual[index] - 12000 * sin(2 * Math.PI * 440 * index / 24000); difference * difference
            } / (actual.size - 400))
            assertTrue("Rate $rate changed pitch or timing: RMS $error", error < 40)
            val silence = PcmNormalization.normalize(tone(rate, 440.0, 2, opposite = true))
            assertTrue(values(silence).all { abs(it) <= 1 })
        }
    }
    @Test fun attenuatesAboveNyquistBeforeDownsamplingAndHonorsCancellation() {
        for (rate in listOf(48000, 96000)) {
            val speech = rms(PcmNormalization.normalize(tone(rate, 1000.0)))
            val rejected = rms(PcmNormalization.normalize(tone(rate, 18000.0)))
            assertTrue("Aliased high frequency at $rate: $rejected/$speech", rejected < speech * .01)
        }
        var checks = 0
        try { PcmNormalization.normalize(tone(22050, 440.0)) { if (++checks == 3) throw kotlinx.coroutines.CancellationException() }; fail() }
        catch (_: kotlinx.coroutines.CancellationException) { assertEquals(3, checks) }
    }
}
