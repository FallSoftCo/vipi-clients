The largest observed availability gate is the retained dictionary/form link stage, before actual-message role checking or density selection. This identifies where to investigate; it does **not** show how much correct vocabulary would return if a guard were lifted. In particular, the analysis does not support relaxing `explicit=true` or target-safety rules.

One read-only pass over completed r02 proofs and decisions took 18.38 seconds, with 68,976,640 bytes process VmHWM and a 13,041-byte aggregate result. No extraction, fit, inference, selector replay or new target lookup occurred. [Receipt and input SHA bindings](loss-accounting-r01-receipt.json); [full private aggregates](/home/ai/Development/investigations/vipi-context-key-expansion-20261109-r01/head-preparation-r01/loss-accounting-r01/result.json).

These are **nested availability counts**, separately denominated by source key and message. A message survives when at least one matching context or candidate survives; it is not a statement about every content word or target correctness. Message rows below use the expanded arm before known-family exhaustion.

| Stage | Matching source keys | Messages with any survivor / 9,535 |
|---|---:|---:|
| Retained source context | 25,931 | 9,506 |
| Aligned top target context | 19,960 | 9,504 |
| Any shared dictionary head/link | 15,967 | 9,411 |
| Eligible shared form/sense/POS/number link | 3,524 | 6,221 |
| Alignment and containing-unit guards passed | 2,514 | 5,622 |
| Projected head candidate | — | 5,622 |
| Single-token focus | — | 5,587 |
| Actual role assessed | — | 5,305 |
| Actual role compatible | — | 5,219 |
| Content classified | — | 5,107 |
| Nonidentical target | — | 4,958 |
| Literal protection passed | — | 4,955 |
| Actual-message compound masks passed | — | 4,557 |
| Selected at 25% | — | 4,557 |

With the first 300 source families withheld, 1,681 of those 4,557 messages lose their last eligible candidate, leaving 2,876. This is an experimental exhaustion policy, not evidence that the user learned those meanings. The declared exclusive order attributes 3,190 messages first to no eligible link, 599 to head structural guards, 398 to actual-message compound masks, 282 to unassessed role, 86 to conflicting role, and smaller groups to other gates. These disjoint first-loss bins depend on that order; they are not recoverable-correctness estimates.

Source absence, form absence, missing links and witness mismatch are different gaps:

- **Source context absence:** only 29 messages lack every retained source context, and two more lack every aligned context. This hides partial-word gaps: of 39,588 native word occurrences exactly tagged noun/adjective/adverb, 4,324 are outside every retained source context. Inventory caps, stop rules and tokenization are confounded with corpus absence. Merely being inside a matched context does not make that word a valid head.
- **Absent supported forms versus absent retained links:** among the 3,993 aligned contexts with no shared head at all, 316 have no complete supported source form; another 1,279 have a supported source form but no complete supported target form. The remaining 2,398 contain supported forms on both sides but no shared retained sense link. These counts apply only to that no-shared-head branch. They neither prove dictionary semantic absence nor distinguish missing translation relations from a paraphrased/inappropriate top witness.
- **Excluded verbs:** 26,810 native word occurrences are tagged VERB/AUX and lie outside this noun/adjective/adverb experiment. This is deliberate scope exclusion, not a dictionary failure. AUX includes native grammatical material, so the count is not a proposed vocabulary-emission gain.
- **Witness/form mismatch:** the prior independent review found a university/school sense mismatch, a still-wrong equality “just” sense, and copied adjective agreement/capitalization defects despite dictionary and role passage. Aggregate loss counts cannot establish whether another existing witness/form is correct; the current top-target and first-representative policy remains fixed.

Dictionary rejection totals are particularly easy to misread. Of 21,425 paired head candidates, 17,785 have no eligible shared sense/POS/number match. Across **347,767 shared-link records**, overlapping reasons include unsupported POS (311,168), unsupported form mode (283,493), incomplete form (283,270), dictionary guard (242,527), nonexplicit sense (10,166), ineligible term (6,016), unsafe target form (2,513), POS mismatch (1,498) and number mismatch (1,345). A link can have several reasons, and many records are outside the allowed content-head scope. These totals do not identify explicitness as the sole bottleneck. Nonexplicit direct-English links can be valid; retained linked pivot senses are not an exhaustive inventory of source meanings.

Alignment/compound rejection totals also overlap: 7,032 head candidates have crossing union edges, 4,887 sit inside larger source units, 1,381 inside larger target units, and 1,131 lack a mutual anchor. After assigning dictionary eligibility first, the **exclusive** head bins are 698 crossing-edge losses, 325 source-containing-unit losses, 23 target-containing-unit losses and 38 missing-anchor losses; 2,556 heads survive. Different ordering would assign overlapping cases differently.

Selection is not the main cause of empty outputs in this scoped run. After guards, the expanded arm has 9,642 candidate instances but only **6,554 distinct message-local focus occurrences**. It selects 6,362; the candidate-count decrease includes competing contexts for the same word. Under family exhaustion, 5,163 candidates cover 3,579 focuses and 3,501 are selected. No message with an admitted pre-budget candidate becomes empty at selection because this experiment emits single-word focuses and its minimum budget is one. Repeated-concept, overlap and remaining-budget rejection counts overlap; they cannot be added to claim thousands of lost vocabulary words.

The most actionable next diagnostic is therefore the **complete supported head-to-target evidence gap**, not a larger density budget: inspect whether retained complete noun/adjective/adverb source units lack a usable target form/link, or whether the frozen top witness/representative supplies the wrong sense/form. The existing no-shared-head branch separates 2,398 both-supported/no-link contexts from 1,279 missing-target-form contexts and 316 missing-source-form contexts. It offers a bounded starting set, but its counts are not a promise of recoverable coverage. Keep verbs as a separate scope question and preserve compound, role, safety and explicit-link distinctions until concrete retained examples establish the cause. No architecture or guard change follows from these aggregates alone.
