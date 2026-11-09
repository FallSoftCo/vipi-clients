The single frozen Tatoeba fit and phrase extraction completed. It produces variants for 5,816 of the same 8,000 source keys versus 5,752 in the unchanged PGV control. That small overall increase hides a shift from unigram availability toward longer source spans; it is not a translation-quality or reusable-construction result.

| Native source-key length | Shared | Tatoeba only | PGV only | Tatoeba available | PGV available |
|---|---:|---:|---:|---:|---:|
| 1 | 2337 | 119 | 333 | 2456 | 2670 |
| 2–3 | 2564 | 632 | 446 | 3196 | 3010 |
| 4–8 | 55 | 109 | 17 | 164 | 72 |
| Total | 4956 | 860 | 796 | 5816 | 5752 |

Neither corpus produces a retained variant for 1,388 keys. Length buckets use the frozen native source-key costs; extraction still uses the exact prior token geometry and caps. This is source-key availability, not message coverage. All target variants, individual observations, expansion geometry and provenance remain available for review.

Root approved the exact [fit plan](fit-plan-r01.json) and [adapter](fit_phrases.py) before launch. Production ran one five-iteration forward fit, one reverse fit and one `grow-diag-final-and` symmetrization in 6.29 seconds; the largest sampled child RSS was about 89 MB. Phrase extraction took 27.49 seconds with 80.4 MB process VmHWM, retaining 217,484 observations including 17,080 boundary expansions. Its lexical-score calculation explicitly recorded 88,337 missing exported parameter lookups using the unchanged probability floor. No probability is called semantic confidence. Phrase artifacts total about 58.7 MB; no source corpus or full candidate database was restored locally.

The adapter loads only the exact hash-bound pure geometry/scoring functions and normalizer from retained source AST nodes. It never imports the old hardcoded driver or changes its globals. Ten original phrase tests and two adapter tests pass. Input hashes, per-stage create-only receipts, resource bounds and artifact hashes are in [execution receipt](fit-execution-receipt-r01.json). The PGV alignments and candidates remain unchanged.

The source-only comparison completed in 2.59 seconds at 50.8 MB VmHWM. Its deterministic source-key selection produced all 32 proposals with no bucket shortage; exact keys were frozen before any target proposal was inspected. The [private packet](/home/ai/Development/investigations/vipi-tatoeba-domain-comparison-20261108-r01/review-evidence-r01/review-packet.json) retains full parallel sentences, all ranked variants, each chosen supporting observation and the entire emitted phrase. The shown mixed output replaces one phrase only; it is not a budgeted native runtime projection. Author and root labels were frozen separately before the [semantic comparison](semantic-comparison-r01.md).

The comparison remains diagnostic: Tatoeba's 40,000 pairs average about 7.9 English tokens versus PGV's 21.0, and one retained Tatoeba component contributes 4,478 pairs. Tatoeba has no full-text overlap with the PGV control or expanded exclusions, while the unchanged PGV control includes 44 subsequently reviewed pairs. These are explicit corpus differences, not a randomized domain effect or held-out accuracy estimate. No new projection grid or catalog/app activation occurred.
