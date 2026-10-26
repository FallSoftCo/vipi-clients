# Native phrase frames — 2026-10-25

Schema-6 phrase packs and both native implementations are mechanically qualified. General conversation immersion, majority coverage and store readiness remain unachieved. No release trust key, production backend or store state changed.

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
