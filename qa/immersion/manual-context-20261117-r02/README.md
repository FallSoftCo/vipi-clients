# Contextual manual translation, 2026-11-17 r02

Uncovered selections now translate the enclosing complete sentence(s). The unchanged gesture request identifies the selected original slice; additive result fields `sourceContextText`, `sourceContextStartUTF16`, `sourceContextEndUTF16`, and `contextExpanded` identify what was actually translated. These offsets belong to the immutable original message, not to a guessed target word. Explicit whole-message requests stay whole-message requests. Covered immersion-word flips remain on their existing path.

Android uses native BreakIterator and Apple uses NLTokenizer. Boundaries must preserve composed characters and protected literals. Common abbreviation boundaries are excluded; unbalanced quotation/bracket context falls back conservatively to the entire original message. A message without established sentence boundaries also remains whole. Reference lookup occurs after expansion so an isolated authored dictionary entry cannot bypass contextual translation. Source 32 KiB, provider chunk 8,192 UTF16, output 65,536 UTF16, existing deadline/cancellation/generation and 64-entry valid-result cache limits remain in place. Only language detection may use a bounded window; the translated source context is never arbitrarily truncated.

## Evidence

The frozen 18-case fixture covers ambiguous words, multi-sentence selections, Dr. Lee, decimals, quoted attribution, protected URLs with trailing punctuation, protected code, mixed scripts, Japanese/Korean/Arabic punctuation, emoji and combining characters, unpunctuated chat and explicit whole-message requests. Actual native macOS NLTokenizer and host JVM BreakIterator produced identical original UTF16 context ranges for all 18. A resolver call collector additionally proves the isolated `book` reference cannot bypass the full `Please book a table tonight.` input. The revised 15 resolver checks exercise actual result context fields, selected-slice identity, direction, marked Chinese reading, invalid composed/surrogate boundaries, cancellation/stale result suppression, missing models, integrity, 30 KiB originals and provider chunk limits.

These tests inject translation output. They prove source selection and resolver behavior, not machine-translation accuracy, Android rendering, mobile gesture behavior or spoken acceptance. Native sentence segmentation remains language-dependent and can conservatively include extra context. Sentence context reduces known lexical ambiguities; it cannot guarantee the provider chooses the intended meaning. Root is separately qualifying actual installed Apple Translation against the original authored cases. Japanese CF-based readings remain orthographic guides and do not establish conversational phonetic correctness.

## Reproduction

The new native source/CLI directory is `/Users/Apple/Development/vipi-quality-20261117-r01/manual-context-r02`; the original `/manual-translation` directory was left unchanged. Its existing VipiCore module/library is compatible: this change adds no VipiCore symbols or schema. That original module was compiled from production FullReadingCache.swift and TranslationIntegrity.swift.

```sh
swiftc -I ../manual-translation -L ../manual-translation -lVipiCore ManualTranslation.swift ManualTranslationContext.swift ContextProbe.swift -o context-probe
DYLD_LIBRARY_PATH=../manual-translation ./context-probe context-regressions.json context-native-swift-results.json
swiftc -I ../manual-translation -L ../manual-translation -lVipiCore ManualTranslation.swift ManualTranslationContext.swift ChineseFullReading.swift ManualTranslationProbe.swift -o manual-context-probe
DYLD_LIBRARY_PATH=../manual-translation ./manual-context-probe ../manual-translation/chinese-ordinary.json resolver-native-swift-results.json
```

The host JVM compile reused cached Kotlin 2.4 compiler artifacts with one worker and production TranslationIntegrity/FullReadingCache sources; it did not run Gradle or build an APK. The local compile script is `/home/ai/Development/investigations/vipi-quality-20261117-r01/compile-manual-context-kotlin-r02.py`. Native results and host results are retained alongside the exact fixtures/probes here.
