# Android candidate producer: qualified research integration

The real indexed catalog reader, frozen producer/selector and native current-tuple wrapper compiled and passed on the existing API 35 x86_64 emulator. The run used the separate `co.fallsoft.vipi.sourcecontextqa` package, retained offline models, app-private streamed inputs and the current clean Android source plus frozen overlays. No customer path was activated.

All 52 frozen records matched exactly: 145 candidate occurrences, 46 gate records and 312 selection decisions. All stale-text, changed-protection and changed-bundle checks passed. Actual Android candidate fields, gates and selections also matched the frozen results for all 52 records. Native source-mask objects are intentionally different representations; their geometry sets matched 51/52. In `qualified-noun-009`, the native snapshot lacked frozen masks `[73,78]` and `[79,81]`; selections remained equal.

The current-tuple wrapper retained evidence for 60 original head occurrences with 149 supported tuple occurrences. None became conditionally eligible: 25 gates explicitly reported `native_name_protection_unavailable`; the other 21 had no qualified context rule. Ordinary qualification remained intact (42 occurrences). This is an explicit Android capability limit, not a hidden POS-to-name approximation or a semantic-policy change.

The offline build completed successfully in about 81 seconds. Instrumentation reported 15.825 seconds for one test. Identity/model/catalog preparation took 6.807 seconds; frozen producer median was 23.775 ms and native preparation median was 60.780 ms. These measurements cover different operations and do not establish production message latency. Process PSS sampled before initialization and after case calculations was 116,650 and 223,117 KiB; VmHWM at the latter sample was 416,172 KiB. Samples include the app/test process, JSON fixtures and retained result records. No forced GC or heap-retention study was performed.

Both isolated packages were uninstalled and confirmed absent; main package identity and secure/system settings remained exactly unchanged. Only owned emulator 5620 was stopped (exit 0). No other emulator, phone or backend was touched. No new ARM64, API 28, R8, meaning or population-coverage claim is made.

Review artifacts:

- `integration.patch`: clean committed-base patch for the twelve Kotlin source/test files; canonical app files remain unchanged.
- `staged-main/` and `staged-test/`: exact compiled source overlays.
- `qualification.json`: source/APK/output hashes, exact parity result, native limitations, resource observations and closure.
- `launch.py` and `execution-freeze.json`: executed bounded launcher and immutable binding.
- Private root: `/home/ai/Development/investigations/vipi-android-candidate-producer-20261109-r01`; raw output is `execution-r01/candidate-output.stdout` (SHA256 `17370d22d63087a77ad0249ea2ce7f9896d8de258a31e24f32d77846e0ab1c59`). Original accepted APKs and r04 authority/receipts remain preserved.

The full catalog and scalar-case fixture were supplied as pinned QA inputs. A customer catalog/resource distribution route and any display admission remain separate work. Root owns source integration and commits; this worker committed nothing.
