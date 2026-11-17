# Reverse source reading guide, r04

`ManualTranslationResult.sourceReading` is an optional guide for the exact `sourceContextText`. It is generated when the resolved source is the request learning language and is Arabic, Chinese, Japanese or Korean. Existing `reading` remains the guide for `targetText`; no guide is relabelled and there is no second translation. Both calls use the existing native reading provider/cache. UX displays each guide beside its corresponding script and autoplays actual learning-language script, never the Latin guide.

Chinese, Japanese and Korean use the existing live producers. Arabic remains authored-only in the production provider; the dormant research diacritizer/renderer is not enabled by this change. Missing source guides remain nil. Japanese CF readings retain their documented orthographic/particle limitations.

A validity check follows each reading call. Android whole-request timeout/cancellation remains enforced by its existing owner. Swift now receives the existing owner absolute deadline and checks cancellation/deadline before and after guide generation, including the second reading; no expired source-guide result is published. The extra optional deadline defaults to nil for existing injected CLI callers.

Both host JVM and actual native macOS probes passed the extended resolver regressions: reverse Chinese 银行→bank returns sourceReading=yínháng while target reading stays nil; stale and cancellation during the second read produce no result; Swift additionally checks an expired reading deadline. These tests inject translation and execute the actual marked Chinese reader; they are component evidence, not mobile gesture/model/TTS acceptance. Kotlin also now rejects malformed displayed UTF16 before UTF8 comparison (whole-raw fallback), closing a replacement-encoding identity edge identified by the independent reviewer.

Native isolated directory: `/Users/Apple/Development/vipi-quality-20261117-r01/manual-source-reading-r04`. Earlier directories unchanged.

```sh
swiftc -I ../manual-source-r03 -L ../manual-source-r03 -lVipiCore ManualTranslation.swift ManualTranslationContext.swift ChineseFullReading.swift ManualTranslationProbe.swift -o reading-probe
DYLD_LIBRARY_PATH=../manual-source-r03 ./reading-probe ../manual-translation/chinese-ordinary.json native-swift-results.json
```

The host compiler script `/home/ai/Development/investigations/vipi-quality-20261117-r01/compile-manual-source-reading-kotlin-r04.py` reuses cached Kotlin artifacts and one worker, without Gradle or APK creation. No emulator actions occurred.
