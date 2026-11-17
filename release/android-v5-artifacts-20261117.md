# Android v5 artifacts

Production `co.fallsoft.vipi` version 5 / 1.0.4 was built once from frozen commit `55a9f723f436f4252730c0a85358a9aa32080f8b`, offline with two workers and the selected shared Fallsoft public client.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `vipi-v5-release.aab` | 546,599,495 | `108e1152a8bf50d93e2d4ab9fd4d464aaf5ca04a9a36a25fc3f6bd0c6383714d` |
| `vipi-v5-release.apk` | 539,181,694 | `b49354c1fba8540a5dc1dcc12a281d37b392c64643224de24fdba43d47ebd9fe` |

Private artifacts and complete receipts are in `investigations/vipi-quality-20261117-r01/android-v5-release-r01/`. Both use upload certificate `f01ec81085007945c6cbc1e81953d51cb9aa11e16777c1962f196acb088ea35c`, matching the retained upload-signed v4 APK. Play-generated APKs use a different certificate.

Static checks passed: signatures, production package/config, non-debuggable release, bundle validation, all four ABIs and 28 native libraries, 16 KiB alignment, retained native guard, and 1,082 asset hashes matching between AAB/APK. The only asset changes since v4 are the approved Chinese reading data and immersion preview. All 13 locale variants contain the concrete tap cue, translating/Stop feedback, unsupported-pair recovery and Fallsoft Settings entry. R8 mapping and native symbols remain retained.

The tap/Stop controllers match previously qualified native UI source. Compiled strings and static correspondence do not constitute a new runtime screenshot, acoustic, payment, live-login or physical 16 KiB device test. Conditional research advice did not disable repeated taps or change the reviewed interaction.

Root owns the matching small source supplement, store portal and phone actions. This task performed no install, upload or store action. Both artifact stages respected the fixed 4,504,682,496-byte reserve; exact closed bundle intermediates were retired only after replacement hashes and no-consumer checks.
