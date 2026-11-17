# Native translation and speech findings

November 17, 2026. Actual installed Apple low-latency translation models on native macOS, using the committed manual resolver. Fifteen newly authored examples, with no authored dictionary/reference result injected. This is a targeted failure probe, not a conversation-coverage or accuracy benchmark. The original execution receipt pins the exact source hashes.

Thirteen examples returned translations and two Swahili directions reported unsupported. Word-by-word translation produced `Libro` for “book” in “book a table,” and `Gafas` for drinking glasses. Full-sentence translation correctly returned `reservar` and `vasos`. Both isolated and full-sentence translation incorrectly rendered the bird “crane” as a machine. A successful API return is not evidence of semantic correctness.

Actual attributed full-sentence translation did not provide universally usable word mappings: the Chinese “tomorrow” projection included “you,” Korean “music” included its particle, and French “chat” had no projection. These spans must not be presented as proven word equivalences.

The resulting implementation direction is to retain direct, context-backed immersion-word flips. For a manual selection without such a mapping, translate its enclosing complete sentence(s), and display that actual source context beside the translated context. Keep the original tapped range for anchoring, cancellation and request identity. Do not label a translated sentence as the translation of one word. This avoids the demonstrated loss of context; it does not eliminate errors made by the local translation model.

The Chinese results generated live Latin guides with tone marks. Japanese and Korean generated their existing lexical/orthographic guides. These guides are not phonetic guarantees; for example, the Japanese output retains orthographic `ha` for the particle は. Original-script audio remains the pronunciation path.

The separate production `LocalVoice` probe rendered all six emitted Chinese, Japanese and Korean targets to nonempty PCM audio. It passed the actual target script, never the Latin guide, to the selected installed language voice. Render time was 0.23–0.53 seconds for these samples. The receipts include voice IDs, locales, duration, sample rate and peak. This proves native macOS file synthesis of those outputs; it does not prove mobile gesture behavior, acoustic quality, offline-network isolation, all language pairs or seamless device playback.

No account, store, purchase, message, production configuration or provider mutation occurred. No model downloads were requested. The network was not disabled during these local API probes. The iOS simulator separately reported English–Spanish translation unsupported, so simulator gesture screenshots must not be counted as actual translation inference evidence.

Files: `cases.json`, `NativeManualProviderProbe.swift`, `execution-r01.json`, `results-r01.json`, `EmittedSpeechProbe.swift`, `run-emitted-speech-r01.py`, `audio-execution-r01.json`, `audio-results-r01.json`. Original native audio remains under `/Users/Apple/Development/vipi-quality-20261117-r01/native-manual-provider-r01/emitted-speech-r01/`.
