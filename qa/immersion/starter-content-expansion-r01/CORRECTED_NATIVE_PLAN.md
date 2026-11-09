# Combined corrected qualification

This additive run uses the private JA 190 / SW 214 data-only correction and root's shared technical-literal integrity change. Original candidates, native captures, reviews and completion receipt are retained. No production pack is enabled.

Shared input manifest: `native-inputs-r03/native-input-manifest.json`, SHA256 `804b3866dcef5815b80ad4caf4cabc60cc41121feb2168e6dbeeefb33956f629`. Source rows, known/exclusion snapshots, baseline expectations and density policy are unchanged. The original comparison harness is unchanged. Only candidate files/manifests are replaced, with all retained entry objects exact.

Root owns both TranslationIntegrity implementations. Review caught partial-token gaps in intermediate underscore patterns before staging; the final branch consumes the same dot/hyphen/underscore domain it tests, requires a non-dot end, and prevents partial-prefix acceptance before remaining token characters. Existing code, URL, email and mention precedence remains. Common filename suffixes are bounded; arbitrary unquoted paths, proper names and unknown dot-only names are not claimed to be recognized.

Android runtime integrity SHA256: `13c4b6ed6da2f5a1d36991eb9adb46194f767e6533d8cb095c44ade79fad0944`. The source/input/runner freeze is `native-freeze-r02.json`, SHA256 `c2a90c68397a15e519b178bd48d3754dd85c1c6c3362ecd020cf26df826bd561`. Root independently owns Apple staging/execution.

The combined Android build runs the existing TranslationIntegrity and Unicode suites plus TechnicalLiteralIntegrity tests, then builds the isolated QA APKs. Native execution runs the frozen comparison and 14 technical tokens through each pair's actual default ConversationImmersion route. Each literal control requires ordinary trailing “music” to emit, no span to intersect the technical token, and zero translation calls. Controls retain full source, mixed output, spans, origin and status. No injected output is used.

Fresh admission retains the prior two-CPU/one-Gradle-worker, 900-second build, 600-second instrumentation, 1,200-second capture/cleanup, 8 GiB floor and measured APK/DEX/boot reservation. Existing main app/settings and unrelated emulators remain untouched. Captures go to new `android-assembly-r02` / `android-capture-r02` directories; failures are retained without automatic replay.

After both captures, compare exact selected spans/full mixed outputs against the original run, separating changed candidate emissions from unchanged current-arm outputs. Pack-reference hashes necessarily change for the new candidate version; retained entry identities and record hashes must remain exact. Retain every added/lost span and newly exposed packing backfill for independent agent review. Do not infer corrected semantic acceptance from green tests alone.
