package co.fallsoft.vipi

import org.junit.Assert.*
import org.junit.Test

class MackerelSchoolTest {
    @Test fun stableSceneVariesBetweenSessionsAndCyclesAndLeavesOpenWater() {
        for (seed in listOf(-35, 0, 1, 12, Int.MAX_VALUE)) {
            val passes = mackerelSchool(seed, 2)
            assertEquals(passes, mackerelSchool(seed, 2))
            assertNotEquals(passes, mackerelSchool(seed, 3))
            assertNotEquals(passes, mackerelSchool(seed + 1, 2))
            assertNotEquals(passes[0].right, passes[1].right)
            assertEquals(2, passes.count { 7f in it.start..(it.start + it.duration) })
            assertFalse(passes.any { 62f in it.start..(it.start + it.duration) })
            assertTrue(passes.all { it.start >= 0f && it.start + it.duration < 92f &&
                it.width in .2f.. .75f && it.lane in .2f.. .86f })
        }
    }
}
