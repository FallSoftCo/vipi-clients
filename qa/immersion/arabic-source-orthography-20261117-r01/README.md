# Arabic source orthography guard, 2026-11-17 r01

The supplied iOS image shows الماء and الموسيقى broken into a literal ال plus a native replacement attachment. Exact original UTF16 geometry is ماء [11,14) inside الماء [9,14) in `أنا أشرب الماء الآن.`, and موسيقى [10,16) inside الموسيقى [8,16) in `أنا أحب الموسيقى.`. Inline attachment boundaries separate Arabic shaping even on the original-language face; logical text concatenation alone does not preserve its joined display.

## Diagnosis and bounded change

The lexical noun-carrier compiler `language-packs/noun_carriers.py` explicitly emits an attested definite word with focus starting two UTF16 units after ال. `LexicalConcordance.sourceFocus` retains noun/article/particle scopes while rejecting partial verb stems. Previously core ImmersionEngine trusted these explicitly scoped source ranges without checking Arabic orthography. SourceFrameLookup has a second explicit carrier exception which borrows the whole carrier’s native word cost for the inner focus.

The native before-fix comparison reproduces both exact inner source ranges through actual explicit carrier/frame and core scoped-entry admission. The actual macOS LocalImmersion/NLTokenizer keeps these definite words whole; ordinary bare frame matching already rejects the inner stems before the fix. Therefore native tokenization itself is **not** claimed as the reproduced defect. The screenshot’s exact installed dictionary row was not independently extracted; its geometry and the source mechanisms are established separately.

Four production files change, independently on each native platform: both core Immersion files add SourceOrthography and filter ordinary as well as explicitly scoped source occurrences; both SourceFrameLookup files reject an unsafe focus before recognition/selection. Unsafe frame hits use `partial_arabic_word` and do not become approved source units or masks. Arabic letters adjacent across a boundary, including supplied vowels, combining marks, U+0640 tatweel and U+200C/U+200D join controls, cause abstention. Full original orthographic tokens remain eligible when independently supplied with a validated whole-word mapping. No stem meaning is expanded to swallow an article. Original text, punctuation, controls, word boundaries and TTS input are never normalized or rewritten by this guard. Existing non-Arabic carrier behavior remains unchanged.

This intentionally reduces automatic replacement coverage for inner Arabic noun heads. The untouched complete word stays readable in the source; manual context translation and actual-script TTS remain separate paths. It is not a new Arabic morphology/vocalization model or a claim that every Arabic reading is available.

## Qualification

The frozen 33-case boundary fixture passed with exact result parity on actual native macOS Swift and host JVM. Cases include both screenshot ranges, full-token positives, clitic prefixes/suffixes, vocalization, marks, start after/end before tatweel, trailing tatweel, ZWJ/ZWNJ, names, RTL punctuation, mixed text/emoji, invalid surrogate edges and unchanged Latin/Korean/Japanese/Chinese behavior. Production core ordinary/native-boundary and explicitly scoped admission reject unsafe stems; typed partial factories also abstain, and a mixed fixture retains a separate safe Arabic word with exact original restoration. A supplied whole-word native frame remains admitted.

The native executable compiles the actual full VipiCore, LocalImmersion, SourceUnitLookup and SourceFrameLookup sources. Before/after source-frame geometry is retained. FrameProbeSupport supplies only compile-time seams for unused resource factories plus the production-equivalent SHA256 function; invoking its catalog factory would trap. No linguistic matching or tokenizer is stubbed. The probe never requests translation, models, UI or a network service. Native output is component proof; final app render evidence must be captured after integration.

Host JUnit ran 18 focused orthography/source-reference/context-frame regressions successfully. New XCTest source regressions and the updated Android source-carrier device test are provided, but their app test suites were not executed here. The first fixture run caught tatweel’s Common-script classification; both implementations explicitly handle it. Native testing also required explicit low-surrogate edge rejection because Foundation range conversion alone did not reject that test input. The final retained results include both fixes.

## Reproduction and resource use

Native directory: `/Users/Apple/Development/vipi-quality-20261117-r01/arabic-source-orthography-r01` (about 2.4 MiB owned output). Existing old directories/libraries remain unchanged. No native desktop input or unrelated process was touched. The before probe reuses the qualified old full-core library; exact binary/source hashes are retained.

```sh
swiftc -enable-testing -emit-library -emit-module -module-name VipiCore core/*.swift -o libVipiCore.dylib
swiftc -I . -L . -lVipiCore LocalImmersion.swift SourceUnitLookup.swift SourceFrameLookup.swift FrameProbeSupport.swift OrthographyProbe.swift -o orthography-probe
DYLD_LIBRARY_PATH=. ./orthography-probe source-boundaries.json native-swift-results.json
swiftc -I ../manual-source-r03 -L ../manual-source-r03 -lVipiCore LocalImmersion.swift SourceUnitLookup.swift before/SourceFrameLookup.swift FrameProbeSupport.swift BeforeFrameProbe.swift -o before-probe
DYLD_LIBRARY_PATH=../manual-source-r03 ./before-probe native-before-results.json
```

The cached Kotlin single-worker compile script is `/home/ai/Development/investigations/vipi-quality-20261117-r01/compile-arabic-orthography-kotlin-r01.py`; owned Linux jar/results stay below 1 MiB. No dependencies, APKs, models or data expansion were built/downloaded. Main’s unrelated dirty files and all UX UI/controller files were untouched. Root owns integration and final native rendering verification.
