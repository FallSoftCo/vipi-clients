The learned longest-first lookup ran on the fixed 781-record noun benchmark. **The narrow arm changed nothing; the wider arm changed three choices, with no demonstrated semantic improvement.** Two changes used noncentral three-token context; only one used a longer, four-token context. No client/catalog change was deployed.

### Frozen method and actual table

This is a transparent adaptation of the [Apertium parallel-corpus maximum-likelihood rule recipe](https://wiki.apertium.org/wiki/Learning_rules_from_parallel_and_non-parallel_corpora), not execution of its trainer or a new statistical classifier. Pinned [v0.4.2 pattern extraction](https://raw.githubusercontent.com/apertium/apertium-lex-tools/v0.4.2/scripts/ngram-count-patterns.py) sets `MAX_NGRAMS=2` with `range(1,2)`, producing adjacent bigrams and centered trigrams. Its [rule converter](https://raw.githubusercontent.com/apertium/apertium-lex-tools/v0.4.2/scripts/ngrams-to-rules.py) uses a strict ratio threshold. The frozen comparison has three arms:

- Exact previous component-weighted frequency default.
- Narrow: left/right bigram and centered trigram.
- Wide: every contiguous 2–8-native-token window containing the focus, including noncentral positions.

Both contextual arms use identical original-token and exact singleton lemma+POS channels, normalized source spelling, original occurrence positions, punctuation/unknown barriers, independent-component support and tie policy. Rules require a unique contextual winner different from default, at least two supporting components, and winner mass strictly above 1.5 times contextual default mass. Longest match wins, then token before lemma, ratio, independent support, mass, leftmost start and stable ID; absence of a rule backs off to the exact previous default. No labels or held-out targets enter fitting.

Explicit adaptations are supported target **faces**, source-focus/component-normalized counts, JSON lookup rather than LRX binary, and the wider window range. An absent contextual default receives zero count: a repeated supported alternative may qualify. The pinned script instead initializes absent-default probability to one, suppressing such rules. This difference was disclosed before predictions; **26 of 30 compiled rules and all three applied choices use this adaptation**. This is not evidence that the unmodified upstream trainer would make these choices.

The unchanged explicit pool has 2,987 training occurrences / 2,742 components / 257 source keys, with 30 multi-target keys. It produced 11,848 distinct patterns and 30 rules: 12 length-two, 13 length-three and five length-four. Fourteen rules fit the narrow geometry. No length-five-to-eight rule met support. All candidates, rejected-pattern reasons, target counts, source-occurrence/component support IDs and absolute context positions remain retained. Single-target keys need no context rule; their defaults and support records remain. The compiled JSON table is 270,164 bytes including defaults/provenance; its measured Python object graph is 677,538 bytes. These are not a native mobile runtime estimate.

### Paired outcomes, not translation accuracy

| Same cases | Default | Narrow | Wide |
|---|---:|---:|---:|
| Reference agreement, all 781 | 735 | 735 | 734 |
| Reference agreement, 201 multi-target | 172 | 172 | 171 |
| Matched contextual rule | — | 0 | 3 |
| Supported default fallback | 769 | 769 | 766 |
| Unseen key / unavailable | 12 | 12 | 12 |
| Emitted identical-source face | 44 | 44 | 44 |
| Emitted changed-source face | 725 | 725 | 725 |

The 568 single-training-target cases agree with 563 references in every arm. Twelve cases have unseen source keys; 18 overall have no training-supported reference target, and one has competing reference faces. No matching-rule target conflicts occurred in the test set. Raw `metrics.json` combines unavailable and identical-source outputs as 56 zero-immersion cases; the additive audit separates **12 unavailable** from **44 emitted same-source faces**, preserving the previous study's convention.

The wider arm gains one reference match and loses two, all within the 201 genuine-choice cases. Winning `(length, zero-based focus offset)` is `(3,2)` twice and `(4,2)` once. The two noncentral trigrams change job from trabajo to empleo; the four-token window changes set from conjunto to juego. Each winner has only two independent supporting training components. Thus two changes reflect **window position**, not longer context. No 5–8-token benefit was observed; lack of repeated supported rules limits this corpus test, rather than proving longer context is useless.

This benchmark is reused and exposed. Component and normalized-source-text split disjointness were reasserted over the retained eligible dataset (the original whole-corpus split proof stays hash-bound), and all previous explicit frequency-default predictions matched exactly. Component 1 remains quarantined in the unchanged development split (4,478 pairs, 4,147 source endpoints, 147 eligible records). Component weighting prevents repeated bilingual expansions from becoming independent support; it does not create new evidence. Source/target form, number, eligible term, noun-role, alignment, name, compound and mask guards remain fixed. Corpus occurrence roles do not establish the role of a future live user's word.

### Independent agent review

The frozen packet contains all three eligible changed cases plus four deterministic controls: seven complete mixed messages, ten unique anonymous options, one case per component. Fifty actually exposed diagnostic source IDs / 48 components were excluded, alongside the original split's exposure quarantine. The 525 machine-stored contexts were not presumed reviewed. No outcome-based backfill or reselection occurred.

Both agents labeled all ten options correct under intended source-grammar preservation: each method has 3/3 acceptable changed-case outputs and 4/4 acceptable controls, with no zero-immersion case and no label disagreement. Both empleo/trabajo choices preserve employment; conjunto is a valid collection of sheets while juego is more idiomatic for a matched bedding set. Therefore the surrogate's one gain/two losses do not establish meaning gains/losses.

The author review was method-, reference- and peer-label-blind. Root was method-blind and peer-independent **but accidentally saw some parallel references** before freezing; it is not a second reference-blind review. Root's preserved additive correction retracts a mistaken recollection of exact prior source exposure: earlier job sentences were similar, not identical. All original labels and the correction remain unchanged. These are independent **agent** judgments, not human/native-speaker validation, semantic gold or population accuracy.

### Execution, evidence and decision

Compile ran once in 2.804 seconds / 270,094,336 bytes VmHWM; apply ran once in 1.217 seconds / 277,864,448 bytes. Both stayed within one CPU, 1 GiB address space and 300 seconds. The table loaded in 0.00166 seconds; both lookup arms over all 781 records took 0.271 seconds in this Python evidence implementation. Compile/apply outputs total 21,151,481 bytes before receipts, below the frozen 96 MiB aggregate cap and 192 MiB reserve; fresh disk free was 288.0 GB, with the 8 GiB floor preserved. No failed inference, refit, parameter replay, download of runtime/models or activation occurred.

Independent verification reconstructed 4,141 source token/lemma contexts directly from the retained database, all 11,848 pattern weights/support/admission records, all 30 rules, all 2,343 method choices, metric strata, split identities and 15 file hashes (2.491 seconds / approximately 268.6 MB). It imported no experiment runner and did not rerun the experiment. Its source and receipt remain bound in the closure.

The actual table proves that a compact top-down context lookup can be learned and executed with inspectable supporting occurrences. This particular corpus/cohort does **not** yet support replacing the default: only three test records matched a qualifying alternative, all accepted as synonymous by both agents, and none established improved meaning. The larger-window arm is useful evidence about sparse repeated context, not justification for relaxing guards or expanding architecture. No further algorithm was started.

Private evidence: `/home/ai/Development/investigations/vipi-context-rule-lookup-20261109-r01`. Full pattern/occurrence evidence remains on production at `/srv/fallsoft/staging/vipi-context-rule-lookup-20261109-r01`; small table, predictions, packet and receipts were transferred with deterministic gzip and exact raw SHA verification. Protocol `a63969b5ceba833099d58dc9112e6e1ae9a9da2f0bcd206593ff6fe251ed70a5`; predictions `defc2a59948200eb81a12e1eeb25e949c54e772ffedb0786f75631eb9a47c2ef`; packet `879cf7be967b46b2a9efd351bcd9ead6b66c21170dbda6dc5a17e64c63446b6e`. The completion receipt binds scripts, sources, stage outputs and both original reviews.
