# Arabic local diacritization candidate — research only

Ichkil v0.3 can run locally fast enough to investigate further. It is **not**
enabled in either app, and the model's output is not certified pronunciation.
Current live Arabic reading remains exact authored data only. Unseen Arabic
therefore still has a genuine reading-coverage gap; consonant-only romanization
or a cached demo does not resolve it.

The actual model is pinned to Hugging Face revision
`ff8783fff6f6986929d8986983279d2f307d7bed`, 22,284,311 bytes, SHA-256
`9779e1aca89cebc77a9b92037b7d700c422cdf6c3774d4883f4652f641f3f705`.
The exact vocabulary/normalization/I/O config, manifest and checksum file are
retained here. Inference-client source and MIT text are pinned to GitHub commit
`380cf89465fafa6341ab007532101e299d20bb53`. The model card declares MIT for the
ONNX/config; it supplies no separate model LICENSE file. Its manifest asserts
training commit `18ab3ce5bcde2f4097cdc05890b18346729ef435`, but the linked
`github.com/Ichkil/ichkil` training repository returned 404. That provenance gap
remains explicit; the client source does not prove the unavailable training tree.
See [the pinned model](https://huggingface.co/ichkil/ichkil/tree/ff8783fff6f6986929d8986983279d2f307d7bed)
and [client source](https://github.com/Ichkil/ichkil-python/tree/380cf89465fafa6341ab007532101e299d20bb53).

The 28 fresh qualification cases were frozen before first inference. Sixteen
have author-assessed MSA reference vowels; twelve separately examine ambiguous
speaker context, names, dialect, mixed Latin, supplied vowels and protected
literals. These are not copied from the upstream benchmark, independently
accepted Arabic references, or proven disjoint from all training text.
`qualification-results-r02.json` is the current full result. See
`projection-erratum.json` for a corrected research-wrapper whitespace bug; the
obsolete derived outputs were retired. No such code was deployed.

Measured on the existing native arm64 Mac, with pinned ONNX Runtime 1.32.0,
NumPy 2.5.5, CPU provider only and one inference thread:

| Measurement | Result |
|---|---:|
| Model load | 27.09 ms |
| Warm median across the fresh cases | 3.76 ms |
| Warm maximum | 5.05 ms |
| 1,024-character resource probe | 215.52 ms |
| Process peak RSS including Python/runtime/model | 192.36 MiB |
| Owned model/wheels/runtime/results on disk | under 150 MiB |

Matching official wheels were unpacked only inside
`/Users/Apple/Development/vipi-quality-20261117-r01/arabic-candidate`.
Nothing was globally installed, no application dependency changed, and no
message text was uploaded. This proves native macOS CPU execution; it does not
measure iPhone/Android latency, binary impact, battery or runtime operator
compatibility. Runtime/artifact hashes are in `pin-receipt.json`.

The upstream string API normalizes letter variants, strips existing vowels,
removes zero-width characters and collapses whitespace. It cannot replace the
user's text. The tested adapter constructs a mapped model view, then projects
new marks as derived metadata over unchanged original clusters. All 28 cases
retain exact source partitions, supplied vowel clusters, code, URLs and other
protected literals. Production would still need parity with the exact native
protected-range matcher, rather than the research Python matcher.

There are 13 differing letter-mark positions among 273 reference Arabic letters
in the sixteen author-assessed MSA cases. These differences include case,
interpretation and possibly accepted lexical variants; they are not a reliable
population error rate. More serious meaning risks are visible in the samples:
`رفع العامل العلم` was read as `رَفْعَ الْعَامِلِ الْعِلْمَ`, where the intended
new test meant raising a flag, and colloquial Egyptian/Levantine samples receive
forced MSA-like vowels. Names and unspecified speaker gender can admit multiple
readings. Raw model confidence is not an independent correctness guarantee.
Readable source/derived-script samples and per-case timings are retained.

A second native check tried Foundation `toLatin` only on unprotected Arabic
runs. Its output includes strings such as `dẖahaba ạlṭãbību` and superscript
nunation. That is unsuitable as Vipi's learner-facing reading guide. A reviewed,
conventional vocalized-Arabic renderer, plus explicit irregular-orthography
rules and honest abstention, is still required. The model alone does not solve
readable live transliteration. See `candidate-latin-results-r01.json` for the
actual output; it remains disabled.

Alternatives inspected from primary sources: [CAMeL Tools packages](https://camel-tools.readthedocs.io/en/stable/reference/packages.html)
list an 88.7 MB MSA MLE disambiguator plus 40.5 MB morphology database under
GPLv2; their Python/data/native integration and redistribution need assessment.
[Mishkal](https://github.com/linuxscout/mishkal) is GPLv3/Python with several
morphology/syntax dependencies, so it is not a small drop-in native path.
[Libtashkeel](https://github.com/mush42/libtashkeel) provides MIT Rust/C-callable
MSA diacritization and uncertainty controls; its exact model/runtime footprint
has not been measured here. ONNX Runtime documents [native mobile bindings](https://onnxruntime.ai/docs/tutorials/mobile/)
for Android Java/C/C++ and iOS Objective-C/C, but those are integration options,
not evidence this model has already been qualified on either mobile platform.
