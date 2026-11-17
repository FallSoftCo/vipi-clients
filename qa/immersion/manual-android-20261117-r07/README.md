# Android manual translation qualification, 2026-11-17 r07

Qualified only owned emulator `emulator-5624`, package `co.fallsoft.vipi.uxqa`. Installed app and test APK SHA256 values were independently read from the device and match the UX handoff in `installed-apks.json`. The original `co.fallsoft.vipi` QA account, other emulators and the user phone were untouched.

## Results

The updated reverse native gesture test passed in 8.635 seconds. It taps an asserted uncovered normalized-English word, expands safely to the actual whole Spanish source, verifies exact raw Original mode, and observes Spanish script/language passed to SpeechPlayback. This case uses the actual bundled reverse reference, not ML Kit. The first version of this test incorrectly tapped the covered book slot and timed out; that failed run is retained, not counted as a product failure after fixture correction.

The word/whitespace/Copy gesture test remains **failed**. Initial plain-word tap invoked the provider exactly once and Stop cancelled it. The native trace then shows selection 4:10 remaining after Stop. The next whitespace tap produced no whole-message callback and merely collapsed selection to 16:16. The provider count stayed 1. Native Copy and subsequent phrase-release behavior were not reached; they are not qualified by this run. UX owns the fix. Exact failing state and screenshot are retained; this is a real interaction failure, not a passing final UI acceptance.

Separately, actual installed ML Kit inference passed all four scoped resolver/reading/speech execution checks in 37.27 seconds:

| Selected input | Actual translated context | Observed behavior |
| --- | --- | --- |
| book | Could you book a table for two tomorrow evening? | Spanish uses reservar, not the noun libro. |
| glasses | Please bring two glasses of water to the balcony. | Spanish uses vasos de agua, not gafas. |
| music | My younger cousin enjoys quiet music after lunch. | Chinese target and marked live target reading generated. |
| 音乐 | 我喜欢音乐，也想去银行。 | Exact source context retained; source guide includes yīnyuè and yínháng; English target reading remains nil. |

Each case invoked the real local translator exactly once with the entire enclosing sentence. The actual production owner, reading providers and SpeechPlayback were exercised. Speech input equals the actual learning-language script: Spanish/Chinese translated target in forward direction and original Chinese source in reverse. It never equals the Latin guide. All four entered PLAYING and completed without an error. Observed playback start was 107–255 ms; completion 2.900–5.314 seconds. These are native emulator input/state/completion observations, not human acoustic quality or gesture integration proof for real-model output.

Actual outputs and timings are retained verbatim. Translation is imperfect: younger cousin became 年轻堂兄, which over-specifies paternal male/older-relative kinship and is awkward. Chinese fallback word spacing is not a qualified natural word-segmentation model. Marked reading availability does not establish perfect pronunciation for every polyphonic context. These four cases do not validate every supported pair; Arabic remains authored-only for production reading guides, and Japanese phonetic limitations remain documented elsewhere. No narrow/dark/large-text acceptance is claimed here.

## Resource receipt and reproduction

The guarded runner used a 150 MiB maximum net host allocation allowance and exact 4,504,682,496-byte reserve. Spanish and Chinese models initially required explicit downloads (8.146 and 7.223 seconds). Maximum net additional allocation was 151,744,512 bytes (144.71 MiB); minimum free space 4,949,671,936 bytes. No guard stop occurred. Models remain installed for the coordinated UI rerun. Logs and final receipts are small; no model binaries are committed.

Actual test-only harness source is `android/app/src/androidTest/java/co/fallsoft/vipi/ManualTranslationActualDeviceTest.kt` (commit a042a6d). The approved UX build updated only the test APK, with app assets/native producers excluded. Invoke its class with `vipiDedicatedEmulator=true`, `allowModelDownload=true`, and a new three-digit `vipiActualRun` only after resource/device ownership is reconciled. Existing report directories are deliberately not overwritten. `run-actual-guarded.py` records the exact original run and its bounded stop behavior; inspect existing receipts before replaying any run.

Device ownership was released back to UX after qualification for the whitespace fix and coordinated install. The final gesture acceptance remains open.
