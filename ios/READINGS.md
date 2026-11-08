# Full-message reading guides

`ConversationImmersion` asks `FullReadingCache` for display metadata after a
complete translation is available. This work runs outside SwiftUI rendering;
the original script, audio and copy action remain usable while it completes.
The exact text, language and reader policy identify a cache entry. Conversation
changes discard stale results. Repeated flips read the cached value.

Reviewed entries in `data/examples/sentence-readings.json` take precedence.
For an unauthored Chinese target, `ChineseFullReading` uses the ordinary,
tone-free pinyin data from pinned MIT `pinyin-pro` 3.29.5. The native Swift
implementation preserves the qualified upstream phrase-selection behavior;
it requires no JavaScript runtime or network model.

The app resource is `data/readings/chinese-ordinary.json` (773,812 bytes,
SHA-256 `1d6d270bdf6dbb7eefdf35f5b5f40358e3e4013b950ba431b90f5db4f6e48acc`).
The parser verifies its hash, size and schema. A missing or changed resource
leaves reviewed authored readings usable. The source archive, exporter and
complete MIT notice are retained in `qa/immersion/chinese-reading-upstream-r01`;
`data/readings/chinese-ordinary.provenance.json` gives the reproduction route.
The same complete notice is included in the app's Third-party notices.

Protected identifiers, URLs, names, numbers and code retain their original
bytes. Unknown unprotected script, invalid ranges and input above 16,384 UTF-16
units do not produce a full guide. This protects content; it does not establish
contextual pronunciation accuracy. Source-script audio is the pronunciation
authority, and the guide never becomes speech or copied message content.

The retained 332-message diagnostic exposed ten contextual syllable-error
messages, alongside readable results and explicit abstentions. It is reused
research evidence, not a population accuracy estimate. The error classes and
informed-review provenance are retained in
`data/readings/chinese-quality-debt.json`; no sentence-specific corrections were
added to pass those cases. Broad suppression of every multi-reading character
was rejected because it also hid many useful readings.

Native coordinator, display and delayed-reading timeline receipts are under
`qa/immersion/apple-full-reading-*`. Simulator UI checks use supplied targets
or authored references; they do not prove fresh Apple translation or physical
device inference. The full-reading metadata path and the translation provider
are separate qualifications.

For an unauthored Korean target, `KoreanFullReading` uses the operating system's
Core Foundation Hangul transcription. Its spelling-based convention retains
hyphens and invariant consonants; this is the reversible convention described
in [NIKL section 3(8)](https://www.korean.go.kr/front_eng/roman/roman_01.do),
not a promise of pronunciation-oriented Revised Romanization. Reviewed authored
readings still win. No additional dictionary, model or download is required.
Modern precomposed Hangul is supported; unknown unprotected Hanja, compatibility
or conjoining Jamo, and other untranscribed scripts abstain. Protected literals
and exact source ranges remain intact. The frozen native qualification and its
limits are recorded in `qa/immersion/apple-korean-reading-qualification-r01.json`.
