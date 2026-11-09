# ML Kit privacy packaging

The device Release build linked MLKitCommon 13.0.0, MLKitLanguageID 8.0.0,
MLKitNaturalLanguage 9.0.0 and MLKitTranslate 7.0.0 statically. Their installed
frameworks contained privacy manifests, but CocoaPods 1.17.0 did not copy those
files into Vipi.app. The original compiled bundle contained nine manifests.

The app target now runs `ios/package-mlkit-privacy.py` before signing. It verifies
all four manifests against the reviewed dependency hashes, then places each
unchanged file in a named resource bundle. It preserves the app's own manifest.
The UI-only Simulator configuration omits this step because it does not link
ML Kit. Dependency upgrades must review new declarations and update the pins
and privacy inventory together; missing or changed inputs fail the build.

An actual arm64 device Release build passed in 137.019 seconds, with signing
disabled. All four added manifests match their installed vendor bytes; all nine
prior manifests remain unchanged. Missing and changed final input manifests
both fail before writing any resource bundle. Simulator execution succeeds
without access to Pods. The private fixtures never modify vendor dependencies.
Exact source, output and evidence hashes are in `receipt.json`.

This isolates the packaging fix on preserved source `6063b0c`; it does not
qualify later immersion changes, signing, store upload, runtime network behavior
or the final store questionnaire. The final signed export still needs inspection.

References: Apple's [privacy manifest placement documentation](https://developer.apple.com/documentation/bundleresources/adding-a-privacy-manifest-to-your-app-or-third-party-sdk)
and Google's [ML Kit data disclosure documentation](https://developers.google.com/ml-kit/ios-data-disclosure).
