# Full-message reading guides

Full-message display uses exact authored readings first. If no authored reading
exists, Japanese uses the existing Kuromoji/IPADIC pronunciation and reading
features with Vipi's deterministic kana-to-Roman-letter conversion. Korean uses
a small spelling-based converter derived from pinned Unicode CLDR rules. Arabic
and Chinese retain their existing authored-only Android path in this revision.

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

There is no new runtime model or dictionary download for either reader.
Kuromoji/IPADIC and its notices were already packaged. Japanese source supports
API 28 without an Android ICU 29 dependency; exact API 28 runtime and physical
hardware qualification remain separate release gates. Current emulator evidence
is API 35/x86_64, not an acoustic-quality or broad conversational-accuracy claim.

The debug-only supplied translator/readiness parameters support isolated native
UI qualification when a translation model is absent. Production defaults do not
supply them. In particular a fixed Korean QA reference is not evidence that the
Korean ML Kit model is installed or that a provider produced a correct translation.
