# Build environments

Vipi is a new isolated project, not a cutover of the old consumer repositories.

- Linux source/build authority: `/aosp/development/vipi` on `ssh OZZZ-OS`, hostname `ozzz-aosp`.
- Local authoring/control mirror: `/home/ai/Development/vipi`. No dependency installation or substantive builds here.
- Native iOS build mirror: `/Users/Apple/Development/vipi` on `ssh apple@macbook-pro`.
- Existing Enterprise/Osmos repositories and unrelated emulators/services remain untouched.

Sync source without `.git`, dependencies, caches, generated projects, private fixtures or outputs. Native source and shared QA JSON are authoritative source files. Copy exact synthetic fixtures separately when required. Do not copy credentials into a source mirror.

Android: `storage-build --peak-bytes <measured incremental budget> -- /aosp/development/vipi/scripts/build-android.sh -PvipiQaAbi=x86_64 :app:assembleDebug :app:assembleDebugAndroidTest`. Omit the QA ABI filter for release qualification. Gradle 8.13 wrapper, AGP 8.13.2, Kotlin 2.4.0, R8 9.5.28; Java 17 bytecode. SDK `/aosp/ozzz-android-toolchain/sdk`. Own emulator serial `emulator-5620` only.

iOS: run `xcodegen generate` inside `ios`, then `xcodebuild -project Vipi.xcodeproj -scheme Vipi -configuration Debug -destination 'platform=iOS Simulator,id=46CB569D-EA59-40E3-82CC-F4A0F36EDB87' -derivedDataPath ../build/ios CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=- -parallel-testing-enabled NO test`. Select relevant tests and a fresh result bundle; do not rerun unrelated/expensive fixtures by default. The private libsignal vendor qualification tree is required for the crypto test target. Ad-hoc simulator signing is necessary for Keychain access. This is not release signing.

Backend: existing virtualenv `backend/.venv`; run pytest there. PostgreSQL proof uses `scripts/test-postgres.py <three-digit receipt revision>` under storage-build through the authorized OZZZ root route. It creates only a random isolated local container/socket, uses a unique schema per test, exposes no TCP listener and destroys its own container/volume afterward. Source pin and deletion receipt are retained.

Secrets inventory (locations only): WorkOS staging API key and QA account/token receipts under `/home/ai/.local/state/vipi/workos/`, domain registration receipt under `/home/ai/.local/state/vipi/domain-registration/`, development pack signing key under `/home/aosp/.local/state/vipi/pack-signing/` on OZZZ. The WorkOS key expires seven days after 2026-10-24 creation. No production WorkOS client, release service credentials, push keys or billing secrets have been configured.

Retain failed test receipts. Evidence records distinguish execution, linguistic quality, listening, UX and release acceptance. Generated QA audio contains authored synthetic conversation only.
