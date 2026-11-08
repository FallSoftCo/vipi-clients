# Small offline Arabic vowel restoration

This is a feasibility comparison, not an activated reader. `qualification.json`
retains the decision, concrete errors, source identities and measured limits.

The fixed forty inputs comprise sixteen retained diagnostics and twenty-four
authored conversational, ambiguity and literal controls. Rawi V2 INT8 and
Libtashkeel ran first. Ichkil 0.3 was subsequently added against the same inputs,
with the extension recorded before its output. This is an informed diagnostic,
not blind model selection or conversational population accuracy.

All models ran on one Linux CPU thread using ONNX Runtime 1.23.2. The largest
observed per-sentence first-call times after session loading were 4.52, 4.38 and
7.17 ms respectively. Model sizes were 2,469,528, 4,788,213 and 22,284,311 bytes.
Whole-process peaks include imports and runtime allocation; they are not native
mobile or incremental memory measurements. No training, GPU, playback or mobile
dependency change occurred.

Vowel restoration is practical at this size. Correct contextual reading remains
a separate question. All three have common-word errors in these examples. Raw
upstream normalization can also remove an emoji, overwrite supplied vowels or
insert marks into an Arabic URL path. Original messages and literal ranges must
remain authoritative. Source-aware authored readings should take precedence.
Any future ordinary Latin display must be qualified separately; these probes do
not produce an approved Latin guide or expose IPA in the product.

The pinned eSpeak language documentation restricts its Arabic support to fully
diacritized text. An available offline voice or a nonempty synthesized file does
not establish correct pronunciation of unvocalized Arabic. Android already
prefers an installed offline system voice before the bundled fallback.

## Reproduction and provenance

`retrieval.json` records exact primary URLs, immutable revisions, sizes and
SHA-256 values. Model weights, source dependencies and the Python environment
remain outside Git. The three compressed captures retain exact original bytes;
their decoded hashes are recorded in `qualification.json`.

For an isolated reproduction, copy this directory to a disk-backed working
directory, fetch the manifest's exact URLs into their relative paths, and verify
every size/hash before execution. Create a Python 3.12 environment with NumPy
1.26.4 and the recorded ONNX Runtime wheel. Run from that working directory.
The original probes refuse to overwrite their capture filenames; preserve the
retained evidence and use a fresh working directory. `probe.py` accepts
`rawi-v2-int8` or `libtashkeel`; `probe_ichkil.py` runs the third candidate using
the pinned pure text pipeline and direct local ONNX. The latter avoids the
upstream wrapper's automatic model-download path. Limit each process to 180
seconds and retain errors as well as successes.

Upstream licenses are declared Apache-2.0 for Rawi and MIT for Libtashkeel and
Ichkil. These declarations and the source snapshots are research provenance;
shipping a model still requires native packaging and distribution closure.

Primary sources: [Rawi V2](https://huggingface.co/TigreGotico/rawi-v2),
[text2tashkeel](https://github.com/TigreGotico/text2tashkeel),
[Libtashkeel](https://github.com/mush42/libtashkeel),
[Ichkil](https://huggingface.co/ichkil/ichkil), and
[Ichkil Python pipeline](https://github.com/Ichkil/ichkil-python).
