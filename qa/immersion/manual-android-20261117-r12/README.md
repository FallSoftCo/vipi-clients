# Android popup Stop fix qualification, r12

Qualified only owned emulator 5624 and `.uxqa`. Installed APK hashes were independently read from the device and match the explicit reviewed build: app `db1b1357f5b446f38f8e667c6793da09db75014aa3225c05bbc7fe64eaea03ff`, test `682ee0714df757060ff96026943adefea04b2f1c81237d75c30be25e81358cba`. Original app account/data, user phone and other emulators were untouched. Existing models were retained; no model downloads or standalone four-case MT rerun occurred.

## Observed results

The strengthened production-popup real-provider case passed in 12.755 seconds. A native uncovered book tap invokes real ML Kit with `Could you book a table for two tomorrow evening?` exactly once and displays `¿Podrías reservar una mesa para dos mañana por la noche?` in production popup semantics and screenshot. Actual Spanish-script SpeechPlayback enters PLAYING; tap-to-playing was 1,191 ms. The report records one provider call and exactly four intentional Spanish speech inputs. Same-word Stop, a fresh cached word play followed by an active different-word switch once, footer Stop without generic-message replay, and cached whole-message playback all pass strict assertions. No Latin guide is spoken. The prior failed same-word popup receipt remains preserved under r11.

ManualLookupGestureDeviceTest passed both methods in 20.066 seconds: native word/whitespace taps, Stop, programmatic selection cancellation, exact native Copy, reverse normalized-display fallback to whole raw Spanish, raw Original mode and accepted Spanish speech input. EmbeddedSpeechStopDeviceTest passed in 6.603 seconds on the bundled covered presentation: generic footer Stop and stable native text width while audio is active.

These are actual native gesture/provider/input/state observations on this bounded fixture, not acoustic acceptance, all-pair linguistic correctness or physical-phone evidence. **Actual Android long-press/handle-drag/release translation remains unqualified.** The selection helper uses programmatic selection; it is not counted as genuine handle evidence. Existing debug MainActivity intents expose welcome/language/home/model setup, not a persistent manual-translation fixture. The instrumentation fixtures close after their run and expose no hold mode. No extra build or fixture was created for this gap.

## Source and ownership

The root reviewed `android-popup-fix-r12-source.diff` (SHA256 `56ded21249b95bf307d82295f1a81b04fea7365e6ecd5c2bcf4a1960fb0ee577`) before packaging. Outside dismissal uses touch-aware idempotent halt, preserving the interrupted range Stop token for the pass-through native gesture. Same-word consumes it; a different word begins once. Footer consumes the pending touch Stop before falling through to generic playback. Existing explicit Close and Back remain deliberate cancel. Source/file hashes are retained separately.

No partial source commit was made from the shared UX worktree. After runtime qualification, the sole separately approved title Text→weighted Spacer line was applied and is retained in `approved-title-only.diff` with before/after hashes. That visual-only adjustment was **not** present in the qualified APK and was not rebuilt here. UX owns final packaging, the complete UI source commit and the three handed-back files. Device ownership was also released to UX after capture.

## Guard and reconciliation

An inherited pre-packaging baseline initially stopped a dispatch because it counted 42.6 MB of intervening UX build allocation against test growth. That stopped attempt and its empty log are retained. The new dispatch began before the subsequent requested device audit; this sequencing mistake was reported. The later audit found no suffix-003 report directory, only the suffix-004 test, an ended runner, and a cached/frozen QA process. No overlapping instrumentation was observed; absence of initial log output is not claimed as proof that remote startup never occurred. Exact reconciliation is recorded in `guard-reconciliation.json`.

The parent approved a post-packaging test baseline with only 17 MiB remaining and 3 MiB conservatively reserved for earlier focused tests/receipts, maintaining the cumulative 20 MiB allowance. Across the three completed runs, including final free-space samples, minimum free space was 4,926,349,312 bytes. Net additional allocation was 6,037,504 bytes (about 5.76 MiB), below 17 MiB; exact floor remained 4,504,682,496 bytes. No completed run triggered a guard. No models, APK binaries or unrelated source files are committed with this evidence.
