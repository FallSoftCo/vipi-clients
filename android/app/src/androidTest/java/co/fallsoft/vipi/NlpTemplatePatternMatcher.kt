package co.fallsoft.vipi

import co.fallsoft.vipi.core.ContextMappingMatcher
import co.fallsoft.vipi.core.ContextPart
import org.json.JSONArray
import org.json.JSONObject

/** QA source parser for the frozen comparison. Never generates or installs target text. */
internal object NlpTemplatePatternMatcher {
    data class Scope(val start: Int, val end: Int) {
        val length get() = end - start
        fun overlaps(other: Scope) = start < other.end && other.start < end
        fun json() = JSONArray(listOf(start, end))
    }
    data class Form(val id: String, val surface: String, val lexemeID: String, val pos: String,
                    val features: List<String>, val faceIDs: Map<String, String>, val primaryRef: String, val analysesJSON: String?)
    data class Part(val kind: String, val name: String, val value: String?, val values: List<String>,
                    val type: String?, val maxWords: Int?, val maxUTF16: Int?, val formSet: String?)
    data class RangeSpec(val kind: String, val part: String?, val from: String?, val through: String?)
    data class Output(val id: String, val scope: RangeSpec, val faceFromPart: String?,
                      val faceIDs: Map<String, String>, val conceptID: String)
    data class Pattern(val id: String, val family: String, val source: String, val arms: Set<String>,
                       val parts: List<Part>, val atomicMode: String, val atomicScope: RangeSpec?,
                       val atomicReason: String, val outputs: List<Output>, val meaningID: String,
                       val priority: Int, val evidenceRef: String, val recordSha256: String)
    data class LiteralScope(val kind: String, val scope: Scope)
    data class Binding(val name: String, val kind: String, val scope: Scope, val original: String, val formID: String?)
    data class Parse(val context: Scope, val bindings: List<Binding>) {
        fun scope(spec: RangeSpec): Scope? = when (spec.kind) {
            "context" -> context
            "part" -> bindings.singleOrNull { it.name == spec.part }?.scope
            "parts" -> {
                val a = bindings.indexOfFirst { it.name == spec.from }
                val b = bindings.indexOfFirst { it.name == spec.through }
                if (a < 0 || b < a) null else Scope(bindings[a].scope.start, bindings[b].scope.end)
            }
            else -> null
        }
    }
    data class Result(val parses: List<Parse>, val rejection: String?, val peakStates: Int)
    private data class State(val offset: Int, val bindings: List<Binding>)
    private val name = Regex("[\\p{L}\\p{M}]+(?:[-'’][\\p{L}\\p{M}]+)*")
    private val number = Regex("\\+?[0-9](?:[0-9 .()/\\-]*[0-9)])?")
    private val possessives = setOf("my", "your", "his", "her", "its", "our", "their")
    // Android uses Unicode character classes by default and rejects JVM's (?U).
    // https://developer.android.com/reference/java/util/regex/Pattern#UNICODE_CHARACTER_CLASS
    private val literal = Regex("https?://\\S+|\\b[^\\s@]+@[^\\s@]+\\.[^\\s@]+|```[\\s\\S]*?```|`[^`]*`")
    private val handle = Regex("(?<![\\w@])[@#][\\w]+")
    private val protectedNumber = Regex("(?<!\\w)\\+?[0-9](?:[0-9.,:/()\\-]*[0-9)])?")

    fun literalScopes(text: String): List<LiteralScope> {
        val scopes = mutableListOf<LiteralScope>()
        for (match in literal.findAll(text)) {
            val kind = when {
                match.value.startsWith("http://") || match.value.startsWith("https://") -> "url"
                match.value.startsWith('`') -> "code"
                else -> "email"
            }
            scopes += LiteralScope(kind, Scope(match.range.first, match.range.last + 1))
        }
        for (match in handle.findAll(text)) scopes += LiteralScope("handle", Scope(match.range.first, match.range.last + 1))
        for (match in protectedNumber.findAll(text)) scopes += LiteralScope("number", Scope(match.range.first, match.range.last + 1))
        // Exact quote scanner policy from diagnose_editorial_guards_r02.py,
        // expressed in original UTF16 coordinates. Single apostrophes are not quotes.
        var index = 0
        while (index < text.length) {
            val marker = listOf("```", "`", "“", "\"").firstOrNull { text.startsWith(it, index) }
            if (marker == null || (index > 0 && text[index - 1] == '\\')) { index++; continue }
            val closing = if (marker == "“") "”" else marker
            var end = text.indexOf(closing, index + marker.length)
            while (end >= 0 && end > 0 && text[end - 1] == '\\') end = text.indexOf(closing, end + closing.length)
            end = if (end < 0) text.length else end + closing.length
            scopes += LiteralScope("quote", Scope(index, end)); index = end
        }
        return scopes.distinct().sortedWith(compareBy<LiteralScope> { it.scope.start }.thenBy { it.scope.end }.thenBy { it.kind })
    }

    private fun possessiveEnding(text: String) = listOf("'s", "’s", "s'", "s’").any(text::endsWith)
    fun possessor(text: String, maxWords: Int): Boolean {
        if (maxWords !in 1..3 || text.any { it == '\n' || it == '\r' }) return false
        if (text in possessives) return true
        val base = when {
            text.endsWith("'s") || text.endsWith("’s") -> text.dropLast(2)
            text.endsWith("s'") || text.endsWith("s’") -> text.dropLast(1)
            else -> return false
        }
        val tokens = base.split(' ')
        return tokens.size in 1..maxWords && tokens.all { name.matches(it) && it.codePoints().anyMatch(Character::isLetter) } &&
            tokens.dropLast(1).none(::possessiveEnding)
    }
    private fun boundary(text: String, offset: Int) = offset in 0..text.length &&
        (offset == text.length || !Character.isLowSurrogate(text[offset]))
    private fun wordCharacter(text: String, offset: Int): Boolean {
        if (offset !in text.indices) return false
        val cp = text.codePointAt(offset)
        return Character.isLetterOrDigit(cp) || Character.getType(cp) in setOf(
            Character.NON_SPACING_MARK.toInt(), Character.COMBINING_SPACING_MARK.toInt(), Character.ENCLOSING_MARK.toInt()) || cp == '_'.code
    }

    fun match(text: String, context: Scope, pattern: Pattern, forms: Map<String, List<Form>>,
              literals: List<LiteralScope>, requireFiniteControl: Boolean): Result {
        if (text.length > 16_384 || context.length !in 1..256 || context.start < 0 || context.end > text.length ||
            !boundary(text, context.start) || !boundary(text, context.end) || pattern.parts.size !in 1..12 ||
            pattern.parts.map { it.name }.distinct().size != pattern.parts.size) return Result(emptyList(), "invalid_context_or_pattern_bounds", 0)
        var states = listOf(State(context.start, emptyList())); var peak = 1
        for (part in pattern.parts) {
            val next = linkedSetOf<State>()
            for (state in states) {
                val choices: List<Pair<String, String?>> = when (part.kind) {
                    "literal" -> listOf(requireNotNull(part.value) to null)
                    "enum" -> part.values.map { it to null }
                    "morph", "focus" -> part.formSet?.let(forms::get).orEmpty().map { it.surface to it.id }
                    "typed" -> {
                        val maximum = part.maxUTF16 ?: return Result(emptyList(), "typed_bound_missing", peak)
                        if (maximum !in 1..128) return Result(emptyList(), "typed_bound_missing", peak)
                        buildList {
                            if (state.offset > context.start && wordCharacter(text, text.offsetByCodePoints(state.offset, -1))) return@buildList
                            for (end in state.offset + 1..minOf(context.end, state.offset + maximum)) {
                                if (!boundary(text, end) || wordCharacter(text, end)) continue
                                val scope = Scope(state.offset, end); val value = text.substring(state.offset, end)
                                val allowed = when (part.type) {
                                    "possessor" -> possessor(value, part.maxWords ?: 0)
                                    "number" -> value.length <= 64 && number.matches(value)
                                    "identifier" -> literals.any { it.kind in setOf("url", "email", "handle", "code") && it.scope == scope }
                                    else -> false
                                }
                                if (allowed) add(value to null)
                            }
                        }
                    }
                    else -> return Result(emptyList(), "unknown_part_kind", peak)
                }
                if (part.kind != "typed" && choices.size > 32) return Result(emptyList(), "finite_alternative_limit", peak)
                for ((value, formID) in choices) {
                    val end = state.offset + value.length
                    if (value.isEmpty() || value.length > (if (part.kind == "focus") 128 else 256) || end > context.end ||
                        !boundary(text, end) || !text.startsWith(value, state.offset)) continue
                    next += State(end, state.bindings + Binding(part.name, part.kind, Scope(state.offset, end), value, formID))
                    peak = maxOf(peak, next.size)
                    if (next.size > 128) return Result(emptyList(), "active_match_state_limit", peak)
                }
            }
            if (next.isEmpty()) return Result(emptyList(), null, peak)
            states = next.toList()
        }
        var parses = states.filter { it.offset == context.end }.map { Parse(context, it.bindings) }
        if (requireFiniteControl) {
            if (pattern.parts.count { it.kind == "focus" } != 1 || pattern.parts.any { it.kind !in setOf("literal", "enum", "focus") })
                return Result(emptyList(), "existing_finite_control_ineligible", peak)
            parses = parses.filter { parse ->
                val parts = pattern.parts.map { part -> when (part.kind) {
                    "literal" -> ContextPart.Literal(requireNotNull(part.value))
                    "enum" -> ContextPart.Slot(part.values)
                    else -> ContextPart.Focus(parse.bindings.single { it.name == part.name }.original)
                } }
                val actual = ContextMappingMatcher.focus(text.substring(context.start, context.end), parts)
                val focus = parse.bindings.single { it.kind == "focus" }.scope
                actual != null && actual.first + context.start == focus.start && actual.last + 1 + context.start == focus.end
            }
        }
        return Result(parses, null, peak)
    }

    fun strings(array: JSONArray) = (0 until array.length()).map(array::getString)
    fun stringMap(value: JSONObject?) = value?.let { row -> row.keys().asSequence().associateWith(row::getString) } ?: emptyMap()
    private fun nullable(value: JSONObject, key: String) = if (!value.has(key) || value.isNull(key)) null else value.getString(key)
    fun range(value: JSONObject) = RangeSpec(value.getString("kind"), nullable(value, "part"), nullable(value, "from"), nullable(value, "through"))
    fun form(value: JSONObject) = Form(value.getString("id"), value.getString("surface"), value.get("lexeme_id").toString(),
        value.getString("pos"), strings(value.getJSONArray("features")), stringMap(value.getJSONObject("face_ids")),
        value.getString("primary_ref"), value.optJSONArray("analyses")?.toString())
    fun pattern(value: JSONObject): Pattern {
        val raw = value.getJSONArray("parts")
        val parts = (0 until raw.length()).map { index -> val p = raw.getJSONObject(index)
            Part(p.getString("kind"), p.getString("name"), nullable(p, "value"), p.optJSONArray("values")?.let(::strings).orEmpty(),
                nullable(p, "type"), if (p.has("max_words")) p.getInt("max_words") else null,
                if (p.has("max_utf16")) p.getInt("max_utf16") else null, nullable(p, "form_set")) }
        val atomic = value.getJSONObject("atomicity"); val outputs = value.getJSONArray("approved_outputs")
        require(atomic.has("scope") && atomic.getString("mode") in setOf("none", "atomic", "head_backoff", "ambiguous"))
        return Pattern(value.getString("id"), value.getString("family"), value.getString("source_language"),
            strings(value.getJSONArray("arms")).toSet(), parts, atomic.getString("mode"),
            if (atomic.isNull("scope")) null else range(atomic.getJSONObject("scope")), atomic.getString("reason"),
            (0 until outputs.length()).map { index -> val o = outputs.getJSONObject(index)
                Output(o.getString("id"), range(o.getJSONObject("scope")), nullable(o, "face_from_part"),
                    stringMap(o.optJSONObject("face_ids")), o.getString("concept_id")) },
            value.getString("meaning_id"), value.getInt("priority"), value.getString("evidence_ref"),
            value.getString("record_sha256").also { require(it.matches(Regex("[a-f0-9]{64}"))) })
    }
}
