# Bilingual supplied-token role qualification — completed

The frozen 32-pair test completed on production. Full-sentence POS evidence caught the noun/verb distinction in the `order→pedido` perfect-tense development control, but it also assigned noun tags to Spanish verbs. It is useful evidence, not a correctness gate or a complete name guard. No dictionary, selector or app was changed.

Both independent reviews were frozen before inference and before reading each other's judgments. All 39 source and 41 target focus-token role labels, and all 39 focus-relation compound/unassessable flags, agree. Original labels and rationales remain separate in the joined evidence; agreement is not gold labeling.

| Frozen stratum | Pairs | Source role matches | Target role matches | Source / target false noun rejections |
|---|---:|---:|---:|---:|
| Explicit development controls | 8 | 13/15 | 16/16 | 0/9; 0/9 |
| Dictionary noun/verb ambiguous surfaces | 8 | 8/8 | 8/8 | 0/8; 0/8 |
| Source-ID-hash audit diagnostics | 16 | 16/16 | 15/17 | 0/15; 0/14 |

The ambiguous-surface stratum does not necessarily contain difficult actual roles. Zero false noun rejections here is a result on 63 reference-noun tokens, not a corpus retention guarantee. These reused diagnostic witnesses and development controls do not estimate population accuracy.

All observed focus-role errors:

- Development case 004: English `New` in a place name was tagged ADJ, score 0.994, while both reviewers labeled PROPN.
- Development case 006: English personal name `Tom` was tagged NOUN, score 0.597; both reviewers labeled PROPN.
- Diagnostic case 017: Spanish finite verb `pediste` was tagged NOUN, score 0.718. The source `order` was correctly VERB, so a hypothetical both-sides-noun requirement still rejects that relation.
- Diagnostic case 025: Spanish finite verb `llamas` was tagged NOUN, score 0.698. The English `name` is a noun. A both-sides-noun requirement therefore falsely admits this cross-POS paraphrase as noun-pair evidence.

A separate hypothetical all-focus-tokens noun check retained all 29 reference noun-only relations and falsely accepted one additional relation, case 025. This is accounting only, not a projection or proposed all-token eligibility rule. Broad retained alignments include an article in case 007 and an adjective in case 027; making every aligned token a noun is itself too restrictive for those relations. Names and compounds are separately flagged. The packet does not test actual Dragon Ball Z title protection.

## Execution and provenance

The successful run tagged 64 complete endpoints / 554 supplied tokens, preserving all original token text and UTF16 geometry. Compilation plus execution took 2.011 seconds; inference/model loading/serialization within the JVM took 0.769 seconds. JVM VmHWM was 87,484 KiB and VmPeak 2,629,724 KiB. Annotations were 30,735 bytes, SHA256 `797f8cee4ec0719bb7b704d7f0d72a01196381e9c3454c12b77aa3049972b866`. No tokenization, sentence splitting, model training, parameter change or bulk corpus annotation occurred.

Private evidence is `/home/ai/Development/investigations/vipi-bilingual-occurrence-roles-20261109-r01/`. `joined-comparison.json` SHA256 `5cc6d24c13d3d78645e93df71e39de5185bd2acbd39cb23d11592265b3ca0c1b` includes every original review label/rationale, raw model role/score, every disagreement (none), individual errors and separate denominators. Models and runtime remain under the corresponding `/srv/fallsoft/staging/` experiment directory on production.

Spanish model provenance follows the [official OpenNLP inventory](https://opennlp.apache.org/models.html), with published SHA512 verified; its signature is retained but not cryptographically verified. The official distributed-model README/LICENSE is retained. The existing pinned English model and OpenNLP engine were reused unchanged.

The initial launch failed before compilation because production had no javac; its receipt/output remains intact. An Adoptium metadata request then returned HTTP 403 before archive transfer, also retained. Under root's explicit dependency authorization, the isolated official [Corretto 21 portable distribution](https://docs.aws.amazon.com/corretto/latest/corretto-21-ug/downloads-list.html) was acquired instead: resolved version 21.0.13.0.11, archive SHA256 `f3330bf440b8f4514b7b279b6145d4b4493dea9dda5f3a702b49c53c41bec1e4`, matching the official digest. All archive paths, member types and link targets were checked before extraction. Exact GPLv2/Classpath notices remain included. Regular extracted bytes: 364,679,387; retained archive/runtime: 573,923,728 bytes. Root-authorized r02 used absolute java/javac paths and a separate output directory; model, packet, harness and reviews were unchanged. No global installation or service change occurred.

## Candidate relation representation and decision

`direct-english-candidates.json` contains 17 evidence records from the already-retained native trace. It preserves foreign native entry/sense/gloss provenance, exact published English spelling/POS, every matching English entry candidate, and the old unique resolver result for comparison. The new record does not select an English entry or invent a source sense ID, including when the old resolver is unique. It is not a shipping edge and cannot authorize foreign-to-foreign pivoting. Aliases were not newly propagated; existing packed terms are unchanged.

The next bounded comparison should keep relation availability, actual occurrence roles and lexical choice as separate evidence axes. The new direct-English representation repairs an evidence omission without pretending it chooses a meaning; bilingual tags can detect some cross-POS leakage, but case 025 proves they cannot alone certify noun evidence. A later evidence pass may annotate the frozen existing occurrence cohort and report disagreements with dictionary and alignment evidence, retaining all raw tags and unresolved cases before any ranking experiment. This run does not authorize that pass. Name-span handling remains independent; a new blanket guard relaxation, confidence threshold or all-senses agreement gate is unsupported.
