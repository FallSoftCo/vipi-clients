# Broader starter qualification — not promoted

The private JA 193-entry and SW 217-entry candidates add useful vocabulary, but neither is ready to promote unchanged. Both independent agents identified the same seven material source occurrences: company **Apple**, surname **Jobs**, and **school of fish** in each pair, plus Japanese replacement inside `coffee_today.txt` on Apple. These produce nine distinct material full-output options. Original candidates, inputs, outputs and labels remain frozen.

Each pair retained 231 inputs: 128 prior native examples, 79 historical conversation examples, and 24 authored contrast controls. These are reused or authored diagnostics, not population coverage. Three explicit exclusion states were retained; exclusions are not familiarity or mastery. Native source grammar with target vocabulary was intentional.

## Actual native execution

Both platforms completed 1,386 source/pair/state rows and 5,564 arm evaluations, including the source-only selected boundary densities. Each reproduced 1,536 retained direct outputs and 768 retained normal-route outputs. Current production loaders, sorting, packing, budget, guards and source assets were unchanged; private candidate files were injected only into the test harness. Translation/model calls were zero; local lookup providers were called throughout.

Android assembly took 57.90 seconds, instrumentation 75.105 seconds, and the complete boot/install/capture/cleanup stage 232.34 seconds. Fresh free space was 16.43 GB, with 1.177 GB reserved for capture; minimum observed free space was 16.40 GB. The 8 GiB floor was preserved. Raw Android output is 8,856,505 bytes. QA packages were removed, the main package was unchanged, and the owned emulator stopped. System settings were identical; secure settings acquired only `play_determined_dma_eligibility=0` during boot, retained explicitly without overwriting unrelated Play state.

Root's Apple execution passed in 18.81 seconds build / 57.02 seconds test command (32.25-second XCTest body), with an 8,754,380-byte raw attachment and restored preferences. Both use their own native tokenization. There are 78 geometry/budget differences across the main density cells and six output-difference cells, all from Apple accepting `coffee` inside the filename. Every platform-only option was included in the merged review packet.

## Availability and meaning are separate

The following normal-route figures use Android, empty exclusions, and all 231 inputs per pair. Apple agrees on the headline nonempty totals but has the additional filename error. Depth is covered original native words, not target-string length.

| Pair / density | Nonempty current → candidate | Native words current → candidate | Distinct traced concepts current → candidate |
|---|---:|---:|---:|
| JA / .25 | 172 → 190 | 289 → 340 of 2,336 | 43 → 77 |
| JA / .75 | 173 → 191 | 336 → 433 of 2,336 | 43 → 89 |
| SW / .25 | 191 → 200 | 351 → 374 of 2,318 | 67 → 87 |
| SW / .75 | 192 → 201 | 448 → 506 of 2,318 | 78 → 107 |

At .25, both reviewers judged 69 added JA units correct, six minor and three material. Packing displaced 26 prior units: author calls all 26 correct; root calls 25 correct and one minor. SW added 39 correct, one minor and three material units, displacing 20 correct units. At .75, additions were JA 88 correct / six minor / three material and SW 54 / one / three, with no lost units on Android. These are occurrence counts at a fixed state/density, not independent words or proof of deployment quality.

Whole-message strict nonempty judgments at .25 were JA current 165–167 → candidate 175–176 and SW 189–191 → 194–196 (reviewer range). Allowing minor issues gives JA 172 → 187 and SW 191 → 197; material outputs remain excluded. Paired minor-tolerant gains/losses are JA 15/0 and SW 7/1. Thus raw nonempty gains overstate acceptable-message gain.

With all current concepts excluded, Android candidates still emit in 63 JA / 39 SW messages at both main densities, versus zero current-pack messages. Root judged 54 JA / 36 SW strictly correct; minor-tolerant counts are 60/37. This is a tail-vocabulary diagnostic, not a learned-user state. Apple has one additional nonempty tail message from the invalid filename replacement.

Stratified counts are retained separately. At .25 on Android, root's historical 79 JA judgments change from 55 correct / two minor / 22 empty to 57 / six / 16; SW changes from 67 correct / 12 empty to 67 correct / one minor / 11 empty. All name and fish-sense errors are in authored controls; the filename failure is in retained diagnostic input. The authored controls must not be blended into a fresh-corpus accuracy claim.

## Independent agent review

The anonymous packet has 462 complete sources and 1,175 distinct full-output options, with exact duplicates merged only within the same source/pair. State, method, platform and provenance bindings are physically separate. Author: 678 correct / 26 minor / nine material / 462 empty. Root: 677 / 27 / nine / 462. Empty has zero usefulness. Neither review is native-speaker validation or semantic gold.

Four occurrence disagreements affect seven options: root marks JA wellbeing `okay` and opinion `think` minor where author preserves the prior correct judgments; author marks two restrained SW `oh → lo` uses minor where root accepts them. All original judgments/reasons survive in the joined evidence; no majority label replaces either reviewer. Existing hair specificity, Japanese kinship register, counted-year reading and holiday nuance remain visible.

Author froze before reading peer judgments or the method key. Root supplied aggregate nonempty counts before the author freeze, which is disclosed. Both had historical/design exposure. No labels were used to reselect examples or tune this frozen comparison.

## Provenance and remaining decision

Private evidence root: `investigations/vipi-starter-content-expansion-20261109-r01`. Key files are `native-inputs-r02/native-input-manifest.json`, both raw captures, `review-r01/anonymous-packet.json`, both frozen reviews, `joined-r01/joined.json`, `joined-r01/strata.json`, and `mechanics-r01/changes.json`. Complete added/lost spans and mixed outputs remain available.

The original preparation failed on raw known-snapshot equality: historical JA all-known includes Winter, whereas current and candidate packs both exclude it. Failed source/partial output remain intact. The additive amendment verifies the differing ID is absent from both packs, binds both snapshots, and claims only effective-exclusion/output parity—not identical cache identity. Native execution did not fail or replay.

See `CORRECTION_PROPOSAL.md`. No candidate pack or runtime correction is activated by this result.
