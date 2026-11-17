# Chinese tone regression, 2026-11-17

The fresh-install defect has two independent causes. `immersion-preview.json`
authored Chinese words and full preview without tones, and both native preview
implementations rendered them unchanged. Separately, the earlier upstream
projection deliberately called `getPinyinWithoutTone` on every character and
contextual phrase. Fonts and a global display sanitizer were not responsible.

The preview now has `kāfēi`, `míngtiān`, `hé` and a marked full-sentence guide.
The replacement generator preserves original marked pinyin-pro 3.29.5 values.
Both native readers retain independent implementations and validate the new
813,708-byte resource hash. No shared runtime, download or guessed Latin tones.
The retained upstream archive SHA-256 is
`00e9d2961bb0ba2d247ba5090c242ecbf3793473c9f66f0c69af7248dd4616b4`.
The MIT notice remains packaged unchanged.

The bounded reviewed word file has 22 Simplified words and 13 explicit
Traditional equivalents. These supply 35 display joins, and 13 Traditional
phrase rules. Display joins require the contextual selected syllables to match;
they do not override a different selected reading. Proper names retain case and
`nǚ'ér` retains its syllable-dividing apostrophe. This is not comprehensive
Traditional conversion or general word segmentation. Other boundaries remain
syllable-separated. Neutral syllables in upstream phrases, including `māma`,
`háizi` and `shénme`, remain unmarked. Underlying dictionary tones are used;
this does not attempt every acoustic sandhi change.

All 3,067 bundled mapping rows targeting Chinese and 607 context rows have
marked supplied readings already; no data remapping was needed. Exact authored
sentence readings already contain tones and retain precedence. Original written
Chinese remains the speech/copy input in preview and full-message playback;
reading text is only visual metadata. Japanese/Korean/Arabic consumers and the
shared readable-romanization validator contain no global diacritic-stripping
operation. No changes to those engines were justified.

`native-swift-results.json` records 36 actual native macOS CLI cases, warm
identity, exact original source partitions and the 16,384-UTF16 boundary. This
includes contextual polyphones, both scripts, neutral tones, ü/iu placement,
protected marked Latin and URLs, punctuation and unknown-Han abstention. The
combining-Latin boundary case additionally exposed inconsistent Swift spacing;
combining marks now retain a separator before a converted Chinese word, matching
Kotlin's existing behavior. Native source files and the CLI probe were compiled
with `/usr/bin/swiftc` in an isolated directory under
`/Users/Apple/Development/vipi-quality-20261117-r01/readings` on the existing Mac.
No iOS app rendering or acoustic evaluation is claimed by that receipt.

The Android instrumented test is self-contained and reads the actual APK assets;
it also asserts exact onboarding readings, authored-first precedence and Chinese
speech spans. It replaces old tests requiring externally seeded tone-free replay
files. The iOS app tests cover equivalent marked words and preview data. Their
execution and final native screenshots belong to integrated app qualification.
The two Python data checks passed, and fresh generator output compared byte for
byte with the bundled resource. Historical tone-free QA receipts remain evidence
of the old component, not current-version acceptance.

Context errors outside these bounded cases remain possible, including `还` in
return contexts and colloquial particles. Existing quality-debt counts are
historical; no new broad accuracy percentage is claimed.

Sources: retained upstream [pinyin-pro](https://github.com/zh-lx/pinyin-pro)
3.29.5 package; Taiwan MOE [音樂](https://dict.concised.moe.edu.tw/dictView.jsp?ID=41985&la=0&powerMode=0)
and [銀行](https://dict.revised.moe.edu.tw/search.jsp?la=0&md=1&order=0&powerMode=0&word=%E9%8A%80%E8%A1%8C)
lexicographic cross-checks. The source references are pronunciation evidence,
not certification of Vipi's arbitrary-message accuracy.
