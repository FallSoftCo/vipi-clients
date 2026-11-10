# Test-only source-context result

Do not activate this revision. Direct phrase lookup gains are real in these finite cases, but composing its masks with the current whole-reference route removes many previously available outputs. Canonical runtime and shipped packs remain unchanged.

Both platforms completed 656 rows, 1,536 original-loader parity comparisons and 780 exact expansion geometry checks. All selected spans, references, masks and traces in the baseline reconstruction matched. Direct native budgets, nonoverlap, complete source words, 128-unit cap, known withholding, enclosing atomic/ambiguous masks and full-context literals passed. There were no translation/model calls. The 24 rows with native geometry differences produced zero platform selection differences.

Android build took 66.62 seconds, test body 142.12 seconds and complete owned capture 271.88 seconds. Its 2,202,927-byte raw output is retained. The minimum free disk was 15,309,725,696 bytes against the 8 GiB floor. Main app path and secure/system settings matched before/after; QA packages were removed and the owned emulator stopped (exit -6 recorded, not asserted to be a clean exit). Other emulators were untouched. Apple execution and state restoration are separately retained by root.

Each main stratum below has 80 case/pair rows. These are reused authored seed contexts and explicit controls, not population coverage. Excluding all current starter concept IDs is a synthetic exclusion state, not learned familiarity. Added/lost counts are span occurrences, including replacements; native word counts measure depth, not semantic correctness.

| Path | Pair | Exclusions | Density | Nonempty before→after | Native words before→after | Added/lost units |
|---|---|---|---:|---:|---:|---:|
| direct | en-ja | current concepts | 0.25 | 0→36 | 0→43 | 38/0 |
| route | en-ja | current concepts | 0.25 | 26→20 | 35→27 | 21/25 |
| direct | en-ja | current concepts | 0.75 | 0→48 | 0→69 | 51/0 |
| route | en-ja | current concepts | 0.75 | 26→22 | 36→33 | 24/26 |
| direct | en-ja | none | 0.25 | 67→73 | 70→83 | 40/32 |
| route | en-ja | none | 0.25 | 54→33 | 66→43 | 21/40 |
| direct | en-ja | none | 0.75 | 67→76 | 92→157 | 52/5 |
| route | en-ja | none | 0.75 | 54→34 | 72→67 | 24/28 |
| direct | en-sw | current concepts | 0.25 | 0→33 | 0→40 | 35/0 |
| route | en-sw | current concepts | 0.25 | 23→20 | 32→27 | 21/22 |
| direct | en-sw | current concepts | 0.75 | 0→45 | 0→66 | 48/0 |
| route | en-sw | current concepts | 0.75 | 23→22 | 33→33 | 24/23 |
| direct | en-sw | none | 0.25 | 73→76 | 78→87 | 36/32 |
| route | en-sw | none | 0.25 | 55→35 | 69→46 | 21/40 |
| direct | en-sw | none | 0.75 | 73→77 | 116→179 | 48/3 |
| route | en-sw | none | 0.75 | 55→36 | 79→78 | 24/24 |

All 1,384 changed platform/layer/state rows, their complete original sources and added/lost spans are retained in private `mechanics-r02/all-deltas.json`. Complete outputs are in both raw captures. The anonymous review merges duplicate complete outputs, preserving occurrence counts, rather than scoring repeated empties as useful output. SW piano remains unchanged/no frame usefulness; capitalized Sherehe/Nambari are not silently normalized.

## Actual route composition

There are 348 whole-reference-origin rows per platform. Of 196 baseline-nonempty→candidate-empty route rows, 192 remain LOOKUP_REFERENCE in both arms; 168 losses still have a nonempty direct candidate. The other four are the deliberately protected `@my dog` context in both pairs/densities. The original source-only branch is not responsible for those 192 reference losses.

Kotlin `LookupFirst.kt` resolves forward/composed references first, collects source evidence even on the hit, and uses evidence.partial only when forward is absent. Swift `LookupFirst.swift` follows the same contract. `SourceLookupEvidence.filterLegacy` denies legacy spans overlapping a recognition mask because legacy spans carry no approved output ID. Therefore identical target spelling does not rescue a newly masked reference output. For example, excluded-state .75 `I am looking for a hotel.` had hotel→ホテル on the baseline reference route; the direct candidate has the same approved face, but the candidate reference route is empty.

The smallest proposed correction is a test-only composition wrapper: on an existing exact/composed reference hit return the unchanged baseline evidence (re-enveloped under the adapter identity); invoke the frame adapter only when that reference path is absent. This preserves the prior reference route and its original protections instead of weakening masks or inventing approval IDs. It necessarily gives no new frame credit on a preempting reference hit. This proposal has not been implemented or run.

The independent summary initially applied the adapter floor budget to the unchanged reference route and failed. Original summary code/failure are preserved in `mechanics-r01`; corrected count-only accounting is in `mechanics-r02`. Existing .25 baseline reference outputs exceed the adapter floor budget in nine rows per pair/state (for example, door key costs two words in a five-word source). This is reported separately; no native policy or output was changed.

## Independent agent reviews

Both reviewers read all 156 full source/pair groups and 521 distinct complete options. Root: 345 compatible, 18 minor, 2 uncertain, 156 empty. Author: 353 correct, 10 minor, 2 material, 156 empty. Original reviews are frozen; there is no majority gold or native-speaker validation. Both had prior seed/design exposure; neither read method keys, peer labels or parallel witnesses before freezing.

Twelve option disagreements remain: six before-bed furniture/sleep nuances, two room-service compound splits, two Japanese Doctor-title uncertainties, and two quoted-label cases. Both reviewers flag ten inherited mid-sentence Sherehe/Nambari capitalization cases as minor. Author accepts the bed/room-service vocabulary in native grammar; root marks it minor. Root cannot establish that Doctor Smith denotes a physician; author judged the occupational reading compatible.

For `The label says "bank account".`, the new candidate frame emits account→口座/akaunti in both direct and actual routes; neither baseline emits it. Author treats changing reported literal wording as material. Root treats reversible reading-view vocabulary as lexically compatible, while recognizing exact-label use can matter. This is an unresolved presentation-policy disagreement, not an agreed wrong financial sense. Both labels remain unchanged.

Read-only UI tracing confirms that original text remains in result.original, Original/Show meanings and the continuous flips expose it, and “Copy original message” copies originalMessage/result.original in both clients. Ordinary text-selection Copy instead copies the currently visible mixed text. No new UI execution or blanket quote-protection change was made.

Next step is the narrow route-composition qualification above, after root review. No new content, target normalization, threshold change, translation call, native deployment or runtime activation is justified by this capture alone.
