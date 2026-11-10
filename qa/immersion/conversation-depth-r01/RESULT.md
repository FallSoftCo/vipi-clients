# Frozen conversation diagnostic — capture closure

The actual Android default route captured all 80 frozen BST VALID messages in both pairs at densities 0.25 and 0.75, with empty exclusions: 320 rows, zero translation/model calls and zero captured exceptions. No runtime or content changes were made. Independent semantic review remains pending; these are raw selection counts, not useful or correct coverage.

| Pair | Density | Nonempty / 80 | Selected native words / 864 |
|---|---:|---:|---:|
| EN→JA | 0.25 | 63 | 137 |
| EN→JA | 0.75 | 63 | 153 |
| EN→SW | 0.25 | 68 | 151 |
| EN→SW | 0.75 | 68 | 179 |

Every selected unit is a single source word with starter-pack provenance. There are no selected frame units or exact-reference hits. All zeros remain in the denominator. Pronouns/function words versus useful content/constructions require the separately frozen review rubric.

Android and Apple match all 320 span arrays, complete script/reading outputs and native word ranges. Android contributes no additional anonymous review option. Raw origin/status names differ on all rows only by enum spelling: 262 partial and 58 model-not-ready rows. The additive reconciliation normalizes spelling solely for comparison; raw evidence remains unchanged.

Android build took 69.80 seconds; instrumentation body 97.69 seconds; capture including boot/install/cleanup took 297.36 seconds. Fresh-engine route elapsed median is 245.19 ms, p95 332.55 ms and maximum/first route 2,029.62 ms. These are emulator observations, not production-device latency or total-process memory measurements.

Both scoped QA packages were removed, the main application path stayed unchanged, and secure/system settings are byte-identical before/after. The emulator exited abnormally with -6 during requested cleanup shutdown: its log records the graceful-shutdown request, then `stop: Not implemented` and `libc++abi: terminating`. All output retrieval, uninstall and postflight commands had already succeeded. The owned process is absent. This is explicitly not a clean emulator exit. The original bookkeeping script rejected exit -6; its bytes remain retained, and an additive closure reconciliation permits read-only accounting of the completed capture without replay.

Selection uses 40 persona and 40 empathetic-context conversations with fixed length quotas and hash ordering, not matching-based selection. Exact/normalized source and complete-prior overlap checks passed against the declared finite exposure inventory; five cases contain individual previously seen prior turns. Broader historical exposure cannot be excluded. BST is prompted crowdsourced dialogue, not representative customer traffic. Prior dialogue is reviewer-only and was never staged into the native capture.

Private evidence root: `/home/ai/Development/investigations/vipi-conversation-depth-20261109-r01`. `completion-r01.json` binds the frozen selection, capture, bookkeeping, cross-platform comparison and cleanup reconciliation. Root’s semantic review has not been opened by this worker.
