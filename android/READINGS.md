# Full-message reading guides

Full-message display uses exact authored readings first. If no authored reading
exists, Japanese uses the existing Kuromoji/IPADIC pronunciation and reading
features with Vipi's deterministic kana-to-Roman-letter conversion. Korean uses
a small spelling-based converter derived from pinned Unicode CLDR rules. Chinese uses the pinned marked-pinyin data and native phrase selection described
below. Arabic retains its existing authored-only Android path in this revision.

These are ordinary display guides. They do not replace original-script audio,
copying, stored messages, or translation. Users can switch between the guide and
original script, and use Listen for pronunciation. A missing reading leaves the
original script visible. This policy does not imply that the full translation is
semantically correct: translation and reading quality are separate concerns.

The per-conversation `FullReadingCache` keys exact text, language and policy,
coalesces identical work, remembers abstentions, and runs producers away from
rendering. Conversation/language/account lifecycle closes its owner; a stale
completion cannot publish into the replacement owner. Reading metadata can
arrive after the complete translation without resetting inline flip state.

Japanese preserves protected names, URLs, code and identifiers and withholds
unresolved Japanese script. It uses dictionary context, not a pronunciation
model. Recorded limitations include 一人 rendered `ichinin` where ordinary
context needs `hitori`, lexical segmentation and other contextual readings.
Repeated prolonged marks and unsupported terminal small kana can abstain. Kana
normalization preserves the original UTF-16 piece boundaries; the original
message itself is not normalized.

Korean encodes spelling rather than applying contextual sound changes. The
separate orthographic convention is described in
[NIKL section 3(8)](https://www.korean.go.kr/front_eng/roman/roman_01.do). It preserves
opaque literals and converts modern precomposed Hangul. Unprotected Hanja or
other unsupported script, decomposed/compatibility/archaic jamo and oversized
input/output withhold the complete guide. Chat shorthand and canonical
decomposed Hangul remain coverage limitations. The source is a mechanical
adaptation of `qa/immersion/korean-reading-cldr-r01`: object renaming and a doc
comment only, with `KoreanLetterRules.kt` byte-identical. The pinned Unicode
license ships in the app's Licenses and notices inventory.

Chinese packages the hash-verified 813,708-byte marked pinyin-pro 3.29.5
resource and MIT notice. Original dictionary tone marks, ü and neutral-tone
syllables survive export. The native phrase selector retains the upstream
probabilities and tie ordering. Thirteen explicit Traditional word equivalents
extend context coverage; no broad script conversion or tone inference runs.
Thirty-five reviewed word joins apply only when the chosen syllables match,
including `yīnyuè`, `yínháng`, `Chóngqìng` and `nǚ'ér`. Other output retains
syllable boundaries. Dictionary tones use the underlying orthographic convention,
not a promise to transcribe every spoken tone-sandhi change.

Unknown unprotected script withholds the complete guide. Names, URLs, identifiers
and code keep their original characters. The source script remains speech and
copy authority. The exact onboarding preview has separately authored tone marks;
it does not use the full-reading fallback. Other authored sentence and word
readings retain their existing precedence.

Contextual limits remain, including `还` in return contexts and colloquial
particles. `data/readings/chinese-quality-debt.json` preserves the older
assessment as historical evidence; its original counts do not describe the
revised table. The focused marked-reading regressions establish specified
behavior, not population accuracy or acoustic quality.

There is no new runtime model or dictionary download for these readers.
Kuromoji/IPADIC and its notices were already packaged. Japanese source supports
API 28 without an Android ICU 29 dependency; exact API 28 runtime and physical
hardware qualification remain separate release gates. Current emulator evidence
is API 35/x86_64, not an acoustic-quality or broad conversational-accuracy claim.

The debug-only supplied translator/readiness parameters support isolated native
UI qualification when a translation model is absent. Production defaults do not
supply them. In particular a fixed Korean or Chinese QA reference is not evidence that the
corresponding ML Kit model is installed or that a provider produced a correct translation.
