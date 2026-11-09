# Apertium occurrence-role comparison — completed

The retained EN–ES morphology and contextual tagger supplied useful complementary evidence on the same frozen 32 pairs. It correctly distinguished Spanish verbal `pediste` and `llamas`, which OpenNLP tagged NOUN, and recognized `Tom` as a proper name. This is a diagnostic comparison, not a population accuracy claim or catalog approval.

| Stratum | Source exact-token mapping / matches | Target exact-token mapping / matches |
|---|---:|---:|
| Eight development controls | 12/15 mapped; 12 match | 13/16 mapped; 13 match |
| Eight dictionary-ambiguous surfaces | 8/8; 8 match | 8/8; 8 match |
| Sixteen source-hash diagnostics | 16/16; 16 match | 17/17; 17 match |

Both frozen reviewers agree on all original 80 labels and compound flags; their independent records were not edited or harmonized. Apertium maps 74 focus tokens to exact single lexical-unit spans, and all 74 match both reviews. All 63 reference-noun tokens remain assessable and correctly tagged, with no false noun acceptance or rejection on these cases. This does not establish corpus retention or translation correctness.

Six tokens remain explicitly unassessable under the frozen token mapping:

- `New York` and `Nueva York` are recognized as complete `<np><loc>` units, covering four original tokens. Their span evidence is retained, but a single multiword tag is not silently converted into four independently assessed token tags.
- `Fisher` is unanalyzed on both sides. Unknown morphology does not become a guessed name or noun.

## Where the evidence differs

For `pediste`, the finite-state analyzer supplies only `pedir<vblex><ifi><p2><sg>`; the contextual tagger retains it. For `llamas`, analysis retains both `llama<n><f><pl>` and `llamar<vblex><pri><p2><sg>`, and the contextual tagger chooses the verb in the full sentence. The latter is a real contextual disambiguation result, not a dictionary uniqueness shortcut. `Tom` has a proper-name analysis. The retained pipeline therefore fixes three OpenNLP focus errors while abstaining at token level on the fourth (`New` within the recognized name span). There are no new assessable errors relative to previously correct OpenNLP focus labels in this packet.

The distinction matters for the earlier bad `name→llamas` candidate: bilingual Apertium role evidence exposes the cross-POS paraphrase where the OpenNLP noun tags did not. It does not decide between same-POS translations, establish seasonal sense, or certify a bilingual relation. Existing candidate relation identities remain necessary, and name-span protection remains separate. The packet contains names/compounds, not a Dragon Ball Z title-protection test.

## Exactly what ran

Reused the previously verified 20-case private closure: Apertium 3.9.4-1build1, lttoolbox 3.7.6-1build1 and apertium-eng-spa 0.8.1-2. All 184 retained file identities were reconciled; 11,045,191 regular source bytes were staged privately on consolidated production. SCP expanded eight symlinks; their resulting bytes were verified against the exact retained targets. Current host libraries satisfied `ldd` for every executable. No dependency installation, download, rebuild or global/service change was needed.

Each of the same 64 full endpoints ran through `apertium-destxt`, directional `lt-proc …automorf.bin`, then `apertium-tagger -g -p …prob`. The retained modes contain no Constraint Grammar stage. This is finite-state morphology plus the existing pretrained HMM/Viterbi contextual tagger, not a newly authored rule system or an HFST experiment. `-p` preserves surface forms for alignment. No bilingual transfer, target generation or translated output was used as role truth. The [official POS description](https://wiki.apertium.org/wiki/Part-of-speech_tagging), [stream format](https://wiki.apertium.org/wiki/Apertium_stream_format), and retained tagger man page document these distinctions.

The runner captured all morphological readings and contextual choices before interpretation. Generic escaped-stream parsing matched exact surfaces left-to-right and mapped only one lexical unit with exactly the original token range. Multiword, split, joined-morpheme, unknown and unmapped-tag cases remain unassessable. No word-specific repairs were added. The complete streams, span maps and raw model comparison remain retained.

Execution: 192 stage processes, 3.565 seconds total, maximum observed child `/proc` VmHWM 42,250,240 bytes, parent VmHWM 19,857,408 bytes. Child memory was polled every 2 ms and is explicitly an observed maximum, not guaranteed sampling of every final peak. Bounds: one CPU, nice 10, 256 MiB address space, 120 seconds and 8 MiB outputs, with the 8 GiB free floor. Two preparatory read-only readiness failures are retained: manifest queried before transfer completion, then a relative documentation symlink lookup requiring path normalization. Neither launched an inference stage; the 64-endpoint run occurred once after complete verification.

Private evidence root: `/home/ai/Development/investigations/vipi-apertium-occurrence-roles-20261109-r01`. `joined-comparison.json` SHA256 `a6a9e07ede3fe74a1991f00a80eed6ca55981aea1ce287a4ff7e69b50d11c859` contains both original reviewers' roles/rationales, OpenNLP tags/scores, Apertium alternatives/choice and exact span accounting. Complete per-stage stdout/stderr remains on production under the corresponding `/srv/fallsoft/staging/` directory. `completion-receipt.json` binds the artifacts.

## Practical decision

This supports carrying finite-state alternatives plus contextual disambiguation forward as complementary occurrence evidence before learning lexical-choice rules. It specifically supports inspecting disagreement with OpenNLP and recognizing complete name spans without treating every surface match as a name. It does not support silently choosing whichever tool agrees with a desired translation, treating unknowns as safe, or relaxing dictionary guards globally.

A next bounded evidence pass could apply these unchanged stages to the deduplicated full endpoints already referenced by the frozen candidate-occurrence cohort, retaining both analyzers and disagreements before selecting any translation. Endpoint counts, streaming boundaries, output reservation and representative span-mapping checks should be frozen first; this task did not run or authorize bulk annotation. Same-POS target selection still requires the retained direct-English relation provenance and contextual parallel evidence. All 17 previously serialized direct relations and completed OpenNLP artifacts remain unchanged. No app or catalog activation occurred.
