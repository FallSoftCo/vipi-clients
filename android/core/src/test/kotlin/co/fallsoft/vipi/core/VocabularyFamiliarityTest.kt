package co.fallsoft.vipi.core

import org.junit.Assert.*
import org.junit.Test

class VocabularyFamiliarityTest {
    @Test fun repeatedFlipsAndBackwardClockCannotClaimExtraExposure() {
        val value = VocabularyFamiliarity().observe(100)
        for (day in listOf(100, 100, 99, -1)) assertEquals(value, value.observe(day))
        assertEquals(1, value.exposureDays)
    }
    @Test fun spacedExposureGivesMoreTargetTimeAndAbsenceRestoresBeginnerPace() {
        var value = VocabularyFamiliarity()
        for (day in 100..103) value = value.observe(day)
        assertEquals(6000L, value.targetMilliseconds(103))
        for (day in 104..111) value = value.observe(day)
        assertEquals(9000L, value.targetMilliseconds(111))
        assertEquals(4500L, value.targetMilliseconds(142))
        assertEquals(4500L, value.targetMilliseconds(90))
        assertEquals(12, value.exposureDays)
    }
}
