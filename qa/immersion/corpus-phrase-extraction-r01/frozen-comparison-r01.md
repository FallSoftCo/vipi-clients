# Frozen contextual phrase comparison — 2026-11-08

Complete dictionary units and context heads merit a bounded source-context
selection experiment. None of these arms is approved for production. Raw corpus
phrases provide broad availability but retain meaning, boundary and form errors;
dictionary POS agreement alone does not establish the POS of the actual source
occurrence. No corpus/model job or runtime change accompanies this comparison.

## Evidence and scope

The projection reuses 9,535 TRAIN messages. Review covers 96 deterministically
nominated scopes: six arms × two target languages × eight scopes. Different
arms have different nominated examples; these are descriptive diagnostics, not a
paired accuracy comparison, random sample, fresh holdout or bilingual gold.
Prior dialogue was supplied to reviewers, not to the matcher. Whole-message
correctness cannot be inferred from one nominated scope.

The frozen [author review](/home/ai/Development/investigations/vipi-immersion-reconciliation-20261107-r01/corpus-phrase-extraction-r01/projection-r02/contextual/author-review-r01.json),
[Apple review](/home/ai/Development/investigations/vipi-apple-delivery-20261107-r01/corpus-context-independent-review-r01/apple-review-r01.json)
and [root review](/home/ai/Development/investigations/vipi-production-delivery-20261107/corpus-context-root-independent-review-r01.json)
all refer to packet SHA-256 `490a7ec8bb45cb21b9cd5c14f7c78c19f85f935ee35266feccaff56972cc0b1d`.
Their respective verified SHA-256 values are:

- Author: `1f6eb7c82162a0dd2dabb02d8e7191fce385d5b212fbf039434697810ced6395`.
- Apple: `9ac264b9fdb3e5b2c632b45015a5d87f54a4edb9e6ef7ff274e864a65ea5751a`.
- Root: `19c8fd4f354fc415320b9c461077e69edc561c73b5ae90cf2256487f185bb96f`.

The private [joined comparison](/home/ai/Development/investigations/vipi-immersion-reconciliation-20261107-r01/corpus-phrase-extraction-r01/projection-r02/contextual/frozen-review-comparison-r01.json)
retains every original judgment and note, keyed by review ID. Its SHA-256 is
`bd87990ae4ec560f9bed2c246354964f44c9433fffc648677d8fd0377e4434fb`.
The join verified 96 unique matching IDs and matching case, pair, target and
focus coordinates. Only `material_error` → `material` is normalized for meaning
comparison; other rubric fields remain distinct. Agreement is not semantic
approval, and no majority decision replaces an original judgment.

## Nominated meanings and raw reach

| Arm | All three label correct / 16 | Raw content reach SW / ES | Reach after known-function + global300 depletion SW / ES |
| --- | ---: | ---: | ---: |
| mutual_word | 11 | 9,017 / 9,042 | 6,792 / 6,973 |
| raw_intersect | 4 | 8,496 / 8,595 | 7,067 / 7,226 |
| raw_grow | 5 | 8,358 / 8,506 | 6,971 / 7,200 |
| complete_grow | 14 | 6,872 / 8,865 | 3,181 / 6,235 |
| heads_grow | 16 | 1,719 / 4,630 | 720 / 3,020 |
| heads_r03_union | 15 | 4,810 / 6,572 | 1,856 / 3,962 |

Reach counts messages with a raw content anchor out of 9,535 per language,
using the frozen [compact raw metrics](/home/ai/Development/investigations/vipi-immersion-reconciliation-20261107-r01/corpus-phrase-extraction-r01/projection-r02/contextual/compact-raw-comparison-r01.json)
(SHA-256 `51f60025d0af7446187d4b5899f54b85f823c47edeb7e2dbae592917c9dca1c2`).
These counts do not measure correct useful reach. Depletion is the specified
diagnostic knowledge simulation, not evidence that a person learned the phrases.

Normalized meaning labels agree in 90/96 scopes. The six differences are retained
below; C = correct, M = material, m = minor, U = uncertain, in author/Apple/root
order. Even a minor label is not acceptance of the displayed form.

| Review suffix | Source → target | Labels | Unresolved distinction |
| --- | --- | --- | --- |
| 019 | beach → pwani | C/C/U | Beach specificity versus coast/shore breadth |
| 063 | a big fan of → un gran entusiasta de los | C/M/m | Following masculine plural article leaks outside focus |
| 064 | a lot of fun → divertido | C/C/m | Lost degree and unqualified agreement |
| 066 | love → amor | M/M/m | Noun supplied for the actual verb use |
| 068 | be able to → ser capaces de | C/M/m | Plural target against singular source subject |
| 072 | have a lot of → tienen mucha | C/M/m | Finite person/number and gender imported into another use |

The stronger head result has a concrete limit: case 088 nominates
`great → gran`, correctly supported by “be a great … place”, while the same
selected output contains `visit → visita` in “place to visit”. All three reviewers
flag that separate noun/finite-versus-infinitive issue. Matching a dictionary noun
sense on both sides does not prove that this occurrence of “visit” is a noun.
Also, 699 of 944 eligible head records have only a one-token recognized context
in the frozen heads-r02 catalog (SHA-256
`e7220c2dc173799442440a803e4f18592ee1c0ca526716bacfb221350795b289`).
Calling an arm contextual does not make every candidate disambiguated.

## Proposed next experiment — not started

Test whether actual source-role evidence can retain useful complete units and
heads while abstaining on incompatible or unresolved uses. Freeze the protocol,
candidate hashes, source-only selection, thresholds and budget before inspecting
new target judgments. Reuse the existing candidates and native geometry; do not
retrain alignments, generate target text or expand the corpus for this step.

1. Compare the unchanged complete/head baselines with one experimental selector
   that requires occurrence-level source POS/role support, checks target form
   compatibility and abstains when evidence conflicts or is absent. A longer
   literal context or dictionary POS match is evidence to inspect, not a pass.
   Keep target alternatives, provenance, compound protection, density budgets
   and original source text fixed.
2. Cap the diagnostic packet at 120 distinct source occurrences, balanced across
   EN–SW and EN–ES: 40 ambiguous noun/verb or adjective uses, 40 person/number/
   boundary-sensitive phrases, and 40 ordinary content controls. Select by frozen
   source-only rules and stable hash order; report empty strata instead of filling
   from target outcomes. Use identical occurrences across arms. Exclude the 96
   reviewed scopes from this comparison; retain their failures separately as
   regression examples. Further TRAIN use must still be called diagnostic.
3. Review every emitted scope in each selected message, with separate meaning,
   form, boundary completeness and useful-content judgments. Preserve abstentions,
   alternative readings and independently frozen reviewer disagreements. Report
   both nominated-unit and whole-output defects; do not convert votes into gold.
4. Report correct-useful content reach, loss from abstention, all observed material
   errors, unresolved cases and known-vocabulary depletion on the fixed packet.
   Treat any new material error or recurrence of the source-role/boundary failures
   as failure of the proposed rule. Require zero observed material errors and no
   loss of correct ordinary controls before considering a fresh held-out trial;
   neither condition alone establishes release quality. Keep ambiguity-related
   coverage loss visible, rather than relaxing rules after seeing outcomes.

This bounded experiment should decide whether source-context selection is worth
a separately frozen conversational holdout. Deployment, all-language quality and
native runtime performance remain unestablished.
