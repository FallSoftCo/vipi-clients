# Build environments

## Current authority — November 26, 2026

- The private Vipi Git origin is the source authority for the integrated branch `integration/chat-actions-20261126`. The public `FallSoftCo/vipi-clients` repository contains intentionally published source previews.
- New Apple builds run on the native MacBook Pro. The Git checkout is `~/Development/vipi-integrated-20261126`. Use the pinned project setup script and two compiler jobs. Keep prior release snapshots and generated outputs available for reproduction.
- Android development uses disk-backed worktrees and dedicated QA emulators. Select the emulator explicitly. Preserve the user's physical phone, simulator accounts and previous build artifacts.
- Use the private native journey in `scripts/test-native-chat-actions.py` for cross-platform delivery. Use `scripts/test-postgres.py` for a disposable database. Neither requires production services or credentials.
- Public site source is tracked under `release/marketing-homepage`. Source sync, website publication, API rollout and store submission are separate operations with their own receipts.

## November 18 source and device record

The records below this section are historical. In particular, their signing
holds, restricted-staging status, old emulator numbers and dictionary-based
qualification do not describe the current release effort. The user explicitly
reauthorized signing; successful later signed builds and uploads are retained in
[delivery status](DELIVERY_STATUS.md). Both store reviews are now withdrawn
pending qualification of the full-message replacement. Do not replay completed
uploads, withdrawals, authentication exchanges or production activation.

- The canonical delivery worktree remains
  `/home/ai/Development/vipi-production-20261107`. Its nine inherited modified
  experimental files remain preserved and excluded from release assembly.
- Android's current implementation and native QA owner use
  `/home/ai/Development/investigations/vipi-quality-20261117-r01/ux-worktree`
  and `emulator-5624`, isolated Android user 10. The actual qualified runtime is
  API 34. The current API 29 minimum is a packaging result, not an API 29 runtime
  qualification. Preserve the separate user 0 installation and data.
- iOS's current source owner uses
  `/home/ai/Development/investigations/vipi-simulator-completion-20261118-r01/ios/worktree`.
  New Apple builds and tests run on native `apple@macbook-pro`, using the existing
  `/Users/Apple/Development/vipi-quality-20261117-r01/ux-source` mirror and owned
  simulator `E640C5EE-A159-48B7-99D0-E330E8781FAF`. Only the native owner changes
  that mirror; each job binds its source manifest and restores temporary source,
  application, preference and audio changes. Keep two compiler jobs. Preserve
  the existing translation-preparation application and unrelated Mac work.
- Translation uses existing on-device provider APIs only. Separate model
  experiments are stopped. iOS ML Kit's missing arm64 Simulator slice remains
  a real validation gap; authored Swahili fixtures do not establish execution
  of that device adapter. The iPad remains reserved for 8bar Club.
- The former Apple VM and OZZZ CPU/GPU hosts are retired. The consolidated
  production activation already completed; no new deployment is implied by
  these source changes. Use retained receipts before any external action.

Source branches are still under qualification and have not been assembled into
a fresh signed release. Exact source revisions, native test outcomes and
remaining limitations are tracked in the current investigation receipts and
[delivery status](DELIVERY_STATUS.md).

## Historical environment records

## Local immersion and identity qualification — November 10, 2026

The current bounded revision is retained in `qa/immersion/local-release-r01`
and `qa/design/vipi-identity-r01`. Native source snapshots are explicitly bound
by source-r02 through source-r07 manifests; they do not include the seven
inherited unqualified contextual/lexical edits in the canonical worktree.
Apple uses `vipi-native-delivery-20261109-r01/japanese-starter-promotion-r01/source`
and the existing `app-build-r01` DerivedData. Android uses the existing
`vipi-android-source-context-integration-20261109-r01/source`, qualification
package `co.fallsoft.vipi.sourcecontextqa`, and emulator-5620. The historical
base package is separate and was preserved. Do not install a qualification APK
under an assumed production application ID.

Only unsigned Simulator builds were performed on Apple; signing and distribution
keychains remain held. Apple familiarity vault test fails with OSStatus -34018
before persistence can be qualified; it was not retried after the dependency was
identified. No iPad was used. Store-name change to Vipi is prepared but company
App Store Connect login is required; no name save or upload was attempted.

The final app bundles contain JA197/SW237 and match their source hashes. Default
lookup outcomes match all 140 previously reviewed candidate configurations on
each platform, without automatic translation calls. Scope, errors, reviews and
native interaction evidence remain separate from the release gates.

## Current authority and consolidation — November 9, 2026

The owner reserves the physical iPad for 8bar Club. Vipi development and validation now use the existing simulators and native Mac; do not launch Vipi iPad tests or interact with that device. Historical physical commands below are receipts, not current instructions. An earlier native iOS development build is qualified in `qa/release/native-ios-development-build-r01`. The later iOS-on-Mac attempt compiled but failed signing with `errSecInternalComponent` after the login keychain locked; no app launch followed. Both that dependency and the separate `pbtv58` distribution-keychain hold remain in force. Do not retry signing until the dependency changes; see `qa/release/apple-mac-development-r01/RESULT.md`.

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
- Apple: new work belongs on native `apple@macbook-pro`, under the owner's
  November 8 instruction. The separate migration owner verified the VM shut down
  at 2026-11-09 00:19:52 UTC and completed preservation and backing-disk retirement
  at 01:17:27 UTC. Do not restart it or create a replacement VM. All 120,732
  retained development entries passed the migration owner's independent check;
  this is preservation evidence, not Vipi release qualification. The historical guest mirror is
  `/Users/lume/Development/vipi-delivery-20261107-r01/source`; the old native
  `/Users/Apple/Development/vipi` tree is not automatically current source.
  A new clean mirror at
  `/Users/Apple/Development/vipi-native-delivery-20261109-r01/source` now contains
  all 351 committed `ios` files from `a330fdc`, independently hash-verified.
  Its first native core build passed 105 XCTest and 26 Swift Testing cases with
  Xcode 26.6. The additional 254 committed app inputs, 66 generated lexical
  assets, pinned native libsignal libraries and all four Swift package revisions
  are now verified. The clean arm64 Simulator app and test bundles built in
  132.17 seconds with two compiler jobs; final build-directory allocation was
  2.08 GB. Six selected simulator UI/crypto tests then passed with no failures or
  skips: continuous fixed-geometry flips, Swahili in both roles, three default
  non-Roman reading views and explicit peer-key replacement. Authored UI fixtures
  do not establish translation quality. The mirror has no independent
  Git history and excludes the inherited unqualified changes. Preserve native projects, accounts and unrelated jobs;
  keep two compiler jobs and measured physical storage admission.
- Android: existing `emulator-5620` QA AVD on system76, two virtual CPUs and 2 GiB
  RAM. It is a 4-KiB runtime, not physical 16-KiB page-size qualification. The
  user's Pixel was not reachable through the bounded ADB attempt; do not assume
  its old device availability still applies.
- Native iOS model quality is not established by Simulator UI tests. Apple
  Translation needs a supported runtime and prepared models; historical guest
  runs did not establish physical-device capability. Swahili uses the separate ML Kit path, which is
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

The current native build mirror additionally includes the English source-role
provider and the new context reader/tokenizer/source-recognition components.
The latter checks verified 616 source/app inputs and retained the four pinned
dependency revisions. The Simulator build passed, followed by focused matcher,
Unicode and corrected recognition checks; prior preferences and data were restored.
These components remain uncalled by customer paths. The exact clean
LexicalConcordance index blob adds only the recognition API; seven inherited
working-tree experiments remain excluded. See
`qa/immersion/native-context-reader-r01/qualification.json`.

Current provider preparation: a dedicated production WorkOS environment/client
exists, with Vipi branding and callback URLs. Native live tests still use the
dedicated staging client. Production provider password/JWT/public-refresh/revocation qualification now passes on a disposable tagged fixture; this does not establish hosted native sign-in or a live authentication cutover. Firebase project `mambo-vipi-4f569` is registered under
FallSoft; real FCM credentials and push delivery remain unqualified. The first
Android upload key has an encrypted PKCS#12 recovery copy on Storage Box, with
its password held separately in private local/production paths. No secret value
belongs in source. New November 8 migration evidence demonstrates native company
Xcode account access for the separate 8bar release, but that team's later native
distribution attempt failed authentication before upload. Vipi now has a verified company App Store Connect session and private app `6832624092`, distribution profile, draft metadata and annual products. Its own production-configured Release compilation passed; signing still prompts for locked `pbtv58` despite the interactive login keychain being unlocked. Owned waiting processes were stopped and both attempts retained. The retired VM is not a signing fallback. Google Cloud and AWS authentication steps remain open; no Vipi app-store submission receipt exists.

The native migration reconciliation retained the legacy Vipi source snapshot,
final post-drain runtime state and offline guest backups. The migration owner
reports zero remaining development files and a verified retirement receipt;
native working paths and offline backups are distinguished in
`mac-dev-migration-20261108/README-native-routing.txt` on the Mac. Vipi's clean
current build mirror is the separate path above. Full app compilation and the
six selected simulator checks have passed; broader runtime, release and model
qualification remain separate.
The Vipi team has no outstanding guest build or model job and is not duplicating
the migration owner's transfer or retirement work.

Committed private source through `b1e2b84c4a1165ce9172d80116390ed29ccd2dc0` is
retained on the consolidated host under
`refs/heads/checkpoints/production-20261109-r21`. Push and exact remote reference
were verified. This separate reference
does not replace the recovery repository's checked-out branch. Later native
changes and uncommitted work require their own checkpoint; this is not public
corresponding-source publication.

The native clean mirror now also has the documented `50c5a3e` subscription-error
copy change in `ChatSession.swift`. Its original baseline manifest remains
historical. The later Android `7693f9f` Bot allowance error-code/copy correction
has source-contract verification only. The iOS correction now has the native
Simulator compilation receipt below; neither correction has fresh device
qualification.

The native source mirror also includes the production configuration check in
`ios/project.yml`. Each newly generated Release target rejects a missing,
malformed or known staging WorkOS client and a non-production push environment.
The exact XcodeGen-generated production-check script passed eight scoped
configuration checks on the native Mac, including valid production inputs and
unchanged Debug/Simulator behavior. The initial inspection project was separate.
The native CocoaPods workspace has since been regenerated with `scripts/prepare-ios-project.sh`, preserving
the pinned dependencies. All 605 original source/app inputs match the baseline
plus the two reviewed iOS overlays. An incremental arm64 Simulator app build
passed in 35.90 seconds with two compiler jobs; the exact qualified guard ran
after the CocoaPods manifest check and before source compilation. No app
installation, new UI run, distribution signing, store access or production
login follows from compilation. Existing UITextItemInteraction deprecation and
AppIntents metadata warnings remain. See `qa/release/ios-production-config-r01.json`
and `qa/release/ios-native-incremental-build-r01.json`.

The native mirror additionally contains the three hash-qualified English source
role provider/test/fixture files. Its actual Swift 6 Simulator app/test build
passed in 33.61 seconds, followed by one selected provider XCTest in a 10.64-second
test command. All 156 source annotation payloads match the desktop provider.
The existing QA startup prevented ordinary authenticated startup; preferences
were restored, the private-speech generation retained, the app stopped and both
legacy labs preserved. No customer caller is installed. These receipts are in
`qa/immersion/native-source-role-provider-r01`; they do not establish physical
performance or semantic accuracy.

Seven inherited infinitive-experiment files remain dirty in the canonical
workspace. Their exact source and additional untracked experiments are preserved
privately. Some changed matching behavior can execute without optional data;
these are not entirely dormant changes. Final native qualification must use a
separate clean committed-source snapshot, excluding those unqualified deltas
while retaining the previously committed source-verb correction `a27eff2`.
Do not revert or silently discard the canonical experiments.

The private client-source candidate built by `prepare-client-source.py` includes
4,744 exact files, 66 catalog-hash-bound lexical assets and 575 pinned upstream
archives. Its 557,375,923-byte archive passed a complete independent hash and
membership reread. Backend, infrastructure and Git history are excluded. This is
a packaging candidate at `df21fe9`, not final native binary correspondence,
public publication or completed license/privacy review.
The portable `CLIENT_SOURCE.md` accompanies the export; internal host build
notes are excluded. The superseded r02 archive was retired only after r03's
complete hash/membership reread and source retention checks. Its manifest and
retirement receipt remain private; do not assume the older tar still exists.
The inherited 25-file experiment closure is separately preserved in private Git
at `research/preserved-inherited-nlp-20261108-r01` (`a1a1b2f`); preservation is not
production acceptance and does not alter the canonical dirty files.

The separately retained pinned upstream source inputs have a full SHA-256
verified private copy at Storage Box path
`dev-workspaces/vipi/private-release/upstream-source-20261108-r01/`:
597 files, 139,888,340 bytes including the manifest. No local inputs were deleted.
Rebuilding the native library and completing the public source closure remain
separate requirements.

Historical guest model preparation was held: the guest's observed low-disk purge threshold
was 10 GiB and the pending model required roughly 1.85 GiB peak additional space.
Removing 69 proven obsolete Vipi app-only simulator bundles reclaimed 3.60 GB,
but guest free space remained below the threshold at that checkpoint. Native
physical free space was also low before migration; those readings are historical.
The guest and its backing disk have since been retired after verified preservation.
New native preparation requires fresh measured capacity and must not recreate the VM.
The November 8 native migration changes the execution host, not this historical
result. Fresh native macOS 26.6 qualification now executes the same three
authored intents across six English↔Spanish/Japanese/Chinese directions using
installed models. Both low-latency and platform-default strategies return
identical sentence and isolated-word outputs. Swahili is unsupported by both
checked Apple strategies and retains its separate ML Kit product path. No model
download occurred, and networking was not disabled. This small CLI result does
not establish physical iOS execution, general semantic accuracy or app readiness;
see `qa/immersion/native-mac-translation-20261109-r01`.

## Historical October setup — do not replay host commands

Vipi is a new isolated project, not a cutover of the old consumer repositories.

- Linux source/build authority: `/aosp/development/vipi` on `ssh OZZZ-OS`, hostname `ozzz-aosp`.
- Local authoring/control mirror: `/home/ai/Development/vipi`. No dependency installation or substantive builds here.
- Native iOS build mirror: `/Users/Apple/Development/vipi` on `ssh apple@macbook-pro`.
- Existing Enterprise/Osmos repositories and unrelated emulators/services remain untouched.

Sync source without `.git`, dependencies, caches, generated projects, private fixtures or outputs. Native source and shared QA JSON are authoritative source files. Copy exact synthetic fixtures separately when required. Do not copy credentials into a source mirror.

Android: `storage-build --peak-bytes <measured incremental budget> -- /aosp/development/vipi/scripts/build-android.sh -PvipiQaAbi=x86_64 :app:assembleDebug :app:assembleDebugAndroidTest`. Omit the QA ABI filter for release qualification. Gradle 8.13 wrapper, AGP 8.13.2, Kotlin 2.4.0, R8 9.5.28; Java 17 bytecode. SDK `/aosp/ozzz-android-toolchain/sdk`. Own emulator serial `emulator-5620` only.

iOS: run `xcodegen generate` inside `ios`, then `xcodebuild -project Vipi.xcodeproj -scheme Vipi -configuration Debug -destination 'platform=iOS Simulator,id=46CB569D-EA59-40E3-82CC-F4A0F36EDB87' -derivedDataPath ../build/ios-simulator CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=- -parallel-testing-enabled NO test`. Select relevant tests and a fresh result bundle; do not rerun unrelated/expensive fixtures by default. The private libsignal vendor qualification tree is required for the crypto test target. Ad-hoc simulator signing is necessary for Keychain access. This is not release signing.

Backend tests use the project virtualenv. For transaction and delivery coverage, run the PostgreSQL suite from the repository root as your development user:

```sh
backend/.venv/bin/python scripts/test-postgres.py --run-directory /path/on/disk/pg-run-01
```

Use a new directory with a short absolute path and PostgreSQL 16 binaries. The runner uses `pg_config` by default or accepts `--pg-bin`. It starts a disposable cluster reachable only over a private Unix socket, runs each database fixture in its own schema, and keeps `suite.log`, `suite.xml` and `result.json` after removing the cluster. To run a focused check, pass the pytest path or selector after the runner arguments. For example, add `tests/test_media_postgres.py`.

### Cross-platform messaging integration

Run `scripts/serve-signed-native-pair.py` with the project backend Python, a fresh `--run-directory`, the tested commit as `--source-revision`, and `--launch-features`. This starts the real HTTP relay on loopback with a disposable database, three synthetic identities, groups, encrypted attachments and a local push sink. Use Android `adb reverse` on the dedicated emulator and an SSH reverse forward bound to Mac loopback when the iOS simulator is on a separate machine.

Exchange the generated credentials for signed fixture tokens at `/qa-auth/token`. Keep the credentials, tokens and any captured preview ticket in private fixture files. Use the native iOS `CombinedLaunchTests/testThreeMemberMessagingAndPreview` and Android `LaunchPairRelayTest#exchangeWithNativePeer` stages. Both test targets use the app's message and group stores and libsignal.

1. Register iOS, Android and a third member before creating a group. Record each actual profile name and device identity once.
2. Create the group on iOS. Have both Android roles accept, then approve each join. Verify that an established friend can read the group text and that the third member holds it before trusting the inviter. Send the direct introduction and verify that the member can approve the original roster and read the original message.
3. Send an attachment in a direct chat and compare the received plaintext hash. Verify the matching media and message permissions using the actual recipient.
4. Remove the third member. The remaining peer should receive new group text. The removed account should be unable to read the new message.
5. Send direct text before the iOS client refreshes. Pass the local APNs ticket to the iOS preview stage and verify the envelope fetch and local decryption. System push delivery and actual lock-screen permissions are physical acceptance checks.

Keep per-stage receipts. This test uses local signed identities. Hosted WorkOS sign-in and account recovery, provider push, camera and microphone capture, and on-device translation and pronunciation still require the corresponding distribution-device checks.

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
