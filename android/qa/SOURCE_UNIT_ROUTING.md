# Source-unit routing qualification

The routing candidate uses only the accepted bundled catalog. It changes when a full local translation is requested; it does not expand the catalog, relax source authorization, or claim wider linguistic coverage.

An automatic request returns a nonempty approved source partial immediately, without checking translator readiness, invoking translation, or performing target-dependent alignment. An explicit full-reference action may extend that same partial with one bounded local translation after identifier validation. It retains the source faces and never runs alignment merely to discard its result. Complete-reference and lookup-miss routes retain their existing behavior. Cached partials remain useful when a row re-enters the viewport; an explicit full request bypasses a partial-only cache. Same-attempt failures and cancellations are retained until a new explicit retry epoch. Separate message lookups are not held behind a pending provider request.

The frozen contract and six fixtures are in `qa/immersion/coverage_ceiling_experiment/source-unit-routing-{contract,fixtures}-r01.json`; the separate fixture erratum clarifies that lookup misses must have no approved partial. Do not tune rows or inputs when a native boundary check fails.

`SourceUnitRoutingDeviceTest` records actual native catalog results and actual ML Kit outputs. Its direct-core probe counts readiness, translation, alignment, and partial callbacks; separate production `ConversationImmersion` phases measure automatic first/warm and explicit first/repeated requests. These prepared-model engine observations are not global cold-start measurements. The test verifies the already installed model, disables the assigned emulator's network during provider calls, records network observations, and restores both radios. Stage the hash-verified fixture at app-private `files/source-unit-routing-fixtures-r01.json`. Use a fresh run ID and preserve failures:

```sh
adb -s "$VIPI_QA_SERIAL" shell am instrument -w \
  -e class co.fallsoft.vipi.SourceUnitRoutingDeviceTest \
  -e vipiDedicatedEmulator true -e vipiRoutingArm candidate -e vipiRoutingRun 001 \
  co.fallsoft.vipi.test/androidx.test.runner.AndroidJUnitRunner
```

`SourceUnitRequestDeviceTest` uses the real native catalog/cache with explicitly synthetic providers. It exercises same-attempt coalescing, cancelled work, generation changes, unavailable models, controlled errors, the actual 30-second deadline, and independent-message responsiveness while full translation is pending. It does not constitute provider-quality evidence.

`SourceUnitUIDeviceTest` uses the actual native row and frame clock in an isolated screen, with no peer traffic or account substitution. Controlled gates allow a visible cancel and a visible failure/retry; the successful retry calls the actual installed ML Kit translator. It records continuous source/target phase geometry while a full request waits, exact original copy, complete-reference view, actual local player start/completion, and zero extra translation on repeated view selection. Player observations do not establish acoustic pronunciation quality. The source row remains a deliberately curated approved example.

```sh
adb -s "$VIPI_QA_SERIAL" shell am instrument -w \
  -e class co.fallsoft.vipi.SourceUnitRequestDeviceTest \
  -e vipiDedicatedEmulator true \
  co.fallsoft.vipi.test/androidx.test.runner.AndroidJUnitRunner
adb -s "$VIPI_QA_SERIAL" shell am instrument -w \
  -e class co.fallsoft.vipi.SourceUnitUIDeviceTest \
  -e vipiDedicatedEmulator true -e vipiRoutingUIRun 001 \
  co.fallsoft.vipi.test/androidx.test.runner.AndroidJUnitRunner
```

Use only the explicitly assigned existing emulator. Preserve its account and history. Retain exact source manifests, installed APK hashes, logs, complete or incomplete JSON receipts, screenshots, and restored environment settings. Run instrumentation serially. Frozen control and candidate sources must remain distinguishable; method presence alone is not source qualification.
