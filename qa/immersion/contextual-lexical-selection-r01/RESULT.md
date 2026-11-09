The frozen contextual estimators did **not improve held-out corpus-target agreement over default frequency**. Independent mixed-output review also found no strict acceptability gain in the small stratified sample. This is a completed negative comparison, not evidence that default translation is semantically safe or that context cannot help.

### What ran

The same retained dictionary/form/number/term, exact bilingual NOUN roles, alignment and compound/name restrictions supplied all methods. Old explicit links and unresolved direct-English candidates were evaluated separately. No new annotations, language models, downloads, app builds or catalog changes occurred. **Deployed: none.**

Training labels were exact supported target faces from parallel occurrences, not human QA judgments. All form/lexeme/reading identities and original relation IDs remain available behind each face. Repeated heads, forms and translations do not create extra votes: each source-focus occurrence contributes once; conflicting faces split its weight; each component has total weight one per source spelling/number key.

Three fixed methods use this training data: default component-weighted face frequency, local ±2 token/lemma context, and full-sentence token/lemma context. The latter two use add-one multinomial naive Bayes on binary feature occurrences, a train-only vocabulary requiring two components, and frequency fallback when no retained features occur. This is **MNB, not BernoulliNB**: absent features are ignored. Token and lemma features are correlated, and scores are not calibrated confidence. No tuning or second model was run. This estimator is a reproducible comparison inspired by the contextual frequency/weighted-feature approach in the [official Apertium training recipe](https://wiki.apertium.org/wiki/Learning_rules_from_parallel_and_non-parallel_corpora), not an execution of its lex-tools ML/ME rule compiler. The likelihood follows the [documented MNB formula](https://scikit-learn.org/stable/modules/naive_bayes.html#multinomial-naive-bayes).

### Frozen split and support

Whole parallel components were hash-assigned 80/20 to train/test. Any component containing an exposed source or target was quarantined as development, including the prior 32-pair role packet, full-context audit witnesses, earlier source-name/Tatoeba packets and all five final diagnostics. The inherited exclusion inventory covers earlier reviews; exact source files/hashes are in the protocol. No human labels entered fitting. An additional read-only check found **zero normalized full-source-text overlaps across splits**, both over all 38,682 normalized corpus sources and 4,143 eligible sources. Original split bytes were unchanged.

| Pool / split | Source-focus records | Components | Source spelling/number keys |
|---|---:|---:|---:|
| Explicit train | 2,987 | 2,742 | 257 |
| Explicit test | 781 | 706 | 162 |
| Explicit development | 617 | 406 | 90 |
| Direct train | 53 | 52 | 4 |
| Direct test | 20 | 20 | 2 |
| Direct development | 254 | 237 | 9 |

Pools can overlap and must not be summed as independent coverage. Component 1 contains 4,478 of the 40k corpus pairs and 4,147 source endpoints; all 147 eligible records from it are quarantined. Only **30/257 explicit training keys** have multiple observed target faces; 104 keys have fewer than three training components. Four training occurrences have conflicting reference faces, preserved as sets. The direct pool has just one multi-target training key and is too small for a broad learning claim; its source-entry/sense identities remain unresolved.

### Held-out surrogate agreement

Of 781 explicit test occurrences, 12 have no training source key. Eighteen have no training-supported reference target, including those 12; one has multiple reference faces. Forty-eight have fewer than three training components. Prediction candidates come only from training and are never restricted using the held-out target.

| Explicit test subset | Default | Local context | Sentence context |
|---|---:|---:|---:|
| All 781 occurrences, agreement with any reference | 735 | 733 | 727 |
| 568 occurrences with one train target | 563 | 563 | 563 |
| **201 occurrences with multiple train targets** | **172** | **170** | **164** |
| Changed decisions versus default | — | 12 | 18 |
| Paired reference-agreement gains / losses | — | 5 / 7 | 5 / 13 |

Each method predicts on 769 occurrences. Each produces 44 identical-source faces, counted as **zero immersion**, not usable changed-word coverage. High agreement on dominant single-target cases does not show lexical-choice learning. Synonyms can disagree with the one observed corpus rendering while preserving meaning.

Direct test has 20 occurrences: 14 single-target cases agree for all methods; among six multi-target cases, default/local agree on five and sentence context on four. Sentence context changes three decisions (one surrogate gain, two losses). There are no unseen direct test keys/targets, but only two test keys. This remains an unresolved-relation availability experiment, not a shipping edge or accuracy estimate.

Development outputs are retained separately: explicit 235/617 have training-supported keys; direct 23/254 do. They are exposed diagnostics, not fresh evaluation. Detailed counts, every prediction/score and all competing support remain in the remote output closure.

### Independent full-message review

The frozen packet selected eight changed cases, four unchanged multi-target controls and four single-target controls by hash, at most one per component, without outcome-based backfill. Each anonymous option replaces only the exact focus in the complete original source sentence; it does not substitute the full Spanish reference or claim a native-chat budget projection. No prior dialogue was available. Both reviewers froze all 24 option judgments before seeing the method key, metrics or peer labels. The author's prior metrics retrieval had been submitted but its output remained unread until freeze; this is explicitly recorded in the review.

Both reviewers find **14/16 strict acceptable outputs for every method**, including **6/8 in the changed stratum** and all eight controls. Local context makes no semantic acceptability change in this sample. Sentence context removes the agreed material offspring-versus-young-audience error in the children case, but introduces a defect in the technical set-of-intersections case. Author labels that new juego choice material; root labels it minor because juego has a collection sense but is an awkward technical collocation. This is the **only option-label disagreement** and is preserved with both rationales and root's primary references. No majority gold replaces it.

Consequently author sees one material fix and one material regression; root sees one material fix and one minor regression. Root's minor-tolerant sentence score is 15/16, versus 14/16 for default/local; author's is 14/16 for all. Both leave the unspecified glass referent uncertain under either option. Both accept legitimate alternatives for crime, husband, employment and the genetic complement/set context. There are no zero-immersion outputs in this packet. These are stratified diagnostic counts, not population accuracy or proof that matching the corpus face is better immersion.

### Resources, evidence and decision

Preparation ran once in **8.235 s**, with **700,305,408 B VmHWM**; normalized-text verification took **2.373 s / 272,019,456 B**. Fitting, all comparisons and packet assembly took **1.091 s / 270,348,288 B**. Each remained within one CPU, 1 GiB address space and its fixed deadline. The source dataset is 58,343,278 B; the complete packet 5,571,278 B; predictions 1,697,812 B. Existing production source/annotation assets were read in place. Initial production free space was 288,179,220,480 B, with an 8 GiB floor and 192 MiB reservation; new artifacts stayed below the 128 MiB aggregate ceiling.

Protocol SHA256: `fb10aba675945eb208dc085ad9855ea9d8964b765d62faf5bc09787e859b1dc4`.
Split SHA256: `bf9a8638b9bfbe6892ccef01a002da90a7eb1898da251843f4fbde98a9f21a91`.
Predictions SHA256: `176681e6422aeb08ebb2e45734ab821f8cef0c722061518a50345d8b4ca6355f`.
Packet SHA256: `2c8352a1582c1e570a978e1befddc6fb37986e7fb31a623bcbc122ba8d573f8c`.

All remaining hashes and frozen reviews are bound in `completion-receipt.json`; private join preserves every label and transition. Large source/support artifacts stay under `/srv/fallsoft/staging/vipi-contextual-lexical-selection-20261109-r01`, small local review evidence under `/home/ai/Development/investigations/vipi-contextual-lexical-selection-20261109-r01`.

Independent verification recomputed all 1,672 test/development predictions, 4,122 scores, every method metric and component weight, and checked all nine output hashes, split identities and packet focus/method bindings (0.995 s / 267,210,752 B). It imported no experiment runner and did not change the frozen fitting policy.

This frozen MNB comparison does not justify replacing default choice or activating a selector. It establishes a reproducible held-out baseline for assessing an existing lexical-selection/rule component separately. Corpus roles constrain training examples; any later app experiment must still enforce current-user source-role/scope policy. No further algorithm, parameter change or client projection was started.
