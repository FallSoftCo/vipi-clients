# TRAIN-frequency primary inventory and sense-consensus audit

This is build-time research. No new mapping, matcher, provider or app pack is enabled.

The source freeze selects the 3,000 most frequent normalized forms in 9,535 free-human BST TRAIN convai2 turns, before looking up target candidates. It retains frequency ranks and all omissions. There are 7,740 distinct TRAIN forms; the final selected form occurs twice. Persona role-play frequency is not worldwide chat frequency.

The existing exact lexical009 dictionaries supply indexed evidence across all ten non-English targets. One verified target shard was expanded at a time, read, and retired; retained English/Spanish expansions were reused read-only. No dictionary/model download or new infrastructure was required. The full candidate index is 48,627,712 bytes and the initial pass took 13.97 seconds on the controller's existing Python runtime. These are build-time observations, not phone lookup measurements.

| Target | Forms with at least one complete head/POS/reading candidate | Forms with multiple linked senses | Missing target links |
|---|---:|---:|---:|
| Arabic | 2,099 | 1,550 | 527 |
| German | 2,479 | 1,991 | 163 |
| Spanish | 2,498 | 2,139 | 124 |
| French | 2,467 | 2,072 | 145 |
| Italian | 2,424 | 2,022 | 206 |
| Japanese | 2,269 | 1,670 | 339 |
| Korean | 2,166 | 1,710 | 468 |
| Portuguese | 2,437 | 1,978 | 197 |
| Swahili | 1,377 | 661 | 1,246 |
| Chinese | 2,088 | 1,760 | 338 |

These are **candidate evidence**, not approved vocabulary or correct conversation coverage. Of the 3,000 source forms, 2,646 have complete-source content-sense links, 255 have no compiled surface, 74 have no sense link, 15 have only unsafe partial surfaces, and 10 have no content POS. Membership alone can admit rare noun/verb homographs of ordinary function words such as `I` and `a`; the later source-usage audit must reject these interpretations. Reading presence is not pronunciation correctness. A canonical dictionary verb may still need a different displayed form.

`scaled-primary-inventory-summary-r01.json` binds the complete retained index and source receipts. Full evidence is under the private investigation directory `scaled-content-inventory-r01/`. Exact compressed dictionary assets remain in the authoritative source closure, not duplicated in this research commit.

## Full source senses and consensus

The compiled English terms table preserves translation groups and foreign native-gloss supplements, not every native English definition. Therefore an available translation cannot be assumed to cover every source sense. For example, `coffee` has seven retained modern noun definitions but four explicit English translation groups. Absence of another target is not proof of agreement.

`extract_primary_source_senses_r02.py` reads only the 6,464 referenced English entry IDs and their raw definitions from the existing read-only Storage Box inventory. Every completed 128-entry batch is durable. It does not copy or hash-read the complete 4.43GB database. The known historical inventory SHA, exact route/size, embedded source metadata and fresh selected-output hashes are distinguished explicitly. The earlier reader was stopped after observed remote-page latency exceeded its initial time design; its interruption receipt is preserved. No archived source was modified.

`scaled-consensus-policy-r01.json` preserves the first pre-output policy. Revision2 corrects family grouping before execution: POS variants of the same canonical head are grouped for learned-word accounting; ambiguous multi-head families remain unresolved. It also explicitly classifies ordinary `in`/`on` usages with the closed-class source guard.

The evaluator partitions agreement over all explicit active source translation groups, including different POS. It also retains per-POS agreement, missing target groups, missing source definitions, source inflection and reading issues. Multiple target synonyms are allowed: consensus requires at least one shared valid target face/reading, not a globally unique target. Native-sense completeness is kept separate from translation-group-only agreement. The latter is not a qualified fallback.

TRAIN measurements use actual occurrence positions, existing protection/boundary guards, disjoint content selection, 10/25/50% budgets and canonical-family known50/100/300 exclusions. They report both message-mean and token-weighted depth, length strata and distinct selected families. They do not claim semantic accuracy before actual mixed outputs are reviewed. Failed all-senses agreement does not permanently disqualify a useful common concept: source-role and sense-specific policies remain separate possible increments.

The provenance remains Wiktionary contributors, extraction by Tatu Ylonen/wiktextract through Kaikki.org, CC BY-SA 4.0; source entry URLs and exact sense IDs accompany candidates. BST attribution and CC BY 4.0 notices are retained in `evaluation-data-licenses/`. Existing frozen held-out captures are not used to rank or author new entries.

## Completed structural audit: limits and next decision

The exact run took19.61 seconds locally. Raw archive extraction retained6,464 English entries and30,678 native sense rows in1.04MB compressed. The final64 IDs were resumed once from the durable checkpoint; the first6,400 were not read remotely again. `scaled-content-evidence-r01/manifest.json` preserves exact source extracts, initial interruption/incomplete receipts, metadata, full audit and hashes (6.19MB compressed).

Source partition:75 closed-class usages,321 with no active lexical entry,635 needing source-inflection realization,799 lacking an English translation group for an active entry,1,066 with unresolved native-definition completeness,102 in the conservative structural source-evidence stratum and2 unresolved family groupings. These are evidence gaps, not2,898 demonstrated wrong meanings.

At25%, on9,535 TRAIN turns, the structural stratum yields the following **raw eligible** noun/verb/adjective content anchors. Adverb-only output is excluded from these columns:

| Target | Candidate forms | Content-anchor messages | Mean anchor depth | Messages after global known300 |
|---|---:|---:|---:|---:|
| Arabic |35|222|0.18%|113|
| German |63|325|0.29%|177|
| Spanish |57|296|0.26%|189|
| French |56|263|0.24%|192|
| Italian |56|284|0.24%|176|
| Japanese |46|252|0.23%|136|
| Korean |33|147|0.13%|86|
| Portuguese |57|284|0.25%|175|
| Swahili |16|135|0.13%|59|
| Chinese |39|304|0.26%|115|

The weaker translation-group-only arm retains77 Swahili,147 Japanese and245 Spanish forms, with869/1,064/1,727 raw anchor messages and0.75/0.97/1.62% mean anchor depth. It explicitly lacks full native-source-sense support and is not an acceptable automatic fallback. Per-POS agreement after the source-use guards exists for211/365/690 forms respectively; source roles and ordinary conversational senses remain a materially different opportunity from the all-senses floor. All density, known50/100/300, length and adverb/core-content views remain in the exact audit.

Neither arm is semantically approved. The frozen name `source_supported` denotes a structural evidence stratum, not a globally-safe class. Inspecting its outputs exposes additional issues: lexical-only entries omit competing grammatical or abbreviation analyses (`either` also has determiner/pronoun uses; `dr` also abbreviates doctor/drive/debit). A shortest-string target tie-break selects narrow or regional alternatives such as Japanese `医院` for hospital and Spanish `brígido` for dangerous. The full alternative sets survive. No output was rewritten or improved after inspection.

This is a diagnostic floor, **not** the proposed admission rule for every ordinary word. The next proposal must retain ordinary/common-use target evidence, competing source roles and actual-context sense risks. It must not require all dictionary senses to be globally equivalent before a reviewed common concept can be useful. The current reviewed candidate and its fixed results remain unchanged.
