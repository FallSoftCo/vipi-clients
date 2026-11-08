Withholding catalog-function candidates supports the user's vocabulary-first/native-grammar direction, but this diagnostic does not establish a blanket quality improvement or an activation decision. It removes several problematic function substitutions, also removes valid content, and leaves defective constructions and meanings that the catalog calls content. It is a selection-policy comparison, not a claim that the user has learned those words.

The [assembler](assemble.py) reads the existing six-arm decisions at `none` and `all_function`; it never invokes a selector, tagger, model or reranking. It verified all 96 prior outputs, selected indices and candidate IDs exactly for the protocol's fixed 16 cases. The packet has the same 48 unique scope/target units, zero new units and zero newly selected replacements in any arm. Full prior dialogue, source/protection masks, before/after outputs and candidate evidence remain private. Assembly took 2.28 seconds, used 29.6 MB VmHWM and produced approximately 0.8 MB under the 60-second/256-MiB/16-MiB bounds; admission and final free space exceeded the 8-GiB floor. See [assembly receipt](assembly-receipt.json) for protocol, code and artifact hashes.

The [author reread](/home/ai/Development/investigations/vipi-function-withheld-comparison-20261108-r01/assembly-r01/author-review-r01.json) and [root reread](/home/ai/Development/investigations/vipi-function-withheld-comparison-20261108-r01/root-review-r01.json) preserve their original unit labels exactly. Both reread the complete after outputs with prior dialogue; neither found additional cross-unit defects beyond those inherited labels. Both had seen the earlier three-review comparison, so this is not fresh blinded independence. These reused, stratified TRAIN cases provide no population accuracy estimate. There is no majority gold, and the earlier labels are not edited.

Each row compares the same arm before → after withholding. The two reviewers agree on the minor-tolerant whole-output counts and paired gains/losses below. A pass requires nonempty output and no material, role, form, completeness or unresolved defect; minor form/register issues are permitted. Empty outputs never earn a pass.

| Arm | Nonempty whole passes /16 | Paired gains / losses | Empty outputs | Selected units | Removed / added units |
|---|---:|---:|---:|---:|---:|
| Original pool | 9 → 9 | 1 / 1 | 0 → 1 | 39 → 31 | 8 / 0 |
| Eligible links | 10 → 9 | 1 / 2 | 0 → 2 | 38 → 27 | 11 / 0 |
| Apple disagreement veto | 12 → 12 | 2 / 2 | 0 → 2 | 34 → 23 | 11 / 0 |
| Apple role required | 14 → 13 | 1 / 2 | 0 → 2 | 30 → 23 | 7 / 0 |
| OpenNLP disagreement veto | 12 → 12 | 2 / 2 | 0 → 2 | 34 → 23 | 11 / 0 |
| OpenNLP role required | 10 → 12 | 3 / 1 | 1 → 2 | 30 → 23 | 7 / 0 |

Case 018 gains a nonempty pass in every arm after an unresolved auxiliary is removed; several arms also remove a temporal-function defect there. Case 002 improves in both disagreement vetoes and OpenNLP required; case 009 also improves in OpenNLP required. Case 013 loses a valid nonempty output in all arms by becoming empty. Case 021 similarly becomes empty in eligible links, both vetoes and Apple required; it was already empty in OpenNLP required. No new replacement was introduced in these cases, so this comparison does not test the risk of new budget replacements elsewhere.

Valid content is lost, not merely defective or function-only material. The table retains reviewer-specific accepted-content counts. All accepted scopes here have one source-word cost, so counts also give accepted content words; divide by the common 205-source-word denominator for depth. For example, both veto arms end at 20/205 accepted content words under either reviewer.

| Arm | Accepted content units, author | Accepted content units, root | Removed defective units, author / root | Removed unresolved units, both |
|---|---:|---:|---:|---:|
| Original pool | 22 → 22 | 22 → 21 | 3 / 2 | 1 |
| Eligible links | 23 → 21 | 24 → 21 | 3 / 2 | 1 |
| Apple disagreement veto | 22 → 20 | 23 → 20 | 3 / 2 | 1 |
| Apple role required | 24 → 21 | 25 → 21 | 1 / 0 | 1 |
| OpenNLP disagreement veto | 22 → 20 | 23 → 20 | 3 / 2 | 1 |
| OpenNLP role required | 22 → 20 | 23 → 20 | 3 / 3 | 1 |

Both reviewers lose accepted content in case 014 unit 6 and case 017 unit 3 in every filtered arm. The root also counts case 014 unit 5 as acceptable content where present; the author calls it defective. In Apple required, the author additionally loses accepted content at 009:4, while root classifies that unit as function and instead counts the loss at 013:2 as content. Root also counts 013:2 as lost content in OpenNLP required. Original-pool withholding loses accepted content only under root's judgment, at 014:5. Unit ordinals here are one-based. These are inherited disagreements, not relabeling to favor the withholding policy.

Strict whole-pass counts differ because the author retains minor/cosmetic flags. In arm order above, author counts are 5→5, 6→6, 7→7, 7→7, 7→7, 6→7; root counts are 8→8, 10→9, 12→12, 14→13, 12→12, 10→12. The [comparison receipt](comparison-receipt.json) contains all normalized axis disagreements, paired case IDs, raw-label bindings, lost-content scope indices and word-depth denominators. The [private join](/home/ai/Development/investigations/vipi-function-withheld-comparison-20261108-r01/assembly-r01/joined-reviews-r01.json) retains both raw labels and the original whole-output evidence links; its reproducible private join script is hash-bound in the receipt.

This result supports treating native-grammar preservation as an explicit product policy, with its content/coverage tradeoff visible. It does not make the catalog's function/content labels authoritative: case 022's relation/degree confusion survives, and case 014's incomplete construction remains defective. Phrase-first construction completeness and target sense/form evidence are still needed. No corpus/model job was run, no old artifact was changed, and no catalog or application was activated.
