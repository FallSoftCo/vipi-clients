# Raw source coordinates and resolved language, r03

## Confirmed defect

LookupFirst intentionally represents reverse authored input with `presentation.original` normalized into the known language and `presentation.translation` equal to the actual raw learning-language message. Rendered source offsets therefore cannot be applied to the raw message. A canonical English word range can point into unrelated Spanish characters. Original-message presentation must display the actual raw message, not this normalized `presentation.original`.

## Contract

`LookupFirstOutcome.resolvedInputLanguage` now retains the validated pair language established by authored reference, explicit input or local identification. It survives cached invocation and post-detection no-match/error outcomes. Pre-detection validation failures, unsupported identification and stale outcomes contain no resolved language. This is metadata, not a new explicit override or a linguistic guarantee. Kotlin also now checks request validity immediately after model readiness, matching Swift: a readiness callback which invalidates the request cannot return an actionable model-not-ready outcome.

`ManualSourceCoordinates.resolve(rawOriginal, displayedSource, startUTF16, endUTF16)` returns optional `ManualSourceRange(startUTF16, endUTF16, expanded)`. Exact UTF8 source identity and valid displayed grapheme/UTF16 boundaries preserve the gesture range. Different source bytes, malformed ranges, or surrogate/combining splits conservatively select the entire raw original (`expanded=true`). Blank, oversized or invalid raw input is rejected. This helper never estimates target alignment. An NFC/NFD difference is a byte mismatch even when Swift considers the strings canonically equivalent.

UI integration belongs to the UX owner: route every unaligned word/phrase gesture through this helper; retain covered-span flip/audio behavior; original mode uses raw source-only presentation. Retain resolved language against the complete immutable request identity (raw bytes, pair, explicit override, owner epoch), not only message ID, and invalidate on identity changes. Speak raw source with that resolved language. If actual source language remains unresolved, identify locally or expose message-language recovery instead of selecting the known-language voice by default. The engine/helper commit alone does not establish mobile UI integration or gesture acceptance.

## Qualification

Actual native macOS compiled the full production VipiCore module and native manual resolver/helper in the isolated `/Users/Apple/Development/vipi-quality-20261117-r01/manual-source-r03` directory. Host JVM compiled the corresponding full production core plus resolver/helper. Both execute injected-provider fixtures for reverse authored normalization, cached language retention, target-language no-match, stale/invalid metadata, exact-source coordinates, mismatch whole-raw fallback, NFC/NFD, emoji surrogate and combining boundaries, invalid ranges, empty raw rejection, and a full reverse manual request proving actual Spanish input and es→en direction. Native/model/UI quality is not inferred from these synthetic callbacks. Source XCTest/JUnit regressions additionally cover the existing routing harness.

Native commands:

```sh
swiftc -enable-testing -emit-library -emit-module -module-name VipiCore core/*.swift -o libVipiCore.dylib
swiftc -I . -L . -lVipiCore ManualTranslation.swift ManualTranslationContext.swift SourceProbe.swift -o source-probe
DYLD_LIBRARY_PATH=. ./source-probe native-swift-results.json
```

The original manual-translation and manual-context-r02 directories remain unchanged. The host compiler script is `/home/ai/Development/investigations/vipi-quality-20261117-r01/compile-manual-source-kotlin-r03.py`; it reuses cached Kotlin artifacts, one compiler worker, without Gradle/APK build. No emulator interaction occurred during this qualification.
