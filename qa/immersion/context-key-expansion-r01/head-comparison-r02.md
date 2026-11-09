Expanding context keys supplied additional vocabulary replacements, but this diagnostic does not establish better general accuracy or justify activation. Both independent reviewers agreed on the 46 emitted-unit labels and 48 whole-output labels. Their original notes and author-specific axes remain intact in the [private joined review](/home/ai/Development/investigations/vipi-context-key-expansion-20261109-r01/head-preparation-r01/joined-review-r01.json); agreement is not gold truth.

The paired raw inventory covers all 9,535 reused TRAIN messages per withholding state, at 25% density. These are emitted words and nonempty messages, not semantically approved coverage.

| Withholding state | Nonempty fixed → expanded | Emitted words fixed → expanded | Changed paired outputs |
|---|---:|---:|---:|
| Catalog function words | 4,398 → 4,557 (+159) | 6,014 → 6,362 (+348) | 512 |
| Function words + first 300 families | 2,729 → 2,876 (+147) | 3,274 → 3,501 (+227) | 331 |

No paired output lost emitted-word depth, so the frozen no-backfill policy produced 24 review cases rather than 32. That does not mean all previously valid vocabulary was retained: different focuses or forms can replace one another at equal depth.

The 24-case changed-output sample is stratified and deliberately includes eight empty-to-nonempty gains. Both reviewers independently reported:

| Whole-output criterion | Fixed | Expanded |
|---|---:|---:|
| Strict, nonempty, all units correct | 12/24 | 17/24 |
| Nonempty, correct or minor issues only | 14/24 | 22/24 |
| Material-error outputs | 2/24 | 2/24 |
| Empty outputs; zero immersion credit | 8/24 | 0/24 |

Strict paired outcomes comprise eight gains and three losses. Minor-tolerant outcomes comprise eight gains and no losses. Among the 16 cases where both arms already emit something, strict outcomes decline 12→10 while minor-tolerant outcomes improve 14→15. This narrower comparison matters: the overall count gain is substantially driven by new nonempty outputs.

Seven of eight sampled new nonempty outputs were judged correct; case 003 introduces a school-level term for the explicitly discussed university. Case 017 fixes additive versus excessive-degree “too.” Case 021 still misreads the equality construction “just as bad”; lowercasing the target is not a semantic fix. Longer contexts also introduce plural agreement, gender agreement and capitalization defects in 018–020. Case 009 improves the contextual fit of “wrong” but retains a shared plural-adjective issue; neither reviewer counted that as a material-error repair.

At exact focus/target/reading identity level, expansion adds 20 correct,3 minor and 2 material units, removes 8 correct,1 minor and 2 material units, and retains 8 correct plus 2 minor units. These are replacements as well as additions: one added material identity is merely the lowercased version of the already wrong 021 target. Removing eight correct identities is not eight lost concepts: wife/habit synonyms remain valid, and 013 relocates the same boy vocabulary. Cases 011 and 022 do displace valid interesting/lazy vocabulary with other valid focuses. All these original judgments are retained, with no unit-label or normalized whole-output disagreement to reconcile.

The practical result supports continued work on context-assisted content-head selection. It also shows that longer context is not a sufficient meaning or form gate. The present noun/adjective/adverb single-token, role-required, dictionary-linked policy remains incomplete and research-only. No raw phrase emission, runtime change or activation occurred. A later decision should address the observed sense/form failures and test real whole-message retention; these 24 cases do not estimate population accuracy.

Execution reused the exact existing fit/extraction and passed all 43,797 fixed variant rows plus component membership. r02 completed 19,960 context proofs in 274.37 s/127.4 MB peak memory, projection in 121.57 s/142.0 MB, and packet assembly in 1.90 s/123.4 MB. The 317.15 MB head database and full decisions remain on production. The failed r01 database matched all 5,648 retained context rows/blobs and 713 head rows against r02 before its narrowly authorized retirement; failure, size and equivalence receipts remain. [Execution receipt](head-execution-receipt-r02.json) and [joined counts/inputs](head-joined-review-receipt-r01.json) bind the artifacts.
