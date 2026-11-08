package co.fallsoft.vipi

import android.os.Build
import com.atilika.kuromoji.ipadic.Token

/** Dormant native reading candidate. No chat, authored-reading or speech caller uses this yet. */
internal object JapaneseReadings {
    enum class Issue { UNSUPPORTED_API, INPUT_LIMIT, UNRESOLVED_JAPANESE, AMBIGUOUS_IDENTIFIER, CONVERSION, SOURCE_BOUNDS }
    enum class Kind { READING, LITERAL, PUNCTUATION, WHITESPACE, UNRESOLVED }
    enum class Basis { NATIVE_PRONUNCIATION, NATIVE_READING, KANA_SURFACE, COPULAR_NAN }
    data class Piece(val start: Int, val end: Int, val original: String, val value: String, val kind: Kind,
                     val bases: Set<Basis> = emptySet())
    data class Result(val reading: String?, val pieces: List<Piece>, val issues: Set<Issue>)

    fun supported(api: Int) = api >= 28

    fun read(original: String): Result {
        if (!supported(Build.VERSION.SDK_INT)) return Result(null, emptyList(), setOf(Issue.UNSUPPORTED_API))
        if (original.isBlank() || original.length > 16_384) return Result(null, emptyList(), setOf(Issue.INPUT_LIMIT))
        return Reader.read(original)
    }

    private fun japanese(text: String) = text.codePoints().anyMatch {
        it in setOf(0x3099, 0x309a, 0x30fc, 0xff70, 0xff9e, 0xff9f) ||
            Character.UnicodeScript.of(it) in setOf(Character.UnicodeScript.HAN, Character.UnicodeScript.HIRAGANA, Character.UnicodeScript.KATAKANA)
    }
    private fun kana(value: String?) = !value.isNullOrBlank() && value.codePoints().allMatch {
        it == 0x30fc || Character.UnicodeScript.of(it) in setOf(Character.UnicodeScript.HIRAGANA, Character.UnicodeScript.KATAKANA)
    }

    private object Reader {
        // URI/IRI ends cannot be inferred from a grammatical-looking Japanese suffix.
        // Preserve that complete ambiguous token and decline its full reading.
        private val opaque = Regex("```[\\s\\S]*?(?:```|$)|`[^`]*(?:`|$)|(?i:https?://|www\\.)[^\\s<>\\\"「」『』]+|[\\p{L}\\p{N}\\p{M}_.+-]+@[\\p{L}\\p{N}\\p{M}_.-]+\\.[\\p{L}\\p{M}]{2,}|[@#][\\p{L}\\p{N}\\p{M}_]+")
        private val sentencePunctuation = ".,!?;:。！？、，；：…"
        private data class Atom(val start: Int, val end: Int, val original: String, val kana: String?, val token: Token?, val basis: Basis? = null)

        @Synchronized fun read(original: String): Result {
            val pieces = mutableListOf<Piece>()
            val issues = linkedSetOf<Issue>()
            try {
                var cursor = 0
                for (match in opaque.findAll(original)) {
                    var end = match.range.last + 1
                    val isCode = match.value.startsWith('`')
                    if (!isCode) {
                        while (end > match.range.first) {
                            val last = original[end - 1]
                            val opening = when (last) { ')' -> '('; ']' -> '['; '}' -> '{'; else -> null }
                            val value = original.substring(match.range.first, end)
                            if (last in sentencePunctuation || (opening != null && value.count { it == last } > value.count { it == opening })) end-- else break
                        }
                    }
                    if (end <= match.range.first) continue
                    plain(original, cursor, match.range.first, pieces, issues)
                    val value = original.substring(match.range.first, end)
                    pieces += Piece(match.range.first, end, value, value, Kind.LITERAL)
                    if (!isCode && japanese(value)) issues += Issue.AMBIGUOUS_IDENTIFIER
                    cursor = end
                }
                plain(original, cursor, original.length, pieces, issues)
                check(pieces.joinToString("") { it.original } == original)
                check(pieces.zipWithNext().all { (a, b) -> a.end == b.start })
                return Result(if (issues.isEmpty()) render(pieces) else null, pieces.toList(), issues.toSet())
            } catch (_: Exception) {
                return Result(null, emptyList(), setOf(Issue.SOURCE_BOUNDS))
            }
        }

        private fun plain(original: String, start: Int, end: Int, pieces: MutableList<Piece>, issues: MutableSet<Issue>) {
            if (start >= end) return
            val text = original.substring(start, end)
            val analysis = KanaRomanizer.normalizeKana(text)
            val atoms = mutableListOf<Atom>()
            var cursor = 0
            for (token in LocalImmersion.japaneseTokens(analysis.text)) {
                val range = checkNotNull(analysis.sourceRange(token.position, token.position + token.surface.length))
                val a = range.first; val b = range.last + 1
                check(a >= cursor && b <= text.length && analysis.text.substring(token.position, token.position + token.surface.length) == token.surface)
                val source = text.substring(a, b)
                if (a > cursor) atoms += Atom(start + cursor, start + a, text.substring(cursor, a), null, null)
                val reading = if (!japanese(source)) null else when {
                    kana(token.pronunciation) -> token.pronunciation to Basis.NATIVE_PRONUNCIATION
                    kana(token.reading) -> token.reading to Basis.NATIVE_READING
                    else -> java.text.Normalizer.normalize(source, java.text.Normalizer.Form.NFKC)
                        .takeIf(::kana)?.let { it to Basis.KANA_SURFACE }
                }
                atoms += Atom(start + a, start + b, source, reading?.first, token, reading?.second)
                cursor = b
            }
            if (cursor < text.length) atoms += Atom(start + cursor, end, text.substring(cursor), null, null)
            for (i in 0 until atoms.lastIndex) {
                val atom = atoms[i]; val next = atoms[i + 1]
                // A lexical/context rule, not a sentence replacement: nani contracts
                // before the native copula. Do not infer it across a gap or quote,
                // before particles/counters, or inside a longer dictionary word.
                if (atom.original == "何" && atom.kana == "ナニ" && atom.token?.partOfSpeechLevel1 == "名詞" &&
                    atom.end == next.start && next.token?.partOfSpeechLevel1 == "助動詞" && next.token.baseForm in setOf("だ", "です")) {
                    atoms[i] = atom.copy(kana = "ナン", basis = Basis.COPULAR_NAN)
                }
            }
            val group = mutableListOf<Atom>()
            fun flush() {
                if (group.isEmpty()) return
                val source = group.joinToString("") { it.original }
                val native = group.joinToString("") { it.kana!! }
                val roman = try { KanaRomanizer.romanize(native) } catch (_: Exception) { null }
                // The converter explicitly rejects unsupported/terminal geminates.
                val valid = !roman.isNullOrEmpty() && roman.codePoints().allMatch {
                    Character.UnicodeScript.of(it) == Character.UnicodeScript.LATIN ||
                        Character.getType(it) in setOf(Character.NON_SPACING_MARK.toInt(), Character.COMBINING_SPACING_MARK.toInt()) || it == '\''.code
                }
                if (!valid) issues += Issue.CONVERSION
                pieces += Piece(group.first().start, group.last().end, source, if (valid) roman!! else source,
                    if (valid) Kind.READING else Kind.UNRESOLVED, group.mapNotNull { it.basis }.toSet())
                group.clear()
            }
            for (atom in atoms) {
                if (atom.kana != null) {
                    if (group.isNotEmpty() && !join(group, atom)) flush()
                    group += atom
                } else {
                    flush()
                    val kind = when {
                        atom.original.all(Char::isWhitespace) -> Kind.WHITESPACE
                        japanese(atom.original) -> { issues += Issue.UNRESOLVED_JAPANESE; Kind.UNRESOLVED }
                        atom.original.codePoints().anyMatch { Character.isLetterOrDigit(it) } -> Kind.LITERAL
                        else -> Kind.PUNCTUATION
                    }
                    // Exact contiguous non-Japanese runs retain names, times, money and
                    // punctuation inside them. Spaces are inserted only outside the run.
                    val previous = pieces.lastOrNull()
                    if (previous != null && previous.end == atom.start && previous.kind in setOf(Kind.LITERAL, Kind.PUNCTUATION) &&
                        kind in setOf(Kind.LITERAL, Kind.PUNCTUATION) && atom.original.none { it in "。！？、，；：「」『』" } &&
                        previous.original.last() !in "。！？、，；：「」『』") {
                        pieces[pieces.lastIndex] = previous.copy(end = atom.end, original = previous.original + atom.original,
                            value = previous.value + atom.original, kind = if (previous.kind == Kind.LITERAL || kind == Kind.LITERAL) Kind.LITERAL else Kind.PUNCTUATION)
                    } else pieces += Piece(atom.start, atom.end, atom.original, atom.original, kind)
                }
            }
            flush()
        }

        private fun join(group: List<Atom>, next: Atom): Boolean {
            val previous = group.last()
            if (previous.end != next.start) return false
            val token = next.token ?: return false
            val p = token.partOfSpeechLevel1; val detail = token.partOfSpeechLevel2
            // Context required by the kana transform must cross morphology edges.
            if (previous.kana!!.endsWith("ッ") || previous.kana.endsWith("っ") || next.kana!!.startsWith("ー")) return true
            val predicate = group.any { it.token?.partOfSpeechLevel1 in setOf("動詞", "形容詞", "助動詞") }
            if (p == "助動詞" && predicate) return true
            if (p in setOf("動詞", "形容詞") && detail in setOf("非自立", "接尾") && predicate) return true
            if (p == "助詞" && detail == "接続助詞" && predicate) return true
            if (p == "名詞" && detail == "接尾") return true
            return previous.token?.partOfSpeechLevel1 == "接頭詞"
        }

        private fun render(pieces: List<Piece>): String {
            val output = StringBuilder()
            var previous: Piece? = null
            val words = setOf(Kind.READING, Kind.LITERAL, Kind.UNRESOLVED)
            for (piece in pieces) {
                if (previous?.kind in words && piece.kind in words) output.append(' ')
                output.append(piece.value)
                previous = piece
            }
            return output.toString()
        }
    }
}
