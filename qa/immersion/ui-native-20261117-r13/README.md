# Vipi native single-tap UI qualification

The scoped change keeps one permanent speaker/Stop per chat bubble. Covered words reveal meaning and speak; plain words and released phrase selections translate their enclosing source context and automatically speak the learning-language side. Bubble whitespace translates the full message in one tap. Native Copy and contextual reading actions remain available. Transient results show the learning script and its own guide together, followed by the complete meaning.

## Source and build

`final-ui-source-manifest-r13.json` pins the 34 included source/test/catalog files. The QA application ID overlay in Android build.gradle.kts and generated .cxx files are excluded. Swift retains the manual resolver absolute deadline. Auth defaults, billing, package/version/signing and release inputs are outside this UI change.

iOS: native-ui-r12-build-receipt.json, native Xcode simulator build passed with two compiler jobs; isolated co.fallsoft.vipi.uxqa on E640C5EE-A159-48B7-99D0-E330E8781FAF. Android: android-manual-r13-build-receipt.json; two-worker offline build passed after the title-only cleanup. Prior r12 behavioral APK hashes and production-popup evidence are preserved in manual-android-ui-r12; r13 changes only the approved redundant title Text to Spacer.

## Focused results

- Android real-provider popup: actual Spanish translation visible, one full-context provider call, four intended Spanish speech inputs; same-word Stop, different-word switch, footer Stop without generic replay, and cached whole-message tap passed. The two native gesture methods and embedded generic Stop/width test also passed. No model downloads during these tests.
- Android separate real ML Kit cases passed for book/table, drinking glasses, live Chinese target/source guides and learning-script SpeechPlayback through PLAYING/completion. This proves inputs and execution, not acoustic pronunciation quality or universal translation accuracy.
- iOS actual native long press, handle drag/release, Stop/replay and Copy passed. Final released selection triggered once after the final native range update, with no request during handle dragging. Clipboard preserved the displayed selected text. Immutable DTO hashes prove the full source context and complete meaning.
- iOS reverse Spanish and Chinese manual paths used existing authored local references; simulator Apple Translation pair availability is unsupported. The separate real-provider native Mac qualification belongs to the parent receipts, not this simulator claim.
- Welcome highlighted-word tap accepted Spanish Café script into production SpeechPlayback, reached PLAYING and completed, then continuous flips resumed. native-welcome-r12.jsonl contains opt-in synthetic hashes and state only.

## Visual evidence

- visual/ios-large-titleless-r12.png and ios-large-titleless-meaning-r12.png: largest Dynamic Type, light, full script/guide/meaning reachable by native scrolling.
- visual/ios-reverse-chinese-reading-dark-r08.png: default dark Chinese and marked reading.
- visual/ios-phrase-release-r11.png: actual native phrase selection and full-context result.
- visual/ios-welcome-truthful-r12.png and ios-welcome-word-r12.png: readable welcome, primary CTA visible, truthful highlighted-word cue.
- visual/ios-arabic-known-rtl-r12.png: footer order and hit areas fit. This also exposes a separate existing Arabic joining defect: an attachment can split the definite article from a word; Arabic source presentation is not qualified. Parent assigned that separately.

## Limits

Android native handle-drag/release remains unqualified; tested programmatic selection and native Copy are labelled accordingly. Local MT may produce semantic errors or over-specific wording. iOS simulator provider-unavailable recovery is truthful and does not offer nonexistent downloads. StoreKit local tests remain blocked by the iOS 26.5 CLI StoreKit runtime environment; no purchase succeeded. Parent independently ran the three actual identity coordinator tests successfully. Shared social authentication is separate pending work, not claimed ready here. No user phone, store submission, account deletion or live purchase was exercised.

Final r13 Android installed app SHA-256: b0ac40b85bb437ddd26a70e44cc2489344407e14105060bc6cce14e862445803. Test APK: 682ee0714df757060ff96026943adefea04b2f1c81237d75c30be25e81358cba. Successful r13 source compile and isolated install preserved app/model data. The title-only change was compiled; behavior receipts refer to r12. Verified temporary Mac compressed-asset tar and local packaging cache were retired after final asset proofs, with final APK/source/receipts retained.

## Evidence boundary

This directory contains the exact final 34-file source manifest, synthetic-only native state/input hashes, sanitized native build status and four accepted unchanged screenshots. Android r12 reports are already committed separately and are not duplicated here. Screenshot filenames identify capture revisions; the full-manifest commit is 117cabd, integrated as 87fdaa6.

The private review card is staged under output/catalog-extras/vipi-native-single-tap-20261117.json. The existing locked builder failed on an unrelated missing retained poster, personal-digital-double-head-v40/poster.png, so the card is not in the generated index. All 3,678 previous card IDs are preserved. The four direct screenshot URLs in gallery-verification.json return HTTP 200 image/png and match exact source hashes; native Chrome visibly rendered the welcome PNG. No unrelated catalog or retained media was changed. No automated Playwright/DOM checker ran on system76; native visual and HTTP/hash/inventory validation are recorded separately.
