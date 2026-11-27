# Maintaining and releasing Vipi for iOS

Use this guide from a human account on the native MacBook Pro. It covers getting a change from source to a locally signed IPA and qualifying it for TestFlight or App Review. One owner can run two test identities on separate devices and release through Terminal, Xcode and App Store Connect. See [sign-in and credential recovery](RELEASE_ACCESS.md#apple-and-google).

**Start here.** For a first checkout, follow [development setup](#set-up-a-development-checkout) and run [the simulator tests](#run-the-simulator-tests). For an existing signed IPA, start with [offline signature inspection](#inspect-the-actual-ipa-without-sending-it-to-apple). The [human console procedure](#testflight-and-app-review-from-the-human-console) covers upload, tester assignment and review. [Physical QA](#test-on-an-actual-iphone) records which claims can be made from that build.

## Identify the source and the build

| Item | Where to look |
| --- | --- |
| Private release source on system76 | `/mnt/extradrive1/vipi-builds/chat-actions-integration-20261126-r01/source` houses the repository and additional worktrees. For the 2026-11-27 handoff, use local ref `release/native-store-candidate-20261127`, commit `1e12989740301dfd6e46caee6ad284b7a2421bd4`. Check the branch or tag chosen by the release owner for later releases. |
| Native Mac checkout | `/Users/Apple/Development/vipi-integrated-20261126`, as `apple@macbook-pro`. Inspect `git worktree list`, `git status --short --branch`, `git log -1` and `git rev-parse HEAD:ios` first. Multiple people use this checkout. Preserve their edits and use a clean, separate worktree for a new change. |
| Build 11 source | The archive was built from `b96ed1cae09b372bdfc54be8f2ca682077f836e3`. Its `ios` tree is `fe40763f210e02845887cb7025d70b14f40342ae`, which also matches the private handoff commit. Verify shared resources, dependency locks, release flags and signing separately when comparing other commits. |
| Distribution package | The preserved native export is `build/store-release-b11/export/Vipi.ipa` in that Mac checkout. The system76 copy is `/mnt/extradrive1/vipi-builds/ios-store-readiness-20261126-r01/Vipi-1.0-11.ipa`. SHA-256 `b9c7104d513680ee40e0084d48f2e8aff55c7ba16b84c89eb04e3379601071eb`, 61,351,511 bytes, version **1.0 (11)**. Other build-11 files in that directory are earlier candidates. |
| Public client source | `FallSoftCo/vipi-clients` is public. Use its curated corresponding-source publication procedure for licensed client materials. Private qualification branches, portal receipts, tester identities and the full release history belong in owner-controlled storage. See [client source and licensing](../CLIENT_SOURCE.md). |

For offline handoff between the development machines, a maintainer with the local private ref can run `git bundle create /private/path/vipi-release.bundle release/native-store-candidate-20261127`. Transfer it through the owner's private channel. At the destination run `git bundle verify /private/path/vipi-release.bundle`, then `git fetch /private/path/vipi-release.bundle refs/heads/release/native-store-candidate-20261127` and compare `git rev-parse FETCH_HEAD` with the agreed commit. `git worktree add --detach /path/to/new-worktree FETCH_HEAD` creates a checkout beside existing work. Transfer only to a machine approved to hold this private history. A Git bundle excludes ignored binary inputs and live credentials.

## Set up a development checkout

The build-11 Mac reported Xcode **26.6 (17F113)**, iPhoneOS SDK **26.5**, Apple Swift **6.3.3**, XcodeGen **2.46.0** and CocoaPods **1.17.0**. Vipi uses Swift 6 language mode and supports iOS/iPadOS 18 and later. The native simulator evidence below used runtime 26.5 (23F77). Use `xcode-select -p`, `xcodebuild -version`, `xcrun --sdk iphoneos --show-sdk-version`, `swift --version`, `xcodegen --version`, `pod --version` and `xcrun simctl list runtimes` to record your environment. The development VM has been retired.

From the repository root, check `df -h .` and `git status --short`. Keep source, DerivedData, the package cache, archives and results on disk with room for staging as well as final products. The two libsignal libraries alone occupy about 446 MB. Use two compiler jobs on the shared Mac. Treat a full disk as a recoverable disk-space issue. Inventory prior signed exports, active builds and retained test evidence before moving any generated output.

```zsh
export PATH="/opt/homebrew/bin:$PATH"
python3 ios/prepare-libsignal.py
zsh scripts/prepare-ios-project.sh
open ios/Vipi.xcworkspace
```

On a fresh checkout with missing pinned inputs, `python3 ios/prepare-libsignal.py --fetch` obtains and authenticates the existing public libsignal release. Then run preparation again. A hash or Git revision mismatch needs inspection before replacement. The preparation step verifies the shared reading data, generates the `.xcodeproj` from `ios/project.yml`, installs Pods using `--deployment` and copies the committed Swift package resolution into the workspace. Keep `ios/Podfile.lock`, `ios/Package.resolved` and the tracked Android `speech/espeak-ng-699e7969` asset tree. The Apple build verifies and packages shared speech data from that tree. The generated Pods workspace supplies the device ML Kit dependencies. To change a build setting, entitlement, test scheme or target membership, edit the source declaration and regenerate. Check the generated files before staging a commit. [Dependency hashes, notices and rebuild recipes](../ios/BUILDING.md) · [Project declaration](../ios/project.yml)

## Find the code and its regression tests

| Change | Start here | Verify before merge |
| --- | --- | --- |
| Cold start, tutorial, provider sign-in and recovery | `ios/Vipi/VipiApp.swift`, `OnboardingView.swift`, `Authentication.swift` and `ConnectedChatRoot.swift` for authenticated chat startup, profile setup and active-device replacement. The WorkOS browser session returns through `co.fallsoft.vipi://auth/callback`. | Run `SignInProviderTests`, `IdentityLinkCoordinatorTests`, `ChatReauthenticationTests` and `ImmersionTutorialTests`. Exercise cancel and return, a cold invitation and an account change under a dedicated QA identity. |
| Inbox, direct/group navigation and one-row toolbar | `HomeView.swift` merges visible activity by recency. `ConnectedChatView.swift` renders the interactive direct conversation. `GroupsViews.swift` provides the group UI. `ChatSession.swift` coordinates direct messaging. | Open an unread group, go back, reopen a direct thread, type and switch language with the keyboard visible. The draft and focus should survive. `ConversationStreakUITests`, `ChatConversationTests`, `ChatRecoveryTests` and `IncrementalConversationTests` cover these paths. |
| Encrypted sends, receipts, group membership, replies and reactions | `MessageVault.swift`, `MessageJournal.swift`, `DurableSignalStore.swift`, `GroupsSession.swift`, `GroupsMutation.swift`, `MessageActionViews.swift`. A mutation and its receipt can complete across launches. | `DurableMessagingTests`, `GroupsMembershipTests`, `GroupsRoutingTests`, `MessageActionTests`, then the paired native journey. Include lost-response recovery, re-open with old state, recipient membership and a reaction removal. Preserve original operation IDs. [Wire contract](CHAT_FEATURES_RELAY.md) · [Group recovery](GROUPS_OPERATION_RECOVERY_WIRE.md) |
| Direct media and contact avatars | `AttachmentRepository.swift`, `MediaCryptography.swift`, `NativeMediaPicker.swift`, `InlineVoiceComposer.swift`, `PrivateProfileAvatar.swift`. | `MediaOutboxTests`, `MediaAttachmentTests`, `PrivateProfileAvatarTests`, interrupted download, authorized decrypt and peer playback. The build-11 group composer supports text, replies, link previews and reactions. Photo, video and voice composition is supported in **direct** chat. |
| Immersion, practice-language selection, romanization and local speech | `ConversationImmersion.swift`, `StableImmersionText.swift`, `LocalSpeech.swift`, `BundledSpeech.swift`, `ios/VipiCore` and shared data under `data/` and `language-packs/`. | Swift package tests, `SentenceReadingsTests`, `LanguagePreparationTests`, `SpeechWordTimingTests`, `ChatAutoplayTests`, then actual phone model preparation/playback. Verify original text and recoverable fallback when the model is missing. The simulator build deliberately uses the unavailable ML Kit adapter. [Capability inventory](LOCAL_LANGUAGE_SUPPORT.md) |
| Notifications, privacy and destructive user actions | `PushNotifications.swift`, `NotificationAccess.swift`, `ios/VipiNotificationService/NotificationService.swift`, `HumanReport.swift`, `AccountDeletionView.swift`. The extension shares a narrow app group/keychain with the app. | `NotificationEnvelopeTests`, `PushInboxHintTests`, `NotificationNavigationTests`, `HumanReportTests`, `AccountDeletionTests`. Check cancel and privacy-preserving fallbacks. Exercise destructive confirmation only on a disposable identity explicitly designated for that test. |

`TimelineQualification.swift` contains debug-only fixtures. The largest shipping responsibilities include `ChatSession.swift` (messaging coordination), `ConnectedChatView.swift` (direct conversation), `ConversationImmersion.swift` (reading state) and `HomeView.swift` (inbox). When fixing a UI issue, start at the relevant view and keep wire/persistence behavior in the session and store. For a lifecycle change, test transitions and replay protection before extracting a helper. For a storage or wire change, test an existing vault and both native clients. Debug qualification code provides repeatable fixtures. Include ordinary Release launches when validating authentication, signed capabilities, first-run and background behavior.

## Run the simulator tests

For the pure Swift library, run `swift test --package-path ios/VipiCore --jobs 2`. For interactive QA, choose **VipiSimulator** and the desired iPhone or iPad in Xcode, then Product → Test. In Test navigator filter the named suites above to reproduce a specific change. Select the **Vipi** scheme for real-device and archive work. **VipiStoreKitTests** uses historical local paid fixtures and has separate pass criteria from the current free edition.

For the current account flow, use `DeviceRecoveryTests`,
`AccountDeletionTests` and `AccountDeletionPresentationTests`.
The opt-in `ConnectedDeletionRootTests` fixture expects a subscription store
and a seeded bot session from the previous paid startup flow. The free client
does not create them. Its startup assertion fails before it reaches deletion.

For a reusable build and separate `.xcresult` files, choose an available simulator from `xcrun simctl list devices available`. Set `SIM_ID` to the exact simulator UUID. From the project root in zsh run the following commands in sequence. A fresh result directory keeps earlier failures inspectable.

```zsh
: "${SIM_ID:?Set SIM_ID to your dedicated simulator}"
mkdir -p build
OUT=$(mktemp -d "$PWD/build/ios-qa.XXXXXX")
DEST="platform=iOS Simulator,id=$SIM_ID"
xcodebuild -workspace ios/Vipi.xcworkspace -scheme VipiSimulator \
  -destination "$DEST" -derivedDataPath "$OUT/DerivedData" -jobs 2 \
  -disableAutomaticPackageResolution -onlyUsePackageVersionsFromResolvedFile \
  build-for-testing -resultBundlePath "$OUT/build.xcresult" ARCHS=arm64 EXCLUDED_ARCHS=
RUN=$(find "$OUT/DerivedData/Build/Products" -name '*.xctestrun' -print)
[[ -f "$RUN" ]] || { echo 'Inspect Products and select the single VipiSimulator xctestrun'; return 1; }
xcodebuild test-without-building -xctestrun "$RUN" -destination "$DEST" \
  -parallel-testing-enabled NO -only-testing:VipiCryptoTests/GroupsRoutingTests \
  -resultBundlePath "$OUT/groups.xcresult"
xcrun xcresulttool get test-results summary --path "$OUT/groups.xcresult"
open "$OUT/groups.xcresult"
```

The pinned simulator libsignal archive contains arm64 only. The explicit architecture settings select that slice on the Apple Silicon Mac. Keep the complete `Products` directory alongside the `.xctestrun` when moving test-without-building inputs. Xcode Test navigator or the HTML-independent `xcresulttool` summary shows **passed, failed and skipped** tests. Remove `-only-testing` for the full configured run, using a new result path. Device- and fixture-specific cases legitimately skip when their prerequisite is absent. Record which behavior actually ran. Existing isolation assumptions are visible in each test. For instance `CombinedLaunchTests/testThreeMemberMessagingAndPreview` needs a private per-stage config and a `Vipi Window Audit…` simulator is required for the window-resize test that changes the simulator's windowing setting.

| Native presentation check | Observable pass |
| --- | --- |
| Compact, standard and large iPhone | Check signed-out setup, empty/populated Inbox, New, direct/group history, language choices, settings, invitation and cancellation. Retained portrait sizes were 375×667, 402×874 and 440×956 points. Inspect 320-point constrained RTL, large Dynamic Type, dark mode and VoiceOver order separately. Action labels, underlying targets and actual taps matter. |
| Landscape with keyboard | On the compact iPhone, type a draft, open the practice language selector, select a language and send or cancel in the fixture. The keyboard, visible Send and recoverable draft are independent assertions. |
| iPad and resized window | Check full 13-inch portrait/landscape and a genuinely resized 375-point window, group title/info, the one-row toolbar, Inbox New and practice language. Inspect native window controls at the leading edge. Reopen Settings and verify back/focus. `ConversationStreakUITests` contains the dedicated resize and landscape paths. |
| Captures | Keep original PNGs and `.xcresult` attachments, source revision, runtime, simulator model, viewport in points, direction and Dynamic Type. Use synthetic test content for screenshots. For store screenshots, check the current required pixel sizes in App Store Connect. A resized review image has a different purpose from a native store original. |

## Test on an actual iPhone

1. Have the phone owner identify the test device and its intended QA account. On the Mac open Xcode → Window → Devices and Simulators or run `xcrun devicectl list devices`. Use the exact device identifier for subsequent commands. A connected device can still be locked or awaiting trust. Resolve that through the normal device UI with its owner. The attached iPad was reserved during the November qualification.
2. Inspect the installed bundle and build first. On the Mac, `xcrun devicectl device info apps --device "$DEVICE_ID" --include-all-apps --bundle-id co.fallsoft.vipi` is read-only. Check the tester identity, data ownership and install channel with the human holding the phone. An existing messaging vault may contain the only copy of received material. Keep it and any personal Apple Account intact.
3. **Private synthetic protocol or sensor QA.** The companion work is in the private local ref `ios/physical-qualification-20261127-r01`, commit `0f4965bc1fcc450c80fd28255187b3cf96150830`. Use `git show 0f4965bc:qa/ios-hardware/README.md` or open that ref in a separate worktree. Its `stage_scratch.py` makes an isolated project with a distinct bundle/keychain and one explicit private LAN relay origin. Build the development target for the registered QA phone. Keep relay tokens, device IDs and per-stage results private. The production target's signing and push entitlement are exercised separately through TestFlight.
4. In a synthetic pair, use a dedicated subject and fresh profile sign-in. The service checks authentication freshness independently of token expiry. Preserve the same account, device, vault and ratchets through invitation, acceptance, approval, text, media, group membership and reactions. Put the per-stage JSON where the fixture README specifies, use one unique receipt name for an action and check both sender acceptance and recipient decode. On a timeout or interruption inspect the original stage receipt and the receiver before considering another send. A queued row or acceptance alone does not prove recipient delivery.
5. Use neutral fixtures for camera, microphone and video. In the isolated build allow/deny the exact app prompt normally, test denial recovery, and grant access for the intended test. Capture non-sensitive dimensions, sample counts and playback callbacks. For the local model test use the approved Wi-Fi download option and check the actual translated phrase in both directions. For backgrounding, type a draft, press Home and reopen, then inspect the same draft and return to the same thread. A process lifecycle observation and an actual locked-device push are different results.
6. **Signed production two-device QA.** Choose one owned internal TestFlight tester on the iPhone and a separate dedicated partner phone and app identity. Use the normal app sign-in and confirm the expected Vipi account, production callback and no device-replacement prompt. If another active device is associated, use a different dedicated QA identity. Enable notifications through Vipi and iOS. Exchange harmless unique test text in both directions. At foreground, background and locked states record sender acceptance, receiver notification, tap destination, actual content, duplication and read state separately. Repeat outside-preview off/on only with the test subject's consent, checking for generic lock-screen content while outside previews are disabled. Check direct attachments, decryption, playback and membership permissions only for features already available on the live service. Record an unavailable route or a missing token path as its own finding. Production account and provider effects require the release owner's ordinary test coordination.
7. For upgrade coverage, use a compatible existing TestFlight install on the dedicated tester, create a synthetic thread/draft first, update through TestFlight and reopen. Check retained identity, messages, unread state, preferences and local downloads. If the test phone has no earlier install, report clean-install coverage and reserve update proof for an actual update. Use Xcode Organizer / TestFlight feedback to capture crashes with the matching archive and dSYMs. Keep account details and message payloads out of shared logs.

The November 27 SE (3rd generation, iOS 27) qualified the side-by-side development app. Its camera returned 15 frames at 192×144, the microphone yielded 48,576 samples, and a subsequent lifecycle-only run recorded active → background → active with the same process. Local English/Swahili model translation and device-side speech were exercised. The private iPhone/Pixel pair delivered encrypted messages, direct media and group membership/action changes. TestFlight and the production Vipi bundle were absent on that SE when inventoried. Production APNs, real lock-screen delivery and a store-installed update on that phone remain open. The receipt paths below distinguish the original sensor run from its later foreground-return check.

## Archive and export locally

In Xcode → Settings → Accounts, select the company's authorized account and team. Check **Signing & Capabilities** for both **Vipi** and **VipiNotificationService**. Use the approved release configuration for the production **public** WorkOS client identifier. A private WorkOS API key, Apple password or APNs signing key has no place in the app or build command. The build rejects its known staging client and requires `VIPI_PUSH_ENVIRONMENT=production`. Verify the actual expected public ID out of band as well. In `ios/project.yml` check the marketing version/build and increment the project version for a new, uploadable change. Both targets inherit it. Keep the agreed version/build for reproducing an existing archive.

For the Xcode GUI, supply those release settings to the Release build configuration in the prepared local workspace, select scheme **Vipi** and a generic iOS device, then Product → Archive. Organizer → Distribute App → App Store Connect can export a local package. Review the destination before completing the wizard. The following native Terminal equivalent preserves the exact version and exports to disk. Start from a clean, approved worktree with the dependencies prepared above. Supply the proper public ID via the release owner's local configuration. Use the prior export only if its digest and release scope match.

```zsh
: "${WORKOS_CLIENT_ID:?Provide the approved production public client ID}"
mkdir -p build
umask 077
OUT=$(mktemp -d "$PWD/build/ios-release.XXXXXX")
git rev-parse HEAD HEAD:ios > "$OUT/source-revisions.txt"
xcodebuild -workspace ios/Vipi.xcworkspace -scheme Vipi -configuration Release \
  -sdk iphoneos -destination 'generic/platform=iOS' -jobs 2 \
  -derivedDataPath "$OUT/DerivedData" -disableAutomaticPackageResolution \
  -onlyUsePackageVersionsFromResolvedFile -skipPackageUpdates \
  -archivePath "$OUT/Vipi.xcarchive" -resultBundlePath "$OUT/archive.xcresult" \
  archive WORKOS_CLIENT_ID="$WORKOS_CLIENT_ID" VIPI_PUSH_ENVIRONMENT=production
```

The preserved Mac build also set `-clonedSourcePackagesDirPath build/native-qualification/SourcePackages` to use its existing pinned cache. In a fresh checkout, let Xcode resolve the versions in the copied lockfile and inspect the resulting revision list. Check the archive command's exit status and Organizer entry before the local export.

```zsh
python3 - "$OUT/export.plist" <<'PY'
import plistlib, sys
with open(sys.argv[1], "xb") as destination:
    plistlib.dump({
        "method": "app-store-connect", "destination": "export",
        "teamID": "3TNL2455JT", "signingStyle": "automatic",
        "manageAppVersionAndBuildNumber": False,
        "stripSwiftSymbols": True, "uploadSymbols": False,
    }, destination)
PY
xcodebuild -exportArchive -archivePath "$OUT/Vipi.xcarchive" \
  -exportOptionsPlist "$OUT/export.plist" -exportPath "$OUT/export"
shasum -a 256 "$OUT/export/Vipi.ipa"
```

Keep the archive including dSYMs, build result, export log/options, IPA, SHA and source pointer together in private retained storage. For an SDK upgrade use the local `xcodebuild -help` export options and check the app's SDK availability and current App Store submission requirements. A provisioning error should identify which of the two targets, capabilities, profile expiration, distribution certificate or private key is missing. Use the team's normal Xcode/Developer account management to resolve the specific problem.

### Inspect the actual IPA without sending it to Apple

Build 11 demonstrates why the final IPA matters. Its archive was signed for development with `get-task-allow=true` and a development APS entitlement while the main Info.plist selected production. The **exported** IPA was re-signed for Apple Distribution and both push environments agree. The steps below run locally on the Mac against an owned IPA. Use a private scratch directory on disk. Display only the selected fields, since raw provisioning profiles can include a device list.

```zsh
: "${IPA:?Set IPA to the exact store export}"
CHECK=$(mktemp -d)
chmod 700 "$CHECK"
ditto -x -k "$IPA" "$CHECK"
APP="$CHECK/Payload/Vipi.app"
EXT="$APP/PlugIns/VipiNotificationService.appex"
for ITEM in "$APP" "$EXT"; do
  codesign --verify --deep --strict "$ITEM" || return 1
  codesign -dv --verbose=4 "$ITEM" 2>&1 | grep -E '^(Identifier|Authority|TeamIdentifier)='
  /usr/libexec/PlistBuddy -c 'Print CFBundleShortVersionString' "$ITEM/Info.plist"
  /usr/libexec/PlistBuddy -c 'Print CFBundleVersion' "$ITEM/Info.plist"
done
python3 - "$APP" "$EXT" <<'PY'
import plistlib, subprocess, sys
from pathlib import Path
for path in map(Path, sys.argv[1:]):
    signed = plistlib.loads(subprocess.check_output(
        ["codesign", "-d", "--entitlements", ":-", str(path)], stderr=subprocess.DEVNULL))
    profile = plistlib.loads(subprocess.check_output(
        ["security", "cms", "-D", "-i", str(path / "embedded.mobileprovision")]))
    info = plistlib.loads((path / "Info.plist").read_bytes())
    print(info["CFBundleIdentifier"], info["CFBundleShortVersionString"], info["CFBundleVersion"])
    for key in ("application-identifier", "com.apple.developer.team-identifier",
                "get-task-allow", "aps-environment", "com.apple.developer.associated-domains",
                "com.apple.security.application-groups", "keychain-access-groups"):
        print("  ", key, signed.get(key))
    print("   registration environment", info.get("VipiPushEnvironment"))
    print("   profile expiration UTC", profile["ExpirationDate"])
    print("   device list", "ProvisionedDevices" in profile,
          "enterprise", profile.get("ProvisionsAllDevices", False),
          "beta", profile["Entitlements"].get("beta-reports-active", False))
PY
```

Compare both bundle IDs (`co.fallsoft.vipi`, `co.fallsoft.vipi.NotificationService`), version/build, signing authorities, team `3TNL2455JT`, profile validity, no debugger allowance, no device list, no enterprise distribution, and beta eligibility. Both signatures must include app group `group.co.fallsoft.vipi.notifications` and shared keychain group `3TNL2455JT.co.fallsoft.vipi.notification-access`. The main app needs signed `aps-environment=production`, Info.plist `VipiPushEnvironment=production`, production WorkOS ID and `applinks:api.mambovipi.app`. The notification extension does not declare its own APS registration. Inspect the privacy manifests, Settings → Licenses and notices, the speech manifest and native device behavior for any dependency update. Remove only your temporary extraction after recording the selected values. Use the release archive for symbolication.

## TestFlight and App Review from the human console

On **November 27, 2026**, the authenticated company console showed app **Vipi: Immersive Chat**, Apple ID **6832624092**, version **1.0**. Build **9** was the latest listed upload and had status Ready to Submit. Distribution 1.0 showed Developer Rejected. App Review history showed the previous submission as Removed. Uploaded/processing lists contained no build 11. The internal group **Vipi Release QA** had one existing tester and builds 6, 3 and 2. Apple's native Transporter showed the company's account and older deliveries. This snapshot predates any future operator action.

1. **Reconcile first.** Visit Apps → Vipi → TestFlight → iOS builds and build uploads, Distribution → iOS version, and App Review → submission history. Compare the exact version/build, recent delivery receipts and existing group assignments. Read current agreements, roles and version ownership in the console. Record UTC, observed state, SHA and intended operation privately. Someone else may already have delivered the candidate.
2. **Internal beta delivery, when the release owner chooses it.** Use Apple's Transporter signed in to the correct provider. Add the exact verified IPA, confirm title, version, build and destination, then Deliver once. Preserve its receipt, delivery ID, timestamp and any warning. Return to the original upload entry and wait for processing before making a distribution decision. Use the offline inspection above for local package checks. Transporter validation can contact Apple. Read the original status before retrying after an interruption. [Apple's build upload procedure](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/)
3. **Make the processed build available to the intended tester.** Address any actual processing or encryption-compliance question using the reviewed product declarations. In TestFlight → Internal Testing → Vipi Release QA, check existing tester membership and distribution settings, then add the processed build if needed. Record the assigned build and tester acceptance. Use the Apple Account already authorized for that group on the dedicated SE. Install Apple's TestFlight through the ordinary App Store, accept the intended beta if necessary, choose the exact version/build, and verify it in TestFlight after installation. Record tester installation and the physical QA separately. Internal beta, external beta review and public release use distinct controls. [Apple's internal testing steps](https://developer.apple.com/help/app-store-connect/test-a-beta-version/add-internal-testers/) · [TestFlight for testers](https://testflight.apple.com/)
4. **Prepare public review after the approved release scope passes.** Review store copy, release availability, pricing/free-access claims, categories, age rating, rights, privacy disclosures, encryption declarations and required storefront documents against the current product and account records. Verify the actual support and privacy URLs, screenshots on supported device families and the current healthy reviewer journey. Use the approved dedicated reviewer credentials through the ASC review-information fields. Supply clear steps for the free account, second test contact and optional permissions. Test the instructions from a fresh approved install. Keep the demo working throughout review. Reconcile the historical draft and removed submissions before choosing the build. [Store metadata](../release/store-metadata-en-US.json) · [Privacy inventory](../release/privacy-data-inventory.json) · [Submission history example](../release/apple-review-submission-20261124-r01.json)
5. **Submit and release are separate decisions.** An authorized human chooses the intended version and processed build, checks the release timing, and selects Add for Review. Inspect the draft and included items, then use Submit for Review only for the intended scope. Record the submission ID and resulting status. Read messages and rejection details in that submission. A fix to the binary needs a uniquely numbered build. A metadata request may use the same binary when Apple permits it. Follow the selected manual/automatic release setting after approval. [Apple's submission instructions](https://developer.apple.com/help/app-store-connect/manage-submissions-to-app-review/submit-an-app)

## Diagnosing an interrupted release

| Symptom | Next observation and recovery |
| --- | --- |
| Xcode cannot find libsignal, ML Kit or a package | Run the pinned verifier, inspect workspace/lockfiles and free disk. Open the generated workspace and select the intended scheme. Simulator-only ML Kit absence is expected. Retain an existing signed package while repairing a fresh checkout. |
| Auth browser cancelled, stale login, unexpected profile or device replacement | Record the stage and expected QA subject without the bearer. Check callback and the production public client setting. Return via normal sign-in for the same identity. Reconcile the original registration before a second attempt. Preserve the existing device vault. |
| Message missing, repeated or undecryptable | Save sanitized sender/receiver build, time, event/receipt references and lifecycle. Distinguish queued, accepted, delivered, read and expired. Check membership, account binding and per-device key state. Recover original durable work before issuing a distinct operation. |
| Push arrives generic, is absent or opens a wrong thread | Compare package APS, registration environment, consent, OS delivery settings, app/extension team and shared groups. Test a foreground fetch, then background and locked delivery separately. Identify server acceptance and provider response with the authorized service owner. A valid entitlement or simulator injection alone gives no evidence of provider delivery. |
| Apple shows “Processing”, duplicate build, removed submission, or the upload client disconnected | Retain the initial Transporter delivery log, version/build and SHA. Examine build uploads, processing details, submission history and Apple's status. Wait for the original upload to resolve. A confirmed rejection goes through the specific remedy Apple reports. A replacement binary receives a new build number. |
| Crash after upgrade, bad beta or rollout | Preserve crash reports and matching dSYMs, reproduce using a designated tester and a compatible retained vault. Limit further exposure through the appropriate TestFlight or public release controls, coordinated by the release owner. People who installed the build may retain it. Prepare and test a forward fix that reads existing state. Distribution controls cannot undo accepted messages, restore a device's private keys or roll back the service database. |

## Leave evidence the next person can use

Keep a private release folder with source commit, shared resource revisions, app/extension versions, archive and IPA checksums, Xcode and OS versions, signing summary, `.xcresult` summaries and original captures with synthetic content, physical model/build/channel, actual sender and receiver observations, known gaps, and the Apple delivery/submission IDs if issued. Record separate statuses for local export, Apple processing, tester install, physical production E2E, App Review and public availability. A skipped test, signed package or HTTP 200 cannot substitute for the next stage's observation.

November 27 reference evidence on system76 is under `/mnt/extradrive1/vipi-builds/`:

- `ios-store-readiness-20261126-r01/RESULT.json`, `final-signed-receipt.json`, `native-matrix.json` and `FEATURES.md` cover candidate provenance, native screenshots, failures and subsequent layout fixes.
- `ios-production-qualification-20261127-r01/verified-ipa.json` compares the archive and actual store export and records a read-only device inventory. The same directory holds the dated private ASC readback.
- `ios-physical-20261127-r01/hardware-review.json`, `local-model-summary.json` and `permissions-enabled-1534/RESULT.json` cover the isolated iPhone journey, real local translation, original sensors and same-process foreground return.
- The command blocks for the export plist and offline IPA inspection were also exercised on this Mac. The plist matched the one used for build 11, and both signatures and profile fields were read from that exact export. The native Mac package test recorded 103 XCTest tests and 26 Swift Testing tests passing on the source-equivalent Apple tree. The original log is `build/human-guide-20261127-r01/core-tests.log` under the Mac checkout. Read the suite names when deciding if this proof covers a later change.

The open build-11 release work at this handoff includes an actual store-channel installation on the intended iPhone, signed production sign-in and two-device E2E, production notification delivery and tap routing, a real compatible upgrade, and any current service or store requirements applicable to the shipped claims. The build-11 archive and local export are already retained for that work.
