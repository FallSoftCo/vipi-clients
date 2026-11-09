The narrow source-name exception recovered useful content in this diagnostic, but also admitted a wrong noun sense and split a named title. It is not ready for activation. All original baseline decisions matched exactly; both frozen reviews remain intact and their one disagreement is preserved.

Across the 9,535 reused TRAIN messages, the mechanical results were:

| Known-state policy | Nonempty baseline → experiment | Emitted source words baseline → experiment |
|---|---:|---:|
| all_function | 4,557 → 5,855 | 6,362 → 9,091 |
| all_function_global300 | 2,876 → 3,468 | 3,501 → 4,415 |

These are availability counts, not translation accuracy. Catalog eligibility increased from 2,556 to 4,036 heads, with 1,480 additions and zero baseline competition losses. The complete original 9,535 traces—including both original arms and known states—matched field-for-field before any result was credited.

The predeclared review selected 24 changed outputs, 12 per known state. Both loss strata were empty; their eight slots were not backfilled. Root and author independently reviewed all 45 union emissions and 48 full outputs in this sample, plus the separate exposed controls. Both reviewers counted 26 correct added emissions and three materially wrong additions across two messages. The wrong additions were the season *fall* emitted as *caída*, and both words of the lowercase title *Dragon Ball Z* translated as ordinary nouns. The season candidate used context key `the fall`; the title candidates used unigram keys. High noun scores and lowercase source spelling did not resolve either failure.

| Sampled whole-output outcome (24 case-state records) | Baseline | Experiment | Paired gains / losses |
|---|---:|---:|---:|
| Strict nonempty, both reviewers | 6 | 17 | 11 / 0 |
| Minor-tolerant nonempty, root | 9 | 20 | 11 / 0 |
| Minor-tolerant nonempty, author | 8 | 19 | 11 / 0 |

The experiment removed one previously material additive `too→demasiado` emission when the selector chose a correct noun instead. No reviewed correct emission was lost. Existing errors also survived: another additive `too→demasiado`, the generic fighter mapping inside the bullfighter profession, and minor form/agreement issues. Correct added nouns do not approve those complete outputs. Zero paired strict losses does not mean no newly introduced errors: the two new material-error messages started with empty baseline outputs.

The sole unit disagreement is case `name-scope-013`, `tight→apretada`, retained in both arms. Root calls it minor: financial constraint remains understandable, with poor collocation and feminine agreement. Author calls it material: the physical-lid witness does not adequately support the financial idiom. Both reject a strict pass. This creates exactly two whole-output disagreements, one for each arm's minor-tolerant result. Original labels and rationales are retained, without a majority decision. Empty outputs normalize to empty for comparison; the author's original `correct` plus `nonempty=false` records are preserved and receive no immersion credit.

The 12 previously exposed sources appear under both states as 24 separate development controls. Baselines are all empty; experimental outputs are nonempty and judged correct in five all_function controls and two global300 controls. These contain nine emitted case-state units, representing the six inspected noun mappings. The brand example, grammatical controls and missing-link/context examples remain unchanged. That is mechanism evidence on exposed examples, not fresh validation of name safety.

Execution completed in 17.27s / 60.23MB VmHWM for catalog, 124.71s / 142.07MB for projection, and 1.57s / 87.61MB for packet. Catalog is 25,784,320 bytes; decisions 21,809,866; packet 1,841,454. R01's failed prefix and all receipts remain retained. No application/catalog activation or cleanup occurred.

The frozen packet is [private review evidence](/home/ai/Development/investigations/vipi-source-name-scope-20261109-r01/r02-evidence/packet-r02/review-packet.json), SHA `683deace2caefe33addba06053a622f019f44095c742382c150ad8ad97c15c81`. The [joined review](/home/ai/Development/investigations/vipi-source-name-scope-20261109-r01/joined-review-r01.json) preserves every raw judgment. [result.json](result.json) contains per-state paired counts, disagreements and execution receipts; [join_reviews.py](join_reviews.py) binds and verifies the inputs.

Next proposed diagnosis—read-only, not executed: determine whether the retained alternatives supply an existing correct target choice and contextual evidence, separately from title-span protection. Freeze the complete 1,480 newly eligible head IDs for an alternative-availability census; count distinct retained target variants per source key while explicitly distinguishing whole-phrase spelling diversity from actual noun-head alternatives. Inspect all 29 added sampled emissions, including all 26 judged correct additions as comparators, using exact retained variant IDs, full pair witnesses/alignments and dictionary form/link records. Record whether an alternative has supported target identity, number/form and occurrence alignment; preserve unsupported and missing evidence rather than treating the default or majority as correct. Measure available source-context features and independent witness/component counts, without fitting rules or changing ranking. The two introduced error messages are development diagnostics, not a new evaluation set.

Treat the named-title case as a separate span question: inventory existing complete-unit/guard recognition and retained multiword contexts for its exact span, then record why unigram emission survived. Do not turn a lexical-choice result into a claim that names are protected. Suggested bounds are one CPU, 1GiB address space, at most 120s per read-only pass and 8MiB new metadata; no fit, corpus extraction, model calls, candidate activation, broad guard relaxation, per-word patch or all-senses-agree rule. Root review should approve the exact query protocol before that work begins.
