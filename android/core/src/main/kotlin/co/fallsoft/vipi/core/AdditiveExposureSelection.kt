package co.fallsoft.vipi.core

/** Selects already-authorized source units; never infers meaning or creates a translation. */
object AdditiveExposureSelection {
    data class Seen(val observed: Boolean, val due: Boolean = false, val available: Boolean = true)
    fun select(units: List<SourceReferenceUnit>, nativeWords: Int, density: Double, seen: (SourceReferenceUnit) -> Seen): List<SourceReferenceUnit> {
        require(nativeWords >= 0 && density.isFinite() && density in 0.0..0.75)
        if (density == 0.0 || nativeWords == 0) return emptyList()
        val novelBudget = maxOf(1, (nativeWords * density).toInt())
        val ceiling = maxOf(1, (nativeWords * .75).toInt()).coerceAtMost(nativeWords)
        return selectWithBudgets(units, novelBudget, ceiling, seen)
    }
    fun selectWithBudgets(units: List<SourceReferenceUnit>, novelBudget: Int, ceiling: Int, seen: (SourceReferenceUnit) -> Seen): List<SourceReferenceUnit> {
        require(novelBudget >= 0 && ceiling >= 0)
        if (novelBudget == 0 || ceiling == 0) return emptyList()
        val eligible = units.filter { (it.nativeSourceTokens ?: 0) in 1..ceiling }.sortedWith(compareBy({ it.start }, { it.end }, { it.referenceId }))
        val status = eligible.associateWith(seen)
        val authorized = eligible.filter { status.getValue(it).available }
        val novel = authorized.filter { status.getValue(it).observed.not() }.sortedWith(compareBy<SourceReferenceUnit> { it.selectionPriority ?: Int.MAX_VALUE }.thenBy { it.start }.thenBy { it.end }.thenBy { it.referenceId })
        val known = authorized.filter { status.getValue(it).observed }.sortedWith(compareByDescending<SourceReferenceUnit> { status.getValue(it).due }.thenBy { it.start }.thenBy { it.end }.thenBy { it.referenceId })
        val chosen = mutableListOf<SourceReferenceUnit>(); var total = 0; var newCost = 0
        fun add(u: SourceReferenceUnit, isNovel: Boolean): Boolean {
            val cost = requireNotNull(u.nativeSourceTokens)
            if (total + cost > ceiling || (isNovel && newCost + cost > novelBudget) || chosen.any { it.start < u.end && u.start < it.end }) return false
            chosen += u; total += cost; if (isNovel) newCost += cost; return true
        }
        // Reserve one fitting new unit before seen words; seen never consumes the novel budget.
        novel.firstOrNull { add(it, true) }
        for (u in known) add(u, false)
        for (u in novel) if (u !in chosen) add(u, true)
        return chosen.sortedWith(compareBy({ it.start }, { it.end }))
    }
}
