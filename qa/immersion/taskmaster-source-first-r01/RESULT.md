# Frozen Taskmaster200 companion-producer comparison

The unchanged native companion-catalog/current-dictionary producer returned 61 nonempty messages and 79 emitted source words out of 200 messages / 1,587 words. Retained target-informed B returned 133 messages / 214 words. This is **not overall app coverage**: authored exact-reference and starter routes were not executed by this harness. No production policy changed or customer path activated.

All 200 original rows remain (185 unique source texts; 14 historical null translation rows). Inputs contained no target text; caller-known IDs were empty, function withholding false, density 0.25. The producer added 3 nonempty messages and lost 75 relative to B. There were 36 added and 156 lost spans, 117 changed messages. All 14 historical null-target rows remained empty here. Historical exposure makes this diagnostic, not a new population estimate.

## Independent agent judgments

| Reviewer / subset | Arm | Correct nonempty | Minor | Material | Uncertain | Empty |
|---|---|---:|---:|---:|---:|---:|
| Author / all 200 | Companion producer | 40 | 15 | 5 | 1 | 139 |
| Author / all 200 | Retained B | 113 | 7 | 11 | 2 | 67 |
| Root / 40 changed cases | Companion producer | 8 | 2 | 2 | 0 | 28 |
| Root / 40 changed cases | Retained B | 31 | 3 | 5 | 0 | 1 |

Author strict whole-message gains/losses were 10/83; allowing minor issues, 10/75. Root changed-subset strict gains/losses were 4/27; minor-tolerant 3/27. Empty output earns no usefulness credit. Added spans: 17 correct, 13 minor, 5 material, 1 uncertain. Lost spans: 138 correct, 5 minor, 11 material, 2 uncertain. Removing old errors by withholding is not a corrected translation.

Both review files were frozen before unblinding; the author's freeze was received before root's freeze. Reviewers were method/peer-blind, with disclosed historical familiarity with old outputs/targets. These are agent judgments, not native-speaker validation or gold. All original labels and six whole-option disagreements remain in the private join: help→ayudar twice (author material/root minor), eating→comer and fitness room→habitación (author correct/root minor), standalone Great→gran (author minor/root material), and Awesome→asombroso capitalization (author minor/root correct). No majority reconciliation.

## Concrete failure stages and provenance

All five author-material additions are **ordinary baseline** heads, not conditional noun rescues. Exact candidate, head/context IDs, source keys, train ranks, native roles, masks and selected ranges are retained in `joined-review.json` and `closure-audit.json`:

- Movie trailer→caravana comes from source key `a trailer`; the two-word context does not distinguish a preview from a vehicle.
- Additive too→demasiado occurs twice from unigram `too`; the actual Adverb tag cannot determine additive versus excess sense.
- Four→cuatro inside a place name comes from `four`. Native role is Noun; supplied/name protection did not cover that token. Other recognized names remain protected.
- Meal course→curso comes from `course`; actual Noun role does not establish the meal sense.

These are candidate-source meaning/protection gaps, not proof that every dictionary relation or context is invalid. Minor casing, gender/form and native-grammar disagreements remain separate. No new veto or replacement was tested.

The 139 empty messages have exclusive earliest-stage counts: 104 no candidate records, 24 no qualified candidates before current-tuple checking, 10 all selector inputs rejected, and 1 withheld by current-tuple evidence. Candidate rejection reasons overlap and must not be summed as message losses. The last case has supported price→precio forms/terms but `native_source_structural_protection` for the enclosing price-range unit; the mask survives. The private audit retains every empty case's candidates, gates, assessments, geometry rejection lists and selector reasons. No-record status is a producer matching result, not proof that a word is absent from all dictionaries or product routes.

A read-only committed-source routing audit found exact whole authored references for **21 of these 139 empty rows**, including Hi., Hello., Thank you., Yes. and Okay.; 39 empty rows have at least one exact native sentence reference. `ConversationImmersion.swift` supplies `BundledImmersionCatalog.reference/partial` to `LookupFirst` separately from source evidence. Catalog entries also include standalone Please/Please., but that does not authorize substring replacement in “Yes, please.” or arbitrary punctuation variants. Those reviewed extended please messages have no exact whole reference. This audit did not rerun routing or claim every reference produces nonzero immersion at this density (e.g. unchanged No.).

## Execution and retained evidence

One native run: preparation 2.276 s, build 18.380 s, tests 18.849 s. Tuple initialization 1,223.562 ms; first prepare/select 138.466/10.590 ms; subsequent median 26.356/10.128 ms. Aggregate prepare/select 5.585/2.035 s. Output 651,095 bytes; serialization 22.538 ms. No whole-process memory measurement is claimed. Two compiler jobs; frozen deadlines and disk bounds passed. Preferences restored, app stopped, source/dependencies verified, existing labs alive. No Translation calls.

The initial local collection stopped on an already-existing frozen runner file after native computation succeeded; the retained collection amendment verified existing bytes and collected the same attachment. A premature assembler invocation stopped on missing local output before packet writes. Neither incident reran native computation or changed policy. The closure audit's local reporting predicate was corrected to `selected_spans == 0` before final receipt; no engine or review changed.

Private evidence root: `/home/ai/Development/investigations/vipi-taskmaster-source-first-20261109-r01`. `completion-receipt.json` binds protocol, harness, runner, raw output, restoration/collection receipts, masked packets, frozen reviews, full added/lost span join and routing audit. Anonymous source/options remain physically separate from method keys. No further experiment, app edit or activation follows from this result.
