package co.fallsoft.vipi.core

/** Spaced visual exposure, never a claim of mastery. Contains no chat text or message ID. */
data class VocabularyFamiliarity(val exposureDays: Int = 0, val lastDay: Int = -1) {
    init { require(exposureDays in 0..3650 && lastDay >= -1) }
    fun observe(day: Int): VocabularyFamiliarity =
        if (day < 0 || day <= lastDay) this else copy(exposureDays = (exposureDays + 1).coerceAtMost(3650), lastDay = day)
    fun targetMilliseconds(day: Int): Long = when {
        day < lastDay || day.toLong() - lastDay > 30 -> 4500L
        exposureDays >= 12 -> 9000L
        exposureDays >= 4 -> 6000L
        else -> 4500L
    }
}
