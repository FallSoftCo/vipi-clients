# Native phrase frames — 2026-10-25

Schema-6 phrase packs and both native implementations are mechanically qualified. Current pack revision 005 contains 18 constructions and 1,620 directed mappings. General conversation immersion, majority coverage and store readiness remain unachieved. No release trust key, production backend or store state changed.

## Current expansion — pack 005

Fourteen constructions supplement the original four: drinking coffee/tea, eating bread/cheese, listening to music, watching a movie, playing piano, walking a dog, bank account, train station, bus stop, phone number, liking music and a possessed dog. Each is authored in all ten languages. These are 18 constructions, not 1,620 independent concepts. Train station, bus stop and phone number use a complete lexical unit where replacing only one word would duplicate a modifier. No rice construction was accepted because common Japanese/Korean terms also denote a meal.

Finite nonempty context slots can now constrain a focus without requiring an additional literal. Explicit possessors remain outside the focus, including Arabic suffixes and Korean particles. Bare focus and whitespace-only context remain invalid. French apostrophe windows accept only listed clitic prefixes; they do not split arbitrary names such as O’Neill. Bounds remain 12 pattern parts, 32 choices per slot, 128 matcher states, eight words/256 UTF-16 units per window and 4,096 windows per input.

The first activity revision had an incorrect French `Je écoute` reference. Eighteen affected record revisions were quarantined before corrected `J’écoute` records were assessed. Historical pack 004 and its mechanical test passes are retained as superseded evidence, not linguistic acceptance. Bound authoring sources are archived beside both generated batches.

Current authored records: `authored-phrase-frames-006/records.jsonl`, SHA `9aa29558a7421c771f6b7860293c4ca952bfa26e3116e5d116bd6bb369b8e877`. Reviewed export 005 SHA: `9e562715665c8d5b1daa729d945abb6eea04a81eac2ed1f1d5c6022306a32f44`. Ledger: 140,521 revisions, 140,062 current records; 132,967 candidate, 18 quarantined and 7,077 reviewed (5,457 exact contexts + 1,620 frames); 14 imports complete, sequence 148372. Assessments are by the author, not independent reviewers.

The 90 signed revision-005 pair files total 10,469,376 SQLite bytes. Archive SHA: `04febc283d23fc84e9e03bae5b5e047794b46007d20afaca57ade716089bc835`; build receipt SHA: `13627594049a4d1db20a9d14f71b65e1b6decd4045c302194c3c631205c2deed`. Qualification keys remain ephemeral and outside release trust; exports remain `release_ready:false`.

Both native platforms pass 1,620 reference mappings, with 1,588 visible substitutions and 32 unchanged Roman-spelling cases. Android combined run 009 passes in 45.548 seconds; physical iPad combined run 008 passes in 23.027 seconds. Reports are `reviewed-frame-android-009.json`, `frame-capture-android-009.json`, `reviewed-frame-apple-007.json` and `frame-capture-apple-007.json`.

| Actual provider-output replay | Android | Physical iPad |
| --- | ---: | ---: |
| Cases | 1,620 | 1,620 |
| Cases with matched mapping | 982 | 1,133 |
| Cases with visible immersion | 964 | 1,109 |
| Lookup/alignment median / p95 | 4.085 / 8.059 ms | 2.882 / 3.416 ms |

Replay uses explicit composite captures: 1,431 unchanged cases reused from the prior full capture, plus 189 fresh cases (180 new and nine corrected French sources). `incremental_phrase_probe.py` compares complete sample content, protocol methods and provider labels, checks expected/unique case counts and binds every row to its originating capture. Changed content under the same ID cannot be silently reused. The composite does not claim identical provider model bytes or a fresh full model execution. Android component runs verified network absence; Apple component runs had networking available.

Composite hashes: Android `9aaf280da0dcb03219a30305294885ff9b0b43adbd3d1ca9f6956d8e0d454c29`; Apple `29df1b27594cd7a26e6c0f630236db1cb3ab469e5e7f92eb27ecacd5efc6bead`. Actual-output report hashes: Android `783accdf6ad157b34419bfe80ae4c2fe62d4e56767701037399b459df8bafcf6`; Apple `bb9254c9f152b6d9d6eed736406941f5468d87abf6d2d031b3ec7bc7c6b56949`.

## Conversation evaluation

`conversation_probe:true` evaluates all approved focuses in an actual source/translation pair, without demanding that the first-token translation probe happen to be the focus. The evaluator validates capture/build identity, exact text, UTF-16 spans, readings, non-overlap and baseline identity. Its optional dictionary comparison reports separate-path availability; it does not merge mappings or claim accuracy.

On 300 XPersona Italian/Japanese/Korean validation messages translated to the other nine languages, pack 004 produced zero matches on Android. Pack 005 produces 22 Android and 21 iPad matches, all from four Italian messages. Twenty and 19 are new relative to the respective strict dictionaries. Separate-path union availability is 558/2,700 (20.67%) Android and 606/2,700 (22.44%) iPad. No Japanese/Korean source gain is demonstrated. No majority claim is justified.

Reports: `frame-conversation-android-010.json` SHA `2b6f10a7f16db1ed451929329b1b9acf942c17b002307ec657dff8ef9520cd3d`; `frame-conversation-apple-008.json` SHA `6dde396c21cc0e063e2bdcfa4b34b61b2e1fbd784c8b04a891c51cb758555e1b`. Median/p95 lookup/alignment: 5.260/10.993 ms Android and 3.419/4.957 ms iPad. Native replay passed Android run 010 and physical iPad capture-only run 009.

Current regressions pass: 60 language-pack tests; Android core and both debug APK builds; Swift core; two frame-evaluator tests; two XPersona selection tests; incremental-capture provenance checks. Earlier captures, failed runs and the exact emulator storage-retirement receipt remain retained. Old revision-006 emulator dictionary files were removed only after verifying all 90 database hashes and the retained revision-007 replacement; current packs, models, captures and account data were preserved.

## Historical first four constructions — pack 003

## Implementation

Explicitly assessed local phrases constrain both the source focus and its occurrence in the actual translation. Two indexed tables enumerate approved finite variants. Native sentence/word boundaries produce bounded query windows; no approximate search or generated target enters runtime. Contradictory source meanings veto a substitution even when their target phrase is absent. Repeated matched focuses, oversized scans and mismatched scopes abstain.

Only a successful two-sided match creates ephemeral UTF-16 source and target scopes; generic vocabulary decoding cannot grant them. Existing protection, reading, density, overlap and speech rules remain. Qualified shared ideographs such as Chinese/Japanese 水 retain the target reading and speech language. Identical Roman spelling still produces no visual substitution. This verifies speech-language routing, not a fresh acoustic listening assessment.

Pack kind, schema, policy, files and rollback receipts are separate from dictionaries and exact-sentence contexts. Ledger records require a phrase-scope assessment; earlier exact-sentence approval cannot be reused. Exports select `exact_context` or `local_phrase` explicitly.

## Data

Four constructions across ten languages/all 90 directions produce 360 records: reading a book, drinking water, birthday party and phone charger. These are four meanings, not 360 independent vocabulary concepts. Assessments are explicitly authored, not independent.

Revision 002 fixed Korean frames ending before an attached particle: the particle belongs to matching context but remains outside the noun replacement. Revision 003 adds checked verb forms, German `jetzt`, French apostrophe spellings, telephone linking words and Korean particles. It does not accept unlisted compounds or provider errors merely to raise availability.

Current records SHA: `1a565109abb6022799d4cf656ca46e85c0ed3b05fe7f900a643b78f57be1c797`. Reviewed export SHA: `90fb893279f67ab1bdd565affbad439d4f4505bbb38acd7790fe57a593ed9c1f`. Ledger: 139,243 revisions, 138,802 current records; 132,967 candidate, 18 quarantined, 5,817 reviewed; 12 completed imports, sequence 145798. Reviewed records comprise the previous 5,457 exact contexts plus 360 frames.

`artifacts/reviewed-frames-003` contains 90 signed pair files totaling 3,317,760 SQLite bytes, with 1,161 indexed variants per side. Qualification keys are ephemeral; no private key is written. Archive SHA: `44618ba28e2753db508bc138b7f47f0d2c64933e66beafe65c67e63b8342ff43`. Build receipt SHA: `a6ff4961bc1faf7b55a7a806a28f0fbbeb979fd24fe9c4ac6c31578fd73d7794`.

## Native evidence

Both platforms pass 360 reference cases: 360 mappings, 356 visible substitutions and four unchanged Roman-spelling cases. Checks include scripts/readings, emoji/UTF-16 offsets, repeated source/target phrases, an unrelated repeated target word, protected code, overflow, wrong pack kind, tampered signature/data and removal.

| Measure | Android | Physical iPad |
| --- | ---: | ---: |
| Reference report | `reviewed-frame-android-006.json` | `reviewed-frame-apple-006.json` |
| Reference lookup/alignment median / p95 | 5.431 / 11.351 ms | 3.109 / 3.691 ms |
| Literal-pack actual-output mappings | 168 / 360 | 207 / 360 |
| Expanded-pack actual-output mappings | 230 / 360 | 267 / 360 |
| Expanded-pack actual-output immersion | 226 / 360 | 263 / 360 |
| Newly available / lost cases | 62 / 0 | 60 / 0 |
| Actual-output lookup/alignment median / p95 | 6.147 / 10.070 ms | 2.979 / 3.588 ms |

These are availability results on the same authored development cases and retained provider outputs, not accuracy or majority-conversation rates. Each source is reused across nine targets. Variants respond to development results, so this is not held-out acceptance. Remaining misses include wording, compounds, token boundaries and model errors.

Each provider made 2,493 fresh whole/focus/window calls for 360 cases. Protocol SHA: `7474ddb13e1ee6bedba1b579b2f69c1d202aba9b77b575a26ffe01ecd1012cfc`. Android run 008 took 121.487 seconds and verified network absence; capture SHA `ffb33302b7e1fbd1a2b8ef6afd2c3bffaddd5bfeff4d61195ea2801e49ca5a80`. Apple run 007 completed on the physical iPad with networking available; capture SHA `e2911c6790db4aaeb3723a2a4e363e4ee06fe59e463f88bce0dc4098bd40f3ef`.

Current actual-output report SHAs: Android `1b8f0b069667fbe1ea2e201b13c11581fe54fed124fc8bf31968c6f6b415107e`; Apple `0d29f5084e48760f0252969fb38a167585c7ff97b60386ee3678720c2ba39192`. `evaluate_frame_capture.py` checks capture/build identities, exact source/target text, Unicode spans and required readings before calculating per-direction availability and same-capture changes. Replay is not another model execution.

## Validation and retained failures

Language-pack regressions: 59 pass. Swift core: 17 XCTest and 23 Swift Testing pass. Android core/debug/instrumentation builds pass. Android combined native tests pass in 13.451 seconds; physical iPad combined run 007 passes. Xcresults remain on the Mac; JSON/log receipts are retained on OZZZ-OS.

Earlier failures are preserved: missing Android SDK environment; an incorrect test expectation for identical spelling; an iPad test launched before fixture staging; Korean particle boundaries; and a test substring search that could not address an Arabic focus before a combining mark. Expected offsets now use retained code-point spans. iPad run 006 refused to overwrite earlier receipts because device copy skipped changed configuration with identical size/mtime. Updating the source mtime and reading back exact bytes confirmed the new configuration before successful run 007. None of those failures is counted as a pass.

Validated `frame-qa.json` configuration now lets both harnesses evaluate new pack revisions/captures without rebuilding apps. Read device configuration back after copying; a successful copy response alone is insufficient for same-size/same-mtime changes.
