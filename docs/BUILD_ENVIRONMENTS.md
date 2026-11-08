# Build environments

## Current authority and consolidation — November 7, 2026

This section supersedes host commands and availability claims in the historical
receipts below. OZZZ-OS and OZZZ-GPU were provider-cancelled. Do not reconnect,
restart their services, or create replacement VMs.

- Canonical Git worktree: `/home/ai/Development/vipi-production-20261107`, branch
  `delivery/production-20261107`. Recovery authority is retained privately in
  `vipi-recovery-20261107/source-authority.json`. The old local `vipi` tree is stale.
- Production host: `ssh fallsoft-production`, actual hostname
  `fallsoft-production-20261106`. Existing Vipi HTTPS origin is
  `https://api.mambovipi.app`. The backend is still restricted staging with real
  provider authentication; production subscription enforcement is not waived.
- Apple: existing `ozzz-development-20261021` VM, user `lume`, controlled through
  `ozzz-mac-vm`. Current source mirror is
  `/Users/lume/Development/vipi-delivery-20261107-r01/source`.
  Use two compiler jobs on the shared 4-CPU/8-GiB VM. Preserve native Mac test
  processes. Guest free space does not establish physical Mac backing capacity.
- Android: existing `emulator-5620` QA AVD on system76, two virtual CPUs and 2 GiB
  RAM. It is a 4-KiB runtime, not physical 16-KiB page-size qualification. The
  user's Pixel was not reachable through the bounded ADB attempt; do not assume
  its old device availability still applies.
- Native iOS model quality is not established by Simulator UI tests. Apple
  Translation needs a supported runtime and prepared models; the current VM has
  no attached physical device. Swahili uses the separate ML Kit path, which is
  excluded from the arm64 Simulator UI configuration.
- Retained bulk data uses existing Storage Box `u684605`. Exact Mac artifact
  offload receipts were hash-verified before removing closed duplicate files.
  No active VM backing, original source, accepted pack, or unrelated project was
  removed for space.
- Backend qualification uses the isolated socket-only PostgreSQL 16.15 instance
  under the November 7 investigation directory. It was cleanly stopped after
  verifying that no other clients were using it; its existing data directory
  and stop receipt remain available for later owned qualification.
  Do not run old container/host scripts against retired environments.

Current provider preparation: a dedicated production WorkOS environment/client
exists, with Vipi branding and callback URLs. Native live tests still use the
dedicated staging client. Firebase project `mambo-vipi-4f569` is registered under
FallSoft; real FCM credentials and push delivery remain unqualified. The first
Android upload key has an encrypted PKCS#12 recovery copy on Storage Box, with
its password held separately in private local/production paths. No secret value
belongs in source. Apple, Google Cloud and AWS owner authentication steps remain
open; no app-store submission receipt exists.

Committed private source through `1aa48fb` is retained on the consolidated host
under `refs/heads/checkpoints/production-20261108-r05`. This separate reference
does not replace the recovery repository's checked-out branch. Later native
changes and uncommitted work require their own checkpoint; this is not public
corresponding-source publication.

The separately retained pinned upstream source inputs have a full SHA-256
verified private copy at Storage Box path
`dev-workspaces/vipi/private-release/upstream-source-20261108-r01/`:
597 files, 139,888,340 bytes including the manifest. No local inputs were deleted.
Rebuilding the native library and completing the public source closure remain
separate requirements.

Apple model preparation is held: the guest's observed low-disk purge threshold
is 10 GiB and the pending model requires roughly 1.85 GiB peak additional space.
Removing 69 proven obsolete Vipi app-only simulator bundles reclaimed 3.60 GB,
but guest free space is still below the threshold. Native physical free space
is independently low. Do not retry preparation, override the purge service or
resize/restart the shared VM on the strength of apparent file-size savings.

## Historical October setup — do not replay host commands

Vipi is a new isolated project, not a cutover of the old consumer repositories.

- Linux source/build authority: `/aosp/development/vipi` on `ssh OZZZ-OS`, hostname `ozzz-aosp`.
- Local authoring/control mirror: `/home/ai/Development/vipi`. No dependency installation or substantive builds here.
- Native iOS build mirror: `/Users/Apple/Development/vipi` on `ssh apple@macbook-pro`.
- Existing Enterprise/Osmos repositories and unrelated emulators/services remain untouched.

Sync source without `.git`, dependencies, caches, generated projects, private fixtures or outputs. Native source and shared QA JSON are authoritative source files. Copy exact synthetic fixtures separately when required. Do not copy credentials into a source mirror.

Android: `storage-build --peak-bytes <measured incremental budget> -- /aosp/development/vipi/scripts/build-android.sh -PvipiQaAbi=x86_64 :app:assembleDebug :app:assembleDebugAndroidTest`. Omit the QA ABI filter for release qualification. Gradle 8.13 wrapper, AGP 8.13.2, Kotlin 2.4.0, R8 9.5.28; Java 17 bytecode. SDK `/aosp/ozzz-android-toolchain/sdk`. Own emulator serial `emulator-5620` only.

iOS: run `xcodegen generate` inside `ios`, then `xcodebuild -project Vipi.xcodeproj -scheme Vipi -configuration Debug -destination 'platform=iOS Simulator,id=46CB569D-EA59-40E3-82CC-F4A0F36EDB87' -derivedDataPath ../build/ios-simulator CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=- -parallel-testing-enabled NO test`. Select relevant tests and a fresh result bundle; do not rerun unrelated/expensive fixtures by default. The private libsignal vendor qualification tree is required for the crypto test target. Ad-hoc simulator signing is necessary for Keychain access. This is not release signing.

Backend: existing virtualenv `backend/.venv`; run pytest there. PostgreSQL proof uses `scripts/test-postgres.py <three-digit receipt revision>` under storage-build through the authorized OZZZ root route. It creates only a random isolated local container/socket, uses a unique schema per test, exposes no TCP listener and destroys its own container/volume afterward. Source pin and deletion receipt are retained.

Secrets inventory (locations only): WorkOS staging API key and QA account/token receipts under `/home/ai/.local/state/vipi/workos/`, domain registration receipt under `/home/ai/.local/state/vipi/domain-registration/`, development pack signing key under `/home/aosp/.local/state/vipi/pack-signing/` on OZZZ. The original shared-project QA credentials are historical and are not used by the dedicated staging deployment. The dedicated Vipi staging API key is stored separately at `/home/aosp/.local/state/vipi/workos-isolated/api-key` on OZZZ-OS and in the root-only live service environment; never copy its value into source or receipts. No production WorkOS client, release service credentials, push keys or billing secrets have been configured.

Retain failed test receipts. Evidence records distinguish execution, linguistic quality, listening, UX and release acceptance. Generated QA audio contains authored synthetic conversation only.

## Durable native messaging qualification

The app now links libsignal directly on both platforms. The Swift test target depends on the app; adding a second direct package dependency caused Xcode to synthesize a separate package framework without the native FFI library search path. Keep the native library paths on the app and test host. The Android library is an implementation dependency, with upstream JNI test/desktop binaries excluded as before.

Use fresh receipt names. Android `DurableMessagingDeviceTest#exportDurableHandshake` creates a synthetic account and a private `files/durable-handshake.json`; run `storageIntegrityAndExpiry` and `concurrentTransactionsDoNotLoseUpdates` alongside it. Copy that exact synthetic file to the Mac's ignored `ios/VipiCryptoTests/Fixtures/` directory. Run `VipiCryptoTests/DurableMessagingTests` with the existing simulator signing settings. Copy the generated app Documents/durable-swift-replies.json back to the same Android app's files directory, then run `DurableMessagingDeviceTest#importDurableSwiftReplies` with `-e vipiDurableReplyReady true`. The Android import test receives replies in order 2,0,1 and reopens the database per message. Do not run import against stale fixtures or re-export between the Swift and Android steps.

Actual process termination: after a successful current app build, run `python3 scripts/check-storage-crash.py android NNN` on OZZZ-OS or `python3 scripts/check-storage-crash.py ios NNN` on the Mac. Each runner installs the current debug build, creates a fresh synthetic account, waits for an armed uncommitted transaction, terminates only the dedicated Vipi process, relaunches, and verifies rollback. Android uses force-stop; iOS uses SIGKILL. This does not simulate device power loss. Debug probes never operate on real accounts; the Swift probe is DEBUG-only and Android's release call path is disabled by BuildConfig.DEBUG. Release shrinker/packaging behavior is a separate gate.

Private synthetic fixtures and generated receipts stay under ignored artifacts/test-fixture paths. No production keys or user conversations are exported by these tests. Source-only LICENSE/NOTICE files begin the approved open-source client distribution work; complete dependency notices, reproducible native vendor preparation and a public corresponding-source release still need qualification before distribution.

## Native network and physical-device qualification

`scripts/serve-network-qa.py NNN` runs under storage-build through the existing authorized OZZZ root route. It creates an isolated socket-only PostgreSQL container, a real WorkOS-verifying API on **127.0.0.1:48942**, and a maximum 30-minute deadline. Writing `artifacts/network-qa-NNN.stop` closes the service and removes its own database/runtime. It never installs an authentication bypass. Record the temporary listener and closure in the private fleet coordination announcements. SSH/ADB forwards are separately owned and must also be removed.

`NetworkMessagingDeviceTest` and `NetworkMessagingTests` use private QA account credentials injected into each app's Documents/files directory, consume that file, save the session in native secure storage, and restore any previous session on completion. Never bundle those credentials or publish them. Android additionally requires the `vipiLiveNetwork=true` instrumentation argument. Invoke stages explicitly: Android publish, Swift publish/send, Android receive/reply, Swift receive out of order, Android verify delivery. Both first requests deliberately use an invalid access token so the public refresh flow must execute. The server still validates the resulting real token and active device.

The iPad is available as CoreDevice `7B6D180F-1D57-5036-8E42-C057698FBAB2`, iPad Pro M2, iPadOS 18.1.1, Developer Mode enabled. Physical build `ipad-build-003` and install `ipad-install-001` succeeded. SSH signing returned errSecInternalComponent; `scripts/build-ipad.sh` run via an owned Terminal window in the Mac's interactive login session resolved it. No keychain ACL/password changes were made. `scripts/test-ipad-translation.sh` likewise runs in that session; its initial test runner timed out enabling UI automation before any test method executed. This is not Apple translation execution evidence.

Native multilingual lookup fixture: run `backend/.venv/bin/python language-packs/make_lookup_fixture.py artifacts/signed-lookup-NNN.json` on OZZZ-OS under storage admission. Copy the generated **public/synthetic** fixture as Android `files/signed-lookup.json` and ignored iOS test resource `Fixtures/signed-lookup.json`. Tests decline to replace existing language-pack anti-rollback receipts, clean up their own installed fixtures, and preserve native account sessions. This fixture's signing private key is ephemeral and never written; it is unrelated to production trust.

Main-browser store access (2026-10-25 UTC): the correct seller is FallSoft.Co / Fallible Software, Co. Google Play is `one@fallsoft.co`, developer `4750854689150545006`; Jeane LLC is unrelated and remains untouched. App Store Connect requires renewed FallSoft sign-in and Account Holder acceptance of updated agreements. No Vipi store record or submission exists. The seller is settled; do not ask the user to choose it again.

## Backend deployment-mode contract (S2, development hardening)

`VIPI_ENVIRONMENT` is an explicit, case-sensitive label: `development` (unchanged
existing default), `test`, `native-qa` (the existing isolated native-QA caller),
`staging`, or `production`. Unknown/misspelled labels are rejected; aliases are
not guessed. The local development/test/isolated-QA modes retain SQLite support.
They are not production deployment modes or permission to contact providers.

Settings construction for `staging` and `production` requires a PostgreSQL URL
according to SQLAlchemy's URL backend parser. SQLite, other backends and malformed
URLs fail before application startup, with generic errors that do not echo URL
or password/input values. URLs/drivers are not rewritten; the actual existing
async driver/toolchain still must be qualified. This adds no production config,
credential, default, routing or security/deployment approval. Existing issuer,
client-ID/token verification and the staging subject allowlist remain required.

The staging unit fixtures use an inert PostgreSQL configuration URL while
explicitly injecting their disposable fixture database; that URL is never opened.
The historical `scripts/check-deletion-provider.py` staging+SQLite combination is
now intentionally rejected. It was NOT rerun or silently downgraded to a local
mode; any future provider-QA change requires separate review and isolation.
