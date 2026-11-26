# Native Apple source and dependencies

New owner builds run on native `apple@macbook-pro` under the November 8 owner
directive. Reconcile the existing VM migration receipts before using retained
sources or artifacts; do not create new guest work or a replacement VM. Use a
clean committed-source mirror, preserve native projects and accounts, and keep
two compiler jobs. Check physical APFS capacity before restoring dependencies.
Keep at least 1 GiB headroom in addition to measured operation size; a full
source build needs its own larger admission.

The qualified project uses Xcode 26.6 (iOS Simulator 26.5), Swift 6, iOS deployment
18.0, XcodeGen 2.46.0 and CocoaPods 1.17.0. Commit `Podfile.lock` and
`Package.resolved`; never update them as part of a routine build. The Simulator
configuration excludes the arm64-incompatible ML Kit binary adapters. It does
not establish Apple Translation or ML Kit device inference capability.

## libsignal source and native archive preparation

`python3 ios/prepare-libsignal.py` verifies the existing ignored vendor tree,
source HEAD and both native library hashes without changing files. On a fresh,
capacity-admitted checkout, `--fetch` obtains only missing pinned public files.
It refuses to overwrite another source HEAD, source edits or mismatching binary
files. This helper supplies the vendor paths already used by `project.yml`.

- Source: https://github.com/signalapp/libsignal/tree/4beb029d8a941f81e7d9c6d8af1ed25a677569a8
- Release: https://github.com/signalapp/libsignal/releases/tag/v0.105.0
- Published checksum: https://github.com/signalapp/libsignal/releases/download/v0.105.0/libsignal-client-ios-build-v0.105.0.tar.gz.sha256
- Upstream archive, as specified in its pinned `LibSignalClient.podspec`:
  https://build-artifacts.signal.org/libraries/libsignal-client-ios-build-v0.105.0.tar.gz
- Archive SHA-256: `556a82414b545490085a0e21d94990788bdcbee4d769043f7889397872443faf`.
- iOS arm64 static archive SHA-256:
  `296840c5af0ca4c2bccd638d19d19741d3f3433221846cd64eaa13100e0bacd2`.
- iOS Simulator arm64 static archive SHA-256:
  `6b1fc5f32ea114d9b01a761fb2c6ee26c741412a4b535b972825b4f0781a15c0`.

These are the exact upstream release files currently linked, independently
hashed in the development VM. They were not rebuilt during this qualification.
The checksum served by the official release matches the retained archive.

To modify and rebuild libsignal, retain its complete repository, `Cargo.lock`,
`rust-toolchain`, `bin/`, `rust/`, `swift/`, generated FFI headers and upstream
acknowledgments. Pinned upstream `.github/workflows/ios_artifacts.yml` is the
canonical build recipe. It requires Rust **1.98.1**, its `rust-src` component,
Apple iOS targets and `protoc` (protobuf). The pinned libsignal checkout has no
Git submodules. Reuse native tools and install any missing prerequisites only
after capacity review. A matching native Rust toolchain is not yet qualified.

From `vendor/libsignal/source`, after those prerequisites are installed:

```sh
export CARGO_BUILD_JOBS=2
export CARGO_TARGET_DIR="$(pwd)/../target"
cargo fetch --locked
export CARGO_NET_OFFLINE=true
CARGO_BUILD_TARGET=aarch64-apple-ios swift/build_ffi.sh --release
CARGO_BUILD_TARGET=aarch64-apple-ios-sim swift/build_ffi.sh --release
git diff --exit-code -- Cargo.lock
```

The upstream script supplies the ARM crypto/tokio configuration, iOS deployment
15, full LTO, small BoringSSL tables and INFO-only release logs. Preserve it
rather than reconstructing a subset of its flags. This documented rebuild path
has not been executed in this VM; independently rebuilt archives require fresh
hash receipts and native interoperability tests. Bit-for-bit reproducibility
across Xcode toolchains is not claimed.

## Remaining packages and notices

WorkOS 0.8.0 is pinned at `388a4bf903f53747887eeba55a79a7d2fdf64ee2`.
eSpeak NG's Swift package is pinned at
`fd28f6460cc4cdf631528c8e2f7bd825747aac5c`; its exact submodules are eSpeak NG
`699e79690f23e2558d990a3a78b0050745b96932` and Sonic
`9a8d05dc0baa9159fc322dd9905a04e23b161337`. Preserve their complete source,
voice data, CMake/build inputs and license texts in the release source closure.
The local VipiCore package and all Vipi Swift files are app source.

The app also bundles the retained compiled voice data at
`android/app/src/main/assets/speech/espeak-ng-699e7969`. Each Xcode build runs
`ios/package-swahili-speech.py`, which verifies and copies the shared manifest and all
413 data files for the 57 voice profiles into the app. The source package must retain
this Android asset tree even for an Apple build. Generate replacements using
`scripts/build-android-speech-data.py` and review the manifest pin and linked
library revision together. A successful packaging check does not replace an
actual Apple synthesis and listening test.

`Vipi/ThirdPartyNotices/index.json` maps each bundled complete notice text to its
SHA-256 and upstream component. It includes libsignal's complete iOS Rust
dependency acknowledgments, eSpeak/Sonic/WorkOS license texts, pinned CocoaPods
acknowledgments and Google's complete installed ML Kit notices. They are visible
under Settings → Licenses and notices. `Podfile.lock` remains the exact binary
SDK version/spec inventory. The Google SDK retains its separate vendor terms;
listing its notices does not relicense it.

The public release closure must include this app's complete source and build
inputs, the exact corresponding upstream sources and transitive dependency
locks/notices. A dependency URL alone is not the retained source closure. Public
publication and final licensing compatibility remain release gates owned by the
integrating release session.

After vendor preparation, run `scripts/prepare-ios-project.sh` on the native Mac and
build the generated workspace with `-jobs 2 -disableAutomaticPackageResolution
-onlyUsePackageVersionsFromResolvedFile`. The preparation script copies the
source-controlled `ios/Package.resolved` into the generated workspace. StoreKit/provider credentials,
production WorkOS configuration and signing are separate release configuration.
Inspect the migrated signing wrapper and native Xcode account readiness before
signed exports; a guest wrapper receipt does not qualify its native replacement.
Never upload the old qualification build 63.

The app's post-build phase preserves the four pinned ML Kit privacy manifests
from its static frameworks in separate resource bundles before signing.
`package-mlkit-privacy.py` checks every upstream manifest before copying any;
an SDK update requires reviewing its new declarations and updating the hashes
and `release/privacy-data-inventory.json`. The Simulator configuration skips
this phase because it does not link ML Kit. Device Release packaging is qualified
in `qa/release/mlkit-privacy-packaging-r01`; inspect the final signed export too.


## Free edition tests

The default Vipi and VipiSimulator schemes cover free friend chat and
account-bound entitlement handling. The separate VipiStoreKitTests scheme
preserves the historical paid-client scenarios and their local Xcode fixtures.
Those scenarios assume checkout is enabled. The free edition disables checkout.

## Swahili conversation qualification

The standard VipiCryptoTests run exercises the Shallow word request and Deep
sentence request with controlled local SDK responses. To evaluate the frozen
AfriWOZ corpus on an owned physical iPad, place the output of
`qa/immersion/prepare_afriwoz_probe.py` in the test host's Documents directory
as `afriwoz-probe-001.json`. Prepare the ten local language pairs first.
`scripts/test-ipad-swahili.sh NNN` explicitly enables ML Kit model downloads.
`scripts/test-ipad-swahili-coverage.sh NNN` enables the corpus test, which uses
the app's installed provider and records the actual practice and authored text
for both modes. Archive the existing receipt before reusing the same container.

Evaluate the exported receipt with the original frozen corpus:

```sh
python3 qa/immersion/evaluate_swahili_coverage.py \
  --report swahili-conversation-modes-001.json --corpus afriwoz-probe-001.json \
  --output swahili-summary.json
```
