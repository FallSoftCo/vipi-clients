# Frozen short-conversation lookup experiment

This research batch did **not** increase automatic clean reach or content depth at the frozen beginner 10% setting. None of these targets is enabled in the apps. The unchanged starter control is a source-only Python projection, **not** the current native production pipeline or a translation-provider comparison.

The 50 source variants (35 sense groups) were selected from TRAIN frequency before targets or new contexts. Independent target authoring review left 34 Swahili, 46 Japanese and 44 Spanish variants available. Complete source sentences and strong punctuation boundaries were required; arbitrary prefixes, questions mapped to declarative statements, quoted messages and unsafe boundaries were rejected. Complete units exceeding the source-word budget were not forced into a single-word slot.

The original freeze remains intact. A root-approved amendment, made before sampling, permits familiar/repeated surfaces in unseen TEST conversations instead of excluding the very common phrases lookup is meant to reuse. The fixed sample has 80 different conversations and 80 distinct normalized texts: 26 short, 27 medium and 27 long messages. Three overlap TRAIN surfaces; one of these also overlaps prior seen surfaces. Seventy-seven overlap neither. The matcher sees only the selected message; preceding turns are review-only. BST persona role-play is not worldwide chat frequency.

## Primary result: unchanged 10% budget

Counts below tolerate minor form/register caveats, with material errors and uncertainty excluded. All 228 observed scopes were author-reviewed; the independently frozen 24-source subset covered 66 scopes across three languages. Agreement was 64/66, with two correct-versus-minor differences retained conservatively. No material errors were identified in this limited review; that is not a universal guarantee. All 74 supplied Japanese readings were inspected. Independent reviewers are agents, not certified bilingual human raters.

| Target | Clean messages /80 | Content messages /80 | Mean changed depth | Mean content depth | All function faces known |
|---|---:|---:|---:|---:|---:|
| Swahili | 64 | 28 | 9.60% | 3.38% | 28/80 |
| Japanese | 58 | 16 | 8.37% | 2.03% | 16/80 |
| Spanish | 55 | 11 | 8.33% | 1.41% | 11/80 |

Starter+short-units is identical to starter on these metrics. Strict clean reach is 56/54/51. Short-message clean reach is only 16/14/16 of 26, versus 26/26/24 of 27 long messages. Excluding all surface overlaps gives 62/56/53 clean messages out of 77. Unique-text and message-weighted views coincide because this sample has no repeated surfaces.

Complete references are available in 7/9/9 messages, including only one whole-message reference per target. Most are embedded sentences or over-budget complete units. These are reported separately and never credited as automatic flips. With I/and/but simulated known, reach falls to 49/39/28; with all function units known it falls to 28/16/11. The new short units add zero in every scenario. This does not qualify sustained progression.

The controlled Japanese positive/negative-question and knowledge/empathy probes are authored diagnostics, not held-out evidence. Their unchanged target responses demonstrate that a source-only formula does not infer missing conversational polarity or pragmatic context. The natural held-out occurrences were assessed in their actual review contexts separately.

## Retention and reproduction

`short-conversation-evaluation-freeze-r01.json` pins targets, the r03 starter and evaluator. `short-conversation-sampling-amendment-r01.json` pins the corrected sampling rule before new selection. `short-conversation-context-heldout-r01.json` retains exact source IDs, contexts, seeds and source hashes. The target compiler reproduced all three target files byte-for-byte; the sampler reproduced exact selected cases/contexts; evaluator output reproduced except measured elapsed time. See `short-conversation-reproduction-r01.json`.

`short-conversation-evidence-r01/manifest.json` binds eight exact gzip-compressed evidence files, including raw projections, label-free packets, both frozen reviews, joined metrics and authored contrasts (145 KB compressed). Decompress them into a disk-backed evidence directory with their `original_name`; check their `original_sha256`. Then run:

```sh
python3 summarize_short_conversation_r01.py --evidence /path/to/decompressed-evidence --out /path/to/reproduced-decision.json
```

The retained joined decision SHA256 is `35c68c7c810b3fbf0d7f8b9de065b86ed788d9b96522c3249d58fa99e44c1269`. Labels remain frozen; the join takes the more cautious independently assessed label without rewriting either review.

No native builds, new inference calls, runtime data promotion, or learning-efficacy claim are part of this batch. The 10% setting is the frozen beginner research arm; the actual app default is a separate policy question, not retroactively changed here.
