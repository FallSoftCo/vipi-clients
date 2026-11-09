# Reject this gate as the final admission policy

Requiring every source-unsafe ordinary form to have a wider context with two components removes too much usable vocabulary. Retain the experiment and its evidence, but do not promote its rule or the original parity-qualified catalog as semantically ready. Nothing was activated.

| Reused TRAIN state (9,535 messages each) | Nonempty before → after | Emitted native words before → after |
|---|---:|---:|
| All function words known | 5,088 → 2,419 | 7,376 → 2,821 |
| Function + global300 control known | 3,019 → 1,053 | 3,700 → 1,129 |

Each state contains 121,960 native words. These are changed-word/message availability counts, not useful whole-message acceptance or semantic accuracy. Actual user knowledge is not inferred from frequency. Lost/added candidate events are 4,864/309 and 2,739/168 respectively; alternative candidates can emit the same face, so these are not counts of newly learned translations.

On the exposed actual-native52 diagnostics, nonempty outputs fall 26→25 and 14→12; emitted words fall 45→31 and 21→13. All 19,070 TRAIN decisions and 104 actual-native decisions matched the frozen qualified comparator in every field before gated predictions. This establishes plumbing parity only.

## Meaning tradeoff

The additive agent review covers every lost/added actual-native event: 30 events across both states, including four same-output candidate switches. Plane→avión, help→ayuda and food→comida switch supporting contexts while leaving the emitted word unchanged. They are not coverage gains.

After excluding these switches and deduplicating the same focus across known states, 14 actual emissions disappear:

- Two clearer meaning errors are withheld: additive **too→demasiado** and emphatic **just→Apenas**.
- Six valid vocabulary emissions are lost: **here→aquí, exercise→ejercicio, station→estación, beauty→belleza, eggs→huevos, definitely→definitivamente**.
- Four preserve meaning but have mixed-grammar/form/casing qualifications: **different→diferentes**, restrictive **Just→sólo**, **unfortunately→Desafortunadamente**, imperative **just→Solo**.
- **football→fútbol** has a valid association-football reading; source variety remains ambiguous.
- Temporal **just→Solo** remains uncertain, not established material error. The retained Spanish relation includes temporal use, and “only started … last month” can overlap pragmatically. Capitalization is separate.

These are exposed single-agent diagnostic judgments, not a new independent accuracy score. Earlier author/root labels remain immutable; this additive temporal-just calibration does not replace them. The gate also leaves some previously observed form issues, such as feminine cansada without established speaker gender. It therefore neither preserves coverage nor completes form/meaning qualification.

## Why the flag is prevalent

The committed `build_lexical_shards.py` defines source safety from lexical eligibility, supported POS, no nonlemma condition, **exactly one native sense**, and absence of grammatical/proper-name homograph flags. Target lexical eligibility is separate. `source_safe=false` does not mean that the selected translation is false in this occurrence, or even that competing meanings require different target faces.

The retained 2,556 ordinary heads include 2,335 whose eligible source forms are all source-unsafe. A bounded keyed read of the frozen English dictionary found 738 distinct eligible source lexemes: 657 unsafe, of which 654 have more than one native sense. Only three unsafe entries have one native sense; this audit does not fabricate a breakdown of their nonlemma/homograph causes. Examples include here(8), football(13), exercise(6), egg(14), just(9), too(5), definitely(2), unfortunately(2). These are native dictionary sense counts, not exhaustive aligned target meanings and not occurrence labels.

The gate predominantly penalizes dictionary richness. Two independent aligned components also establish repeated availability, not that the context distinguishes the intended meaning. The `they just` witness demonstrates why a generic short context can be misleading; the many valid lost unigrams demonstrate why universal context requirements are too broad.

## Smallest remaining evidence gap

The missing information is **target-specific contextual support for the current intended reading**, especially where an otherwise eligible same-POS link introduces a different semantic function (additive versus excessive, emphatic versus barely). Neither source safety, POS, raw component count nor native parity supplies that fact. Keep current sense uncertainty explicit; do not turn this rejected ablation into a universal default or a per-word blacklist. The existing full-sentence local translation fallback is a separate route, not evidence that this lookup has high useful-message coverage. Any eventual integration must distinguish unresolved lookup from validated vocabulary replacement and qualify the actual fallback output separately.

No new selector, threshold sweep, corpus work, model run or app change was performed for this closure.

## Provenance and resources

Original preparation remains `compare.py` / `protocol.json`. Root found a synthetic mask-control fixture missing `concept_id`; before execution, root preserved those files and wrote `compare_r02.py` / `protocol-r02.json`, adding that field solely to the synthetic control and retaining a separate r02 approval/execution closure. The semantic gate was unchanged. This was a pre-execution control defect, not a failed corpus run.

The single amended run completed in **12.1207 seconds**, VmHWM **115,507,200 bytes**, within one CPU/nice10/1 GiB/120 seconds/32 MiB output and the 8 GiB reserve. Code SHA `c317bd6d4c7ce80ce610d7af8a1d4e43be7031cbd5cc0bbd16e694d4b66ea715`; protocol SHA `e1220caf9fa6c41b0a4c5122e3e9d3d3bcd444550aaebc24a333681a9adeef38`. All output hashes were independently reread for this closure. The earlier malformed read-only SQL inspection and correction remain recorded in the preparation receipt; no data was mutated.

Private evidence: `/home/ai/Development/investigations/vipi-semantic-admission-gap-20261109-r01/`, including `outputs-r02`, `changed-emission-review-r01.json`, `dictionary-flag-keyed-read-r01.json`, root run intent/transport and preparation receipt. `completion-receipt.json` binds the original and amended sources, all output/provenance hashes and this result. No commits or original artifact edits were made by this closure.
