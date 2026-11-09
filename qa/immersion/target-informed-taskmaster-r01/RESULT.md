# More vocabulary, but new sense errors: do not activate

The frozen cached200-row Taskmaster comparison retained all rows, including14 `INVALID_LANGUAGE` nulls,185 unique normalized source strings and zero overlap with the earlier eight cases. Both arms used the same186 full targets, current protections, dictionary assets, density0.25 and caller-known behavior. No new translation calls occurred.

| Mechanical result | Unchanged A | Target-informed B |
|---|---:|---:|
|Nonempty messages /200|97|133|
|Selected spans|129|199|
|Changed native words /1,587|146|214|
|Null provider outcomes|14|14|

B added81 spans, lost11, changed64 messages and gained36 previously empty messages without an empty loss. The original denominator is200, not only successful targets or nonempty outputs. These are availability counts, not semantic accuracy.

## Frozen agent review

The author read all400 anonymous options, including all230 nonempty outputs with source/prior dialogue. Root read all80 options in the fixed40-case subset selected by ID hash before outputs. The method key and full target references were separate until both reviews froze. Aggregate mechanics and historical corpus exposure were disclosed; no bilingual gold or population claim follows.

| Whole-output judgment | Author A /200 | Author B /200 | Root A /40 | Root B /40 |
|---|---:|---:|---:|---:|
|Correct, nonempty|90|113|18|24|
|Minor form/casing issue|1|7|1|2|
|Material error|6|11|0|1|
|Uncertain|0|2|0|1|
|Unavailable, zero usefulness|103|67|21|12|

Author strict clean-message changes are30 gains/7 losses; minor-tolerant33 gains/4 losses. Root40 changes are8/2 strict and9/2 minor-tolerant. Among81 added spans the author labels68 correct,6 minor,5 material and2 uncertain. All11 lost spans were judged valid. Do not erase losses or use majority votes to overwrite judgments.

The five newly material author judgments are cabin-class **Economy→Economía**, approval **Great→Grandes** twice and travel-duration **drive→disco** twice. Root independently identifies the drive error in its40-case subset. Post-freeze inspection confirms all five bad faces already occur in the full cached target: B exposes an erroneous provider interpretation as a dictionary-backed inline replacement. Exact ownership did not validate the intended sense.

Author pre-existing material judgments are assistance-noun **help→ayudar** in four cases and football-team **manager→gerente** in two. These remain in both arms. Root considers the assistance mapping a minor role/form concern rather than material in the overlapping case; both original judgments stay retained.

Four option disagreements occur in the root40 overlap: help→ayudar material(author)/minor(root) in both options; eating→comer correct(author)/minor(root); interesado minor(author, unsupported speaker gender)/correct(root). Both mark noisy open-gyros→abrir uncertain. Sports juego is accepted as regional vocabulary. The cabin-class terminology judgment is not as indisputable as the disk-drive sense error and has only author review here.

Author word accounting distinguishes correct individual units from clean whole outputs. Strict accepted unit words rise139→194; strict clean whole-output words134→173. Minor-tolerant clean whole-output words135→187, all out of1,587 native words. This is measured diagnostic depth, not a90% usable-coverage claim.

## Limits and decision

Retain the evidence, but do not activate B as a general admission policy. It produces useful gains and new clear errors. Reciprocal scope ownership prevents competing alignment claims; it cannot establish that the provider chose the right same-POS sense. Full source/prior context, lexical function and unresolved dictionary alternatives remain relevant. No word blacklist, ratio sweep, source-safety reset or new grammar exception was applied after these outcomes.

The graph contains172 unique edges (max8 per message),383 form/term proofs and186 ownership-control passes. No query-overflow or non-provider abstention was recorded. Null inputs remain explicit. Actual source POS was computed inside the native snapshot but was not serialized; it must not be retrospectively inferred from dictionary POS. Source/target native words and sentences, masks, full raw diagnostics, complete mixed outputs and every added/lost span are retained.

## Execution and exposure provenance

The first run completed A/B collections but crashed while building the final report dictionary: a descriptive `baseline` key duplicated the baseline array key. Its source, compile warning, test failure, restored state and absent attachment remain retained. Root authorized one serialization-only r02 rerun: rename the descriptive key to `baseline_provenance`. No algorithm, source/target, sampling or threshold changed. This was two execution attempts with one retained complete result, not zero computation in r01 or a hidden successful-first-run claim.

R02: prepare4.74s, build21.07s with two jobs, test31.24s (selected test8.10s). A first invocation468.5ms, subsequent median9.77ms; B first407.2ms, subsequent median10.88ms. B runs after A; these are actor-first/subsequent timing, not reset-cache or same-input warm repeats, and exclude new translation. Raw result4,862,966B; peak additional owned disk165,175,296B; final free50,092,052,480B. No process-memory measurement was made. Preferences restored, app stopped, user data retained, both labs alive.

Author review SHA `c848b0d16c9c17ffcd2d6005b41fa51ccd68bb0b64d05de3ed096b2659d5c0e8` froze at16:30:51.121UTC; root review SHA `87299d778185a65d13a6e4aab3ef997a2b17570ed38f90332df7fd03827f893d` records16:30:31.920UTC. Root's example-judgment message became model-visible here after the author freeze tool returned and its notification was sent; the judgments were already in that tool call. A distinct transport-arrival timestamp is unavailable, so only this visibility ordering is claimed. Original labels remain unchanged. `review-exposure-receipt.json` preserves the distinction.

Private root: `/home/ai/Development/investigations/vipi-target-informed-taskmaster-20261109-r01/`. Key files are `run-r02/output.json`, `packet/anonymous-all200.json`, `packet/anonymous-root40.json`, separate key/witnesses/deltas, both frozen reviews, `joined-review-r01.json`, and r01/r02 receipts. No customer activation, Swahili run, new model call or canonical app edit occurred.
