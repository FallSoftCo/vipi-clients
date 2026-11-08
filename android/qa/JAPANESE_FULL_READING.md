# Japanese full-reading probe

`JapaneseFullReadingProbeDeviceTest` observes exactly the twelve Japanese rows
from `qa/immersion/full-reading-probe-inputs-r01.json`, identified by the original
48-row file SHA-256 `98e26a9fa030796ea138bb92a5dd62d445c405259e90127b6a572b296d042a38`.
These are authored controls and stress cases, not conversation coverage sampling.

The probe calls the existing pinned Kuromoji tokenizer through
`LocalImmersion.japaneseTokens`. It retains surfaces, UTF-16 units/ranges, POS,
base/conjugation fields, known/unknown flags, readings and pronunciations. It
also records the current Japanese speech adapter's kana output or error without
rendering audio.

A separately labeled QA candidate uses native kana pronunciation, then native
kana reading as fallback, followed by the public Android ICU
`Hiragana-Katakana; Katakana-Latin` transform. Latin/digit/non-Japanese tokens stay
literal; unresolved source text remains in the diagnostic output. Remaining
Japanese script makes the full-reading candidate unavailable. Gap-preserving and
separately token-spaced candidates are retained without phrase overrides. These
outputs have no semantic acceptance. Production full readings remain the authored
`SentenceReadings` path; production speech and matching are unchanged.

Public `Transliterator` requires API 29; this probe ran on API 35. It does not
establish an API 28 production fallback. First/warm timings and PSS/RSS describe
the instrumented emulator process, not isolated model size or acoustic latency.

With a matching debug app already installed, only the instrumentation APK is
needed. The qualification used the existing r58 app without rebuilding it:

```
./scripts/build-android.sh :app:assembleDebugAndroidTest -PvipiQaAbi=x86_64
adb -s emulator-5620 install -r android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb -s emulator-5620 push qa/immersion/full-reading-probe-inputs-r01.json /data/local/tmp/vipi-ja-reading-inputs.json
adb -s emulator-5620 shell run-as co.fallsoft.vipi cp /data/local/tmp/vipi-ja-reading-inputs.json files/full-reading-probe-inputs-r01.json
adb -s emulator-5620 shell rm /data/local/tmp/vipi-ja-reading-inputs.json
adb -s emulator-5620 shell am instrument -w -r \
  -e class co.fallsoft.vipi.JapaneseFullReadingProbeDeviceTest \
  co.fallsoft.vipi.test/androidx.test.runner.AndroidJUnitRunner
adb -s emulator-5620 exec-out run-as co.fallsoft.vipi cat files/japanese-full-reading-probe-001.json
```

Set the existing SDK/JDK environment required by the build wrapper. Check the
target app/test hashes and device ownership before execution. No network service,
model download, translation call, production data promotion or app-store claim
is part of this probe.
