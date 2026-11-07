# Native Apple source and dependencies

New owner builds run in the existing `ozzz-development-20261021` macOS VM,
not on the native Mac controller. Use two compiler jobs. Check both guest free
space and the controller's physical APFS backing capacity before restoring
large dependencies. Keep at least 1 GiB physical headroom in addition to the
measured operation size; a full source build needs its own larger admission.

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
Git submodules. Install tools only in the authorized VM after capacity review.
The existing guest does not currently have a Rust toolchain qualified.

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

After vendor preparation, run `scripts/prepare-ios-project.sh` in the VM and
build the generated workspace with `-jobs 2`. StoreKit/provider credentials,
production WorkOS configuration and signing are separate release configuration.
Use the guest `~/.local/bin/apple-xcodebuild` wrapper for signed exports. Never
upload the old qualification build 63.
