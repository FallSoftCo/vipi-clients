package co.fallsoft.vipi

import co.fallsoft.vipi.core.PartialImmersionResult
import co.fallsoft.vipi.core.SourceReferencePresentation
import co.fallsoft.vipi.core.SourceReferenceUnit
import co.fallsoft.vipi.core.TranslationIntegrity
import org.json.JSONArray
import org.json.JSONObject
import co.fallsoft.vipi.NlpTemplatePatternMatcher.Scope
import co.fallsoft.vipi.NlpTemplatePatternMatcher.Pattern
import co.fallsoft.vipi.NlpTemplatePatternMatcher.Parse
import co.fallsoft.vipi.NlpTemplatePatternMatcher.Form

/** QA selection preserves recognized scopes even when no output can be displayed. */
internal object NlpTemplateSelection {
    data class Face(val id: String, val conceptID: String, val source: String, val sourceForm: String,
                    val targetLanguage: String, val target: String, val reading: String?, val primaryRef: String)
    data class Recognition(val pattern: Pattern, val parse: Parse, val contextCost: Int) {
        val mask: Scope? get() = if (pattern.atomicMode == "none") null else pattern.atomicScope?.let(parse::scope)
        val approved: List<Pair<String, Scope>> get() = pattern.outputs.mapNotNull { output -> parse.scope(output.scope)?.let { output.id to it } }
        val affected: List<Scope> get() = listOfNotNull(mask) + approved.map { it.second }
    }
    data class Candidate(val outputID: String, val face: Face, val scope: Scope, val nativeCost: Int,
                         val context: Scope, val contextCost: Int, val priority: Int, val ruleID: String)
    data class Result(val partial: PartialImmersionResult?, val candidates: List<Candidate>,
                      val selected: List<Candidate>, val rejections: JSONArray, val budget: Int)
    private fun sameOrCrossing(a: Scope, b: Scope): Boolean = a == b ||
        (a.start < b.start && b.start < a.end && a.end < b.end) ||
        (b.start < a.start && a.start < b.end && b.end < a.end)

    fun select(text: String, source: String, target: String, nativeWords: List<IntRange>,
               recognitions: List<Recognition>, faces: Map<String, Face>, forms: Map<String, Form>,
               fallback: List<Pair<Face, Scope>>, literals: List<NlpTemplatePatternMatcher.LiteralScope>,
               density: Double, known: Set<String>, catalogSha: String): Result {
        require(density in listOf(.10, .25, .50))
        val budget = maxOf(1, (nativeWords.size * density).toInt())
        val rejected = JSONArray(); val candidates = mutableListOf<Candidate>()
        fun reject(id: String, range: Scope?, reason: String) {
            rejected.put(JSONObject().put("output_id", id).put("source_range_utf16", range?.json() ?: JSONObject.NULL).put("reason", reason))
        }
        fun cost(scope: Scope): Int? {
            val touched = nativeWords.filter { it.first < scope.end && it.last + 1 > scope.start }
            return touched.size.takeIf { touched.isNotEmpty() && touched.first().first == scope.start &&
                touched.last().last + 1 == scope.end && touched.all { it.first >= scope.start && it.last < scope.end } }
        }
        fun admit(outputID: String, faceID: String?, conceptID: String?, scope: Scope?, context: Scope,
                  contextCost: Int, priority: Int, ruleID: String) {
            if (scope == null || scope.start < 0 || scope.end > text.length || scope.length !in 1..128) {
                reject(outputID, scope, "invalid_output_scope"); return
            }
            val face = faceID?.let(faces::get)
            if (face == null) { reject(outputID, scope, "target_face_unavailable"); return }
            if (face.source != source || face.targetLanguage != target || face.conceptID != conceptID ||
                face.sourceForm != text.substring(scope.start, scope.end)) {
                reject(outputID, scope, "source_face_or_concept_binding_mismatch"); return
            }
            if (face.target.isBlank() || face.target.length > 128 || (target in setOf("ja", "ko", "zh", "ar") && face.reading.isNullOrBlank())) {
                reject(outputID, scope, "target_face_or_reading_unavailable"); return
            }
            val nativeCost = cost(scope)
            if (nativeCost == null) { reject(outputID, scope, "incomplete_native_source_word"); return }
            if (literals.any { it.scope.overlaps(scope) }) { reject(outputID, scope, "protected_literal_scope"); return }
            if (!TranslationIntegrity.preservesIdentifiers(text, text.replaceRange(scope.start, scope.end, face.target))) {
                reject(outputID, scope, "native_full_message_literal_integrity"); return
            }
            candidates += Candidate(outputID, face, scope, nativeCost, context, contextCost, priority, ruleID)
        }
        for (recognition in recognitions) for (output in recognition.pattern.outputs) {
            val faceID = if (output.faceFromPart == null) output.faceIDs[target] else {
                val binding = recognition.parse.bindings.singleOrNull { it.name == output.faceFromPart }
                binding?.formID?.let(forms::get)?.faceIDs?.get(target)
            }
            admit(output.id, faceID, output.conceptID, recognition.parse.scope(output.scope), recognition.parse.context,
                recognition.contextCost, recognition.pattern.priority, recognition.pattern.id)
        }
        for ((face, scope) in fallback) admit("diagnostic-fallback:${face.id}", face.id, face.conceptID, scope,
            scope, cost(scope) ?: 0, Int.MIN_VALUE, "diagnostic-fallback")

        // Recognition is immutable and independent of availability/known/budget.
        // Every overlapping mask must permit this exact output ID AND geometry.
        val admitted = candidates.distinct().filter { candidate ->
            val mask = recognitions.firstOrNull { recognition -> recognition.mask?.overlaps(candidate.scope) == true &&
                (recognition.pattern.atomicMode == "ambiguous" || recognition.approved.none { it.first == candidate.outputID && it.second == candidate.scope }) }
            if (mask != null) { reject(candidate.outputID, candidate.scope, "atomic_scope:${mask.pattern.id}"); false }
            else {
                val conflicts = recognitions.any { left -> recognitions.any { right ->
                    left !== right && left.pattern.meaningID != right.pattern.meaningID && sameOrCrossing(left.parse.context, right.parse.context) &&
                        left.affected.any { a -> a.overlaps(candidate.scope) && right.affected.any { b -> b.overlaps(a) && b.overlaps(candidate.scope) } }
                } }
                if (conflicts) { reject(candidate.outputID, candidate.scope, "conflicting_source_meaning"); false }
                else if (candidate.face.conceptID in known) { reject(candidate.outputID, candidate.scope, "known_concept"); false }
                else true
            }
        }.sortedWith(compareByDescending<Candidate> { it.contextCost }.thenByDescending { it.context.length }
            .thenByDescending { it.priority }.thenByDescending { it.nativeCost }.thenBy { it.scope.start }.thenBy { it.outputID })
        val selected = mutableListOf<Candidate>(); val concepts = hashSetOf<String>(); var used = 0
        for (candidate in admitted) {
            val reason = when {
                candidate.face.conceptID in concepts -> "repeated_concept"
                selected.any { it.scope.overlaps(candidate.scope) } -> "overlapping_output"
                used + candidate.nativeCost > budget -> "native_density_budget"
                selected.size >= 128 -> "selected_unit_bound"
                else -> null
            }
            if (reason != null) reject(candidate.outputID, candidate.scope, reason)
            else { selected += candidate; concepts += candidate.face.conceptID; used += candidate.nativeCost }
        }
        val units = selected.sortedBy { it.scope.start }.map { candidate ->
            SourceReferenceUnit(candidate.scope.start, candidate.scope.end, text.substring(candidate.scope.start, candidate.scope.end),
                candidate.face.target, candidate.face.reading, "nlp-qa:${candidate.ruleID}:${candidate.outputID}:${candidate.face.id}", catalogSha, candidate.nativeCost)
        }
        val partial = if (units.isEmpty()) null else SourceReferencePresentation.create(text, target, units, density, nativeWords.size)
        val actual = selected.filter { candidate -> partial?.spans?.any { it.start == candidate.scope.start &&
            it.end == candidate.scope.end && it.translated == candidate.face.target } == true }
        for (candidate in selected) if (candidate !in actual) reject(candidate.outputID, candidate.scope, "native_presentation_withheld")
        return Result(partial, candidates, actual, rejected, budget)
    }
}
