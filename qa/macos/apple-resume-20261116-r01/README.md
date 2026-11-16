# Native Mac qualification, 2026-11-16

These headless experiments ran on macOS 26.6, SDK 26.5, with networking
available. They are not iOS, offline, listening, linguistic acceptance or
production app/signing evidence. Candidate language data was injected only into
an isolated lookup harness and remains inactive.

- `evidence-r11.tar.gz`: current Swahili source with locally compiled, pinned
  eSpeak data rendered non-silent PCM for all 11 water-word samples. The mixed
  probe rendered 110/110 directed joined outputs and observed AVAudioPlayer start
  and stop. These authored words are not bound to emitted immersion spans; no
  human listened. The five core Swahili/phoneme hashes match retained data.
- `evidence-r12.tar.gz`: candidate 008-r04 pin
  `50185f45db3e3b7a8062eb936207782447213bb2547abf6d18adaccdaa0f9cb8`.
  Direct native provider results: 199/330 floor cases emitted across 110
  directions; untouched holdout-r01 192/330 across 104; holdout-r04 2/110
  across 2. Each run passed 31 carrier metadata checks. These are authored
  fixtures, not population coverage or automatic classification evidence.
- `evidence-r16.tar.gz`: Apple Translation lowLatency with the shared 18-case
  fixture (SHA-256 `7bb7aa2bb45fda9c1ae02c20b2bf721c93eb16e90117638789568c51b64f7dc8`).
  Sixteen pairs ran with installed models; two Swahili cases were unavailable.
  Only six returned a marked target run; only four selective outputs preserved
  the text outside the focus in order. Some results translated the whole text
  or reordered original text. Full-context English examples distinguished train
  and bank senses and the weather idiom, unlike isolated words. This small
  probe does not qualify a production immersion mechanism.

The tarballs retain raw receipts and logs, including a failed initial compile
with the default deployment target. `MixedSpeechProbe.swift` and
`AttributedTranslationProbe.swift` are the corresponding probe sources. No
new model downloads, signing, app startup or cloud translation were performed.
