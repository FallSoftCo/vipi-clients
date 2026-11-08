# Gated native starter qualification

This experiment does not enable new production mappings. `ReviewedSourceUnitQa` is compiled only into the instrumentation package. Its input JSON is staged into app-private QA files, not bundled in the app. `ConversationImmersion` accepts an optional policy only in DEBUG builds, uses its immutable version/hash in cache keys, and keeps the accepted whole/sentence-reference paths first. With no explicit policy, the shipping catalog and routing remain unchanged.

The reviewed r02 input is SHA-256 `67f041f3024c0e3679d54de9afa2debcebba1ad42e0a79b7bb0e4aacb90f2f60`, version `reviewed-source-starter-en-v002`. The paired 240-case protocol is `fd89fd2bf9988b657fe3f8d689f23d5554364c9c5b73675ac80ebf6a6f2e3ec6`. Both live under `qa/immersion/coverage_ceiling_experiment/`. The protocol uses 80 previously reviewed English messages, repeated for Swahili, Japanese and Spanish, at requested density 0.10. It is native qualification, not a new blind coverage estimate.

The producer preserves the frozen source-word/contraction scan and noun/question guards, then requires complete native UTF-16 word boundaries. It rejects unchanged normalized faces and any substitution changing the original message's existing native literal set. This latter guard is deliberately stronger than the research regex for URLs, handles and unfinished code; its source hash and distinct rejection reason are captured. Before choosing one unit, it applies the existing native budget `max(1, floor(native word count × density))`. It does not invoke the aligner's whole-unit budget fallback. Quantization and existing accepted sentence units mean requested 0.10 is not a strict ten-percent population cap. Exact supported Japanese reading accompanies original target script.

Build a frozen app/test source closure and install it only on the assigned existing emulator, preserving account/history. Stage the two unchanged JSON inputs with their exact filenames using `adb push` and `run-as co.fallsoft.vipi cp`; verify destination SHA-256. Run `SourceUnitStarterPolicyDeviceTest` first. The cases cover contractions, inflections, emoji UTF-16 offsets, source capitals, native literal preservation, noun/question context, strict unit budgeting, Japanese pronunciation binding and corrupt-input rejection. They are structural controls, not semantic coverage.

Run baseline before candidate, with the compiler idle and the same APKs/inputs. Preserve host load, memory, APK hashes and the native source manifest. Replace `PRODUCER_SHA256` below with the frozen source hash of `ReviewedSourceUnitQa.kt`:

```sh
adb -s "$VIPI_QA_SERIAL" shell am instrument -w \
  -e class 'co.fallsoft.vipi.SourceUnitStarterDeviceTest#captureBaseline' \
  -e vipiDedicatedEmulator true -e vipiStarterRun 001 \
  -e vipiStarterProducerSha PRODUCER_SHA256 \
  co.fallsoft.vipi.test/androidx.test.runner.AndroidJUnitRunner
adb -s "$VIPI_QA_SERIAL" shell am instrument -w \
  -e class 'co.fallsoft.vipi.SourceUnitStarterDeviceTest#captureCandidate' \
  -e vipiDedicatedEmulator true -e vipiStarterRun 001 \
  -e vipiStarterProducerSha PRODUCER_SHA256 \
  co.fallsoft.vipi.test/androidx.test.runner.AndroidJUnitRunner
```

Each arm creates fresh engines/caches per pair, runs every case, and immediately repeats it. The callback counters record actual readiness, heavy alignment and source-producer work, separately from cheap source-presentation validation. Actual raw provider strings survive rejected results. Native source ranges, selected faces/readings/provenance, rejections, first/warm timing and process PSS are retained. Changed-word counts mean native words fully contained in selected source spans; exact ranges permit independent review. Tokenization precedes the timed request, and model-status checks are reported separately. These are installed-model engine timings, not global cold-start or acoustic latency.

Output is `files/source-unit-starter-{baseline,candidate}-001.json`. Use a fresh run ID and never overwrite completed or incomplete evidence. The test atomically writes checkpoints, restores original radio settings, and never requests a model download. A host-side deadline should also restore radio state after terminating only its own stuck instrumentation if necessary. Preserve misses and unavailable-provider results; do not alter data or budgets to match research hit counts. Capture wall time includes incremental JSON serialization and is not per-message latency. Semantic review of the actual native selections and separate root promotion are required before any production data enablement.
