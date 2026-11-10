# Contextual source-sense hold — Android qualification

The generic `withheld_contextual_sense` guard preserves the Swahili hair record, its target and original provenance, but emits no approved output and records `unqualified_source_sense`. Recognition and the source mask survive. This is a deliberate withholding policy, not a new inferred sense or alternate translation.

The retained dictionary explicitly connects nywele to human-head-hair unywele; unyoya separately attests animal hair/fur, and manyoya is its plural. The original independent review labels remain unchanged. The candidate retains all 213 records; only hair gains the guard. Other 212 records, Japanese data and frame packs remain unchanged.

The actual Android default route captured the frozen 80 sources at two densities and two pairs: all 320 rows completed, zero translation/model calls and zero captured exceptions. Independent comparison found exactly two changes: the Swahili cat-hair span disappears at both densities. All other 318 selected outputs, readings and native geometry are unchanged. Both changed rows retain the source mask with no approved output. This does not improve coverage: valid human-hair uses are deliberately withheld too.

The original combined test failed after the completed default capture because its separate control assumed the existing legacy catalog would emit hair→nywele without evidence. It already abstained, so that positive prerequisite failed. The original test, raw capture, failure and cleanup receipts remain intact; the 320 rows were not replayed.

The amended isolated control supplies an explicitly synthetic lexical entry and target to the real `LocalImmersion.align`: unmasked = 1 span, held source evidence = 0 spans. This proves the actual alignment path respects the retained mask, without adding a production dictionary edge or claiming that the old catalog leaked this particular mapping. Bare, human-hair and cat-hair controls also verify the exact hold reason and mask. Four controls passed in 0.413 seconds; no conversation rows or provider calls occurred.

Original build: 1 minute 34 seconds (Gradle). Original capture body: 61.581 seconds. Control-only test APK build: 1 minute 24 seconds (Gradle). Control capture including boot/install/cleanup: 192.45 seconds. Both attempts preserved the 8 GiB floor, removed the scoped QA packages, preserved secure/system settings and the main app, and ended the owned emulator with exit 0. No signing, iPad, UI replay, service changes or canonical data installation were performed by this worker.

`completion-android-r01.json` binds the code, candidate data, primary-source extract, original failure, completed output verification and isolated control closure. Root owns Apple qualification and any activation decision.
