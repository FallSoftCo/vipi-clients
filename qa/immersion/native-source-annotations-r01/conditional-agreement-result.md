# POS-conditioned common-form potential — scoped result

**Decision:** retain POS-conditioned common-form selection as an A/B candidate,
but do not activate it or describe this calculation as agreement over all source
meanings. The current explicit linked subset permits more choices after POS
conditioning; most apparently admissible groups also have unresolved additional
links. Actual source completeness is unknown. POS-plus-frequency offers many more
choices without establishing their contextual correctness.

The [protocol](conditional-agreement-protocol.json) was written before metrics.
[Code](conditional-agreement-inventory.py) and [receipt](conditional-agreement-receipt.json)
preserve that scoped calculation unchanged. Its `source_senses` fields mean
**retained eligible explicit linked pivot senses**, not exhaustive native senses.
The subsequent [source audit](conditional-agreement-source-audit.py) and
[audit receipt](conditional-agreement-source-audit-receipt.json) expose the omitted
link strata rather than silently declaring that subset complete.

## Denominator and candidate proof

There are **618 distinct normalized alphabetic-bearing token surfaces** across the
frozen 116-source Apple LexicalClass and OpenNLP pass-0 outputs. Every key enters
both pair denominators, including missing records. No new annotator or tokenizer
ran. Only grow-diag-final-and variants were inspected through exact keyed reads.

Each candidate has an exact retained target dictionary surface/form, POS, number,
features and reading, with source/target lexeme and shared explicit eligible sense
proof plus aligned variant identity. Number and POS must match. A form may be
supported through different target lexemes for different linked source meanings.
The intersection retains such legitimate common forms; other synonymous forms do
not invalidate them. Strict union-singleton is a separate overrestrictive control.
Empty sense sets block the scoped intersection. Identical faces remain eligible;
a selected identical face gives zero immersion, with no alternative rescue.

These are pre-budget lookup potentials, not source-context correctness, atomic
phrase permission, target inflection suitability or native displayed output.

| All-key measure | EN–ES | EN–SW |
| --- | ---: | ---: |
| All keys | 618 | 618 |
| No retained source units | 134 | 134 |
| No eligible explicit linked pivot senses | 154 | 154 |
| No grow candidate variants | 101 | 127 |
| Retained explicit linked POS/sense identities | 2,877 | 2,877 |
| Those identities lacking admissible target-form evidence | 1,975 | 2,619 |
| Keys with at least one such missing link | 411 | 446 |
| Common form across all retained explicit linked POS/senses | 46 | 14 |
| Above with nonidentical chosen form | 41 | 14 |
| Any dictionary POS has a common form | 102 | 30 |
| Newly available after dictionary-POS conditioning | 56 | 16 |
| All-POS strict union-singleton control | 29 | 9 |

“Any dictionary POS” is an inventory ceiling, not the POS inferred in the message.
Actual frozen occurrence-POS mappings are limited to noun/verb/adjective/adverb;
all other tags, including OpenNLP PROPN/AUX/composites, are unmapped. No confidence
threshold or new name veto is applied. Token boundaries differ across engines, so
these are separate denominators rather than paired accuracy results.

| Frozen occurrence measure | Apple ES | Apple SW | OpenNLP ES | OpenNLP SW |
| --- | ---: | ---: | ---: | ---: |
| Alphabetic-bearing token occurrences | 1,668 | 1,668 | 1,617 | 1,617 |
| Mapped role occurrences | 982 | 982 | 769 | 769 |
| Mapped role with retained explicit linked senses | 727 | 727 | 645 | 645 |
| With missing target evidence for some linked sense | 571 | 687 | 513 | 606 |
| Conditional common-form choices | 153 | 39 | 129 | 38 |
| Nonidentical common-form choices | 144 | 39 | 123 | 38 |
| Strict union-singleton choices | 106 | 31 | 84 | 31 |
| POS + frequency choices | 585 | 242 | 526 | 220 |
| Frequency winner outside the common-form intersection | 434 | 203 | 398 | 182 |

## Source completeness audit changes the interpretation

The source pack uses `explicit=0` for generated native-gloss links, including
valid direct English relations; that flag restricts unreviewed foreign-to-foreign
pivoting. It is not a reason to erase those links from lexical ambiguity.
Across the 618 keys, **407 contain 4,582 additional eligible nonexplicit linked
POS/sense identities**. No ineligible terms were observed in these retained units.
The audit preserves categories and labels individually, not merely their counts.

Of the 46 Spanish all-POS common-form keys, **41** have additional unresolved links;
**96 of 109** Spanish common-form POS groups do. Swahili counts are **12 of 14**
and **25 of 33**, respectively. Even the remainder is not proven complete:
monolingual `lexemes.senses` counts are retained for 484 keys, but the database does
not provide an exhaustive one-to-one mapping from those native meanings to linked
pivot identities. Never subtract linked counts from native counts to fabricate a
missing-sense count. Missing cached source units likewise do not establish that
an entire dictionary or language lacks a word.

Examples constrain the next decision:

- `visit` verb has one explicit linked pivot sense and common `visitar`, but its
  native verb entry reports seven senses; the source key also has 16 nonexplicit
  linked identities across POS. This is not all-meaning approval.
- `book` does **not** unlock here: noun has six explicit linked identities with
  four missing Spanish target links; verb has five, all lacking admissible links.
  POS evidence helps distinguish uses, but cannot fill the candidate gap.
- `play` verb retains competing musical/game candidates and missing links;
  `too` adverb retains degree/additive alternatives and missing links. Both still
  abstain under the scoped intersection. Frequency chooses `jugar` / `también`
  for Spanish and `pia` for Swahili too; these defaults are not contextual proof.
- `plant` is absent from the frozen key set; no illustrative word patch or new
  example was added. Different senses sharing a justified exact form remain
  supported by the declared intersection math.

The next A/B should keep source-first top-down context lookup and masks fixed,
compare residual POS-conditioned common forms against POS-plus-frequency, and
report incomplete-domain abstentions separately. It first needs a resolved policy
for direct-English nonexplicit links and a source-completeness contract. Preserve
wrong-high-score POS and title/name cases; never infer safety from coarse POS or
a unique surviving linked identity. This result does not authorize a broad replay.

## Receipts

Private [scoped result](/home/ai/Development/investigations/vipi-conditional-agreement-inventory-20261108-r01/result.json):
SHA-256 `e95e74ca64d0b3cda91c502e415cac8ed6850705a9590b8a1ce4a5000721c6cb`.
Private [source audit](/home/ai/Development/investigations/vipi-conditional-agreement-inventory-20261108-r01/source-audit.json):
SHA-256 `0a432854e29180bdd80f5bc4e3140c979590a52338f8111b396fc444a7591d81`.
Original files and judgments remain unchanged. Validated proof presence and exact
set intersections for all 1,236 pair/key records, including empty sets and the
strict control. Main run: 2.38 seconds, `/proc` VmHWM 80,859,136 bytes; additive
audit: 0.42 seconds, VmHWM 51,859,456 bytes. Both used one CPU, 256 MiB address-space
limits and 120-second alarms. Combined output is about 7.2 MB, below 16 MiB; local
8 GiB reserve was checked. No extraction, training, source annotation or runtime
mutation occurred.
