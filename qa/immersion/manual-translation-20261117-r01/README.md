# Native manual translation engine, 2026-11-17

The new path translates an exact original-message selection independently of
immersion alignment. It accepts a word, phrase, or whole message and returns
its immutable request identity, original slice, translated script, optional
live reading, and actual direction within the configured pair. It performs no
lexical expansion, familiarity observation, vocabulary insertion or backend
request. It uses existing local translation/provider queues and existing
Chinese/Japanese/Korean/authored-Arabic reading producers.

`makeManualRequest` captures the owner generation. Request identity includes
exact original UTF-8 bytes, original UTF-16 bounds, message ID, pair, explicit
input language, selection generation and owner generation. Surrogate/composed
character splits and over-budget source messages are rejected. A later request
for that message supersedes the earlier one. Pair/input/account invalidation,
close and task cancellation suppress stale completions after every await.

Original context accepts the composer's 32,768-byte UTF-8 bound. A short word in
a long valid message is not rejected by the old 16k reader limit. Ambiguous
Latin direction uses whole original context, or a bounded original-context
window around long selections, rather than rendered hybrid text. Unique script
within the configured pair can route short Chinese/Japanese/Korean/Arabic
selections without an extra language confirmation. Ambiguous Han in a zh/ja
pair and uncertain language identification still need an explicit input choice.

Long selections are translated in bounded pieces of at most 8,192 UTF-16 units,
preferring word gaps and preserving composed-character and protected-literal
boundaries. Intervening whitespace and oversized opaque literals remain exact.
Whole-output literal integrity is verified. Reading metadata may be unavailable
for an output exceeding a reader's existing safety bound; valid translation is
still usable. That limit is explicit, not a claim of complete transliteration.
Native inference has one bounded request deadline. Memory-only provider-result
caches are bounded and do not enter the immersion/familiarity stores. Existing
reading caches continue to coalesce local metadata work.

The UI owns native selection-to-original mapping and playback lifecycle. A
single active user gesture should display the returned translation/reading and
play `targetText` in `targetLanguage` through existing native speech. It must
never speak the Latin guide, trigger audio from a stale result, or play after
dismissal, scrolling, backgrounding or pair change. No new Translate/Listen
confirmation is required by this engine. Playback and its stop control are UI
integration responsibilities, not implemented by the component probes.

The native macOS Swift CLI and host JVM probes both passed 15 focused component
checks, using actual production literal-integrity code and marked Chinese
reader/data. They cover arbitrary nonaligned selection, reverse direction,
context direction, explicit input, UTF-16/composed bounds, exact Unicode byte
identity, generations, missing models, literal integrity, stale completions,
timeout/cancellation, a word in a valid 30KiB original and long-message/literal
chunk preservation. Provider output is deliberately injected; these checks do
not certify native translation-model quality, app rendering or TTS playback.

The added app tests exercise the actual ConversationImmersion owner path,
packaged live pinyin and warm cache without aligned words; later-selection and
owner invalidation are also checked. Their integrated native execution remains
separate from the component results. No user phone, production account, model
download, dependency installation or store operation was used for this change.
