package co.fallsoft.vipi

import android.os.Build
import com.atilika.kuromoji.ipadic.Token
import com.atilika.kuromoji.ipadic.Tokenizer

/** The local morphological reader is used only for Japanese pronunciation. */
internal object NativeJapaneseTokenizer {
    private val tokenizer by lazy { Tokenizer() }

    fun acceptsText(text: String): Boolean {
        if (text.length > FullReadingLimits.MAX_TEXT_UTF16) return false
        var start = 0
        for (index in text.indices) if (text[index] == '。' || text[index] == '、') {
            if (index + 1 - start > FullReadingLimits.MAX_JAPANESE_SEGMENT_UTF16) return false
            start = index + 1
        }
        return text.length - start <= FullReadingLimits.MAX_JAPANESE_SEGMENT_UTF16
    }

    @Synchronized
    fun tokens(text: String): List<Token> {
        require(text.length <= FullReadingLimits.MAX_JAPANESE_SEGMENT_UTF16)
        return tokenizer.tokenize(text)
    }

    @Synchronized
    fun positionedTokens(text: String): List<Pair<Int, Token>> {
        require(acceptsText(text)) { "Unqualified Kuromoji lattice span" }
        val result = mutableListOf<Pair<Int, Token>>()
        var start = 0
        fun append(end: Int) {
            if (start < end) {
                val offset = start
                result += tokenizer.tokenize(text.substring(start, end)).map { offset to it }
            }
            start = end
        }
        // These are exactly TokenizerBase 0.9's default boundaries, including
        // the delimiter. Avoid its repeated searches for the absent alternative.
        for (index in text.indices) if (text[index] == '。' || text[index] == '、') append(index + 1)
        append(text.length)
        return result
    }
}

/** Live pronunciation for display only. Never used as speech input. */
internal object JapaneseReadings {
    enum class Issue {
        UNSUPPORTED_API,
        INPUT_LIMIT,
        OUTPUT_LIMIT,
        UNRESOLVED_JAPANESE,
        AMBIGUOUS_IDENTIFIER,
        CONVERSION,
        SOURCE_BOUNDS,
    }

    enum class Kind {
        READING,
        LITERAL,
        PUNCTUATION,
        WHITESPACE,
        UNRESOLVED,
    }

    enum class Basis {
        NATIVE_PRONUNCIATION,
        NATIVE_READING,
        KANA_SURFACE,
        COPULAR_NAN,
    }

    data class Piece(
        val start: Int,
        val end: Int,
        val original: String,
        val value: String,
        val kind: Kind,
        val bases: Set<Basis> = emptySet(),
    )

    data class Result(val reading: String?, val pieces: List<Piece>, val issues: Set<Issue>)

    fun supported(api: Int) = api >= 28

    fun read(original: String): Result {
        if (!supported(Build.VERSION.SDK_INT))
            return Result(null, emptyList(), setOf(Issue.UNSUPPORTED_API))
        if (original.isBlank() || original.length > FullReadingLimits.MAX_TEXT_UTF16)
            return Result(null, emptyList(), setOf(Issue.INPUT_LIMIT))
        return Reader.read(original)
    }

    private fun japanese(text: String) =
        text.codePoints().anyMatch {
            it in setOf(0x3099, 0x309a, 0x30fc, 0xff70, 0xff9e, 0xff9f) ||
                Character.UnicodeScript.of(it) in
                    setOf(
                        Character.UnicodeScript.HAN,
                        Character.UnicodeScript.HIRAGANA,
                        Character.UnicodeScript.KATAKANA,
                    )
        }

    private fun kana(value: String?) =
        !value.isNullOrBlank() &&
            value.codePoints().allMatch {
                it == 0x30fc ||
                    Character.UnicodeScript.of(it) in
                        setOf(Character.UnicodeScript.HIRAGANA, Character.UnicodeScript.KATAKANA)
            }

    private object Reader {
        // URI/IRI ends cannot be inferred from a grammatical-looking Japanese suffix.
        // Preserve that complete ambiguous token and decline its full reading.
        private val nonEmailOpaque =
            Regex(
                "```[\\s\\S]*?(?:```|$)|`[^`]*(?:`|$)|(?i:https?://|www\\.)[^\\s<>\\\"「」『』]+|[@#][\\p{L}\\p{N}\\p{M}_]+"
            )
        private val emailOpaque =
            Regex("[\\p{L}\\p{N}\\p{M}_.+-]+@[\\p{L}\\p{N}\\p{M}_.-]+\\.[\\p{L}\\p{M}]{2,}")

        private fun emailLocal(point: Int): Boolean =
            Character.isLetterOrDigit(point) ||
                Character.getType(point) in
                    setOf(
                        Character.NON_SPACING_MARK.toInt(),
                        Character.COMBINING_SPACING_MARK.toInt(),
                        Character.ENCLOSING_MARK.toInt(),
                        Character.LETTER_NUMBER.toInt(),
                        Character.OTHER_NUMBER.toInt(),
                    ) ||
                point in "_.+-".map(Char::code)

        // The old unanchored email alternative retried long no-@ literals at
        // every position. Actual @ anchors bound scanning without word cuts.
        private fun opaqueMatches(text: String): List<MatchResult> {
            val candidates = nonEmailOpaque.findAll(text).map { it to 0 }.toMutableList()
            for (at in text.indices) if (text[at] == '@') {
                var start = at
                while (start > 0) {
                    val point = text.codePointBefore(start)
                    if (!emailLocal(point)) break
                    start -= Character.charCount(point)
                }
                if (start < at) emailOpaque.matchAt(text, start)?.let { candidates += it to 1 }
            }
            val selected = mutableListOf<MatchResult>()
            var end = 0
            for ((match, _) in
                candidates.sortedWith(
                    compareBy<Pair<MatchResult, Int>>({ it.first.range.first }, { it.second })
                )) {
                if (match.range.first >= end) {
                    selected += match
                    end = match.range.last + 1
                }
            }
            return selected
        }

        private val sentencePunctuation = ".,!?;:。！？、，；：…"

        private data class Atom(
            val start: Int,
            val end: Int,
            val original: String,
            val kana: String?,
            val token: Token?,
            val basis: Basis? = null,
        )

        @Synchronized
        fun read(original: String): Result {
            val pieces = mutableListOf<Piece>()
            val issues = linkedSetOf<Issue>()
            try {
                var cursor = 0
                for (match in opaqueMatches(original)) {
                    var end = match.range.last + 1
                    val isCode = match.value.startsWith('`')
                    if (!isCode) {
                        // Count delimiters once. Recounting each shortened URL is
                        // quadratic for long runs of unmatched trailing brackets.
                        val delimiters = "()[]{}"
                        val counts = IntArray(delimiters.length)
                        for (index in match.range) {
                            val delimiter = delimiters.indexOf(original[index])
                            if (delimiter >= 0) counts[delimiter]++
                        }
                        while (end > match.range.first) {
                            val last = original[end - 1]
                            val delimiter = delimiters.indexOf(last)
                            if (last in sentencePunctuation) end--
                            else if (
                                delimiter >= 0 &&
                                    delimiter % 2 == 1 &&
                                    counts[delimiter] > counts[delimiter - 1]
                            ) {
                                counts[delimiter]--
                                end--
                            } else break
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
                val rendered = if (issues.isEmpty()) render(pieces) else null
                if (rendered == null && issues.isEmpty()) issues += Issue.OUTPUT_LIMIT
                return Result(rendered, pieces.toList(), issues.toSet())
            } catch (_: Exception) {
                return Result(null, emptyList(), setOf(Issue.SOURCE_BOUNDS))
            }
        }

        private fun plain(
            original: String,
            start: Int,
            end: Int,
            pieces: MutableList<Piece>,
            issues: MutableSet<Issue>,
        ) {
            if (start >= end) return
            val text = original.substring(start, end)
            val analysis = KanaRomanizer.normalizeKana(text)
            if (!NativeJapaneseTokenizer.acceptsText(analysis.text)) {
                pieces += Piece(start, end, text, text, Kind.UNRESOLVED)
                issues += Issue.INPUT_LIMIT
                return
            }
            val atoms = mutableListOf<Atom>()
            var cursor = 0
            for ((segmentOffset, token) in
                NativeJapaneseTokenizer.positionedTokens(analysis.text)) {
                val position = segmentOffset + token.position
                val range =
                    checkNotNull(analysis.sourceRange(position, position + token.surface.length))
                val a = range.first
                val b = range.last + 1
                check(
                    a >= cursor &&
                        b <= text.length &&
                        analysis.text.substring(position, position + token.surface.length) ==
                            token.surface
                )
                val source = text.substring(a, b)
                if (a > cursor)
                    atoms += Atom(start + cursor, start + a, text.substring(cursor, a), null, null)
                val reading =
                    if (!japanese(source)) null
                    else
                        when {
                            kana(token.pronunciation) ->
                                token.pronunciation to Basis.NATIVE_PRONUNCIATION
                            kana(token.reading) -> token.reading to Basis.NATIVE_READING
                            else ->
                                java.text.Normalizer.normalize(
                                        source,
                                        java.text.Normalizer.Form.NFKC,
                                    )
                                    .takeIf(::kana)
                                    ?.let { it to Basis.KANA_SURFACE }
                        }
                atoms += Atom(start + a, start + b, source, reading?.first, token, reading?.second)
                cursor = b
            }
            if (cursor < text.length)
                atoms += Atom(start + cursor, end, text.substring(cursor), null, null)
            for (i in 0 until atoms.lastIndex) {
                val atom = atoms[i]
                val next = atoms[i + 1]
                // A lexical/context rule, not a sentence replacement: nani contracts
                // before the native copula. Do not infer it across a gap or quote,
                // before particles/counters, or inside a longer dictionary word.
                if (
                    atom.original == "何" &&
                        atom.kana == "ナニ" &&
                        atom.token?.partOfSpeechLevel1 == "名詞" &&
                        atom.end == next.start &&
                        next.token?.partOfSpeechLevel1 == "助動詞" &&
                        next.token.baseForm in setOf("だ", "です")
                ) {
                    atoms[i] = atom.copy(kana = "ナン", basis = Basis.COPULAR_NAN)
                }
            }
            val group = mutableListOf<Atom>()
            fun flush() {
                if (group.isEmpty()) return
                val source = group.joinToString("") { it.original }
                val native = group.joinToString("") { it.kana!! }
                val roman =
                    try {
                        KanaRomanizer.romanize(native)
                    } catch (_: Exception) {
                        null
                    }
                // The converter explicitly rejects unsupported/terminal geminates.
                val valid =
                    !roman.isNullOrEmpty() &&
                        roman.codePoints().allMatch {
                            Character.UnicodeScript.of(it) == Character.UnicodeScript.LATIN ||
                                Character.getType(it) in
                                    setOf(
                                        Character.NON_SPACING_MARK.toInt(),
                                        Character.COMBINING_SPACING_MARK.toInt(),
                                    ) ||
                                it == '\''.code
                        }
                if (!valid) issues += Issue.CONVERSION
                pieces +=
                    Piece(
                        group.first().start,
                        group.last().end,
                        source,
                        if (valid) roman!! else source,
                        if (valid) Kind.READING else Kind.UNRESOLVED,
                        group.mapNotNull { it.basis }.toSet(),
                    )
                group.clear()
            }
            for (atom in atoms) {
                if (atom.kana != null) {
                    if (group.isNotEmpty() && !join(group, atom)) flush()
                    group += atom
                } else {
                    flush()
                    val kind =
                        when {
                            atom.original.all(Char::isWhitespace) -> Kind.WHITESPACE
                            japanese(atom.original) -> {
                                issues += Issue.UNRESOLVED_JAPANESE
                                Kind.UNRESOLVED
                            }
                            atom.original.codePoints().anyMatch { Character.isLetterOrDigit(it) } ->
                                Kind.LITERAL
                            else -> Kind.PUNCTUATION
                        }
                    // Exact contiguous non-Japanese runs retain names, times, money and
                    // punctuation inside them. Spaces are inserted only outside the run.
                    val previous = pieces.lastOrNull()
                    if (
                        previous != null &&
                            previous.end == atom.start &&
                            previous.kind in setOf(Kind.LITERAL, Kind.PUNCTUATION) &&
                            kind in setOf(Kind.LITERAL, Kind.PUNCTUATION) &&
                            atom.original.none { it in "。！？、，；：「」『』" } &&
                            previous.original.last() !in "。！？、，；：「」『』"
                    ) {
                        pieces[pieces.lastIndex] =
                            previous.copy(
                                end = atom.end,
                                original = previous.original + atom.original,
                                value = previous.value + atom.original,
                                kind =
                                    if (previous.kind == Kind.LITERAL || kind == Kind.LITERAL)
                                        Kind.LITERAL
                                    else Kind.PUNCTUATION,
                            )
                    } else pieces += Piece(atom.start, atom.end, atom.original, atom.original, kind)
                }
            }
            flush()
        }

        private fun join(group: List<Atom>, next: Atom): Boolean {
            val previous = group.last()
            if (previous.end != next.start) return false
            val token = next.token ?: return false
            val p = token.partOfSpeechLevel1
            val detail = token.partOfSpeechLevel2
            // Context required by the kana transform must cross morphology edges.
            if (
                previous.kana!!.endsWith("ッ") ||
                    previous.kana.endsWith("っ") ||
                    next.kana!!.startsWith("ー")
            )
                return true
            val predicate = group.any { it.token?.partOfSpeechLevel1 in setOf("動詞", "形容詞", "助動詞") }
            if (p == "助動詞" && predicate) return true
            if (p in setOf("動詞", "形容詞") && detail in setOf("非自立", "接尾") && predicate) return true
            if (p == "助詞" && detail == "接続助詞" && predicate) return true
            if (p == "名詞" && detail == "接尾") return true
            return previous.token?.partOfSpeechLevel1 == "接頭詞"
        }

        private fun render(pieces: List<Piece>): String? {
            val output = StringBuilder()
            var previous: Piece? = null
            val words = setOf(Kind.READING, Kind.LITERAL, Kind.UNRESOLVED)
            for (piece in pieces) {
                val separator = previous?.kind in words && piece.kind in words
                if (
                    output.length.toLong() + piece.value.length + (if (separator) 1 else 0) >
                        FullReadingLimits.MAX_READING_UTF16
                )
                    return null
                if (separator) output.append(' ')
                output.append(piece.value)
                previous = piece
            }
            return output.toString()
        }
    }
}
