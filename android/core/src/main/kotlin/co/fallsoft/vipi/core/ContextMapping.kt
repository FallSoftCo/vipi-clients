package co.fallsoft.vipi.core

/** Finite, authored context patterns. Slots never become replacement text. */
sealed interface ContextPart {
    data class Literal(val text: String) : ContextPart
    data class Slot(val alternatives: List<String>) : ContextPart
    data class Focus(val text: String) : ContextPart
}

data class ContextMapping(val id: String, val meaning: String, val sourceLanguage: String,
                          val targetLanguage: String, val parts: List<ContextPart>,
                          val targets: List<String>, val readings: Map<String, List<String>> = emptyMap())

/** This validates exact context/scope. Authored meaning and readings need data QA.
 * Callers supply a bounded indexed shortlist, never the entire language catalog.
 */
object ContextMappingMatcher {
    private data class State(val offset: Int, val focus: IntRange?)
    private data class Match(val mapping: ContextMapping, val focus: IntRange)

    fun entries(original: String, source: String, target: String, mappings: List<ContextMapping>): List<VocabularyEntry> {
        if (original.isEmpty() || original.length > 16_384 || mappings.size > 256 || source == target) return emptyList()
        val matches = mappings.mapNotNull { record ->
            if (record.sourceLanguage != source || record.targetLanguage != target || record.id.isBlank() || record.meaning.isBlank()) null
            else match(original, record)?.let { Match(record, it) }
        }
        return matches.groupBy { it.focus }.values.flatMap { group ->
            // Agreement on spelling is not agreement on meaning. Conflicting
            // authored claims cannot be resolved by whichever record came first.
            if (group.map { it.mapping.meaning }.distinct().size != 1) emptyList()
            else group.map { hit -> VocabularyEntry(original.substring(hit.focus), hit.mapping.targets, hit.mapping.readings) }
        }.distinct()
    }

    private fun match(original: String, record: ContextMapping): IntRange? {
        if (record.parts.size !in 1..12 || record.parts.count { it is ContextPart.Focus } != 1 ||
            record.parts.none { it is ContextPart.Literal && it.text.isNotBlank() } ||
            record.targets.size !in 1..16 || record.targets.any { it.isBlank() || it.length > 128 }) return null
        var states = setOf(State(0, null))
        for (part in record.parts) {
            val options = when (part) {
                is ContextPart.Literal -> listOf(part.text)
                is ContextPart.Focus -> listOf(part.text)
                is ContextPart.Slot -> part.alternatives
            }
            if (options.size !in 1..32 || options.any { it.isEmpty() || it.length > 256 }) return null
            if (part is ContextPart.Focus && part.text.length > 128) return null
            val next = linkedSetOf<State>()
            for (state in states) for (text in options) {
                val end = state.offset + text.length
                if (end <= original.length && original.startsWith(text, state.offset)) {
                    next += State(end, if (part is ContextPart.Focus) state.offset until end else state.focus)
                    if (next.size > 128) return null
                }
            }
            if (next.isEmpty()) return null
            states = next
        }
        return states.filter { it.offset == original.length }.mapNotNull { it.focus }.distinct().singleOrNull()
    }
}
