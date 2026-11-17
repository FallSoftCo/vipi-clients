# Conventional vocalized-Arabic renderer — dormant candidate

The new Swift and Kotlin components render supplied Arabic vowels with readable
Latin letters. They are not diacritizers, do not predict absent short vowels,
and are not called by either production full-reading producer. The approximate
ONNX outputs remain research-only. There is no new runtime dependency.

General rules cover consonants, supplied short vowels, ā/ī/ū carriers, aw/ay,
shadda, tanwin, silent plural alif, sun/lunar articles, common attached prefixes,
and explicitly marked case endings. Initial hamza carriers omit a leading
apostrophe; internal hamza and ayn use an apostrophe. Tāʾ marbūṭa uses `t` with a
supplied ending and `h` for an unmarked final pause. The style uses th/dh/kh/sh/gh,
ḥ/ṣ/ḍ/ṭ/ẓ and macron vowels; it produces no IPA characters or ICU decorative
superscript output. It is a learner guide with wordwise forms, not continuous
speech transcription or full ALA-LC conformance. Character/vowel conventions
are informed by the [Library of Congress Arabic table](https://www.loc.gov/catdir/cpso/romanization/arabic.pdf);
our sun-article assimilation and case-ending policy are explicit adaptations.

Eleven word forms have explicit missing-long-alif positions, including `هَذَا`
→ `hādhā`, `هَذِهِ` → `hādhihi`, `لَكِنَّ` → `lākinna`, and `اللَّهُ` →
`allāhu`. These correct spelling conventions, not guessed short vowels or
arbitrary sentence matches. Sources include lexicographic entries for
[هذا](https://en.wiktionary.org/wiki/%D9%87%D8%B0%D8%A7),
[لكن](https://en.wiktionary.org/wiki/%D9%84%D9%83%D9%86),
[الله](https://en.wiktionary.org/wiki/%D8%A7%D9%84%D9%84%D9%87), and
[الرحمن](https://en.wiktionary.org/wiki/%D8%A7%D9%84%D8%B1%D8%AD%D9%85%D9%86).
Fully supplied vowels remain authoritative. Unsupported letters, contradictory
marks or unknown required vowels withhold the whole guide. For example `كتب`
and partially marked `كَتب` abstain; the renderer does not invent `kataba`.

Source UTF-16 pieces partition exact original bytes. Punctuation, whitespace,
emoji, Latin names/accents including decomposed forms, URLs, filenames and code
remain exact. Metadata normalization does not rewrite original script. Source
script remains TTS authority; there is no audio/model integration here.

Both actual native macOS Swift and host JVM Kotlin component executions passed
52 focused regressions with identical readings and source partitions. These
include all sixteen supplied-vowel frozen MSA references, general/novel vocalized
words, eleven lexical spellings, shadda/tanwin/long vowels/articles/prefixes,
protected mixed text and honest abstentions. This is component parity and
specified behavior, not native mobile execution or independent Arabic linguistic
acceptance. The untouched inference outputs are compared separately in
`readable-renderer-review.md`; the renderer does not disguise wrong predicted
vowels. Two model-derived cases remain unresolved: missing initial vowels and
unsupported Persian variants.

This supplies a small general native rendering stage rather than a catalog of
fixed sentences. A complete live Arabic path still needs reviewed diacritization
quality, original-to-model range parity on both mobile platforms, operator and
latency/memory qualification, and independent language review before enabling
probabilistic metadata. No such activation is claimed by this experiment.
