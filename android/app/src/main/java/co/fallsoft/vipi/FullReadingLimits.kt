package co.fallsoft.vipi

/** Candidate resource envelope, not a claim of complete linguistic coverage.
 * Native adoption requires the separate real-reader measurements. */
internal object FullReadingLimits {
    const val MAX_TEXT_UTF16 = 65_536
    // Chinese pinned syllables have at most six UTF16 units plus a separator.
    // Korean has at most two initial letters, three vowel letters, two
    // final letters, three boundary hyphens and one external separator. Japanese uses this as an explicit
    // resource ceiling, not a proven lexicon-wide expansion bound.
    const val MAX_READING_UTF16 = MAX_TEXT_UTF16 * 11
    const val MAX_KANA_UTF16 = 65_536
    // Preserve Kuromoji 0.9's EXISTING 。/、 boundaries; never invent word cuts.
    // Larger individual lattice inputs are not qualified by this candidate.
    const val MAX_JAPANESE_SEGMENT_UTF16 = 16_384
}
