The retained Apertium lexical-selection component changed **zero first choices** in this frozen, newly eligible common-noun cohort. It was not an empty/no-op rule asset: six actual rule firings reduced alternative lists, while preserving the already-first bilingual choices. This result is specific to these English→Spanish noun occurrences, not all POS, all language-pair inputs or the general lexical-selection engine. **No client/catalog change was deployed.**

### Exact pipeline and correspondence

The 16 already reviewed development messages qualified the reuse of stored surface-preserving tags: removing only the surface field produced byte-identical output to the pinned normal tagger on stored morphology. All 16 exact focuses retained their occurrence correspondence through normal tagging, pretransfer, the retained source-side genitive rewrite, bilingual lookup and LRX. These verified prefix outputs were reused in the cohort run.

The actual prefix followed retained `eng-spa.mode`, stopping before bilingual structural transfer, interchunk/postchunk and generation. `lrx-proc -m -t` retained every output and rule trace. In pinned [lex-tools v0.4.2](https://raw.githubusercontent.com/apertium/apertium-lex-tools/v0.4.2/src/lrx_proc.cc), `-m` is a deprecated no-op; it does not identify a separately trained maximum-entropy mode. The [official module contract](https://wiki.apertium.org/wiki/Constraint-based_lexical_selection_module) places lexical selection after bilingual lookup and before transfer.

Exact source UTF16/token geometry and complete lexical-unit sequence/header identity were mandatory. Repeated words were traced by occurrence index, not first matching lemma. All 144 unavailable source mappings first diverged at pretransfer; this conservative whole-sequence abstention also withholds an otherwise unchanged focus when another unit splits. It is a mapping limitation, not proof that Apertium cannot process those messages.

### Same 781 exposed benchmark records

The run used the same **781 explicit held-out source-focus records / 734 source endpoints** as the NB comparison. The benchmark is now exposed. Source/target form, number, term, actual noun-role, alignment, name and compound policies were not relaxed. Selected noun lemma/number was joined only to uniquely compatible **training-supported** faces; all alternative readings and immutable proof references remain retained. Off-pool/new candidates were not forced into an output.

| Outcome, identical before and after LRX | Records |
|---|---:|
| Source sequence/focus untraceable | 144 |
| Multiple training-supported faces | 45 |
| Candidate absent from training but retained elsewhere | 11 |
| New or unsupported lexical candidate | 26 |
| Unique face from initial lemma/noun/number join | 555 |

The initial 555 faces agreed with a retained corpus reference in 511 cases, with 30 identical-source faces receiving zero immersion credit. These initial counts are **not full morphology qualification**. There were zero before/after first-analysis changes and zero supported-face changes, both overall and within the exposed 16; quarantine did not conceal changed choices.

Across all 7,583 lexical stream units, there were six alternative-list reductions and zero first-reading changes. Five traces selected the drinking-vessel analysis in glass-of-liquid contexts, and one selected the already-first temporal spend analysis. Four reductions were on mapped noun focuses outside the exposed 16. Complete trace lines, source contexts and before/after alternatives are in `post-audit-r01/rule-firings-and-alternatives.json`.

The bound `eng-spa.autolex.bin` is 141,085 bytes, SHA256 `84a6adbf5b3e10136e3ccd0610376040e91753a445734e21f21a748f1a5e510d`. The published matching [v0.8.1 rule source](https://raw.githubusercontent.com/apertium/apertium-eng-spa/v0.8.1/apertium-eng-spa.eng-spa.lrx) contains 631 multi-position rules; its retained source SHA is `92c7182cffdfff1e3133bc11255c4e87ddf630746019f4d2dd48a41d97abd0f9`. This is version-matching primary source, not an independently reproduced binary build. Actual retained traces establish applicability here; absence of changed first choices must not be attributed to an empty engine or universal contextual failure.

### Additive morphology qualification

Independent inspection identified that the frozen join matched lemma/noun/number but omitted other morphology tags. The original predictions remain immutable. A separate read-only audit compares selected analyses with every retained candidate analysis for the exact emitted face, preserving all tags and evidence references.

**524 of 555 faces have at least one exact all-tag supporting analysis; 31 are unqualified.** Of those 31, 28 involve GD/mf/unspecified gender and three explicit incompatible gender tags (selected feminine muro versus retained masculine analysis). These are qualification differences, **not automatic meaning mistakes**: GD can be a placeholder intended for later transfer, and an emitted surface can preserve meaning despite unresolved/inconsistent analysis. The experiment does not run that later grammar stage or silently repair the tags.

Other conflicting analyses can coexist with exact support: eight outputs have some explicit gender-conflicting evidence, but five also have exact support and remain qualified. All alternatives survive. The 31 unqualified records retain full source contexts, every candidate proof-set reference and immutable training-witness IDs. No majority/all-senses gate was introduced.

On the same **524 exact-tag-qualified cases**, bilingual default and LRX both match 483 references; the frozen NB frequency default matches 507. They differ on 42 faces. This separates dictionary-default differences from a contextual LRX effect. It is surrogate target agreement, not semantic superiority: valid synonyms may disagree with the corpus rendering. Twenty-nine qualified outputs are identical-source faces, yielding zero immersion credit; 495 are changed faces with exact morphology support, not 495 meaning-approved translations.

### Review and limits

The frozen review policy selected newly changed first choices, at most one per component, excluding all earlier exposed components plus the 16 NB review components. **Zero cases qualified**, so the packet is empty and no backfill occurred. Both agents retained empty-review receipts with `semantic_review_performed=false`. There is no new agent, human or native-speaker semantic validation from this empty packet.

The negative result does not justify replacing the default, adding hand-picked rules or activating a selector. The component executed correctly, but its applicable rules did not alter first choices in this noun cohort. Corpus role evidence still describes training/examples, not a current user's role; any eventual app projection needs the live source-role/scope policy.

### Execution and retained closure

Qualification ran once in **2.299 s / 270,692,352 B parent VmHWM**, with 80 child stages. The cohort ran once in **179.742 s / 395,337,728 B parent VmHWM**, with 2,872 new child stages and 50.116 s summed child wall time. These are research startup/capture timings, not native mobile latency. Each stage remained within one CPU, 1 GiB address space and 300 seconds. No morphology/tagger batch was replayed beyond the explicit 16-message normal-stream qualification.

The first read-only morphology audit hit its 24 MiB output cap while repeatedly encoding shared proof lists. Its source and 1,094-byte partial summary remain. Exact rejected bytes and its VmHWM were not captured and are not invented. The authorized representation-only r02 stores **1,110 audit records, 129 unique proof sets and 525 source contexts**, with exact expanded-record reconstruction/hash checks; no alternatives disappeared and no inference was rerun. It completed in **4.103 s / 329,355,264 B**, producing 3,226,464 bytes before receipts. Post-audit took **0.807 s / 345,677,824 B**. Aggregate evidence was approximately 53.5 MB, below 64 MiB; the admitted reservation was 128 MiB with an unchanged 8 GiB floor and initially 288.1 GB free.

Independent verification checked 3,706 stage-file hashes, reparsed 734 endpoints / 7,583 units, recomputed the 781 predictions/reasons/reference counts and reconstructed all 1,110 morphology records and 129 proof sets. It confirmed 524 qualified / 31 unqualified per method (0.797 s / approximately 140.8 MB).

Protocol SHA: `aec4051cacd47e46a527e662be18409da38c5c97462c91b3f4681c821d9af5da`.
Frozen predictions SHA: `4f06814258b29e58e86b9bc16bf197aabdfa4e9aeaae9823a26362d98db12748`.
Empty packet SHA: `0ae4de10aa51dff2bf8f65c9f57bd98ccad28e573f887b1a8ffcf8da4cc6d21f`.

Raw stage bytes and complete alternatives remain at `/srv/fallsoft/staging/vipi-apertium-lexical-selection-20261109-r01`. Small summaries, compact proofs, primary-source provenance and empty review receipts are local at `/home/ai/Development/investigations/vipi-apertium-lexical-selection-20261109-r01`. Deterministic gzip transports were removed only after raw-hash verification. `completion-receipt.json` binds the closure. No further algorithm or activation was started.
