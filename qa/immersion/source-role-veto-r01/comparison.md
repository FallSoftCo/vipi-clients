The fixed-pool experiment supports occurrence POS as a useful veto, but does not justify activating any arm as a semantic acceptance policy. It removes genuine noun/verb mistakes and also removes correct substitutions. Required-role filtering gives the strongest result in this selected packet on Apple; neither tagger resolves same-POS meanings, complete constructions, target forms or protected names. Keep phrase-first, construction-complete lookup as the main direction and treat role evidence as one constraint on its word fallback. No catalog or application was activated.

The single projection reproduced all 95,350 original decisions exactly before ablation, including rejected candidates, masks and budgets. It processed 9,535 reused TRAIN sources × two pairs × five known states in 241.1 seconds, with 218.5 MB VmHWM under the frozen resource bounds. The [projection receipt](projection-receipt.json), [protocol](comparison-protocol.json) and [sampling policy](review-selection.json) bind the run. No projection was repeated for this comparison.

The independently frozen [author review](/home/ai/Development/investigations/vipi-source-role-veto-20261108-r01/projection-r01/author-review-r01.json), [root review](/home/ai/Development/investigations/vipi-production-delivery-20261107/source-role-veto-root-independent-review-r01.json) and [Apple review](/home/ai/Development/investigations/vipi-apple-delivery-20261107-r01/source-role-veto-r01/apple-independent-review-r01.json) cover all 32 whole-output cases and all 77 union focus/target units. Their hashes, complete disagreement listing, per-pair results, transition case IDs and all five-state raw metrics are in the [comparison receipt](comparison-receipt.json). Original labels and notes are retained in the [private join](/home/ai/Development/investigations/vipi-source-role-veto-20261108-r01/projection-r01/joined-reviews-r01.json); the original reviews and earlier 96-case labels are unchanged. No majority label is created.

These are agent judgments on a changed-case diagnostic sample, not bilingual gold, held-out accuracy or population coverage. Empty outputs count as empty, never successful useful output. The minor-tolerant normalization permits minor grammar/register issues, but rejects material meaning, wrong lexical role/form, incomplete units and entity/idiom changes; any uncertainty blocks a pass. Author form combines role and form, so a separate role label cannot be reconstructed. Author completeness often includes role mismatches that the other reviewers classify as complete units with wrong roles. Raw axes remain available rather than being silently equated.

| Arm | Selected units | Nonempty whole passes, minor-tolerant (all three independently) | Empty outputs | Strict whole passes author / root / Apple |
|---|---:|---:|---:|---:|
| Original complete pool | 67 | 21/32 | 0 | 13 / 19 / 18 |
| Eligible links only | 61 | 22/32 | 1 | 14 / 21 / 19 |
| Apple disagreement veto | 53 | 23/32 | 4 | 13 / 21 / 20 |
| Apple role required | 45 | 26/32 | 4 | 14 / 25 / 25 |
| OpenNLP disagreement veto | 54 | 24/32 | 3 | 14 / 22 / 21 |
| OpenNLP role required | 47 | 23/32 | 4 | 14 / 21 / 22 |

Same-case gains and losses below are changes in nonempty minor-tolerant whole passes, not merely fewer flagged substitutions. Each reviewer independently yields these transition counts. Emptying a previously defective output is not a pass gain.

| Comparison | Pass gains / losses | Removed units | Introduced units | Introduced defective units, each reviewer |
|---|---:|---:|---:|---:|
| Original → eligible metadata | 1 / 0 | 11 | 5 | 1 |
| Eligible → Apple veto | 3 / 2 | 9 | 1 | 0 |
| Eligible → Apple required | 6 / 2 | 20 | 4 | 0 |
| Eligible → OpenNLP veto | 3 / 1 | 8 | 1 | 0 |
| Eligible → OpenNLP required | 4 / 3 | 17 | 3 | 1 |

The metadata control alone removes four defective units and six acceptable units, plus one unresolved unit (categories can overlap for some reviewers), and introduces one defective plus four acceptable units. It fixes case 017, empties the title-related case 020 and introduces a temporal-function error in case 018. This improvement cannot be attributed to NLP.

Both vetoes repair whole outputs in cases 001, 006 and 008. Both lose a correct output in 003; Apple also loses 004. They remove a correct predicate adjective in 005 without making the remaining output defective. Required-role filtering repairs the possessive-versus-noun collision in 011, which both disagreement-only arms retain because the tag is outside the mapped classes. OpenNLP required introduces a temporal-function error in 009 through a newly admitted budget replacement; checking only deleted units would miss that regression. Apple required still has a defective construction in 014 and an unresolved or defective target auxiliary form in 018. These are reasons to preserve whole-output review, including the candidates newly selected after a veto.

There are 48/77 units with at least one normalized axis disagreement, including utility and cosmetic/minor judgments. The strict-pass columns must therefore remain separate. Material/uncertainty disagreements are concentrated in the following units (unit ordinals are one-based):

| Case:unit | Author | Root | Apple |
|---|---|---|---|
| 014:5 | Defective auxiliary substitution | Compatible lexical substitution | Defective auxiliary substitution |
| 017:2 | Material role/form mismatch | Wrong form, role uncertain | Meaning correct, role/form wrong |
| 018:4 | Unresolved target auxiliary | Unresolved target auxiliary | Material auxiliary mismatch |
| 020:1 | Defective title substitution | Defective title and form, role uncertain | Defective title substitution |

The receipt lists every other disagreement by case, zero-based union index and axis, including the original normalized values. Utility varies substantially: accepted content-unit counts across the six arms are 45/42/39/39/40/39 for author, 45/43/40/40/41/40 for root, and 35/33/33/34/33/33 for Apple. Thus identical whole-pass totals do not establish identical useful-content judgments.

Raw catalog-classified content reach remains broad, but it is not semantic coverage. Each cell is messages with at least one catalog-content substitution out of 9,535, shown as no known vocabulary / function-plus-global300 known state:

| Arm | English–Spanish | English–Swahili |
|---|---:|---:|
| Original | 8865 / 6235 | 6872 / 3181 |
| Eligible links | 8758 / 6111 | 6784 / 3091 |
| Apple veto | 8398 / 5675 | 6137 / 2776 |
| Apple required | 8197 / 5539 | 5933 / 2685 |
| OpenNLP veto | 8390 / 5661 | 6147 / 2802 |
| OpenNLP required | 8192 / 5481 | 5966 / 2655 |

Only noun, verb, adjective and adverb classes were mapped. Closed classes, proper names and composite tags remain unassessed; a disagreement-only arm can retain a bad noun under a pronoun tag. Eligible links include direct-English nonexplicit links and do not require target POS equality or source-safe flags. Neither a shared dictionary link nor an occurrence POS match proves target meaning/form correctness or dictionary completeness.

The practical next decision is to use this as evidence for an explicit occurrence-role constraint and for reviewing replacement effects, not to turn role compatibility into approval. Before an actual production gate is chosen, retain the existing source/protection masks, address unassessed roles deliberately, and verify construction completeness and target-form evidence in the phrase-first path. A broader independent, conversational holdout with representative sampling and target-language review is still needed to estimate useful coverage and errors. This report proposes no new job or threshold and does not revive the rejected strict all-sense strategy.
