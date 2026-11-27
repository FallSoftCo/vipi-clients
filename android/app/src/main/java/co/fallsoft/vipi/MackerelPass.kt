package co.fallsoft.vipi

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.saveable.listSaver
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import kotlin.random.Random

// Keep the same school and phase across Chats, conversations and Activity recreation.
internal class WaterClock(val seed: Int, elapsed: Float) {
    var seconds by mutableFloatStateOf(elapsed)
}

private val waterSaver =
    listSaver<WaterClock, Any>(
        save = { listOf(it.seed, it.seconds) },
        restore = { WaterClock(it[0] as Int, it[1] as Float) },
    )

@Composable
internal fun rememberWaterClock(): WaterClock =
    rememberSaveable(saver = waterSaver) {
        WaterClock(Random.nextInt(), 7f)
    }

internal data class MackerelPass(
    val start: Float,
    val duration: Float,
    val right: Boolean,
    val width: Float,
    val lane: Float,
    val sway: Float,
    val opacity: Float,
    val tailRate: Float = 3.7f,
    val tailPhase: Float = 0f,
)

// Bounded windows leave quiet stretches between groups. The first pair travels in opposite
// directions.
private val passWindows =
    listOf(
        MackerelPass(0f, 23f, true, .65f, .67f, .018f, 1f),
        MackerelPass(2f, 19f, false, .43f, .39f, -.022f, .72f),
        MackerelPass(27f, 18f, false, .58f, .76f, -.026f, .92f),
        MackerelPass(34f, 22f, true, .32f, .31f, .019f, .58f),
        MackerelPass(46f, 13f, false, .39f, .54f, .033f, .65f),
        MackerelPass(66f, 20f, true, .5f, .49f, -.029f, .86f),
        MackerelPass(72f, 15f, false, .29f, .79f, .023f, .53f),
    )

internal fun mackerelSchool(seed: Int, cycle: Int): List<MackerelPass> {
    val random = Random(seed.toLong() xor (cycle.toLong() * -7046029254386353131L))
    fun vary(amplitude: Float) = (random.nextFloat() * 2f - 1f) * amplitude
    val mirror = random.nextBoolean()
    return passWindows.mapIndexed { index, pass ->
        pass.copy(
            start = (pass.start + vary(1.1f)).coerceAtLeast(0f),
            duration = pass.duration * (1f + vary(.07f)),
            right = if (index < 2) pass.right xor mirror else random.nextBoolean(),
            width = pass.width * (1f + vary(.12f)),
            lane = pass.lane + vary(.045f),
            sway = pass.sway * (1f + vary(.3f)),
            opacity = pass.opacity * (.92f + random.nextFloat() * .08f),
            tailRate = 3.7f + vary(1.0f),
            tailPhase = random.nextFloat() * 6.28f,
        )
    }
}
