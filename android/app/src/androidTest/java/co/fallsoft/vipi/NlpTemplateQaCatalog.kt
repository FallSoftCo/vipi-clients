package co.fallsoft.vipi

import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest
import co.fallsoft.vipi.NlpTemplatePatternMatcher.Scope
import co.fallsoft.vipi.NlpTemplatePatternMatcher.Pattern
import co.fallsoft.vipi.NlpTemplateSelection.Recognition

/** Frozen-data test catalog. Nothing here is reachable by the default app. */
internal class NlpTemplateQaCatalog(payload: ByteArray, semantics: ByteArray, expectedSha: String) {
    companion object {
        const val CONTRACT_SHA = "3767a5f794023ff1fef85f5120658ce7881be0c143fd2357dcfcfe705272fdf2"
        const val SEMANTICS_SHA = "ac0df4d3ef183b9628fd6d29b868e50b7c02556a270de355d13dd6ff595cf3d7"
        fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
        private fun nullable(row: JSONObject, key: String) = if (row.isNull(key)) null else row.getString(key)
    }
    val payloadSha = sha(payload)
    private val data = JSONObject(payload.toString(Charsets.UTF_8))
    private val policy = JSONObject(semantics.toString(Charsets.UTF_8))
    val formsBySet: Map<String, List<NlpTemplatePatternMatcher.Form>>
    val forms: Map<String, NlpTemplatePatternMatcher.Form>
    val faces: Map<String, NlpTemplateSelection.Face>
    val patterns: List<Pattern>
    val knownSnapshots: Map<String, Set<String>>
    val armInheritance: Map<String, Set<String>>
    private val fallback: List<NlpTemplateSelection.Face>
    init {
        require(expectedSha.matches(Regex("[a-f0-9]{64}")) && payloadSha == expectedSha)
        require(sha(semantics) == SEMANTICS_SHA)
        require(data.getString("schema") == "vipi.nlp-template-payload.r01" && !data.getBoolean("production"))
        require(data.getString("contract_sha256") == CONTRACT_SHA && policy.getString("contract_sha256") == CONTRACT_SHA)
        val formSets = data.getJSONObject("form_sets")
        formsBySet = formSets.keys().asSequence().associateWith { key ->
            val values = formSets.getJSONArray(key)
            require(values.length() in 1..32)
            (0 until values.length()).map { NlpTemplatePatternMatcher.form(values.getJSONObject(it)) }
        }
        val allForms = formsBySet.values.flatten(); forms = allForms.associateBy { it.id }
        require(forms.size == allForms.size)
        val faceRows = data.getJSONArray("faces")
        val allFaces = (0 until faceRows.length()).map { index -> val row = faceRows.getJSONObject(index)
            NlpTemplateSelection.Face(row.getString("id"), row.getString("concept_id"), row.getString("source_language"),
                row.getString("source_form"), row.getString("target_language"), row.getString("target"),
                nullable(row, "reading"), row.getString("primary_ref")) }
        faces = allFaces.associateBy { it.id }; require(faces.size == allFaces.size)
        val patternRows = data.getJSONArray("patterns")
        patterns = (0 until patternRows.length()).map { NlpTemplatePatternMatcher.pattern(patternRows.getJSONObject(it)) }
        require(patterns.size <= 4096 && patterns.map { it.id }.distinct().size == patterns.size)
        for (pattern in patterns) {
            require(pattern.parts.size in 1..12 && pattern.parts.map { it.name }.distinct().size == pattern.parts.size)
            require(pattern.outputs.map { it.id }.distinct().size == pattern.outputs.size)
            require(pattern.parts.all { it.formSet == null || it.formSet in formsBySet })
            require((pattern.atomicMode == "none") == (pattern.atomicScope == null))
        }
        fallback = NlpTemplatePatternMatcher.strings(data.getJSONArray("fallback_entries")).map { requireNotNull(faces[it]) }
        val known = policy.getJSONObject("known_snapshots")
        knownSnapshots = known.keys().asSequence().associateWith { NlpTemplatePatternMatcher.strings(known.getJSONArray(it)).toSet() }
        val inheritance = policy.getJSONObject("arm_inheritance")
        armInheritance = inheritance.keys().asSequence().associateWith { NlpTemplatePatternMatcher.strings(inheritance.getJSONArray(it)).toSet() }
    }
    data class Source(val text: String, val language: String, val words: List<IntRange>,
                      val windows: Map<String, List<IntRange>>?, val orderedWindows: List<Pair<Scope, Int>>,
                      val literals: List<NlpTemplatePatternMatcher.LiteralScope>)
    fun source(text: String, language: String): Source {
        require(language == "en" && text.length <= 16_384)
        val words = LocalImmersion.words(text, language)
        val windows = ReviewedFrameLookup.windows(text, language)
        val ordered = windows?.values.orEmpty().flatten().map { Scope(it.first, it.last + 1) }.distinct()
            .map { scope -> scope to words.count { it.first >= scope.start && it.last < scope.end } }
            .sortedWith(compareByDescending<Pair<Scope, Int>> { it.second }.thenByDescending { it.first.length }.thenBy { it.first.start })
        return Source(text, language, words, windows, ordered, NlpTemplatePatternMatcher.literalScopes(text))
    }
    data class Arm(val id: String, val recognitions: List<Recognition>, val parserRejections: JSONArray,
                   val attemptedPatterns: Int, val attemptedWindows: Int, val peakStates: Int)
    fun recognize(source: Source, arm: String): Arm {
        val included = requireNotNull(armInheritance[arm]); val rejected = JSONArray()
        if (source.windows == null) return Arm(arm, emptyList(), rejected.put(JSONObject().put("reason", "native_window_bound")), 0, 0, 0)
        val matches = mutableListOf<Recognition>(); var attemptedPatterns = 0; var attemptedWindows = 0; var peak = 0
        for (pattern in patterns) {
            if (pattern.source != source.language || pattern.arms.none { it in included }) continue
            // A literal or explicitly supplied focus only shortlists possible
            // windows. The complete parser, native ranges and guards admit them.
            val focusSets = pattern.parts.filter { it.kind == "focus" }.map { requireNotNull(it.formSet?.let(formsBySet::get)) }
            if (focusSets.any { set -> set.none { source.text.contains(it.surface) } }) continue
            val anchor = pattern.parts.filter { it.kind == "literal" && !it.value.isNullOrBlank() }.mapNotNull { it.value }.maxByOrNull { it.length }
            if (anchor != null && !source.text.contains(anchor)) continue
            attemptedPatterns++
            for ((window, contextCost) in source.orderedWindows) {
                val text = source.text.substring(window.start, window.end)
                if (anchor != null && !text.contains(anchor)) continue
                if (focusSets.any { set -> set.none { text.contains(it.surface) } }) continue
                attemptedWindows++
                val result = NlpTemplatePatternMatcher.match(source.text, window, pattern, formsBySet, source.literals,
                    requireFiniteControl = "existing_finite_slots" in pattern.arms)
                peak = maxOf(peak, result.peakStates)
                if (result.rejection != null) rejected.put(JSONObject().put("rule_id", pattern.id)
                    .put("context_range_utf16", window.json()).put("reason", result.rejection))
                for (parse in result.parses) {
                    val recognition = Recognition(pattern, parse, contextCost)
                    if (pattern.atomicMode != "none") {
                        val mask = requireNotNull(recognition.mask)
                        require(mask.start >= window.start && mask.end <= window.end && mask.length > 0)
                    }
                    require(recognition.approved.size == pattern.outputs.size)
                    matches += recognition
                    check(matches.size <= 4096) { "Bounded recognition count exceeded" }
                }
            }
        }
        return Arm(arm, matches.distinct(), rejected, attemptedPatterns, attemptedWindows, peak)
    }
    fun select(source: Source, arm: Arm, target: String, density: Double, knownSnapshot: String): NlpTemplateSelection.Result {
        val generic = fallback.filter { it.source == source.language && it.targetLanguage == target }.flatMap { face ->
            source.windows?.get(face.sourceForm).orEmpty().map { face to Scope(it.first, it.last + 1) }
        }
        return NlpTemplateSelection.select(source.text, source.language, target, source.words, arm.recognitions, faces,
            forms, generic, source.literals, density, requireNotNull(knownSnapshots[knownSnapshot]), payloadSha)
    }
}
