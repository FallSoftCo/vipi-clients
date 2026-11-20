# Vipi client source

This source contains the native Android and Apple clients, live transliteration
data and build tools. The backend, company signing credentials, provider secrets, private
operations and Git history are not part of the client source archive. The
archive's `SOURCE_MANIFEST.json` records the exact source revision, file hashes
and included generated assets.

This is currently a source candidate. A successfully assembled archive does not
establish correspondence with a final signed store binary, a completed license
review or a successful clean build. Qualification APKs and simulator builds must
not be submitted as production releases.

## Shared inputs

Keep the directory structure intact. Each eligible message can introduce one new word. Previously introduced words
appear again when they occur in later messages. The original message stays intact,
and the learning history belongs to the account and language pair on that device.
Android uses Google ML Kit and iOS uses Apple Translation, with the existing iOS
ML Kit adapter for Swahili. The providers manage language downloads. The source archive contains no separately distributed
translation model or custom message-translation catalog.

The shared `data/readings` directory supplies live Chinese pinyin data, with its
provenance, pinned upstream package, exporter and license. Verify it before building:

```sh
python3 scripts/check-client-reading-data.py
```

The archive includes pinned upstream source packages under `upstream-sources`.
Their file hashes are in `SOURCE_MANIFEST.json`; dependencies retain their own
licenses. Some build tools still fetch pinned public dependencies. Retaining
source archives does not mean every dependency manager has been configured for
an entirely offline build. Language data and speech voices have separate
attribution requirements from the application code; preserve their notices.

Source-language routing uses Google ML Kit language identification on Android
and Apple Natural Language on iOS. Detection is advisory and is not a
translation-quality score.

Use disk-backed source and build directories with enough space for dependencies,
native libraries, generated assets and compiler output. Do not update dependency
locks during an ordinary reproduction.

## Android

The source pins Gradle 9.3.1, Android Gradle Plugin 9.1.1, Kotlin 2.4.0, compile SDK 37,
target API 36, minimum API 29, NDK 29.0.14206865 and CMake 3.22.1. Use Java 17 or newer (the release build used Java 21). Set `JAVA_HOME`
and `ANDROID_HOME` to compatible installed tools; `ANDROID_SDK_ROOT`, if present,
must identify the same SDK. The helper defaults to two Gradle workers.

```sh
scripts/build-android.sh :core:test :app:assembleDebug
```

To build instrumented tests for an x86_64 emulator:

```sh
scripts/build-android.sh -PvipiQaAbi=x86_64 \
  :app:assembleDebug :app:assembleDebugAndroidTest
```

Select a dedicated test device. Instrumented tests can alter local accounts,
message history and settings; inspect the selected test setup before execution.
An emulator build is not physical-device, minimum-API or acoustic qualification.

eSpeak NG and Sonic sources are in `android/vendor`, with revisions recorded in
`speech-provenance.json`. JNI/CMake code is in `android/app/src/main/cpp`.
`scripts/build-android-speech-data.py` regenerates speech data from those pinned
sources. Preserve its voice inputs and licenses. Full dependency notices are
under `android/app/src/main/assets/legal`.

Production bundles require the public WorkOS client ID, a matching Firebase
configuration and a private upload key. The environment inputs are
`VIPI_WORKOS_CLIENT_ID`, `VIPI_FIREBASE_CONFIG_FILE`, `VIPI_UPLOAD_STORE_FILE`,
`VIPI_UPLOAD_STORE_PASSWORD`, `VIPI_UPLOAD_KEY_ALIAS` and
`VIPI_UPLOAD_KEY_PASSWORD`. Load secrets through a private environment, not
source files or command-line literals. After configuration:

```sh
scripts/build-android.sh :app:bundleRelease
```

The release gate rejects missing inputs, the known staging client and
qualification-only overrides. Do not use company signing identities for a fork.

## Apple

The recorded project toolchain is Xcode 26.6, Swift 6, XcodeGen 2.46.0 and
CocoaPods 1.17.0, with iOS deployment target 18.0. Preserve `ios/Podfile.lock`
and `ios/Package.resolved`. Prepare the pinned libsignal source and official
native archives, then generate the workspace:

```sh
python3 ios/prepare-libsignal.py --fetch
scripts/prepare-ios-project.sh
```

`--fetch` obtains only missing pinned public inputs and refuses to overwrite
conflicting source or artifacts. Without that flag it only verifies the vendor
tree. The preparation script checks live-reading data, runs XcodeGen and `pod install
--deployment`, then copies the pinned Swift package resolution into the generated
workspace. Open `ios/Vipi.xcworkspace` rather than the generated project.

A simulator build can be made with a locally available destination:

```sh
xcodebuild -workspace ios/Vipi.xcworkspace -scheme VipiSimulator \
  -configuration Simulator -sdk iphonesimulator \
  -destination 'generic/platform=iOS Simulator' -jobs 2 \
  -disableAutomaticPackageResolution -onlyUsePackageVersionsFromResolvedFile \
  CODE_SIGNING_ALLOWED=NO build
```

The Simulator configuration excludes the incompatible ML Kit arm64-simulator
adapter. It cannot establish real Apple Translation or ML Kit device behavior.
Use your own signing team/profiles and provider configuration for device builds.
Production subscription, push, authentication and release validation are
separate from compilation.

### Rebuilding libsignal

The client pins official libsignal 0.105.0 at
`4beb029d8a941f81e7d9c6d8af1ed25a677569a8`. Its complete source, Cargo lock,
toolchain, Swift scripts and FFI headers are required. The pinned upstream
`.github/workflows/ios_artifacts.yml` is the canonical build recipe. It uses Rust
1.98.1, `rust-src`, the Apple iOS targets and `protoc`. From
`vendor/libsignal/source`, after installing those prerequisites:

```sh
export CARGO_BUILD_JOBS=2
export CARGO_TARGET_DIR="$(pwd)/../target"
cargo fetch --locked
export CARGO_NET_OFFLINE=true
CARGO_BUILD_TARGET=aarch64-apple-ios swift/build_ffi.sh --release
CARGO_BUILD_TARGET=aarch64-apple-ios-sim swift/build_ffi.sh --release
git diff --exit-code -- Cargo.lock
```

Retain the upstream script's configuration. The current qualification linked
checksum-verified official archives; this source rebuild has not yet been
qualified. Rebuilt native libraries need fresh interoperability checks, and
bit-for-bit identity across toolchains is not claimed. Apple dependency notices
are in `ios/Vipi/ThirdPartyNotices`.

## Licenses and release identity

Client license texts are in `android/LICENSE` and `ios/LICENSE`. Third-party
libraries, linguistic data and voices retain their respective notices and terms.
The generated source manifest records bytes; it is not a blanket relicensing of
included materials. Keep the final release's source revision, generated-data
hashes, dependency identities and binary hashes together. Publication and store
submission require the completed release qualification, not this candidate.

The synthetic backup, speech and package-installer fixtures retained for native
tests are not runtime translation data. Historical dictionary-based releases
retain their original archives and source revisions; use those exact revisions
to reproduce them. The current incremental clients have their own qualification records.
